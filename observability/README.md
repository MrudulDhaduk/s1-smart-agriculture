# observability/ (Person 3)

Task (h): metrics with Prometheus, dashboards with Grafana, centralised logs.

| File | What it does |
|---|---|
| `kube-prometheus-stack-values.yaml` | Settings for the Prometheus + Grafana Helm chart |
| `servicemonitors.yaml` | Tells Prometheus to scrape Partition Manager and every Sensor Store node |
| `dashboards/make_dashboard.py` | The S1 dashboard: every panel and its PromQL query, in one readable list |
| `dashboards/s1-dashboard.yaml` | Generated from the script; Grafana loads it automatically |

## Install on the laptop (Docker Desktop Kubernetes)

```powershell
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install monitoring prometheus-community/kube-prometheus-stack --version 92.14.1 -n monitoring --create-namespace -f observability/kube-prometheus-stack-values.yaml
kubectl apply -f observability/servicemonitors.yaml
kubectl apply -f observability/dashboards/s1-dashboard.yaml
```

- Grafana: http://localhost:3000 (admin / admin). Dashboard: "S1 Smart Agriculture: partitioning and scaling"
- Prometheus: http://localhost:9090 (Status → Targets shows what is being scraped)

## Dashboard rows

1. **Traffic:** requests per second, error rate %, WriteReading latency p50/p95/p99
2. **Scaling:** Partition Manager pods (current / desired / max) and CPU per pod vs the HPA target
3. **Partitioning:** sensors per ring node, writes per ring node, ring version, rebalance events, sensors moved
4. **Cluster health:** app pods running / not ready / restarts, machine CPU and memory

## Logs

All services log one JSON object per line to stdout. On GKE, Cloud Logging collects them
(GKE pods, the Dataproc Flink job and the Cloud Function), see `docs/p3-design-decisions.md`.
