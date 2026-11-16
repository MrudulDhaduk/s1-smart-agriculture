import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app as sensor_app

KNOWN_PLOTS = {"farm7-plot2": {"plot_id": "farm7-plot2", "farm_id": "farm7"}}


@pytest.fixture
def c(monkeypatch):
    # Farm Registry is another service: stand it in with a dict.
    monkeypatch.setattr(sensor_app, "lookup_plot", lambda plot_id: KNOWN_PLOTS.get(plot_id))
    with TestClient(sensor_app.app) as client:
        yield client


def test_register_and_query(c):
    r = c.post("/sensors", json={"sensor_id": "farm7-plot2-s3", "plot_id": "farm7-plot2", "depth_cm": 20})
    assert r.status_code == 201
    assert r.json()["farm_id"] == "farm7"           # taken from Farm Registry, not from the caller
    assert r.json()["status"] == "active"
    assert c.post("/sensors", json={"sensor_id": "farm7-plot2-s3", "plot_id": "farm7-plot2"}).status_code == 409

    assert [s["sensor_id"] for s in c.get("/sensors", params={"plot_id": "farm7-plot2"}).json()] == ["farm7-plot2-s3"]
    assert c.get("/sensors/farm7-plot2-s3").json()["depth_cm"] == 20


def test_unknown_plot_and_bad_id(c):
    assert c.post("/sensors", json={"sensor_id": "farm1-plot1-s1", "plot_id": "farm1-plot1"}).status_code == 422
    assert c.post("/sensors", json={"sensor_id": "other-s1", "plot_id": "farm7-plot2"}).status_code == 422


def test_status_filter(c):
    c.post("/sensors", json={"sensor_id": "farm7-plot2-s4", "plot_id": "farm7-plot2"})
    assert c.patch("/sensors/farm7-plot2-s4", json={"status": "faulty"}).json()["status"] == "faulty"
    assert c.patch("/sensors/farm7-plot2-s4", json={"status": "broken"}).status_code == 422
    assert c.patch("/sensors/nope", json={"status": "inactive"}).status_code == 404
    active = {s["sensor_id"] for s in c.get("/sensors", params={"status": "active"}).json()}
    assert "farm7-plot2-s4" not in active


def test_farm_registry_down_is_503(monkeypatch):
    def down(_):
        raise HTTPException(503, "farm registry unreachable")
    monkeypatch.setattr(sensor_app, "lookup_plot", down)
    with TestClient(sensor_app.app) as client:
        r = client.post("/sensors", json={"sensor_id": "farm7-plot2-s9", "plot_id": "farm7-plot2"})
    assert r.status_code == 503
