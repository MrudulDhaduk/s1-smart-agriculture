"""REST ingress that stores readings through Partition Manager and publishes them to Kafka."""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

import grpc
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from prometheus_client import Counter, Histogram

import webcommon
from webcommon import log

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "gen"))

WRITE_ATTEMPTS = Counter("telemetry_grpc_write_attempts_total", "Partition Manager write attempts", ["result"])
PUBLISHED = Counter("telemetry_kafka_publications_total", "Kafka reading publication outcomes", ["result"])
READINGS = Counter("telemetry_readings_total", "Per-reading processing outcomes", ["result"])
PROCESSING = Histogram("telemetry_reading_processing_seconds", "Time to process one reading")


class Reading(BaseModel):
    """A wire Reading. Optional measurements default to protobuf's zero values."""

    model_config = ConfigDict(extra="forbid")

    sensor_id: str
    farm_id: str = ""
    plot_id: str = ""
    moisture_pct: float = 0.0
    temperature_c: float = 0.0
    timestamp_ms: int = Field(strict=True, gt=0)

    @field_validator("sensor_id")
    @classmethod
    def sensor_must_be_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("sensor_id must be nonempty")
        return value


class Dependencies:
    def __init__(self, partition_manager: Any, producer: Any, request_type: Any):
        self.partition_manager = partition_manager
        self.producer = producer
        self.request_type = request_type


def connect_partition_manager(address: str) -> tuple[Any, Any, Any]:
    import partition_manager_pb2 as pm
    import partition_manager_pb2_grpc as pm_grpc

    channel = grpc.insecure_channel(address, options=[
        ("grpc.initial_reconnect_backoff_ms", 500),
        ("grpc.max_reconnect_backoff_ms", 5000),
        ("grpc.dns_min_time_between_resolutions_ms", 1000),
    ])
    return pm_grpc.PartitionManagerStub(channel), pm.WriteReadingRequest, channel


def kafka_config() -> dict[str, Any]:
    protocol = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT").upper()
    config: dict[str, Any] = {
        "bootstrap.servers": os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        "security.protocol": protocol,
        "client.id": "telemetry-ingestion",
        "enable.idempotence": True,
    }
    if protocol == "SSL":
        for variable, key in (("KAFKA_SSL_CA_PEM", "ssl.ca.pem"),
                              ("KAFKA_SSL_CERT_PEM", "ssl.certificate.pem"),
                              ("KAFKA_SSL_KEY_PEM", "ssl.key.pem")):
            value = os.environ.get(variable)
            if not value:
                raise ValueError(f"{variable} is required when KAFKA_SECURITY_PROTOCOL=SSL")
            config[key] = value
    elif protocol != "PLAINTEXT":
        raise ValueError("KAFKA_SECURITY_PROTOCOL must be PLAINTEXT or SSL")
    return config


def from_env() -> Dependencies:
    from confluent_kafka import Producer

    stub, request_type, _channel = connect_partition_manager(
        os.environ.get("PARTITION_MANAGER_ADDR", "partition-manager:50051"))
    producer = Producer(kafka_config())
    return Dependencies(stub, producer, request_type)


RETRYABLE_GRPC_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
    grpc.StatusCode.RESOURCE_EXHAUSTED,
    grpc.StatusCode.ABORTED,
    grpc.StatusCode.INTERNAL,
    grpc.StatusCode.UNKNOWN,
}


def store_with_retry(deps: Dependencies, reading: Reading) -> int:
    attempts = max(1, int(os.environ.get("GRPC_WRITE_ATTEMPTS", "3")))
    base_delay = max(0.0, float(os.environ.get("GRPC_RETRY_BASE_SECONDS", "0.05")))
    for attempt in range(1, attempts + 1):
        try:
            response = deps.partition_manager.WriteReading(
                deps.request_type(reading=reading.model_dump()), timeout=2.0)
            if response.ok:
                WRITE_ATTEMPTS.labels("ok").inc()
                return attempt
            WRITE_ATTEMPTS.labels("not_ok").inc()
            if attempt == attempts:
                raise RuntimeError("Partition Manager did not confirm a majority write")
        except grpc.RpcError as error:
            code = error.code()
            WRITE_ATTEMPTS.labels(code.name.lower()).inc()
            if code not in RETRYABLE_GRPC_CODES or attempt == attempts:
                raise
        if base_delay:
            time.sleep(base_delay * (2 ** (attempt - 1)))
    raise RuntimeError("Partition Manager write failed")


