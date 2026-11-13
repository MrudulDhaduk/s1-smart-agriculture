"""
The Irrigation Controller's connections to other services. Each one has a cloud version and a
local stand-in, picked by environment variables (same idea as Partition Manager's
MEMBERSHIP_BACKEND), so the service also runs on a laptop with nothing but Docker.

    FARM_REGISTRY_URL / SENSOR_REGISTRY_URL   default http://farm-registry / http://sensor-registry
    PARTITION_MANAGER_ADDR                    default partition-manager:50051
    STATE_BACKEND     memory | firestore      watering cooldown              default memory
    ALERTS_BACKEND    log | pubsub            + ALERTS_TOPIC=projects/<p>/topics/alerts   default log
    KAFKA_BOOTSTRAP_SERVERS                   empty = log watering events instead of Kafka
    KAFKA_SECURITY_PROTOCOL                   PLAINTEXT (local) | SSL (Aiven)
    KAFKA_SSL_CA_PEM / _CERT_PEM / _KEY_PEM   Aiven client certificate (Kubernetes Secret kafka-client)
    IRRIGATION_TOPIC                          default irrigation
"""

import json
import os
import sys
import threading

import httpx
from prometheus_client import Counter

from webcommon import log

HERE = os.path.dirname(os.path.abspath(__file__))

ALERTS = Counter("irrigation_alerts_published_total", "Alerts published", ["type"])
EVENTS = Counter("irrigation_events_published_total", "Watering decisions published", ["result"])


class Registry:
    def __init__(self, farm_url, sensor_url):
        self.farm_url, self.sensor_url = farm_url, sensor_url
        self.http = httpx.Client(timeout=5.0)

    def plots(self, farm_id=None):
        r = self.http.get(f"{self.farm_url}/plots", params={"farm_id": farm_id} if farm_id else None)
        r.raise_for_status()
        return r.json()

    def active_sensors(self, farm_id=None):
        params = {"status": "active", **({"farm_id": farm_id} if farm_id else {})}
        r = self.http.get(f"{self.sensor_url}/sensors", params=params)
        r.raise_for_status()
        return r.json()


class Readings:
    """Partition Manager GetLatest (gRPC). We never call a Sensor Store node directly."""
    BATCH = 500

    def __init__(self, address):
        import grpc
        sys.path.insert(0, os.path.join(HERE, "gen"))
        import partition_manager_pb2 as pm  # generated from contracts/ by tools/gen_protos.py
        import partition_manager_pb2_grpc as pm_grpc
        self.pm = pm
        self.stub = pm_grpc.PartitionManagerStub(grpc.insecure_channel(address))

    def latest(self, sensor_ids):
        out = {}
        for i in range(0, len(sensor_ids), self.BATCH):
            reply = self.stub.GetLatest(self.pm.GetLatestRequest(sensor_ids=sensor_ids[i:i + self.BATCH]), timeout=5)
            for r in reply.readings:
                out[r.sensor_id] = {"moisture_pct": r.moisture_pct, "timestamp_ms": r.timestamp_ms}
        return out


class MemoryCooldown:
    """Laptop only: forgotten on restart and not shared between replicas."""

    def __init__(self):
        self.last, self.lock = {}, threading.Lock()

    def active(self, key, now_ms, cooldown_ms):
        return now_ms - self.last.get(key, 0) < cooldown_ms

    def claim(self, key, now_ms, cooldown_ms):
        with self.lock:
            if self.active(key, now_ms, cooldown_ms):
                return False
            self.last[key] = now_ms
            return True


class FirestoreCooldown:
    """GKE: collection irrigation_state, one document per plot. The read-check-write runs in a
    transaction, so two replicas evaluating the same plot cannot both win."""

    def __init__(self):
        from google.cloud import firestore
        self.firestore = firestore
        self.db = firestore.Client()
        self.col = self.db.collection("irrigation_state")

    def active(self, key, now_ms, cooldown_ms):
        snap = self.col.document(key).get()
        return snap.exists and now_ms - snap.get("last_ms") < cooldown_ms

    def claim(self, key, now_ms, cooldown_ms):
        ref = self.col.document(key)

        @self.firestore.transactional
        def txn(transaction):
            snap = ref.get(transaction=transaction)
            if snap.exists and now_ms - snap.get("last_ms") < cooldown_ms:
                return False
            transaction.set(ref, {"last_ms": now_ms})
            return True

        return txn(self.db.transaction())


