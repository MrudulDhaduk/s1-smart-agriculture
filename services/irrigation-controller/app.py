"""
Irrigation Controller - recommends and triggers watering from the current soil readings.

Runs one control cycle every EVAL_INTERVAL_S (default 30 s) in the background and also offers
it over REST:
    GET  /irrigation/recommendations?farm_id=   what it would do now (no side effects)
    POST /irrigation/evaluate?farm_id=          run a cycle now (waters + alerts), e.g. for a demo
The cycle itself is in controller.py; the connections in backends.py.

Settings: EVAL_INTERVAL_S (0 = no background loop), PORT / METRICS_PORT (8080 / 8000),
plus the backend variables listed in backends.py.
"""

import os
import threading
import time
from contextlib import asynccontextmanager

import grpc
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Histogram

import backends
import controller
import webcommon
from webcommon import log

EVAL_INTERVAL_S = float(os.environ.get("EVAL_INTERVAL_S", "30"))

CYCLES = Counter("irrigation_cycles_total", "Control cycles run", ["trigger", "result"])
DECISIONS = Counter("irrigation_decisions_total", "Per-plot decisions of acting cycles", ["decision"])
WATER = Counter("irrigation_water_litres_total", "Water released by watering decisions")
CYCLE_SECONDS = Histogram("irrigation_cycle_seconds", "Time for one control cycle")

deps = None
stop = threading.Event()


def cycle(trigger, farm_id=None, act=True):
    start = time.perf_counter()
    try:
        results = controller.run_cycle(deps, farm_id=farm_id, act=act)
    except Exception:
        CYCLES.labels(trigger, "error").inc()
        raise
    CYCLE_SECONDS.observe(time.perf_counter() - start)
    CYCLES.labels(trigger, "ok").inc()
    if act:
        for r in results:
            DECISIONS.labels(r["decision"]).inc()
            if r["decision"] == "WATER":
                WATER.inc(r["water_litres"])
    return results


def loop():
    while not stop.wait(EVAL_INTERVAL_S):
        try:
            results = cycle("timer")
            watered = [r["plot_id"] for r in results if r["decision"] == "WATER"]
            log("info", "control cycle", plots=len(results), watered=watered)
        except Exception as e:  # noqa: BLE001  (keep the loop alive; next tick retries)
            log("error", "control cycle failed", error=str(e))


@asynccontextmanager
async def lifespan(_):
    global deps
    deps = backends.from_env()
    if EVAL_INTERVAL_S > 0:
        threading.Thread(target=loop, daemon=True).start()
    log("info", "irrigation controller ready", interval_s=EVAL_INTERVAL_S)
    yield
    stop.set()
    deps.irrigation.flush()


app = FastAPI(title="Irrigation Controller", lifespan=lifespan)
webcommon.instrument(app, "irrigation-controller")


def answer(act, farm_id):
    try:
        return cycle("api", farm_id=farm_id, act=act)
    except httpx.HTTPError as e:
        raise HTTPException(503, f"registry unavailable: {e}") from e
    except grpc.RpcError as e:
        raise HTTPException(503, f"partition manager unavailable: {e.code().name}") from e


@app.get("/livez")
@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/irrigation/recommendations")
def recommendations(farm_id: str | None = None):
    return answer(act=False, farm_id=farm_id)


@app.post("/irrigation/evaluate")
def evaluate(farm_id: str | None = None):
    return answer(act=True, farm_id=farm_id)


if __name__ == "__main__":
    webcommon.start_metrics_server()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
