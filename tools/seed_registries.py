"""
seed_registries.py - register the demo farms, plots and sensors through the REST APIs.

The ids match the readings that `pmctl.py write` generates: farm1..farm5, 4 plots each,
10 sensors per plot (farm3-plot2-s7), 200 sensors in total. Safe to run twice (409 = already there).

    python tools/seed_registries.py                         # Docker Compose (localhost:8081 / 8082)
    python tools/seed_registries.py --base http://<IP>      # GKE: the Ingress address serves both
"""

import argparse
import json
import urllib.error
import urllib.request

CROPS = ["wheat", "rice", "maize", "tomato"]


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return 409
        raise SystemExit(f"POST {url} -> {e.code}: {e.read().decode()[:300]}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", help="one address for both registries (the GKE Ingress)")
    p.add_argument("--farm-url", default="http://localhost:8081")
    p.add_argument("--sensor-url", default="http://localhost:8082")
    p.add_argument("--farms", type=int, default=5)
    p.add_argument("--plots", type=int, default=4)
    p.add_argument("--sensors", type=int, default=10)
    a = p.parse_args()
    farm_url = sensor_url = a.base.rstrip("/") if a.base else None
    farm_url, sensor_url = farm_url or a.farm_url, sensor_url or a.sensor_url

    created = {"farms": 0, "plots": 0, "sensors": 0}
    for f in range(1, a.farms + 1):
        farm = f"farm{f}"
        created["farms"] += post(f"{farm_url}/farms", {"farm_id": farm, "name": f"Farm {f}",
                                                       "location": "Pilani"}) == 201
        for pl in range(1, a.plots + 1):
            plot = f"{farm}-plot{pl}"
            created["plots"] += post(f"{farm_url}/farms/{farm}/plots", {
                "plot_id": plot, "name": f"Plot {pl}", "crop": CROPS[(pl - 1) % len(CROPS)],
                "area_m2": 500.0 * pl}) == 201
            for s in range(1, a.sensors + 1):
                created["sensors"] += post(f"{sensor_url}/sensors", {
                    "sensor_id": f"{plot}-s{s}", "plot_id": plot, "depth_cm": 20.0}) == 201
    print(f"created {created} (the rest already existed)")


if __name__ == "__main__":
    main()
