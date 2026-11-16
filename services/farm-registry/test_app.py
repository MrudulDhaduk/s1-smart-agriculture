from fastapi.testclient import TestClient

from app import app


def client():
    return TestClient(app)


def test_default_crops_are_seeded():
    with client() as c:
        names = {crop["name"] for crop in c.get("/crops").json()}
    assert {"wheat", "rice", "maize", "tomato"} <= names


def test_farm_plot_lifecycle():
    with client() as c:
        assert c.post("/farms", json={"farm_id": "farm7", "name": "Green Acres"}).status_code == 201
        assert c.post("/farms", json={"farm_id": "farm7", "name": "dup"}).status_code == 409

        r = c.post("/farms/farm7/plots", json={"plot_id": "farm7-plot2", "crop": "tomato", "area_m2": 1200})
        assert r.status_code == 201
        assert r.json()["crop"]["min_moisture_pct"] == 25.0

        farm = c.get("/farms/farm7").json()
        assert [p["plot_id"] for p in farm["plots"]] == ["farm7-plot2"]
        assert c.get("/plots", params={"farm_id": "farm7"}).json()[0]["crop"]["name"] == "tomato"
        assert c.get("/plots/farm7-plot2").json()["area_m2"] == 1200


def test_plot_rules():
    with client() as c:
        c.post("/farms", json={"farm_id": "farm8", "name": "Hill"})
        # plot id must carry its farm id
        assert c.post("/farms/farm8/plots", json={"plot_id": "farm9-plot1", "crop": "rice", "area_m2": 10}).status_code == 422
        # crop must exist
        assert c.post("/farms/farm8/plots", json={"plot_id": "farm8-plot1", "crop": "cactus", "area_m2": 10}).status_code == 422
        # farm must exist
        assert c.post("/farms/nofarm/plots", json={"plot_id": "nofarm-plot1", "crop": "rice", "area_m2": 10}).status_code == 404
        assert c.get("/plots/farm8-plot9").status_code == 404


def test_crop_band_validation():
    with client() as c:
        bad = {"name": "odd", "min_moisture_pct": 40, "target_moisture_pct": 30, "root_depth_cm": 20}
        assert c.post("/crops", json=bad).status_code == 422
        good = {"name": "chilli", "min_moisture_pct": 25, "target_moisture_pct": 35, "root_depth_cm": 30}
        assert c.post("/crops", json=good).status_code == 201


def test_health_and_metrics_routes():
    with client() as c:
        assert c.get("/healthz").json() == {"status": "ok"}
        c.get("/farms/unknown")
    import webcommon
    from prometheus_client import REGISTRY
    assert REGISTRY.get_sample_value(
        "http_requests_total", {"method": "GET", "route": "/farms/{farm_id}", "status": "404"}) >= 1
    assert webcommon.SERVICE == "farm-registry"
