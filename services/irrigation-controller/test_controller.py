import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "web-common"))

from backends import MemoryCooldown  # noqa: E402
from controller import Deps, assess, run_cycle, water_needed  # noqa: E402

NOW = 1_762_480_000_000
TOMATO = {"name": "tomato", "min_moisture_pct": 25.0, "target_moisture_pct": 35.0, "root_depth_cm": 40.0}
PLOT = {"plot_id": "farm7-plot2", "farm_id": "farm7", "area_m2": 1200.0, "crop": TOMATO}


def reading(moisture, age_s=10):
    return {"moisture_pct": moisture, "timestamp_ms": NOW - age_s * 1000}


def test_water_needed():
    # 1200 m2, 10 points short over 40 cm of roots: 1200 * 10 * 40 / 10
    assert water_needed(1200, 10, 40) == 48000.0


def test_dry_plot_is_watered_to_target():
    r = assess(PLOT, ["a", "b"], {"a": reading(15), "b": reading(19)}, NOW, 300_000)
    assert r["decision"] == "WATER"
    assert r["moisture_pct"] == 17.0
    assert r["water_litres"] == water_needed(1200, 35 - 17, 40)


def test_moist_plot_is_ok_and_stale_readings_are_ignored():
    latest = {"a": reading(30), "b": reading(5, age_s=600)}  # b is 10 minutes old
    r = assess(PLOT, ["a", "b"], latest, NOW, 300_000)
    assert r["decision"] == "OK"
    assert r["moisture_pct"] == 30.0
    assert r["silent_sensors"] == ["b"]


def test_no_fresh_reading_is_no_data():
    r = assess(PLOT, ["a"], {}, NOW, 300_000)
    assert r["decision"] == "NO_DATA" and r["silent_sensors"] == ["a"]


class Fakes:
    def __init__(self, moisture):
        self.alerts, self.events, self.moisture = [], [], moisture

    def plots(self, farm_id=None):
        return [PLOT]

    def active_sensors(self, farm_id=None):
        return [{"sensor_id": "s1", "plot_id": "farm7-plot2"}, {"sensor_id": "s2", "plot_id": "farm7-plot2"}]

    def latest(self, ids):
        return {"s1": reading(self.moisture)}  # s2 is silent

    def publish(self, msg):
        (self.alerts if "alert_id" in msg else self.events).append(msg)

    def flush(self):
        pass


def deps_for(fakes):
    return Deps(registry=fakes, readings=fakes, cooldown=MemoryCooldown(), alerts=fakes, irrigation=fakes)


def test_cycle_waters_once_then_cools_down():
    f = Fakes(moisture=12.0)
    deps = deps_for(f)

    first = run_cycle(deps, act=True, now_ms=NOW)
    assert first[0]["decision"] == "WATER"
    assert len(f.events) == 1 and f.events[0]["plot_id"] == "farm7-plot2"
    assert {a["type"] for a in f.alerts} == {"DRY_SOIL", "SENSOR_SILENT"}
    dry = next(a for a in f.alerts if a["type"] == "DRY_SOIL")
    assert dry["severity"] == "CRITICAL"  # 12 % is more than 10 points under the 25 % minimum

    second = run_cycle(deps, act=True, now_ms=NOW + 60_000)  # one minute later
    assert second[0]["decision"] == "COOLDOWN"
    assert len(f.events) == 1 and len(f.alerts) == 2


def test_log_sinks_accept_real_messages(capsys):
    # Regression: an alert carries its own "message" field, which once clashed with log()'s.
    from backends import LogSink
    from controller import dry_soil_alert, irrigation_event
    r = assess(PLOT, ["a"], {"a": reading(12)}, NOW, 300_000)
    LogSink("alert").publish(dry_soil_alert(r, NOW))
    LogSink("irrigation event").publish(irrigation_event(r, NOW))
    assert capsys.readouterr().out.count("farm7-plot2") >= 2


def test_recommendations_have_no_side_effects():
    f = Fakes(moisture=12.0)
    r = run_cycle(deps_for(f), act=False, now_ms=NOW)
    assert r[0]["decision"] == "WATER"
    assert f.events == [] and f.alerts == []
