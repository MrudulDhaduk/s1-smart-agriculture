# Person 1: concepts, what and why

Every concept in Person 1's part (Terraform, ArgoCD, storage, services), in plain words.
Each one has: **What** it is · **Why** we use it · **Q** questions the examiner may ask, with short answers.

Companions: `docs/p1-console-demo.md` (what to click) and `docs/p1-code-and-live-changes.md` (code + live changes).

---

## 1. Cloud basics

### GCP project
**What:** a container for all our cloud resources, billing and permissions. Ours: `s1-agri-ams-686974`.
**Why:** everything (cluster, database, buckets) is grouped, billed and secured together.
**Q: Why isn't the project created by Terraform?** Terraform needs an existing project (and a billing link) to run against. Creating it is a one-time manual step.

### Region and zone
**What:** a region is a geographic area (`us-central1`, Iowa); a zone is one data centre inside it (`us-central1-a`).
**Why:** everything sits in one zone so traffic between services stays fast and free.
**Q: Zonal vs regional?** Zonal = one copy of the control plane in one zone (cheaper, free tier). Regional = copies in 3 zones (survives a zone outage, costs more).

### Managed service
**What:** Google runs the servers, patching and backups; we just use it (Cloud SQL, Firestore, Pub/Sub, GKE control plane).
**Why:** a 3-person team on $50 can't run databases and Kafka by hand.

---

## 2. Infrastructure as Code: Terraform (task a)

### Infrastructure as Code (IaC)
**What:** describing cloud resources in code files instead of clicking in the console.
**Why:** repeatable (same result every time), reviewable (PRs), versioned (git history), and we can destroy and recreate the cluster every day.
**Q: What's the benefit over the console?** The console leaves no record and can't be repeated exactly. Code can be reviewed, rolled back, and rebuilt in another project.

### Terraform
**What:** a tool that reads `.tf` files (written in HCL) and makes the cloud match them.
**Why:** the most common IaC tool, supports GCP and Aiven with providers.
**Q: Declarative or imperative?** Declarative: you describe the end state ("a bucket with these settings"), Terraform works out the steps.

### Provider
**What:** a plugin that lets Terraform talk to one API. We use `google`, `aiven`, `helm`, `kubernetes`.

### Resource / data source
**What:** a *resource* is something Terraform creates and owns (`google_storage_bucket`). A *data source* only reads something that already exists (`aiven_service_plan_list`).

### `plan` and `apply`
**What:** `plan` shows what would change (`+` add, `~` change, `-` destroy, `-/+` replace). `apply` does it after you type `yes`.
**Why:** you see the effect before anything happens.
**Q: What's the danger?** A change that forces a **replace** deletes and recreates the resource (and its data). Always read the plan.

### State
**What:** Terraform's record of what it created and their real IDs (`terraform.tfstate`).
**Why:** without it Terraform can't know which bucket is "its" bucket, so it would try to create everything again.
**Q: Where is it?** In a private, **versioned** GCS bucket `<project>-tfstate`, one folder per stack. Versioned = we can restore an old state if it gets corrupted.
**Q: Why not on a laptop?** Then only that laptop could run Terraform, and a lost laptop = lost state.

### State lock
**What:** while one person runs `apply`, the state is locked so a second person can't run at the same time.
**Why:** two applies at once would corrupt the state.

### Backend
**What:** where state is stored. Ours is the `gcs` backend; the bucket name is passed at `terraform init`, so the same code works in another project.

### Stacks (our 6 folders)
**What:** separate Terraform folders, each with its own state: `bootstrap`, `foundation`, `kafka`, `serverless`, `cluster`, `platform`.
**Why:** split by **lifetime**. The expensive `cluster` stack is destroyed every evening; `foundation` (data) stays. A mistake in one stack can't destroy another (smaller blast radius).
**Q: How do stacks share values?** `terraform_remote_state` reads another stack's outputs, e.g. `cluster` reads the subnet and service accounts from `foundation`.

### Bootstrap (chicken and egg)
**What:** the state bucket must exist before any stack can store state in it. So `bootstrap` first runs with **local** state, creates the bucket, then **migrates** its own state into it.

