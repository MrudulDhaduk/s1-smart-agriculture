"""Pub/Sub alert handler for the S1 Smart Agriculture project."""

import base64
import binascii
from datetime import datetime, timezone
import json
import logging
import math
import os

import functions_framework
from google.api_core.exceptions import AlreadyExists, PreconditionFailed
from google.cloud import firestore, storage


SERVICE = "alert-function"
ALERT_TYPES = {"DRY_SOIL", "SENSOR_SILENT", "STORAGE_NODE_DOWN"}
SEVERITIES = {"INFO", "WARNING", "CRITICAL"}
logger = logging.getLogger(SERVICE)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.propagate = False


class InvalidAlert(ValueError):
    """The message is malformed or cannot satisfy the shared alert contract."""


def _log(level, message, **fields):
    payload = {"service": SERVICE, "level": level, "message": message, **fields}
    getattr(logger, level)(json.dumps(payload, separators=(",", ":"), default=str))


def _decode_alert(cloud_event):
    try:
        encoded = cloud_event.data["message"]["data"]
        if not isinstance(encoded, str):
            raise InvalidAlert("message data must be a Base64 string")
        raw = base64.b64decode(encoded, validate=True)
        decoded = raw.decode("utf-8")
        alert = json.loads(decoded)
    except (KeyError, TypeError, UnicodeDecodeError, binascii.Error, ValueError,
            json.JSONDecodeError) as exc:
        raise InvalidAlert(f"invalid Pub/Sub message: {exc}") from exc
    if not isinstance(alert, dict):
        raise InvalidAlert("alert JSON must be an object")
    return raw, alert


def _validate_alert(alert):
    required = ("alert_id", "type", "severity", "source", "farm_id", "plot_id",
                "sensor_ids", "moisture_pct", "threshold_pct", "message", "detected_at_ms")
    missing = [name for name in required if name not in alert]
    if missing:
        raise InvalidAlert(f"missing required fields: {', '.join(missing)}")
    for name in ("alert_id", "source", "message"):
        if (not isinstance(alert[name], str) or not alert[name].strip()
                or "/" in alert[name] or "\\" in alert[name]):
            raise InvalidAlert(f"{name} must be a non-empty string")
    if not isinstance(alert["type"], str) or alert["type"] not in ALERT_TYPES:
        raise InvalidAlert("type is not a supported alert type")
    if not isinstance(alert["severity"], str) or alert["severity"] not in SEVERITIES:
        raise InvalidAlert("severity is not a supported severity")
    if not isinstance(alert["sensor_ids"], list) or any(
            not isinstance(item, str) or not item for item in alert["sensor_ids"]):
        raise InvalidAlert("sensor_ids must be an array of non-empty strings")
    for name in ("farm_id", "plot_id"):
        if alert[name] is not None and (not isinstance(alert[name], str) or not alert[name]):
            raise InvalidAlert(f"{name} must be a non-empty string or null")
    if alert["type"] in {"DRY_SOIL", "SENSOR_SILENT"} and (
            not alert["farm_id"] or not alert["plot_id"]):
        raise InvalidAlert(f"{alert['type']} requires farm_id and plot_id")
    if alert["type"] == "STORAGE_NODE_DOWN" and not alert["farm_id"] and not alert["plot_id"]:
        # The node identity is normally included in the message and encoded in alert_id.
        if "-" not in alert["alert_id"]:
            raise InvalidAlert("STORAGE_NODE_DOWN requires a node identifier")
    for name in ("moisture_pct", "threshold_pct"):
        value = alert[name]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value)):
            raise InvalidAlert(f"{name} must be a finite number or null")
    detected = alert["detected_at_ms"]
    if isinstance(detected, bool) or not isinstance(detected, int) or not 0 < detected <= 253402300799999:
        raise InvalidAlert("detected_at_ms must be a valid positive Unix timestamp in milliseconds")


def _create_firestore_alert(db, collection, alert, received_at_ms):
    """Create once; create() is atomic and cannot reset fields on Pub/Sub redelivery."""
    ref = db.collection(collection).document(alert["alert_id"])
    try:
        ref.create({**alert, "status": "open", "received_at_ms": received_at_ms})
        return True
    except AlreadyExists:
        return False


def _archive_alert(bucket, raw, alert_id, detected_at):
    path = f"alerts/{detected_at:%Y/%m/%d}/{alert_id}.json"
    blob = bucket.blob(path)
    try:
        blob.upload_from_string(raw, content_type="application/json", if_generation_match=0)
        return path, True
    except PreconditionFailed:
        return path, False


@functions_framework.cloud_event
def handle_alert(cloud_event):
    """Validate, persist, and archive one Pub/Sub alert CloudEvent."""
    try:
        raw, alert = _decode_alert(cloud_event)
        _validate_alert(alert)
    except InvalidAlert as exc:
        _log("warning", "invalid alert acknowledged", error=str(exc))
        return

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    archive_bucket = os.environ.get("ARCHIVE_BUCKET")
    collection = os.environ.get("ALERTS_COLLECTION", "alerts")
    if not project or not archive_bucket:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT and ARCHIVE_BUCKET must be configured")

    # Keep the document's reception time distinct from the stable event date in the archive path.
    received_at = datetime.now(timezone.utc)
    received_at_ms = int(received_at.timestamp() * 1000)
    db = firestore.Client(project=project)
    created = _create_firestore_alert(db, collection, alert, received_at_ms)
    bucket = storage.Client(project=project).bucket(archive_bucket)
    detected_at = datetime.fromtimestamp(alert["detected_at_ms"] / 1000, timezone.utc)
    archive_path, archived = _archive_alert(bucket, raw, alert["alert_id"], detected_at)
    _log("info", "alert processed", alert_id=alert["alert_id"], type=alert["type"],
         severity=alert["severity"], farm_id=alert["farm_id"], plot_id=alert["plot_id"],
         firestore_created=created, archive_path=archive_path, archive_created=archived)
