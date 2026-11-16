"""
The control logic of the Irrigation Controller, kept free of I/O so it can be unit-tested.

One control cycle:
  1. plots (with their crop's moisture band) from Farm Registry          REST
  2. active sensors per plot from Sensor Registry                        REST
  3. newest reading of every sensor from Partition Manager GetLatest     gRPC
  4. per plot: average the fresh readings, compare with the crop's minimum
  5. dry plot -> watering decision on Kafka "irrigation" + DRY_SOIL alert on Pub/Sub "alerts"
     silent sensors -> SENSOR_SILENT alert
A cooldown (shared state, Firestore on GKE) stops a plot being watered or alerted again within
COOLDOWN_S, so neither a second replica nor a restart double-waters.
"""

import time
from dataclasses import dataclass


@dataclass
class Deps:
    registry: object      # .plots(farm_id), .active_sensors(farm_id)
    readings: object      # .latest(sensor_ids) -> {sensor_id: {"moisture_pct", "timestamp_ms"}}
    cooldown: object      # .claim(key, now_ms, cooldown_ms) -> bool, .active(key, now_ms, cooldown_ms) -> bool
    alerts: object        # .publish(alert)
    irrigation: object    # .publish(event), .flush()
    stale_ms: int = 300_000
    cooldown_ms: int = 600_000


def water_needed(area_m2, deficit_pct, root_depth_cm):
    """Litres that raise volumetric soil moisture by deficit_pct over the root zone.
    1 m2 x 1 cm of soil = 10 L of soil, and 1 % of that is 0.1 L: litres = area x deficit x depth / 10."""
    return round(area_m2 * deficit_pct * root_depth_cm / 10, 1)


def assess(plot, sensor_ids, latest, now_ms, stale_ms):
    """Decision for one plot from the newest reading of each of its sensors (no side effects)."""
    crop = plot["crop"]

    def is_fresh(s):
        return s in latest and now_ms - latest[s]["timestamp_ms"] <= stale_ms

    fresh = [latest[s]["moisture_pct"] for s in sensor_ids if is_fresh(s)]
    result = {
        "plot_id": plot["plot_id"], "farm_id": plot["farm_id"], "crop": crop["name"],
        "sensors": len(sensor_ids), "fresh_readings": len(fresh),
        "silent_sensors": sorted(s for s in sensor_ids if not is_fresh(s)),
        "moisture_pct": None, "min_pct": crop["min_moisture_pct"], "target_pct": crop["target_moisture_pct"],
        "decision": "NO_DATA", "water_litres": 0.0,
    }
    if not fresh:
        return result
    moisture = round(sum(fresh) / len(fresh), 1)
    result["moisture_pct"] = moisture
    if moisture >= crop["min_moisture_pct"]:
        result["decision"] = "OK"
    else:
        result["decision"] = "WATER"
        result["water_litres"] = water_needed(plot["area_m2"], crop["target_moisture_pct"] - moisture,
                                              crop["root_depth_cm"])
    return result


def dry_soil_alert(r, now_ms):
    critical = r["moisture_pct"] < r["min_pct"] - 10
    return {
        "alert_id": f"DRY_SOIL-{r['plot_id']}-{now_ms}", "type": "DRY_SOIL",
        "severity": "CRITICAL" if critical else "WARNING", "source": "irrigation-controller",
        "farm_id": r["farm_id"], "plot_id": r["plot_id"], "sensor_ids": [],
        "moisture_pct": r["moisture_pct"], "threshold_pct": r["min_pct"],
        "message": f"Average soil moisture {r['moisture_pct']}% is below the {r['crop']} minimum of {r['min_pct']}%",
        "detected_at_ms": now_ms,
    }


def silent_alert(r, now_ms, stale_ms):
    return {
        "alert_id": f"SENSOR_SILENT-{r['plot_id']}-{now_ms}", "type": "SENSOR_SILENT",
        "severity": "WARNING", "source": "irrigation-controller",
        "farm_id": r["farm_id"], "plot_id": r["plot_id"], "sensor_ids": r["silent_sensors"],
        "moisture_pct": r["moisture_pct"], "threshold_pct": None,
        "message": (f"{len(r['silent_sensors'])} of {r['sensors']} sensors on {r['plot_id']} "
                    f"sent no reading for {stale_ms // 60000} minutes"),
        "detected_at_ms": now_ms,
    }


def irrigation_event(r, now_ms):
    return {
        "event_id": f"{r['plot_id']}-{now_ms}", "farm_id": r["farm_id"], "plot_id": r["plot_id"],
        "crop": r["crop"], "action": "WATER", "moisture_pct": r["moisture_pct"],
        "target_pct": r["target_pct"], "water_litres": r["water_litres"], "decided_at_ms": now_ms,
    }


def run_cycle(deps, farm_id=None, act=False, now_ms=None):
    """Assess every plot. act=False only reports; act=True also waters and raises alerts."""
    now_ms = now_ms or int(time.time() * 1000)
    plots = deps.registry.plots(farm_id)
    sensors = deps.registry.active_sensors(farm_id)
    by_plot = {}
    for s in sensors:
        by_plot.setdefault(s["plot_id"], []).append(s["sensor_id"])
    latest = deps.readings.latest([s["sensor_id"] for s in sensors]) if sensors else {}

    results = []
    for plot in plots:
        r = assess(plot, by_plot.get(plot["plot_id"], []), latest, now_ms, deps.stale_ms)
        key = plot["plot_id"]
        if r["decision"] == "WATER":
            if not act:
                if deps.cooldown.active(key, now_ms, deps.cooldown_ms):
                    r["decision"] = "COOLDOWN"
            elif deps.cooldown.claim(key, now_ms, deps.cooldown_ms):
                deps.irrigation.publish(irrigation_event(r, now_ms))
                deps.alerts.publish(dry_soil_alert(r, now_ms))
            else:
                r["decision"] = "COOLDOWN"
        if act and r["silent_sensors"] and deps.cooldown.claim(f"silent:{key}", now_ms, deps.cooldown_ms):
            deps.alerts.publish(silent_alert(r, now_ms, deps.stale_ms))
        results.append(r)
    if act:
        deps.irrigation.flush()
    return results