### Variables, outputs, `.tfvars`
**What:** variables are inputs (`project_id`, `zone`); outputs are values a stack publishes (bucket names, the kubectl command); `terraform.tfvars` holds our values.
**Why `.tfvars` is git-ignored:** it can contain IDs or tokens (e.g. Aiven) that don't belong in Git.

### `up.sh` / `down.sh`
**What:** scripts to start and stop a work session: apply/destroy `cluster` + `platform`.
**Q: Why does `down.sh` delete namespaces first?** The Ingress and disks are created by GKE, not Terraform. Deleting the namespaces makes GKE remove the load balancer and disks; otherwise they'd keep costing money after the cluster is gone.

### What's not in Terraform
The project + billing link, Kubernetes workloads (that's ArgoCD's job), account sign-ups (Aiven, GitHub).

---

## 3. GitOps: ArgoCD (task d)

### GitOps
**What:** Git is the single source of truth for what runs in the cluster. A tool continuously makes the cluster match Git.
**Why:** every change is a reviewed commit (who, what, when), rollback = `git revert`, no one needs cluster admin access to deploy.
**Q: Difference from CI/CD pushing to the cluster?** Push-based CI runs `kubectl apply` from outside. GitOps is **pull-based**: an agent inside the cluster pulls from Git, so the cluster credentials never leave it.

### ArgoCD
**What:** the GitOps agent running in our cluster. It polls Git every **60 s**, compares with the cluster, and applies the difference.
**Q: How is ArgoCD itself installed?** By Terraform (`platform` stack, Helm chart). Terraform installs ArgoCD; ArgoCD installs everything else.

### Application
**What:** one ArgoCD object = "deploy this Git path (or Helm chart) into this namespace". We have 4: **`s1`** (`k8s/gke`), **`external-secrets`**, **`monitoring`** (Prometheus + Grafana), **`observability`** (ServiceMonitors + dashboard).

### Synced / OutOfSync, Healthy / Degraded
**What:** *Synced* = cluster matches Git. *OutOfSync* = they differ. *Healthy* = the objects are actually running fine (pods ready).
**Q: Can it be Synced but not Healthy?** Yes: the manifest was applied, but e.g. the pod keeps crashing.

### Automated sync, prune, self-heal
**What:** *automated* = sync without a button. *prune* = deleted from Git → deleted from the cluster. *self-heal* = changed by hand in the cluster → put back to Git.
**Why:** Git always wins, so manual drift can't survive.

### ignoreDifferences on `/spec/replicas`
**What:** the `s1` app ignores the replica count of Deployments.
**Why:** the HPA changes replicas. Without this, self-heal would reset every scale-out back to the number in Git.
**Q: Side effect?** Changing only `replicas` in Git won't be rolled out; manual `kubectl scale` isn't reverted either.

### Kustomize, base and overlays
**What:** Kustomize builds manifests from a **base** plus **overlays** that patch it. `k8s/base` = the app anywhere; `k8s/local` = laptop; `k8s/gke` = our project (images, Workload Identity, secrets, Ingress).
**Why:** one copy of the app, small per-environment differences, no copy-paste.

### Helm
**What:** a package manager for Kubernetes; a *chart* is a reusable package (ArgoCD, kube-prometheus-stack, External Secrets).
**Q: Why are the ArgoCD Applications created via the `argocd-apps` chart?** Terraform can't plan Application objects before ArgoCD's CRDs exist; a Helm chart is applied later, so it works on the first run.

### CRD (Custom Resource Definition)
**What:** adds a new kind of object to Kubernetes, e.g. `Application` (ArgoCD), `ExternalSecret`, `ServiceMonitor`.

### Image tags = git commit
**What:** images are tagged with the commit hash (`farm-registry:2877b49b0f`), never `latest`.
**Why:** Git says exactly which code is running; a new version only arrives through a Git change; rollback is exact.
**Q: What's wrong with `latest`?** It points at whatever was pushed last, so two pods can run different code under the same name, and you can't roll back to "the previous latest".

