import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import AlreadyExists, PreconditionFailed

import main


@pytest.fixture
def clients(monkeypatch):
    db = Mock()
    doc = Mock()
    db.collection.return_value.document.return_value = doc
    bucket = Mock()
    blob = Mock()
    bucket.blob.return_value = blob
    storage_client = Mock()
    storage_client.bucket.return_value = bucket
    firestore_client = Mock(return_value=db)
    storage_client_ctor = Mock(return_value=storage_client)
    monkeypatch.setattr(main.firestore, "Client", firestore_client)
    monkeypatch.setattr(main.storage, "Client", storage_client_ctor)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("ARCHIVE_BUCKET", "test-archive")
    monkeypatch.setenv("ALERTS_COLLECTION", "alerts-test")
    return SimpleNamespace(db=db, doc=doc, bucket=bucket, blob=blob,
                           firestore_client=firestore_client, storage_client=storage_client_ctor)


def alert():
    return {
        "alert_id": "DRY_SOIL-farm7-plot2-1762480000000",
        "type": "DRY_SOIL", "severity": "WARNING", "source": "irrigation-controller",
        "farm_id": "farm7", "plot_id": "farm7-plot2", "sensor_ids": [],
        "moisture_pct": 18.2, "threshold_pct": 25.0,
        "message": "Average soil moisture is below threshold", "detected_at_ms": 1762480000000,
    }


def event_with(raw):
    return SimpleNamespace(data={"message": {"data": base64.b64encode(raw).decode("ascii")}})


def event_for(body):
    return event_with(json.dumps(body, separators=(",", ":")).encode())


def test_valid_alert_persists_and_archives_exact_json(clients, monkeypatch):
    clients.doc.create.return_value = None
    body = alert()
    raw = json.dumps(body, separators=(",", ":")).encode()

    main.handle_alert(event_with(raw))

    clients.firestore_client.assert_called_once_with(project="test-project")
    clients.db.collection.assert_called_once_with("alerts-test")
    clients.db.collection.return_value.document.assert_called_once_with(body["alert_id"])
    saved = clients.doc.create.call_args.args[0]
    assert saved["status"] == "open"
    assert isinstance(saved["received_at_ms"], int)
    assert {key: saved[key] for key in body} == body
    clients.blob.upload_from_string.assert_called_once_with(
        raw, content_type="application/json", if_generation_match=0)
    assert clients.bucket.blob.call_args.args[0].startswith("alerts/")
    assert clients.bucket.blob.call_args.args[0].endswith(f"/{body['alert_id']}.json")


@pytest.mark.parametrize("mutation", [
    lambda value: value.pop("alert_id"),
    lambda value: value.update(type="UNKNOWN"),
    lambda value: value.update(severity="URGENT"),
    lambda value: value.update(source=""),
    lambda value: value.update(farm_id=None),
    lambda value: value.update(sensor_ids="sensor-1"),
    lambda value: value.update(detected_at_ms=0),
    lambda value: value.update(detected_at_ms=999999999999999999999),
    lambda value: value.update(moisture_pct=float("nan")),
])
def test_invalid_contract_alert_is_acknowledged(clients, caplog, mutation):
    body = alert()
    mutation(body)
    with caplog.at_level("WARNING", logger=main.SERVICE):
        assert main.handle_alert(event_for(body)) is None
    assert "invalid alert acknowledged" in caplog.text
    clients.doc.create.assert_not_called()
    clients.blob.upload_from_string.assert_not_called()


@pytest.mark.parametrize("raw", [b"{", b"not utf-8: \xff"])
def test_invalid_json_is_acknowledged(clients, caplog, raw):
    with caplog.at_level("WARNING", logger=main.SERVICE):
        assert main.handle_alert(event_with(raw)) is None
    assert "invalid alert acknowledged" in caplog.text
    clients.doc.create.assert_not_called()


def test_malformed_base64_is_acknowledged(clients, caplog):
    bad_event = SimpleNamespace(data={"message": {"data": "%%%"}})
    with caplog.at_level("WARNING", logger=main.SERVICE):
        assert main.handle_alert(bad_event) is None
    assert "invalid alert acknowledged" in caplog.text
    clients.doc.create.assert_not_called()


def test_duplicate_delivery_does_not_reset_document_but_still_archives(clients):
    clients.doc.create.side_effect = AlreadyExists("duplicate")
    main.handle_alert(event_for(alert()))
    assert clients.doc.create.call_count == 1
    clients.blob.upload_from_string.assert_called_once()


def test_existing_archive_is_successful_idempotent_delivery(clients):
    clients.blob.upload_from_string.side_effect = PreconditionFailed("exists")
    main.handle_alert(event_for(alert()))
    assert clients.doc.create.called
    assert clients.blob.upload_from_string.call_args.kwargs["if_generation_match"] == 0


def test_firestore_transient_failure_is_raised_and_archive_not_attempted(clients):
    clients.doc.create.side_effect = RuntimeError("Firestore unavailable")
    with pytest.raises(RuntimeError, match="Firestore unavailable"):
        main.handle_alert(event_for(alert()))
    clients.blob.upload_from_string.assert_not_called()


def test_storage_transient_failure_is_raised(clients):
    clients.blob.upload_from_string.side_effect = RuntimeError("GCS unavailable")
    with pytest.raises(RuntimeError, match="GCS unavailable"):
        main.handle_alert(event_for(alert()))


def test_storage_node_alert_can_have_no_farm_or_plot(clients):
    body = alert()
    body.update(alert_id="STORAGE_NODE_DOWN-sensor-store-1-1762480000000",
                type="STORAGE_NODE_DOWN", severity="CRITICAL", source="partition-manager",
                farm_id=None, plot_id=None, sensor_ids=[], moisture_pct=None,
                threshold_pct=None, message="sensor-store-1 is unavailable")
    main.handle_alert(event_for(body))
    assert clients.doc.create.call_args.args[0]["type"] == "STORAGE_NODE_DOWN"


def test_missing_runtime_configuration_is_transient_error(clients, monkeypatch):
    monkeypatch.delenv("ARCHIVE_BUCKET")
    with pytest.raises(RuntimeError, match="ARCHIVE_BUCKET"):
        main.handle_alert(event_for(alert()))


def test_example_alert_through_functions_framework_cloud_event(clients):
    """Exercise the framework's HTTP CloudEvent adapter with cloud services mocked."""
    import functions_framework

    example_path = Path(__file__).parents[2] / "contracts" / "pubsub" / "alert.example.json"
    raw = example_path.read_bytes()
    event = {
        "specversion": "1.0", "id": "local-example-1",
        "source": "//pubsub.googleapis.com/projects/local/topics/alerts",
        "type": "google.cloud.pubsub.topic.v1.messagePublished",
        "datacontenttype": "application/json",
        "data": {"message": {"data": base64.b64encode(raw).decode("ascii"),
                               "messageId": "local-example-1",
                               "publishTime": "2026-11-13T00:00:00Z"},
                 "subscription": "projects/local/subscriptions/alerts-local"},
    }
    app = functions_framework.create_app("handle_alert", str(Path(main.__file__)), "cloudevent")
    response = app.test_client().post("/", json=event, content_type="application/cloudevents+json")
    assert response.status_code == 200
    assert clients.doc.create.call_args.args[0]["alert_id"] == json.loads(raw)["alert_id"]
    clients.blob.upload_from_string.assert_called_once_with(
        raw, content_type="application/json", if_generation_match=0)
