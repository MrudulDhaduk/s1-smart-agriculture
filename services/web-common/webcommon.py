"""
webcommon - plumbing shared by Person 1's HTTP services (Farm Registry, Sensor Registry,
Irrigation Controller). Each Dockerfile copies this one file next to the service's app.py.

Same conventions as the rest of the repo:
    logs     one JSON object per line on stdout: service, level, message + fields
    metrics  Prometheus on :METRICS_PORT/metrics (default 8000), port name "metrics"
"""

import json
import os
import time

from prometheus_client import Counter, Histogram, start_http_server
from starlette.routing import Match

SERVICE = "unknown"

REQUESTS = Counter("http_requests_total", "HTTP requests handled", ["method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "Time to handle an HTTP request", ["method", "route"])

QUIET_PATHS = {"/healthz", "/livez"}  # probes every few seconds: not worth a metric or a log line


def log(level, message, **fields):
    """One JSON object per line on stdout; Cloud Logging turns it into a structured entry."""
    print(json.dumps({"service": SERVICE, "level": level, "message": message, **fields}, default=str),
          flush=True)


def route_template(app, scope):
    """'/farms/{farm_id}' instead of '/farms/farm7', so metrics don't get one series per id."""
    for route in app.router.routes:
        if route.matches(scope)[0] == Match.FULL:
            return route.path
    return "unmatched"


def instrument(app, service):
    """Count, time and (for writes and errors) log every request."""
    global SERVICE
    SERVICE = service

    @app.middleware("http")
    async def observe(request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            if request.url.path not in QUIET_PATHS:
                route = route_template(app, request.scope)
                elapsed = time.perf_counter() - start
                REQUESTS.labels(request.method, route, str(status)).inc()
                LATENCY.labels(request.method, route).observe(elapsed)
                if request.method != "GET" or status >= 400:
                    log("error" if status >= 500 else "info", "request", method=request.method,
                        path=request.url.path, status=status, ms=round(elapsed * 1000, 1))


def start_metrics_server():
    port = int(os.environ.get("METRICS_PORT", "8000"))
    if port:
        start_http_server(port)


def make_engine(default_sqlite):
    """
    SQLAlchemy engine for a registry service.

    GKE: SQL_INSTANCE_CONNECTION_NAME is set (from Secret "gcp-config"). The Cloud SQL connector
    opens a TLS tunnel authorised by IAM and logs in as the pod's Google service account
    (Workload Identity + IAM database authentication): no password exists anywhere.
    Elsewhere (laptop, tests): DATABASE_URL, default a SQLite file.
    """
    from sqlalchemy import create_engine, event

    instance = os.environ.get("SQL_INSTANCE_CONNECTION_NAME")
    if instance:
        from google.cloud.sql.connector import Connector, IPTypes

        connector = Connector()
        user, db = os.environ["DB_IAM_USER"], os.environ["DB_NAME"]

        def connect():
            return connector.connect(instance, "pg8000", user=user, db=db,
                                     enable_iam_auth=True, ip_type=IPTypes.PUBLIC)

        return create_engine("postgresql+pg8000://", creator=connect,
                             pool_size=5, max_overflow=2, pool_pre_ping=True, pool_recycle=1800)

    url = os.environ.get("DATABASE_URL", default_sqlite)
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def sqlite_foreign_keys(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")  # SQLite ignores foreign keys unless asked

    return engine


def retry(what, fn, attempts=10, delay=3):
    """Run fn until it works: on startup the database may still be coming up."""
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001  (any failure is worth a retry here)
            log("warning", f"{what} failed, retrying", attempt=i, error=str(e))
            if i == attempts:
                raise
            time.sleep(delay)
