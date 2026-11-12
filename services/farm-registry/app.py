"""
Farm Registry - registers farms, their plots and crop details (REST, Cloud SQL).

Every plot belongs to one farm and grows one crop. The crop defines the soil-moisture band the
Irrigation Controller aims for, and how deep its roots are (which sets how much water a plot
needs). Farms -> plots -> crops is relational data with foreign keys, hence a SQL database.

Settings (environment variables):
    SQL_INSTANCE_CONNECTION_NAME   GKE: Cloud SQL instance (connector + IAM login, no password)
    DB_IAM_USER / DB_NAME          GKE: database user = the pod's Google service account
    DATABASE_URL                   elsewhere: any SQLAlchemy URL, default SQLite in /tmp
    PORT / METRICS_PORT            default 8080 / 8000
API: contracts/rest/README.md (or /docs on a running service).
"""

import os
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import (BigInteger, Column, Float, ForeignKey, MetaData, String, Table, insert,
                        select, text)
from sqlalchemy.exc import IntegrityError

import webcommon
from webcommon import log

engine = webcommon.make_engine("sqlite:////tmp/farm-registry.db")
meta = MetaData()

crops = Table(
    "crops", meta,
    Column("name", String(40), primary_key=True),
    Column("min_moisture_pct", Float, nullable=False),     # water when the plot drops below this
    Column("target_moisture_pct", Float, nullable=False),  # water up to this
    Column("root_depth_cm", Float, nullable=False),        # soil depth that must be re-wetted
)
farms = Table(
    "farms", meta,
    Column("farm_id", String(40), primary_key=True),
    Column("name", String(100), nullable=False),
    Column("location", String(200)),
    Column("created_at_ms", BigInteger, nullable=False),
)
plots = Table(
    "plots", meta,
    Column("plot_id", String(60), primary_key=True),
    Column("farm_id", String(40), ForeignKey("farms.farm_id", ondelete="CASCADE"), nullable=False, index=True),
    Column("name", String(100)),
    Column("crop", String(40), ForeignKey("crops.name"), nullable=False),
    Column("area_m2", Float, nullable=False),
    Column("planted_on", String(10)),
    Column("created_at_ms", BigInteger, nullable=False),
)

# Starting crop catalogue (typical agronomic ranges, volumetric water content %).
DEFAULT_CROPS = [
    {"name": "wheat", "min_moisture_pct": 22.0, "target_moisture_pct": 32.0, "root_depth_cm": 60.0},
    {"name": "rice", "min_moisture_pct": 40.0, "target_moisture_pct": 55.0, "root_depth_cm": 30.0},
    {"name": "maize", "min_moisture_pct": 25.0, "target_moisture_pct": 35.0, "root_depth_cm": 60.0},
    {"name": "tomato", "min_moisture_pct": 25.0, "target_moisture_pct": 35.0, "root_depth_cm": 40.0},
]

