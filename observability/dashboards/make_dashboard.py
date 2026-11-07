"""
make_dashboard.py - builds the S1 Grafana dashboard (s1-dashboard.yaml) from the panel list below.

    python observability/dashboards/make_dashboard.py

Every panel = a title + a PromQL query (the language Prometheus uses to ask for numbers).
The output is a ConfigMap; Grafana's sidecar loads any ConfigMap labelled grafana_dashboard="1".

PromQL used below, in one line each:
    rate(x[1m])            per-second speed of a counter over the last minute
    sum by (label) (...)   add up, keeping one line per label value
    histogram_quantile     turn latency buckets into p50 / p95 / p99
    (...) or vector(0)     show 0 instead of "No data" when nothing has failed yet
"""

import json
import os

DS = {"type": "prometheus", "uid": "${datasource}"}

# (row title, [(panel type, title, unit, width, [(query, legend), ...]), ...])
ROWS = [
    ("Traffic: the golden signals", [
        ("timeseries", "Requests per second (Partition Manager)", "reqps", 8, [
            ('sum by (method) (rate(pm_requests_total[1m]))', "{{method}}"),
        ]),
        ("timeseries", "Error rate %", "percent", 8, [
            ('100 * (sum(rate(pm_requests_total{status="error"}[1m])) or vector(0)) / clamp_min(sum(rate(pm_requests_total[1m])), 1e-9)',
             "failed requests %"),
            ('100 * (sum(rate(pm_replica_writes_total{result="failed"}[1m])) or vector(0)) / clamp_min(sum(rate(pm_replica_writes_total[1m])), 1e-9)',
             "failed replica writes %"),
        ]),
        ("timeseries", "WriteReading latency", "s", 8, [
            (f'histogram_quantile({q}, sum by (le) (rate(pm_request_latency_seconds_bucket{{method="WriteReading"}}[1m])))',
             f"p{int(q * 100)}") for q in (0.5, 0.95, 0.99)
        ]),
    ]),
    ("Scaling: HPA on Partition Manager", [
        ("timeseries", "Partition Manager pods (HPA)", "short", 12, [
            ('max(kube_horizontalpodautoscaler_status_current_replicas{namespace="s1", horizontalpodautoscaler="partition-manager"})', "current pods"),
            ('max(kube_horizontalpodautoscaler_status_desired_replicas{namespace="s1", horizontalpodautoscaler="partition-manager"})', "desired pods"),
            ('max(kube_horizontalpodautoscaler_spec_max_replicas{namespace="s1", horizontalpodautoscaler="partition-manager"})', "max allowed"),
        ]),
        ("timeseries", "CPU per Partition Manager pod (millicores; HPA target = 50m)", "short", 12, [
            ('1000 * sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="s1", container="partition-manager"}[1m]))', "{{pod}}"),
        ]),
    ]),
    ("Partitioning: the consistent hashing ring", [
        ("bargauge", "Sensors stored per ring node (keys per node)", "short", 8, [
            ('max by (node) (ss_sensors_stored)', "{{node}}"),
        ]),
        ("timeseries", "Writes per second per ring node", "reqps", 8, [
            ('sum by (node) (rate(pm_replica_writes_total{result="ok"}[1m]))', "{{node}}"),
        ]),
        ("stat", "Ring", "short", 8, [
            ('max(pm_ring_version)', "ring version"),
            ('max(pm_ring_nodes)', "ring nodes"),
            ('sum(pm_rebalance_events_total)', "rebalance events"),
            ('sum(pm_rebalance_sensors_moved_total)', "sensors moved"),
        ]),
    ]),
    ("Cluster health", [
        ("stat", "App pods (namespace s1)", "short", 8, [
            ('sum(kube_pod_status_phase{namespace="s1", phase="Running"})', "running"),
            ('sum(kube_pod_status_ready{namespace="s1", condition="false"})', "not ready"),
            ('sum(increase(kube_pod_container_status_restarts_total{namespace="s1"}[15m]))', "restarts (15 min)"),
        ]),
        ("timeseries", "Machine CPU %", "percent", 8, [
            ('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])))', "CPU used %"),
        ]),
        ("timeseries", "Machine memory %", "percent", 8, [
            ('100 * (1 - sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes))', "memory used %"),
        ]),
    ]),
]


def panel(pid, kind, title, unit, width, x, y, queries):
    p = {
        "id": pid, "type": kind, "title": title, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": width, "h": 8},
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "targets": [{"refId": chr(65 + i), "datasource": DS, "expr": q, "legendFormat": legend}
                    for i, (q, legend) in enumerate(queries)],
    }
    if kind == "stat":
        p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"]}, "textMode": "value_and_name"}
    if kind == "bargauge":
        p["options"] = {"orientation": "horizontal", "displayMode": "gradient",
                        "reduceOptions": {"calcs": ["lastNotNull"]}}
    return p


def build():
    panels, pid, y = [], 1, 0
    for row_title, row_panels in ROWS:
        panels.append({"id": pid, "type": "row", "title": row_title, "collapsed": False,
                       "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []})
        pid, y, x = pid + 1, y + 1, 0
        for kind, title, unit, width, queries in row_panels:
            panels.append(panel(pid, kind, title, unit, width, x, y, queries))
            pid, x = pid + 1, x + width
        y += 8
    return {
        "uid": "s1-smart-agriculture", "title": "S1 Smart Agriculture: partitioning and scaling",
        "tags": ["s1"], "timezone": "browser", "refresh": "10s", "schemaVersion": 39,
        "time": {"from": "now-30m", "to": "now"},
        "templating": {"list": [{"name": "datasource", "type": "datasource", "query": "prometheus",
                                 "label": "Data source", "current": {}}]},
        "panels": panels,
    }


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    dashboard = json.dumps(build(), indent=2)
    with open(os.path.join(here, "s1-dashboard.yaml"), "w") as f:
        f.write("# Generated by make_dashboard.py - edit that file, not this one.\n"
                "# kubectl apply -f observability/dashboards/s1-dashboard.yaml\n"
                "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: s1-dashboard\n  namespace: monitoring\n"
                "  labels:\n    grafana_dashboard: \"1\"\ndata:\n  s1-dashboard.json: |\n")
        for line in dashboard.splitlines():
            f.write("    " + line + "\n")
    print("wrote s1-dashboard.yaml")