def publish_reading(deps: Dependencies, reading: Reading) -> None:
    delivery: list[Any] = []

    def on_delivery(error: Any, message: Any) -> None:
        delivery.append(error)

    deps.producer.produce(
        os.environ.get("READINGS_TOPIC", "readings"),
        key=reading.sensor_id,
        value=json.dumps(reading.model_dump(), separators=(",", ":")).encode("utf-8"),
        on_delivery=on_delivery,
    )
    # poll drives callbacks; flush makes a successful API response mean broker acknowledgement.
    deps.producer.poll(0)
    remaining = deps.producer.flush(float(os.environ.get("KAFKA_DELIVERY_TIMEOUT_SECONDS", "5")))
    if remaining or not delivery or delivery[0] is not None:
        raise RuntimeError(f"Kafka did not acknowledge reading (remaining={remaining})")


def create_app(dependency_factory=from_env) -> FastAPI:
    state: dict[str, Any] = {"deps": None}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        state["deps"] = dependency_factory()
        log("info", "telemetry ingestion ready",
            partition_manager=os.environ.get("PARTITION_MANAGER_ADDR", "partition-manager:50051"),
            kafka=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"))
        yield
        if state["deps"] is not None:
            state["deps"].producer.flush(5)

    application = FastAPI(title="Telemetry Ingestion", lifespan=lifespan)
    webcommon.instrument(application, "telemetry-ingestion")

    @application.get("/healthz")
    @application.get("/livez")
    def health():
        return {"status": "ok"}

    @application.post("/readings", status_code=202)
    async def ingest(request: Request):
        try:
            body = await request.json()
            if isinstance(body, dict) and set(body) == {"readings"}:
                raw_readings = body["readings"]
                if not isinstance(raw_readings, list) or not raw_readings:
                    raise ValueError("readings must be a nonempty array")
            else:
                raw_readings = [body]
            parsed = [Reading.model_validate(item) for item in raw_readings]
        except (ValueError, ValidationError, TypeError) as error:
            detail = error.errors(include_context=False) if isinstance(error, ValidationError) else str(error)
            return JSONResponse(status_code=422, content={"detail": detail})

        counts = {"received": len(parsed), "stored": 0, "published": 0,
                  "failed": 0, "stored_not_published": 0}
        failures = []
        deps: Dependencies = state["deps"]
        for reading in parsed:
            started = time.perf_counter()
            try:
                store_with_retry(deps, reading)
                counts["stored"] += 1
                try:
                    publish_reading(deps, reading)
                    PUBLISHED.labels("ok").inc()
                    READINGS.labels("published").inc()
                    counts["published"] += 1
                except Exception as error:  # Kafka must ack before this reading counts as successful.
                    PUBLISHED.labels("failed").inc()
                    READINGS.labels("stored_not_published").inc()
                    counts["stored_not_published"] += 1
                    counts["failed"] += 1
                    failures.append({"sensor_id": reading.sensor_id, "stage": "kafka", "error": str(error)})
            except Exception as error:
                READINGS.labels("storage_failed").inc()
                counts["failed"] += 1
                failures.append({"sensor_id": reading.sensor_id, "stage": "partition_manager", "error": str(error)})
            finally:
                PROCESSING.observe(time.perf_counter() - started)

        result = {**counts, "successful": counts["published"]}
        if failures:
            log("error", "reading batch partially failed", **result, failures=failures)
            return JSONResponse(status_code=503, content={**result, "failures": failures})
        log("info", "readings accepted", **result)
        return JSONResponse(status_code=202, content=result)

    return application


app = create_app()

if __name__ == "__main__":
    webcommon.start_metrics_server()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
