"""
Sensor Store - one storage node of the ring.

Each pod (sensor-store-0, sensor-store-1, ...) keeps the readings of the sensors
the ring assigned to it, in a SQLite file on its own disk. Only Partition Manager
calls this service; it decides which node gets which sensor.

Settings (environment variables):
    NODE_NAME     name of this node on the ring    (default: sensor-store-0)
    DATA_DIR      folder for the SQLite file       (default: ./data)
    GRPC_PORT     port for gRPC                    (default: 50052)
    METRICS_PORT  port for Prometheus /metrics     (default: 8000, 0 = off)
"""

import json
import os
import sqlite3
import sys
import threading
import time
from concurrent import futures

import grpc
from prometheus_client import Counter, Gauge, Histogram, start_http_server

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen"))
import reading_pb2  # noqa: E402  (generated from contracts/reading.proto)
import sensor_store_pb2 as pb  # noqa: E402
import sensor_store_pb2_grpc as pb_grpc  # noqa: E402

# ---------- metrics (Prometheus scrapes these from :8000/metrics) ----------
REQUESTS = Counter("ss_requests_total", "gRPC requests handled", ["node", "method", "status"])
LATENCY = Histogram("ss_request_latency_seconds", "Time to handle a request", ["node", "method"])
SENSORS = Gauge("ss_sensors_stored", "Distinct sensors stored on this node (keys per node)", ["node"])
READINGS = Gauge("ss_readings_stored", "Readings stored on this node", ["node"])


def log(level, message, **fields):
    """One JSON object per line on stdout; Cloud Logging picks it up as structured logs."""
    print(json.dumps({"service": "sensor-store", "level": level, "message": message, **fields}), flush=True)


class Storage:
    """A tiny wrapper around one SQLite file."""

    def __init__(self, path):
        self.lock = threading.Lock()  # gRPC uses many threads; SQLite wants one writer at a time
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS readings (
                   sensor_id TEXT, timestamp_ms INTEGER,
                   farm_id TEXT, plot_id TEXT, moisture_pct REAL, temperature_c REAL,
                   PRIMARY KEY (sensor_id, timestamp_ms))"""
        )
        self.db.commit()

    def put(self, readings):
        rows = [(r.sensor_id, r.timestamp_ms, r.farm_id, r.plot_id, r.moisture_pct, r.temperature_c)
                for r in readings]
        with self.lock:
            # INSERT OR REPLACE: storing the same reading twice is harmless,
            # so rebalancing can safely copy data more than once.
            self.db.executemany("INSERT OR REPLACE INTO readings VALUES (?, ?, ?, ?, ?, ?)", rows)
            self.db.commit()
        return len(rows)

    def latest(self, sensor_id):
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM readings WHERE sensor_id = ? ORDER BY timestamp_ms DESC LIMIT 1",
                (sensor_id,)).fetchone()
        return row

    def history(self, sensor_id, from_ms, to_ms, limit):
        to_ms = to_ms or 2**62
        sql = ("SELECT * FROM readings WHERE sensor_id = ? AND timestamp_ms BETWEEN ? AND ? "
               "ORDER BY timestamp_ms DESC")
        params = [sensor_id, from_ms, to_ms]
        if limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        with self.lock:
            return self.db.execute(sql, params).fetchall()

    def sensors(self):
        with self.lock:
            return [r[0] for r in self.db.execute("SELECT DISTINCT sensor_id FROM readings")]

    def delete(self, sensor_id):
        with self.lock:
            cur = self.db.execute("DELETE FROM readings WHERE sensor_id = ?", (sensor_id,))
            self.db.commit()
        return cur.rowcount

    def counts(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(DISTINCT sensor_id), COUNT(*) FROM readings").fetchone()


def to_reading(row):
    sensor_id, ts, farm_id, plot_id, moisture, temp = row
    return reading_pb2.Reading(sensor_id=sensor_id, timestamp_ms=ts, farm_id=farm_id, plot_id=plot_id,
                               moisture_pct=moisture, temperature_c=temp)


class SensorStoreService(pb_grpc.SensorStoreServicer):
    def __init__(self, node, storage):
        self.node = node
        self.storage = storage

    def _observe(self, method, fn):
        """Count and time every request, so Grafana can show RPS, errors and latency."""
        start = time.time()
        try:
            result = fn()
            REQUESTS.labels(self.node, method, "ok").inc()
            return result
        except Exception as e:
            REQUESTS.labels(self.node, method, "error").inc()
            log("ERROR", "request failed", node=self.node, method=method, error=str(e))
            raise
        finally:
            LATENCY.labels(self.node, method).observe(time.time() - start)

    def Put(self, request, context):
        return self._observe("Put", lambda: pb.PutResponse(stored=self.storage.put(request.readings)))

    def GetLatest(self, request, context):
        def run():
            rows = [self.storage.latest(s) for s in request.sensor_ids]
            return pb.StoreLatestResponse(readings=[to_reading(r) for r in rows if r])
        return self._observe("GetLatest", run)

    def GetHistory(self, request, context):
        def run():
            rows = self.storage.history(request.sensor_id, request.from_ms, request.to_ms, request.limit)
            return pb.StoreHistoryResponse(readings=[to_reading(r) for r in rows])
        return self._observe("GetHistory", run)

    def ListSensors(self, request, context):
        return self._observe("ListSensors", lambda: pb.ListSensorsResponse(sensor_ids=self.storage.sensors()))

    def DeleteSensor(self, request, context):
        def run():
            deleted = self.storage.delete(request.sensor_id)
            log("INFO", "sensor deleted (moved away by rebalancing)", node=self.node,
                sensor_id=request.sensor_id, readings=deleted)
            return pb.DeleteSensorResponse(deleted=deleted)
        return self._observe("DeleteSensor", run)


def update_gauges(node, storage, every=5):
    """Refresh 'keys per node' for Grafana every few seconds (cheaper than on every write)."""
    while True:
        sensors, readings = storage.counts()
        SENSORS.labels(node).set(sensors)
        READINGS.labels(node).set(readings)
        time.sleep(every)


def serve(node, data_dir, port):
    os.makedirs(data_dir, exist_ok=True)
    storage = Storage(os.path.join(data_dir, "readings.db"))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    pb_grpc.add_SensorStoreServicer_to_server(SensorStoreService(node, storage), server)
    bound = server.add_insecure_port(f"[::]:{port}")
    server.start()
    threading.Thread(target=update_gauges, args=(node, storage), daemon=True).start()
    log("INFO", "sensor store started", node=node, port=bound, data_dir=data_dir)
    return server, bound


if __name__ == "__main__":
    metrics_port = int(os.environ.get("METRICS_PORT", "8000"))
    if metrics_port:
        start_http_server(metrics_port)
    server, _ = serve(
        node=os.environ.get("NODE_NAME", "sensor-store-0"),
        data_dir=os.environ.get("DATA_DIR", "./data"),
        port=int(os.environ.get("GRPC_PORT", "50052")),
    )
    server.wait_for_termination()
