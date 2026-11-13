"""Farm Analytics: consume Flink window summaries, persist them, and serve the latest per farm."""
import json
import os
import threading
import time

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from webcommon import instrument, log

TOPIC = os.getenv("KAFKA_RESULTS_TOPIC", "results")
GROUP = os.getenv("KAFKA_GROUP_ID", "farm-analytics")
PROCESSED = Counter("farm_analytics_messages_total", "Kafka result processing", ["result"])


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")
    farm_id: str = Field(min_length=1)
    window_start_ms: int = Field(gt=0)
    window_end_ms: int = Field(gt=0)
    readings: int = Field(ge=0)
    sensors: int = Field(ge=0)
    avg_moisture_pct: float | None = Field(ge=0, le=100)
    min_moisture_pct: float | None = Field(ge=0, le=100)
    max_moisture_pct: float | None = Field(ge=0, le=100)
    watering_events: int = Field(ge=0)
    water_litres: float = Field(ge=0)

    @model_validator(mode="after")
    def coherent_window(self):
        if self.window_end_ms <= self.window_start_ms:
            raise ValueError("window_end_ms must be after window_start_ms")
        if self.readings and self.sensors > self.readings:
            raise ValueError("sensors cannot exceed readings")
        vals = (self.avg_moisture_pct, self.min_moisture_pct, self.max_moisture_pct)
        if self.readings and any(v is None for v in vals):
            raise ValueError("moisture statistics required when readings are present")
        if not self.readings and any(v is not None for v in vals):
            raise ValueError("moisture statistics must be null when there are no readings")
        if all(v is not None for v in vals) and not (self.min_moisture_pct <= self.avg_moisture_pct <= self.max_moisture_pct):
            raise ValueError("moisture statistics are inconsistent")
        return self


class MemoryRepository:
    """Local stand-in. Firestore uses an atomic transaction in production."""
    def __init__(self):
        self.docs, self.seen, self.lock = {}, set(), threading.Lock()

    def apply(self, result):
        key = (result.farm_id, result.window_start_ms, result.window_end_ms)
        with self.lock:
            if key in self.seen:
                return False
            old = self.docs.get(result.farm_id, {})
            totals = old.get("totals", {"readings": 0, "watering_events": 0, "water_litres": 0.0, "windows": 0})
            totals = dict(totals)
            totals["readings"] += result.readings
            totals["watering_events"] += result.watering_events
            totals["water_litres"] += result.water_litres
            totals["windows"] += 1
            doc = dict(old, totals=totals)
            if result.window_end_ms > old.get("window_end_ms", -1):
                doc.update(result.model_dump())
            self.docs[result.farm_id] = doc
            self.seen.add(key)
            return True

    def get(self, farm_id):
        return self.docs.get(farm_id)


class FirestoreRepository:
    def __init__(self):
        from google.cloud import firestore
        self.firestore = firestore
        self.db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None)

    def apply(self, result):
        farm_ref = self.db.collection("farm_summaries").document(result.farm_id)
        event_ref = farm_ref.collection("processed_windows").document(f"{result.window_start_ms}_{result.window_end_ms}")
        @self.firestore.transactional
        def txn(transaction):
            event = event_ref.get(transaction=transaction)
            if event.exists:
                return False
            snapshot = farm_ref.get(transaction=transaction)
            old = snapshot.to_dict() or {}
            totals = old.get("totals", {"readings": 0, "watering_events": 0, "water_litres": 0.0, "windows": 0})
            totals = dict(totals)
            totals["readings"] += result.readings
            totals["watering_events"] += result.watering_events
            totals["water_litres"] += result.water_litres
            totals["windows"] += 1
            document = dict(old, totals=totals, updated_at_ms=int(time.time() * 1000))
            if result.window_end_ms > old.get("window_end_ms", -1):
                document.update(result.model_dump())
            transaction.create(event_ref, {"processed_at_ms": int(time.time() * 1000)})
            transaction.set(farm_ref, document)
            return True
        return txn(self.db.transaction())

    def get(self, farm_id):
        snap = self.db.collection("farm_summaries").document(farm_id).get()
        return snap.to_dict() if snap.exists else None