class LogSink:
    """Stand-in for Pub/Sub or Kafka: writes the message to the log instead."""

    def __init__(self, kind):
        self.kind = kind

    def publish(self, message):
        # Nested under "body": an alert has its own "message" field, which would clash with log's.
        log("info", f"{self.kind} (not sent: no broker configured)", plot_id=message.get("plot_id"), body=message)
        if self.kind == "alert":
            ALERTS.labels(message["type"]).inc()
        else:
            EVENTS.labels("logged").inc()

    def flush(self):
        pass


class PubSubAlerts:
    def __init__(self, topic):
        from google.cloud import pubsub_v1
        self.client, self.topic = pubsub_v1.PublisherClient(), topic

    def publish(self, alert):
        # Attributes let a subscriber filter without parsing the body.
        future = self.client.publish(self.topic, json.dumps(alert).encode(),
                                     type=alert["type"], farm_id=alert["farm_id"] or "")
        future.result(timeout=10)
        ALERTS.labels(alert["type"]).inc()
        log("warning", "alert published", alert_id=alert["alert_id"], type=alert["type"],
            plot_id=alert["plot_id"], severity=alert["severity"])


class KafkaIrrigation:
    def __init__(self, topic):
        from confluent_kafka import Producer
        protocol = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
        conf = {
            "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            "security.protocol": protocol,
            "client.id": "irrigation-controller",
            "enable.idempotence": True,  # a retried send is written once
        }
        if protocol.upper() == "SSL":
            conf.update({
                "ssl.ca.pem": os.environ["KAFKA_SSL_CA_PEM"],
                "ssl.certificate.pem": os.environ["KAFKA_SSL_CERT_PEM"],
                "ssl.key.pem": os.environ["KAFKA_SSL_KEY_PEM"],
            })
        self.producer, self.topic = Producer(conf), topic

    def _delivered(self, err, msg):
        if err:
            EVENTS.labels("failed").inc()
            log("error", "irrigation event not delivered", error=str(err))
        else:
            EVENTS.labels("delivered").inc()

    def publish(self, event):
        # Key = plot_id: all decisions for one plot land in one partition, in order.
        self.producer.produce(self.topic, key=event["plot_id"], value=json.dumps(event).encode(),
                              on_delivery=self._delivered)
        self.producer.poll(0)
        log("info", "watering decision", plot_id=event["plot_id"], water_litres=event["water_litres"],
            moisture_pct=event["moisture_pct"])

    def flush(self):
        self.producer.flush(10)


def from_env():
    """Build every connection from environment variables (see the module docstring)."""
    from controller import Deps

    state = os.environ.get("STATE_BACKEND", "memory")
    alerts = os.environ.get("ALERTS_BACKEND", "log")
    return Deps(
        registry=Registry(os.environ.get("FARM_REGISTRY_URL", "http://farm-registry"),
                          os.environ.get("SENSOR_REGISTRY_URL", "http://sensor-registry")),
        readings=Readings(os.environ.get("PARTITION_MANAGER_ADDR", "partition-manager:50051")),
        cooldown=FirestoreCooldown() if state == "firestore" else MemoryCooldown(),
        alerts=PubSubAlerts(os.environ["ALERTS_TOPIC"]) if alerts == "pubsub" else LogSink("alert"),
        irrigation=(KafkaIrrigation(os.environ.get("IRRIGATION_TOPIC", "irrigation"))
                    if os.environ.get("KAFKA_BOOTSTRAP_SERVERS") else LogSink("irrigation event")),
        stale_ms=int(os.environ.get("STALE_AFTER_S", "300")) * 1000,
        cooldown_ms=int(os.environ.get("COOLDOWN_S", "600")) * 1000,
    )
