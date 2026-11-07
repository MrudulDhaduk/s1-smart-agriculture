# Person 3: design decisions

Decided 7 Nov 2026. Each decision has a one-line reason (the viva answer).

| # | Question | Decision | Why (viva line) |
|---|---|---|---|
| 1 | Is Partition Manager a router or a lookup service? | **Router.** Callers send `Write`/`Read` to Partition Manager, which forwards to the right Sensor Store nodes. | Partitioning logic lives in one service, so callers never need to know the ring. The extra hop is cheap because the router is stateless and scales with HPA. |
| 2 | Where does ring membership live? | **One Firestore document** `{version, nodes}`. Every Partition Manager copy re-reads it every 5 s. `AddNode`/`RemoveNode` update it. | Partition Manager is stateless (HPA adds and removes copies at any time), so shared state must live outside it. Known limitation: copies can disagree for up to 5 s after a change. |
| 3 | What is a Sensor Store "node"? | **One pod of a StatefulSet** (`sensor-store-0..3`), each with its own persistent disk, storing readings in SQLite. | Partitions are physically separate disks, not one shared database. A stable pod name gives a stable identity on the ring. |
| 4 | Which 2 services get HPAs? | **Telemetry Ingestion + Partition Manager.** Not Sensor Store. | HPA suits stateless, interchangeable services (Scalability lecture, slide 18). Sensor Store is stateful: it scales by adding a ring node and rebalancing ~1/N of the data, never by HPA (scale-down would delete a partition). |
| 5 | Loki or Cloud Logging? | **Cloud Logging**, shown in Grafana via its Cloud Logging data source. | Flink (Dataproc) and Alert Service (Cloud Function) run outside GKE. Cloud Logging collects all three runtimes natively; Loki would need custom shipping. |

## Read and write rules (follow from decision 1)

- **Write:** send to all 3 replica nodes; succeed when at least 2 confirm (majority).
- **Read:** ask the primary node; if it is down, try the next replica.

## What teammates need to do

**Person 1**
- Irrigation Controller reads readings through **Partition Manager**, not Sensor Store directly.
- Dataproc cluster (Terraform) must set, at creation time:
  `dataproc:dataproc.logging.stackdriver.job.driver.enable=true` and
  `dataproc:dataproc.logging.stackdriver.job.yarn.container.enable=true` (both default to false).
- Create the Firestore database (ring membership lives in it).
- Give the Kubernetes service account `s1/partition-manager` read/write access to Firestore (Workload Identity, role `roles/datastore.user`).
- Push our images to Artifact Registry; `k8s/base` currently uses the local names `s1/partition-manager` and `s1/sensor-store`.

**Person 2**
- Telemetry Ingestion's Deployment must set `resources.requests.cpu` (HPA measures CPU % relative to it).
- Telemetry Ingestion calls Partition Manager `WriteReading` over gRPC, with `sensor_id` and `timestamp_ms` always set (both are required).

**Everyone**
- Log one JSON object per line to stdout, with at least: `service`, `level`, `message`, and `sensor_id` / `node` where relevant.
