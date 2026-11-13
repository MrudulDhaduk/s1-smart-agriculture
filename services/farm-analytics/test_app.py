import json

import pytest
from fastapi.testclient import TestClient

import app


def payload(**updates):
    value = {"farm_id": "farm7", "window_start_ms": 1762479960000, "window_end_ms": 1762480020000,
             "readings": 120, "sensors": 20, "avg_moisture_pct": 24.5, "min_moisture_pct": 12.0,
             "max_moisture_pct": 41.0, "watering_events": 2, "water_litres": 80.5}
    value.update(updates)
    return value


def test_valid_result_and_api():
    repo = app.MemoryRepository()
    assert app.process(json.dumps(payload()), repo) is True
    assert repo.get("farm7")["water_litres"] == 80.5
    app.repo = repo
    client = TestClient(app.app)
    assert client.get("/healthz").json() == {"status": "ok"}
    response = client.get("/analytics/farms/farm7")
    assert response.status_code == 200
    assert response.json()["totals"]["readings"] == 120
    assert client.get("/analytics/farms/absent").status_code == 404


@pytest.mark.parametrize("change", [{"farm_id": ""}, {"window_end_ms": 1}, {"readings": -1},
                                    {"sensors": 121}, {"water_litres": -3}, {"unexpected": 1}])
def test_invalid_result(change):
    with pytest.raises(ValueError):
        app.parse_message(json.dumps(payload(**change)))


def test_duplicate_delivery_does_not_count_twice():
    repo = app.MemoryRepository()
    raw = json.dumps(payload())
    assert app.process(raw, repo) is True
    assert app.process(raw, repo) is False
    assert repo.get("farm7")["totals"]["water_litres"] == 80.5


def test_older_window_adds_totals_without_overwriting_latest():
    repo = app.MemoryRepository()
    newer = payload(window_start_ms=2000, window_end_ms=3000, water_litres=10)
    older = payload(window_start_ms=1000, window_end_ms=2000, water_litres=5)
    app.process(json.dumps(newer), repo)
    app.process(json.dumps(older), repo)
    result = repo.get("farm7")
    assert result["window_start_ms"] == 2000
    assert result["totals"]["water_litres"] == 15
    assert result["totals"]["windows"] == 2


def test_store_failure_is_propagated_for_offset_safety():
    class Broken:
        def apply(self, _):
            raise RuntimeError("Firestore unavailable")
    with pytest.raises(RuntimeError, match="Firestore unavailable"):
        app.process(json.dumps(payload()), Broken())


def test_worker_retries_persistence_before_committing(monkeypatch):
    monkeypatch.setattr(app.time, "sleep", lambda _: None)
    raw = json.dumps(payload()).encode()
    class Message:
        def error(self): return None
        def value(self): return raw
        def topic(self): return "results"
        def offset(self): return 4
    class FakeConsumer:
        def __init__(self): self.committed = []
        def poll(self, _): return Message()
        def commit(self, message, asynchronous):
            self.committed.append(message.offset())
            worker.running = False
    class FlakyRepo:
        calls = 0
        def apply(self, _):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary Firestore failure")
            return True
    worker = app.KafkaWorker.__new__(app.KafkaWorker)
    worker.consumer, worker.repository, worker.running = FakeConsumer(), FlakyRepo(), True
    worker.run()
    assert worker.repository.calls == 2
    assert worker.consumer.committed == [4]


def test_kafka_error_does_not_call_repository():
    class FakeMessage:
        def error(self): return RuntimeError("broker disconnected")
    class FakeConsumer:
        def poll(self, _): worker.running = False; return FakeMessage()
    class FakeRepo:
        def apply(self, _): raise AssertionError("must not process a Kafka error")
    worker = app.KafkaWorker.__new__(app.KafkaWorker)
    worker.consumer, worker.repository, worker.running = FakeConsumer(), FakeRepo(), True
    worker.run()


def test_realistic_results_message_consumed_and_exposed():
    repo = app.MemoryRepository()
    # This is the handoff's Flink results shape, with representative one-minute data.
    raw = json.dumps(payload())
    app.process(raw, repo)
    app.repo = repo
    response = TestClient(app.app).get("/analytics/farms/farm7")
    assert response.status_code == 200
    assert response.json()["avg_moisture_pct"] == 24.5
    assert response.json()["watering_events"] == 2
