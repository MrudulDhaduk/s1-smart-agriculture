from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import grpc
import pytest
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "services", "web-common"))

from app import Dependencies, create_app, kafka_config, store_with_retry


class FakeRequest:
    def __init__(self, reading):
        self.reading = reading


class FakePM:
    def __init__(self, responses=None):
        self.responses = list(responses or [SimpleNamespace(ok=True)])
        self.calls = []

    def WriteReading(self, request, timeout):
        self.calls.append((request, timeout))
        value = self.responses.pop(0) if self.responses else SimpleNamespace(ok=True)
        if isinstance(value, Exception):
            raise value
        return value


class FakeProducer:
    def __init__(self, delivery_error=None):
        self.records = []
        self.delivery_error = delivery_error

    def produce(self, topic, key, value, on_delivery):
        self.records.append((topic, key, json.loads(value)))
        self.callback = on_delivery

    def poll(self, _timeout):
        return 0

    def flush(self, _timeout):
        if hasattr(self, "callback"):
            self.callback(self.delivery_error, object())
        return 0


def reading(sensor="farm1-plot1-s1", timestamp=1762480000000):
    return {"sensor_id": sensor, "farm_id": "farm1", "plot_id": "farm1-plot1",
            "moisture_pct": 24.2, "temperature_c": 27.1, "timestamp_ms": timestamp}


@pytest.fixture
def make_client():
    clients = []

    def make(pm_responses=None, producer=None):
        pm = FakePM(pm_responses)
        producer = producer or FakeProducer()
        deps = Dependencies(pm, producer, FakeRequest)
        client = TestClient(create_app(lambda: deps))
        client.__enter__()
        clients.append((client, pm, producer))
        return client, pm, producer

    yield make
    for client, _, _ in clients:
        client.__exit__(None, None, None)


@pytest.mark.parametrize("body", [
    {"sensor_id": "", "timestamp_ms": 1},
    {"sensor_id": "  ", "timestamp_ms": 1},
    {"sensor_id": "s1", "timestamp_ms": 0},
    {"sensor_id": "s1", "timestamp_ms": -1},
    {"sensor_id": "s1", "timestamp_ms": "1762480000000"},
    {"sensor_id": "s1"},
])
def test_invalid_reading_returns_422(make_client, body):
    client, pm, producer = make_client()
    assert client.post("/readings", json=body).status_code == 422
    assert not pm.calls
    assert not producer.records


def test_single_reading_is_stored_and_published(make_client):
    client, pm, producer = make_client()
    response = client.post("/readings", json=reading())
    assert response.status_code == 202
    assert response.json() == {"received": 1, "stored": 1, "published": 1,
                               "failed": 0, "stored_not_published": 0, "successful": 1}
    assert pm.calls[0][0].reading == reading()
    assert producer.records == [("readings", "farm1-plot1-s1", reading())]


def test_batch_processes_each_reading(make_client):
    client, pm, producer = make_client()
    batch = [reading("s1"), reading("s2", 1762480000001)]
    response = client.post("/readings", json={"readings": batch})
    assert response.status_code == 202
    assert response.json()["received"] == response.json()["stored"] == response.json()["published"] == 2
    assert [record[1] for record in producer.records] == ["s1", "s2"]
    assert len(pm.calls) == 2


class RpcFailure(grpc.RpcError):
    def __init__(self, code):
        self._code = code

    def code(self):
        return self._code


def test_transient_grpc_failure_is_retried_then_succeeds(make_client):
    client, pm, producer = make_client(
        [RpcFailure(grpc.StatusCode.UNAVAILABLE), SimpleNamespace(ok=True)])
    with patch("app.time.sleep"):
        response = client.post("/readings", json=reading())
    assert response.status_code == 202
    assert len(pm.calls) == 2
    assert len(producer.records) == 1


def test_invalid_argument_is_not_retried(make_client):
    client, pm, producer = make_client([RpcFailure(grpc.StatusCode.INVALID_ARGUMENT)])
    response = client.post("/readings", json=reading())
    assert response.status_code == 503
    assert len(pm.calls) == 1
    assert not producer.records


def test_exhausted_retries_returns_failure(make_client):
    client, pm, producer = make_client([RpcFailure(grpc.StatusCode.UNAVAILABLE)] * 3)
    with patch("app.time.sleep"):
        response = client.post("/readings", json=reading())
    assert response.status_code == 503
    assert response.json()["successful"] == 0
    assert len(pm.calls) == 3
    assert not producer.records


def test_partition_manager_not_ok_is_retried_and_never_succeeds(make_client, monkeypatch):
    monkeypatch.setenv("GRPC_WRITE_ATTEMPTS", "2")
    client, pm, producer = make_client([SimpleNamespace(ok=False), SimpleNamespace(ok=False)])
    with patch("app.time.sleep"):
        response = client.post("/readings", json=reading())
    assert response.status_code == 503
    assert response.json()["stored"] == response.json()["successful"] == 0
    assert response.json()["failed"] == 1
    assert len(pm.calls) == 2
    assert not producer.records


def test_partial_batch_counts_success_and_failure_separately(make_client):
    pm_responses = [SimpleNamespace(ok=True), RpcFailure(grpc.StatusCode.UNAVAILABLE),
                    RpcFailure(grpc.StatusCode.UNAVAILABLE), RpcFailure(grpc.StatusCode.UNAVAILABLE)]
    client, pm, producer = make_client(pm_responses)
    with patch("app.time.sleep"):
        response = client.post("/readings", json={"readings": [reading("s1"), reading("s2")]})
    assert response.status_code == 503
    assert response.json()["received"] == 2
    assert response.json()["stored"] == response.json()["published"] == response.json()["successful"] == 1
    assert response.json()["failed"] == 1
    assert response.json()["failures"][0]["sensor_id"] == "s2"
    assert len(pm.calls) == 4
    assert len(producer.records) == 1


def test_kafka_failure_is_not_reported_as_success(make_client):
    producer = FakeProducer(delivery_error=RuntimeError("broker unavailable"))
    client, pm, producer = make_client(producer=producer)
    response = client.post("/readings", json=reading())
    assert response.status_code == 503
    assert response.json()["stored"] == 1
    assert response.json()["published"] == response.json()["successful"] == 0
    assert response.json()["stored_not_published"] == 1
    assert len(pm.calls) == len(producer.records) == 1


def test_health_endpoint(make_client):
    client, _, _ = make_client()
    assert client.get("/healthz").json() == {"status": "ok"}


def test_kafka_plaintext_configuration(monkeypatch):
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    config = kafka_config()
    assert config["bootstrap.servers"] == "localhost:29092"
    assert config["security.protocol"] == "PLAINTEXT"
    assert "ssl.key.pem" not in config


def test_kafka_ssl_configuration_requires_all_pems(monkeypatch):
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SSL")
    for key, value in (("KAFKA_SSL_CA_PEM", "ca"), ("KAFKA_SSL_CERT_PEM", "cert"),
                       ("KAFKA_SSL_KEY_PEM", "key")):
        monkeypatch.setenv(key, value)
    config = kafka_config()
    assert config["ssl.ca.pem"] == "ca"
    assert config["ssl.certificate.pem"] == "cert"
    assert config["ssl.key.pem"] == "key"


def test_kafka_ssl_missing_credential_is_clear_error(monkeypatch):
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SSL")
    for key in ("KAFKA_SSL_CA_PEM", "KAFKA_SSL_CERT_PEM", "KAFKA_SSL_KEY_PEM"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="KAFKA_SSL_CA_PEM"):
        kafka_config()
