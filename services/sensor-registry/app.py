"""
Sensor Registry - manages soil-moisture sensors and the farm/plot each one belongs to
(REST, Cloud SQL).

A sensor can only be registered on a plot that Farm Registry knows: the check is a REST call
to Farm Registry, because each service owns its own database (no cross-database foreign key).
The Irrigation Controller asks this service which sensors are active on which plot.

Settings (environment variables):
    FARM_REGISTRY_URL              default http://farm-registry
    SQL_INSTANCE_CONNECTION_NAME   GKE: Cloud SQL instance (connector + IAM login, no password)
    DB_IAM_USER / DB_NAME          GKE: database user = the pod's Google service account
    DATABASE_URL                   elsewhere: any SQLAlchemy URL, default SQLite in /tmp
    PORT / METRICS_PORT            default 8080 / 8000
API: contracts/rest/README.md (or /docs on a running service).
"""

import os
import time
from contextlib import asynccontextmanager
from typing import Literal

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Column, Float, MetaData, String, Table, insert, select, text, update
from sqlalchemy.exc import IntegrityError

import webcommon
from webcommon import log

FARM_REGISTRY_URL = os.environ.get("FARM_REGISTRY_URL", "http://farm-registry")

engine = webcommon.make_engine("sqlite:////tmp/sensor-registry.db")
meta = MetaData()

sensors = Table(
    "sensors", meta,
    Column("sensor_id", String(80), primary_key=True),  # also the partition key on the hash ring
    Column("farm_id", String(40), nullable=False, index=True),
    Column("plot_id", String(60), nullable=False, index=True),
    Column("kind", String(40), nullable=False),
    Column("depth_cm", Float),
    Column("status", String(10), nullable=False),
    Column("installed_at_ms", BigInteger, nullable=False),
)

Status = Literal["active", "inactive", "faulty"]


class SensorIn(BaseModel):
    sensor_id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80, examples=["farm7-plot2-s3"])
    plot_id: str = Field(max_length=60, examples=["farm7-plot2"])
    kind: str = Field(default="soil-moisture", max_length=40)
    depth_cm: float | None = Field(default=None, gt=0, le=300)


class StatusIn(BaseModel):
    status: Status


http = httpx.Client(timeout=3.0)


def lookup_plot(plot_id):
    """The plot as Farm Registry knows it, or None. Raises 503 if Farm Registry is down."""
    try:
        r = http.get(f"{FARM_REGISTRY_URL}/plots/{plot_id}")
    except httpx.HTTPError as e:
        raise HTTPException(503, f"farm registry unreachable: {e}") from e
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise HTTPException(503, f"farm registry answered {r.status_code}")
    return r.json()


@asynccontextmanager
async def lifespan(_):
    webcommon.retry("database setup", lambda: meta.create_all(engine))
    log("info", "sensor registry ready", database=engine.dialect.name)
    yield


app = FastAPI(title="Sensor Registry", lifespan=lifespan)
webcommon.instrument(app, "sensor-registry")


@app.get("/livez")
def livez():
    return {"status": "ok"}


@app.get("/healthz")
def healthz():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"database unavailable: {e}") from e
    return {"status": "ok"}


@app.get("/sensors")
def list_sensors(farm_id: str | None = None, plot_id: str | None = None, status: Status | None = None):
    query = select(sensors).order_by(sensors.c.sensor_id)
    for column, value in (("farm_id", farm_id), ("plot_id", plot_id), ("status", status)):
        if value:
            query = query.where(sensors.c[column] == value)
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(query)]


@app.post("/sensors", status_code=201)
def register_sensor(sensor: SensorIn):
    if not sensor.sensor_id.startswith(f"{sensor.plot_id}-"):
        raise HTTPException(422, f"sensor_id must start with '{sensor.plot_id}-'")
    plot = lookup_plot(sensor.plot_id)
    if plot is None:
        raise HTTPException(422, f"plot {sensor.plot_id} is not registered in Farm Registry")
    row = {**sensor.model_dump(), "farm_id": plot["farm_id"], "status": "active",
           "installed_at_ms": int(time.time() * 1000)}
    try:
        with engine.begin() as conn:
            conn.execute(insert(sensors).values(**row))
    except IntegrityError as e:
        raise HTTPException(409, f"sensor {sensor.sensor_id} already exists") from e
    log("info", "sensor registered", sensor_id=sensor.sensor_id, plot_id=sensor.plot_id)
    return row


@app.get("/sensors/{sensor_id}")
def get_sensor(sensor_id: str):
    with engine.connect() as conn:
        row = conn.execute(select(sensors).where(sensors.c.sensor_id == sensor_id)).first()
    if row is None:
        raise HTTPException(404, f"sensor {sensor_id} not found")
    return dict(row._mapping)


@app.patch("/sensors/{sensor_id}")
def set_status(sensor_id: str, body: StatusIn):
    with engine.begin() as conn:
        result = conn.execute(update(sensors).where(sensors.c.sensor_id == sensor_id).values(status=body.status))
    if result.rowcount == 0:
        raise HTTPException(404, f"sensor {sensor_id} not found")
    log("info", "sensor status changed", sensor_id=sensor_id, status=body.status)
    return get_sensor(sensor_id)


if __name__ == "__main__":
    webcommon.start_metrics_server()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