### Deployment flow
`tools/build_push.sh` (build + push + update tag) → PR changing `k8s/gke/kustomization.yaml` → approval → merge → ArgoCD applies.

### Pull request + approval
**What:** team rule: nobody pushes to `main`; a PR needs 1 approval. Since ArgoCD deploys `main`, a merge **is** a deployment, so review = deployment approval.

---

## 4. Kubernetes bits Person 1 uses

### GKE Standard (vs Autopilot)
**What:** Standard = we choose and pay for the node VMs; Autopilot = Google manages nodes and bills per pod.
**Why Standard:** we size the nodes ourselves, and the free tier covers the management fee of one zonal cluster.

### Node pool and cluster autoscaler
**What:** a group of identical VMs (`main`, `e2-standard-2`). The cluster autoscaler adds VMs (2 → 4) when pods don't fit.

### Deployment
**What:** runs N identical, stateless pods and replaces them on updates. All three Person 1 services are Deployments.
**Q: How does an update avoid downtime?** Rolling update: new pod starts and becomes ready, then an old one stops. Farm/Sensor Registry run 2 replicas so one is always up.

### Readiness and liveness probes
**What:** *readiness* (`/healthz`) = "send me traffic?" (includes a database check). *liveness* (`/livez`) = "am I alive, or should Kubernetes restart me?".
**Q: Why different?** If the DB is briefly down, the pod should stop getting traffic (not ready) but not be killed (still alive).

### Service
**What:** a stable name and IP in front of a set of pods (`http://farm-registry`).

### Ingress
**What:** HTTP routing from outside into Services. On GKE one Ingress = one **Google external HTTP load balancer** with one public IP. Ours, `s1-public`, has 7 paths.
**Q: Why one Ingress, not one LoadBalancer per service?** One IP and one load balancer instead of five, so it's cheaper and there's one URL for everything.

### Namespace
**What:** a folder inside the cluster: `s1` (app), `argocd`, `monitoring`, `external-secrets`.

### Kubernetes Secret
**What:** a Kubernetes object holding sensitive values, given to pods as env vars. Ours (`gcp-config`, `kafka-client`) are **created by External Secrets**, never written in Git.

---

## 5. The three storage products (task g)

