# S1 · Smart Agriculture: sensor-based irrigation across multiple farms

CS/SS G527 Cloud Computing group assignment (BITS Pilani, I Sem 2025-26).
**Required concept:** data partitioning using consistent hashing.
**Cloud:** Google Cloud Platform (GKE, Dataproc, Cloud SQL, Firestore, Cloud Storage, Cloud Functions, Pub/Sub).

## Team and ownership

| | Person 1: Infrastructure & Storage | Person 2: Events & Streaming | Person 3: Concept, Scaling & Monitoring |
|---|---|---|---|
| **Name** | Saravanasudharsan S | Pranav Harresh Vishwanathan | Dhaduk Mrudul |
| **Tasks** | (a) Terraform · (d) ArgoCD GitOps · (g) 3 storage products | (b) Serverless + REST/gRPC/queues · (e) Kafka + Flink | (f) Consistent hashing · (c) GKE + HPA + k6 · (h) Prometheus, Grafana, logging |
| **Services** | Farm Registry · Sensor Registry · Irrigation Controller | Telemetry Ingestion · Alert Service · Farm Analytics | Partition Manager · Sensor Store |
| **Folders** | `infra/` · `services/farm-registry/` · `services/sensor-registry/` · `services/irrigation-controller/` | `services/telemetry-ingestion/` · `services/alert-function/` · `services/farm-analytics/` · `services/flink-job/` | `services/partition-manager/` · `services/sensor-store/` · `observability/` · `loadtest/` |

Shared by everyone: `contracts/`, `k8s/` (each person adds their own services' manifests), `docs/`.

## How the services connect

```
Readings path
  Sensors / simulator ──REST POST /readings──► Telemetry Ingestion (P2)
  Telemetry Ingestion ──gRPC WriteReading────► Partition Manager (P3) ──gRPC──► 3 of 4 Sensor Store nodes (P3)
                                               (consistent-hash ring, membership in Firestore)
  Telemetry Ingestion ──Kafka "readings"─────► Flink job (P2, Dataproc, 1-min window per farm)

Irrigation path
  Irrigation Controller (P1) ──REST──────────► Farm Registry / Sensor Registry (P1, Cloud SQL)
  Irrigation Controller      ──gRPC GetLatest► Partition Manager (P3)
  Irrigation Controller      ──Kafka "irrigation"──► Flink job
  Irrigation Controller      ──Pub/Sub "alerts"───► Alert Service (P2, Cloud Run function) ──► Firestore + GCS archive

Results path
  Flink job ──Kafka "results"──► Farm Analytics (P2) ──► Firestore, served at GET /analytics/farms/{id}

Public URL: one GKE Ingress (/farms /plots /crops /sensors /irrigation /readings /analytics)
Everything: Terraform + ArgoCD (P1) · HPA, k6 load test, Grafana and Cloud Logging (P3)
```

## Repo layout

```
contracts/       shared: .proto files, Kafka JSON schemas, REST specs (change only if all 3 agree)
infra/           P1  Terraform for all GCP resources
services/        one folder per service (see the ownership table)
k8s/             Kubernetes manifests; ArgoCD deploys whatever is on main
observability/   P3  Grafana dashboards, alert rules, logging config
loadtest/        P3  k6 scripts
docs/            design document (each person writes their own section)
task_divison.txt required deliverable (ID numbers, names, tasks)
```

## Working rules

1. **Contracts first.** Agree on `contracts/` before building against each other.
2. **Stay in your own folders.** Touching someone else's folder means asking them first.
3. **Never push to `main`.** Create a branch, open a pull request, and get 1 approval. ArgoCD deploys from `main`.
4. **Develop locally first** with docker-compose. Use the cloud only for integration, to save credits.
5. **Tear down cloud resources whenever you stop working** (`infra/scripts/down.sh`). The whole project runs on one $50 credit.
6. **Never commit secrets** (keys, `.json` service-account files, `.env`). `.gitignore` blocks the common ones.

### Everyday git workflow

```bash
git checkout main && git pull                 # start from the latest main
git checkout -b p3/consistent-hash-ring       # a branch named <person>/<what>
# ...edit files...
git add . && git commit -m "Add hash ring with virtual nodes"
git push -u origin p3/consistent-hash-ring    # then open a pull request on GitHub
```