ID = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class Crop(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$", max_length=40)
    min_moisture_pct: float = Field(ge=0, le=100)
    target_moisture_pct: float = Field(ge=0, le=100)
    root_depth_cm: float = Field(gt=0, le=500)

    @model_validator(mode="after")
    def band(self):
        if self.target_moisture_pct <= self.min_moisture_pct:
            raise ValueError("target_moisture_pct must be above min_moisture_pct")
        return self


class FarmIn(BaseModel):
    farm_id: str = Field(pattern=ID, max_length=40, examples=["farm7"])
    name: str = Field(min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=200)


class PlotIn(BaseModel):
    plot_id: str = Field(pattern=ID, max_length=60, examples=["farm7-plot2"])
    crop: str
    area_m2: float = Field(gt=0)
    name: str | None = Field(default=None, max_length=100)
    planted_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


def now_ms():
    return int(time.time() * 1000)


def setup_database():
    meta.create_all(engine)
    with engine.begin() as conn:
        known = set(conn.scalars(select(crops.c.name)))
        missing = [c for c in DEFAULT_CROPS if c["name"] not in known]
        if missing:
            conn.execute(insert(crops), missing)


@asynccontextmanager
async def lifespan(_):
    webcommon.retry("database setup", setup_database)
    log("info", "farm registry ready", database=engine.dialect.name)
    yield


app = FastAPI(title="Farm Registry", lifespan=lifespan)
webcommon.instrument(app, "farm-registry")


def plot_row_to_dict(row):
    r = row._mapping
    return {
        "plot_id": r["plot_id"], "farm_id": r["farm_id"], "name": r["name"],
        "area_m2": r["area_m2"], "planted_on": r["planted_on"],
        "crop": {"name": r["crop"], "min_moisture_pct": r["min_moisture_pct"],
                 "target_moisture_pct": r["target_moisture_pct"], "root_depth_cm": r["root_depth_cm"]},
    }


PLOTS_WITH_CROP = select(
    plots.c.plot_id, plots.c.farm_id, plots.c.name, plots.c.area_m2, plots.c.planted_on, plots.c.crop,
    crops.c.min_moisture_pct, crops.c.target_moisture_pct, crops.c.root_depth_cm,
).join(crops, plots.c.crop == crops.c.name)


@app.get("/livez")
def livez():
    return {"status": "ok"}


@app.get("/healthz")
def healthz():
    """Readiness (and the load balancer's health check): can we reach the database?"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"database unavailable: {e}") from e
    return {"status": "ok"}


@app.get("/crops")
def list_crops():
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(crops).order_by(crops.c.name))]


@app.post("/crops", status_code=201)
def create_crop(crop: Crop):
    try:
        with engine.begin() as conn:
            conn.execute(insert(crops).values(**crop.model_dump()))
    except IntegrityError as e:
        raise HTTPException(409, f"crop {crop.name} already exists") from e
    return crop.model_dump()


@app.get("/farms")
def list_farms():
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(farms).order_by(farms.c.farm_id))]


@app.post("/farms", status_code=201)
def create_farm(farm: FarmIn):
    row = {**farm.model_dump(), "created_at_ms": now_ms()}
    try:
        with engine.begin() as conn:
            conn.execute(insert(farms).values(**row))
    except IntegrityError as e:
        raise HTTPException(409, f"farm {farm.farm_id} already exists") from e
    log("info", "farm registered", farm_id=farm.farm_id)
    return row


@app.get("/farms/{farm_id}")
def get_farm(farm_id: str):
    with engine.connect() as conn:
        farm = conn.execute(select(farms).where(farms.c.farm_id == farm_id)).first()
        if farm is None:
            raise HTTPException(404, f"farm {farm_id} not found")
        rows = conn.execute(PLOTS_WITH_CROP.where(plots.c.farm_id == farm_id).order_by(plots.c.plot_id))
        return {**dict(farm._mapping), "plots": [plot_row_to_dict(r) for r in rows]}


@app.post("/farms/{farm_id}/plots", status_code=201)
def create_plot(farm_id: str, plot: PlotIn):
    # The plot id carries its farm id ("farm7-plot2"), like the sensor ids do ("farm7-plot2-s3").
    if not plot.plot_id.startswith(f"{farm_id}-"):
        raise HTTPException(422, f"plot_id must start with '{farm_id}-'")
    row = {**plot.model_dump(), "farm_id": farm_id, "created_at_ms": now_ms()}
    with engine.begin() as conn:
        if conn.execute(select(farms.c.farm_id).where(farms.c.farm_id == farm_id)).first() is None:
            raise HTTPException(404, f"farm {farm_id} not found")
        if conn.execute(select(crops.c.name).where(crops.c.name == plot.crop)).first() is None:
            raise HTTPException(422, f"unknown crop {plot.crop}; add it with POST /crops")
        try:
            conn.execute(insert(plots).values(**row))
        except IntegrityError as e:
            raise HTTPException(409, f"plot {plot.plot_id} already exists") from e
    log("info", "plot registered", farm_id=farm_id, plot_id=plot.plot_id, crop=plot.crop)
    return get_plot(plot.plot_id)


@app.get("/plots")
def list_plots(farm_id: str | None = None):
    query = PLOTS_WITH_CROP.order_by(plots.c.plot_id)
    if farm_id:
        query = query.where(plots.c.farm_id == farm_id)
    with engine.connect() as conn:
        return [plot_row_to_dict(r) for r in conn.execute(query)]


@app.get("/plots/{plot_id}")
def get_plot(plot_id: str):
    with engine.connect() as conn:
        row = conn.execute(PLOTS_WITH_CROP.where(plots.c.plot_id == plot_id)).first()
    if row is None:
        raise HTTPException(404, f"plot {plot_id} not found")
    return plot_row_to_dict(row)


if __name__ == "__main__":
    webcommon.start_metrics_server()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