### Why three different ones?
Each kind of data goes where it fits: **relational → Cloud SQL**, **small shared documents → Firestore**, **files → Cloud Storage**. (Sensor readings are in Person 3's Sensor Store ring, not in these.)

### Cloud SQL (PostgreSQL) — relational
**What:** managed Postgres. Ours: `db-f1-micro`, HDD, zonal, no backups; databases `farm_registry`, `sensor_registry`.
**Why:** farms → plots → crops have **relations**: a plot must belong to a real farm and grow a known crop. Foreign keys enforce that; SQL gives joins and transactions.
**Q: Why one database per service?** Each microservice owns its data; others go through its API (Sensor Registry asks Farm Registry over REST if a plot exists).
**Q: Why no backups?** Demo data only, to save cost. In production you'd turn them on.

### Firestore (Native mode) — NoSQL documents
**What:** serverless document database (collections → documents → fields). No server, no schema.
**Why:** small documents read and written by many stateless pods: ring membership, watering cooldown (`irrigation_state`), alerts, analytics summaries. It has **transactions**.
**Q: Why Firestore for the cooldown and not SQL?** It's a tiny key → timestamp record with a transaction ("claim this plot if not watered in 10 min"). No schema, no connection pool, scales to zero cost.

### Cloud Storage (GCS) — objects
**What:** stores files (objects) in buckets. Cheap and durable.
**Why:** alert archive (`…-s1-archive`, deleted after **30 days**), Flink jar and function source (`…-s1-artifacts`), Dataproc staging/temp, Terraform state.
**Q: What is a lifecycle rule?** An automatic policy on a bucket, e.g. "delete objects older than 30 days", so old data never piles up cost.
**Q: Uniform bucket-level access?** Permissions are set on the whole bucket via IAM, not per object. Simpler and safer.

### SQL vs NoSQL in one line
SQL: fixed tables, relations, joins, strong consistency. NoSQL (Firestore): flexible documents, simple key lookups, scales without managing servers.

---

## 6. Networking

### VPC and subnet
**What:** a private network (`s1-vpc`) with a subnet `10.10.0.0/20` for nodes, plus secondary ranges for pods (`10.20.0.0/16`) and Services (`10.30.0.0/20`).
**Why our own VPC:** the network is defined in code, not the default network with its open rules.

### VPC-native cluster
**What:** pods get real IPs from the VPC (the secondary ranges), so they're reachable without extra routing.

### Firewall
**What:** `s1-allow-internal` lets our own VMs talk to each other. A custom VPC starts with no rules, so everything else is blocked.

### Cloud NAT (and why we don't use it)
**What:** lets VMs without public IPs reach the internet.
**Why not:** it charges per hour. Our nodes have public IPs instead (firewalled), so they can reach Aiven and pull images.
**Q: Trade-off?** Nodes have public IPs. Only what GKE needs is opened.

### Dataplane V2 and NetworkPolicy
**What:** a NetworkPolicy says which pods may talk to which ("only Partition Manager may call Sensor Store"). Dataplane V2 (eBPF) is what **enforces** it on GKE.
**Q: Without it?** GKE accepts NetworkPolicies but silently ignores them.

---

## 7. Security and identity

### IAM
**What:** who can do what on which resource (`member + role + resource`).
**Least privilege:** each workload gets only the roles it needs; teammates get `viewer`, `container.developer`, `dataproc.editor`, not `editor`/`owner`.

### Service account (GSA)
**What:** an identity for a program, not a person. One per workload: `s1-farm-registry`, `s1-irrigation-controller`, …
**Why one each:** if one is compromised, it can only do its own small job.

### Workload Identity
**What:** lets a Kubernetes service account (`s1/farm-registry`) act as a Google service account (`s1-farm-registry`) without any key file. Annotation on the KSA + an IAM binding made by Terraform.
**Q: Why not a JSON key?** Keys can leak (Git, laptops) and never expire. With Workload Identity no key exists.

### IAM database authentication
**What:** Farm/Sensor Registry log into Cloud SQL **as their service account**, using a short-lived token, through the Cloud SQL connector. No password exists.
**Q: The instance has a public IP, isn't that unsafe?** There are no authorised networks, so only IAM-authorised connector clients can connect.

### Secret Manager → External Secrets → Kubernetes Secret
**What:** Terraform writes secrets to **Secret Manager**; the **External Secrets Operator** copies them into Kubernetes Secrets; pods read them as env vars. Git only says *which* secret goes *where*.
**Q: How do you rotate a secret?** Add a new version in Secret Manager; External Secrets picks it up.

### Internal-only function
**What:** the Alert Cloud Run function accepts traffic only from Eventarc (Pub/Sub), not from the internet.

---

## 8. Messaging and the other managed pieces

### Pub/Sub
**What:** Google's managed message queue: publishers send to a **topic**, subscribers get every message.
**Why:** Irrigation Controller publishes `DRY_SOIL` / `SENSOR_SILENT` alerts to topic `alerts`; the Alert function is triggered by it. The controller doesn't wait for or know about the function (loose coupling).

### Eventarc
**What:** the GCP service that delivers events (here Pub/Sub messages) to Cloud Run functions.

### Cloud Run function (2nd gen)
**What:** serverless code that runs per event and scales to zero. Ours: `alert-service` (Person 2's code, Person 1's Terraform).
**Why:** alerts are rare; no point paying for an always-on server.

### Kafka (Aiven)
**What:** a distributed log of messages in topics (`readings`, `results`, `irrigation`).
**Why Aiven:** managed and free. The free plan exists only on DigitalOcean clouds; `do-nyc` is nearest to Iowa. Connection is TLS with client certificates (mutual TLS).
**Q: Pub/Sub vs Kafka here?** Kafka is the stream Flink processes (ordered, replayable). Pub/Sub is for one-off alerts that trigger a function.
**Gotcha:** the free plan powers off after 24 h idle; power it on before the demo.

### Dataproc
**What:** managed Hadoop/Spark/Flink clusters. Ours: `s1-flink`, single node, Flink 1.17, deletes itself after 2 h idle.
**Q: Why `internal_ip_only = false`?** Dataproc 2.2 defaults to internal IPs only; without NAT, Flink couldn't reach Aiven Kafka.

### Artifact Registry
**What:** private Docker image registry next to the cluster (`s1`). Cleanup policy keeps the newest 5 versions per image.

---

## 9. Person 1's services

### REST
**What:** HTTP API with resources and verbs: `GET /farms`, `POST /farms`, `GET /plots/{id}`. JSON in and out. Status codes: 201 created, 404 not found, 409 already exists, 422 invalid input.
**Why for registries:** simple CRUD, easy to call from anywhere (curl, browser, other services).

### Farm Registry
Farms, plots, crops. A **crop** defines the moisture band (min, target) and root depth.

### Sensor Registry
Sensors and their status (`active`, `inactive`, `faulty`). Calls Farm Registry to check the plot exists.

### Irrigation Controller
**What:** every 30 s: plots → active sensors → latest readings (gRPC to Partition Manager) → average the fresh ones (≤ 5 min old) → below the crop's minimum = water.
**Water formula:** `area_m2 × (target − moisture) × root_depth_cm ÷ 10` litres (1% of 1 m² × 1 cm of soil = 0.1 L).
**Outputs:** watering event → Kafka `irrigation`; alert → Pub/Sub `alerts`; cooldown → Firestore.
**Q: Why gRPC to Partition Manager but REST to the registries?** Partition Manager is gRPC (fast, typed contract, Person 3's choice); registries are public REST APIs.

### Cooldown and idempotency
**What:** a plot is watered at most once per 10 minutes. The "claim" is a **Firestore transaction**, so a second replica or a restart can't water the same plot twice.
**Idempotent** = doing it twice has the same effect as once.

### Communication styles (assignment requirement)
| Style | Where |
|---|---|
| REST (sync) | users → registries; Sensor Registry → Farm Registry; controller → registries |
| gRPC (sync) | controller → Partition Manager |
| Queues (async) | controller → Kafka `irrigation`; controller → Pub/Sub `alerts` |

### Observability of these services
JSON logs (one object per line: `service`, `level`, `message`, `plot_id`) → Cloud Logging. Metrics on `:8000/metrics`, but not scraped by our Prometheus.

---

## 10. Cost ($50 credit)

| Choice | Saves | Gives up |
|---|---|---|
| Zonal cluster | management fee (free tier) | control plane in one zone |
| Public nodes, no NAT | NAT hourly + data | nodes have public IPs |
| Single-node Dataproc, 2 h idle delete | 2 worker VMs; forgotten clusters | no Flink fault tolerance |
| Aiven free tier | all Kafka cost | 250 KiB/s, 5 topics, sleeps after 24 h |
| `db-f1-micro`, HDD, no backups | most of Cloud SQL's cost | demo data only |
| Destroy cluster after each session | ~90% of the hourly cost | ~15 min to start |
| Budget alerts | — | they warn, they don't stop spending |

**Q: Do budget alerts stop spending?** No, they only send emails at 30/60/80%. You must still tear down.

---

## 11. The 10 most likely "why" questions

| Why… | Answer |
|---|---|
| Terraform at all? | Repeatable, reviewed, versioned infrastructure; rebuild the cluster daily. |
| Six stacks? | Different lifetimes; destroy the expensive part, keep the data; smaller blast radius. |
| State in a bucket? | Shared, locked, versioned; not tied to one laptop. |
| GitOps / ArgoCD? | Git = truth; every deploy is a reviewed commit; drift reverted; rollback = revert. |
| Commit-hash tags? | Git says exactly what runs; exact rollback; no "latest" confusion. |
| Three storage products? | Relational → SQL, small shared docs + transactions → Firestore, files → GCS. |
| Workload Identity? | No key files to leak. |
| External Secrets? | No secret values in Git; one place (Secret Manager) to rotate. |
| No Cloud NAT? | Hourly cost; public firewalled nodes instead. |
| Zonal GKE Standard? | Free management fee, we size the nodes, fits $50. |