def parse_message(raw):
    try:
        return Result.model_validate_json(raw)
    except (ValidationError, ValueError, TypeError) as exc:
        raise ValueError(str(exc)) from exc


def process(raw, repository):
    result = parse_message(raw)
    return repository.apply(result)


class KafkaWorker:
    def __init__(self, repository):
        from confluent_kafka import Consumer
        protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
        config = {"bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
                  "group.id": GROUP, "enable.auto.commit": False, "auto.offset.reset": "earliest",
                  "security.protocol": protocol, "client.id": "farm-analytics"}
        if protocol.upper() == "SSL":
            config.update({"ssl.ca.pem": os.environ["KAFKA_SSL_CA_PEM"],
                           "ssl.certificate.pem": os.environ["KAFKA_SSL_CERT_PEM"],
                           "ssl.key.pem": os.environ["KAFKA_SSL_KEY_PEM"]})
        self.consumer, self.repository, self.running = Consumer(config), repository, True
        self.consumer.subscribe([TOPIC])

    def run(self):
        while self.running:
            message = self.consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                PROCESSED.labels("kafka_error").inc()
                log("error", "Kafka poll failed", error=str(message.error()))
                continue
            try:
                process(message.value(), self.repository)
                PROCESSED.labels("processed").inc()
            except ValueError as exc:
                # Invalid records are poison messages: record and commit so they cannot stall the partition.
                PROCESSED.labels("invalid").inc()
                log("error", "invalid results message", error=str(exc), topic=message.topic(), offset=message.offset())
            except Exception as exc:  # retry the same record; never advance past an unpersisted offset
                while self.running:
                    PROCESSED.labels("persistence_error").inc()
                    log("error", "result persistence failed; offset not committed", error=str(exc), topic=message.topic(), offset=message.offset())
                    time.sleep(1)
                    try:
                        process(message.value(), self.repository)
                        PROCESSED.labels("processed").inc()
                        break
                    except ValueError as invalid:
                        # A deterministic validation issue is poison data; commit it and resume.
                        PROCESSED.labels("invalid").inc()
                        log("error", "invalid results message", error=str(invalid), topic=message.topic(), offset=message.offset())
                        break
                    except Exception as retry_error:
                        exc = retry_error
                if not self.running:
                    continue
            try:
                self.consumer.commit(message=message, asynchronous=False)
            except Exception as exc:
                # A later commit could skip this one. Stop consumption and let group reassignment replay it.
                self.running = False
                PROCESSED.labels("kafka_error").inc()
                log("error", "Kafka commit failed; stopping consumer", error=str(exc), topic=message.topic(), offset=message.offset())

    def close(self):
        self.running = False
        self.consumer.close()


repo = None
worker = None
worker_thread = None
app = FastAPI(title="Farm Analytics")
instrument(app, "farm-analytics")


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/analytics/farms/{farm_id}")
def farm_analytics(farm_id: str):
    if repo is None:
        raise HTTPException(503, "analytics store is starting")
    result = repo.get(farm_id)
    if result is None:
        raise HTTPException(404, "farm analytics not found")
    return result


def start():
    global repo, worker, worker_thread
    repo = FirestoreRepository() if os.getenv("ANALYTICS_STORE", "memory").lower() == "firestore" else MemoryRepository()
    if os.getenv("KAFKA_ENABLED", "true").lower() not in {"0", "false", "no"}:
        worker = KafkaWorker(repo)
        worker_thread = threading.Thread(target=worker.run, daemon=True)
        worker_thread.start()
    log("info", "farm analytics ready", store=os.getenv("ANALYTICS_STORE", "memory"), topic=TOPIC)


def stop():
    if worker:
        worker.close()


if __name__ == "__main__":
    import uvicorn
    from webcommon import start_metrics_server
    start()
    start_metrics_server()
    try:
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")), access_log=False)
    finally:
        stop()
