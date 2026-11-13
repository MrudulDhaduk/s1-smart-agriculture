"""
simulate_sensors.py - the 200 soil sensors, posting readings to Telemetry Ingestion over REST.

Same ids as tools/seed_registries.py and pmctl (farm1-plot1-s1 ... farm5-plot4-s10). Each plot's
moisture drifts slowly, and the plots named in --dry dry out steadily, so the Irrigation
Controller has something to water during a demo. Standard library only.

    python tools/simulate_sensors.py --url http://localhost:8084            # Docker Compose
    python tools/simulate_sensors.py --url http://<ingress-ip> --rate 50    # GKE, 50 readings/s
    python tools/simulate_sensors.py --url ... --dry farm1-plot2,farm3-plot1 --duration 300

Body sent to POST /readings: {"readings": [Reading, ...]} (fields of contracts/reading.proto).
"""

import argparse
import json
import random
import time
import urllib.error
import urllib.request


def sensors(farms, plots, per_plot):
    return [(f"farm{f}", f"farm{f}-plot{p}", f"farm{f}-plot{p}-s{s}")
            for f in range(1, farms + 1) for p in range(1, plots + 1) for s in range(1, per_plot + 1)]


def post(url, readings):
    req = urllib.request.Request(f"{url}/readings", data=json.dumps({"readings": readings}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="Telemetry Ingestion base URL")
    p.add_argument("--rate", type=float, default=20, help="readings per second (all sensors together)")
    p.add_argument("--batch", type=int, default=20, help="readings per request")
    p.add_argument("--duration", type=float, default=0, help="seconds to run, 0 = until Ctrl+C")
    p.add_argument("--dry", default="", help="comma-separated plot ids that dry out")
    p.add_argument("--farms", type=int, default=5)
    p.add_argument("--plots", type=int, default=4)
    p.add_argument("--sensors", type=int, default=10)
    a = p.parse_args()

    all_sensors = sensors(a.farms, a.plots, a.sensors)
    dry = set(filter(None, a.dry.split(",")))
    level = {plot: random.uniform(30, 45) for _, plot, _ in all_sensors}  # per-plot moisture %
    url = a.url.rstrip("/")
    sent = failed = 0
    start = time.time()
    interval = a.batch / a.rate

    try:
        while not a.duration or time.time() - start < a.duration:
            tick = time.time()
            for plot in level:  # slow random walk; dry plots lose 1 point per minute
                level[plot] += random.uniform(-0.05, 0.05) - (interval / 60 if plot in dry else 0)
                level[plot] = min(60.0, max(5.0, level[plot]))
            batch = []
            for farm, plot, sensor in random.sample(all_sensors, min(a.batch, len(all_sensors))):
                batch.append({"sensor_id": sensor, "farm_id": farm, "plot_id": plot,
                              "moisture_pct": round(level[plot] + random.gauss(0, 1.5), 1),
                              "temperature_c": round(random.uniform(20, 34), 1),
                              "timestamp_ms": int(time.time() * 1000)})
            try:
                post(url, batch)
                sent += len(batch)
            except (urllib.error.URLError, TimeoutError) as e:
                failed += len(batch)
                print(f"POST failed: {e}")
            if (sent + failed) % (a.batch * 50) == 0:
                print(f"sent {sent}, failed {failed}, dry plots {sorted(dry) or '-'}")
            time.sleep(max(0.0, interval - (time.time() - tick)))
    except KeyboardInterrupt:
        pass
    print(f"done: sent {sent}, failed {failed} in {time.time() - start:.0f} s")


if __name__ == "__main__":
    main()
