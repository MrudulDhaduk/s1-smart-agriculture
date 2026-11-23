# Person 1: GCP Console demo (practice sheet)

Person 1 = **Saravanasudharsan S**. Tasks: **(a) Terraform**, **(d) GitOps with ArgoCD**, **(g) three cloud storage products**.
Services: **Farm Registry**, **Sensor Registry**, **Irrigation Controller**.
Project: **S1 Smart Agriculture** (`s1-agri-ams-686974`), region `us-central1`, zone `us-central1-a`.

Everything is clicked in the console. The only typing is in **Cloud Shell** (the `>_` icon at the top right, part of the console): ArgoCD has no page in the GCP console, and a curl to the public URL is the quickest way to show the services answering.

✅ = this exact page was seen on the live console on 22 Nov (during the Person 3 walkthrough).
⏳ = written from the Terraform code and the design document, not yet clicked live. Walk it once with the cluster up and fix any button names that differ.

---

## Opening line (learn by heart)

> "I'm Person 1. I built the **infrastructure as code with Terraform**: every cloud resource in this project is created by code. I set up **GitOps with ArgoCD**, so every Kubernetes deployment comes from Git. And I chose the **three storage products**: Cloud SQL, Firestore and Cloud Storage. My services are **Farm Registry**, **Sensor Registry** and **Irrigation Controller**."

---

## The 10-minute run order (practise exactly this)

| # | Min | Console page | Point at | Key line |
|---|---|---|---|---|
| 0 | 0:30 | — | — | Opening line |
| 1 | 1 | **Cloud Storage → Buckets** → `…-tfstate` | one folder per Terraform stack, versioning | "Terraform state, split by lifetime" |
| 2 | 1 | Kubernetes Engine → **Clusters** → `s1-gke` | zonal, node pool 2–4, Dataplane V2, Workload Identity | "Created by Terraform, destroyed every evening" |
| 3 | 2 | **Cloud Shell** → ArgoCD UI (Web Preview 8080) | 4 Applications Synced + Healthy | "Git is the truth, nobody runs kubectl apply" |
| 4 | 1 | **Workloads**, namespace `s1` | farm-registry 2/2, sensor-registry 2/2, irrigation-controller 1/1 | "My three services, deployed by ArgoCD" |
| 5 | 1 | **Gateways, Services & Ingress** → `s1-public` | one public IP, 7 paths | "One public URL for every REST service" |
| 6 | 1 | **SQL** → `s1-sql-…` → Databases, Users | 2 databases, IAM users, no passwords | "Storage 1: relational data" |
| 7 | 1 | **Firestore** → `irrigation_state` | one cooldown doc per watered plot | "Storage 2: small docs, transactions" |
| 8 | 0:30 | **Cloud Storage** → `…-s1-archive`, `…-s1-artifacts` | lifecycle 30 days | "Storage 3: cheap blobs" |
| 9 | 1 | **Secret Manager** + **IAM → Service accounts** | secrets, one GSA per workload | "No secrets in Git, no key files" |
| 10 | 1 | **Artifact Registry** → `s1` | images tagged with the git commit | "Rollback = git revert" |

**After the demo:** run `infra/scripts/down.sh` (only Person 1, or whoever started the session).

---

## Step 1. Terraform state ⏳

**Clicks:** ☰ → **Cloud Storage** → **Buckets** → click **`s1-agri-ams-686974-tfstate`** → folder **`s1/`**.
- One folder per **stack**: `bootstrap`, `foundation`, `kafka`, `serverless`, `cluster`, `platform`. Each holds a `default.tfstate`.
- **Configuration** tab (or bucket details): **Object versioning: On**, public access: **Not public**.

| Stack | Creates | Lifetime |
|---|---|---|
| `bootstrap` | APIs, this state bucket, budget alerts | once per project |
| `foundation` | VPC, Artifact Registry, Firestore, Cloud SQL, buckets, Pub/Sub, service accounts, Secret Manager | whole project |
| `kafka` | Aiven Kafka (free plan), topics, user | whole project |
| `serverless` | Alert function (Cloud Run function) | whole project |
| `cluster` | GKE, Dataproc, Workload Identity bindings | **only while working** |
| `platform` | ArgoCD and its 4 Applications | with the cluster |

🗣 *"All the infrastructure is Terraform. It's split into six stacks by lifetime, each with its own state in this private, versioned bucket. That way I can destroy the expensive part, the cluster, every evening without touching the data in Cloud SQL and Firestore."*

**Why versioning?** If a state file gets corrupted or overwritten, we can restore an older version.

---

## Step 2. The cluster Terraform made ✅ (Details tab ⏳)

**Clicks:** ☰ → **Kubernetes Engine** → **Clusters** → click **`s1-gke`**.
- **Details** tab: Location **`us-central1-a`** (zonal). Scroll to **Networking**: **Dataplane V2: Enabled**. Scroll to **Security**: **Workload Identity: Enabled**.
- **Nodes** tab: node pool **`main`**, `e2-standard-2`, autoscaling **2–4** nodes.

🗣 *"Terraform creates this cluster in our own VPC, `s1-vpc`. It's zonal because the free tier covers the management fee of one zonal cluster. Dataplane V2 is on so NetworkPolicies are enforced, and Workload Identity is on so pods get Google credentials without any key files. Up and down takes about 15 minutes with `up.sh` and `down.sh`."*

If the list is empty: the cluster is destroyed after every session to save credit. That's by design (~90% of the hourly cost).

---

## Step 3. ArgoCD (GitOps) ⏳

ArgoCD runs inside the cluster, so it has no GCP console page. Open **Cloud Shell** (`>_`) and paste:

```bash
gcloud container clusters get-credentials s1-gke --zone us-central1-a --project s1-agri-ams-686974
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
kubectl -n argocd port-forward svc/argocd-server 8080:80
```

Copy the password it prints. Then click **Web Preview** (eye icon at the top of Cloud Shell) → **Preview on port 8080**. Log in as **`admin`** with that password.

**Point at:** four tiles, all **Synced** (green) and **Healthy** (green heart):
| Application | Deploys | From |
|---|---|---|
| **s1** | all 7 services in namespace `s1` | Git folder `k8s/gke` |
| **external-secrets** | External Secrets Operator | Helm chart |
| **monitoring** | Prometheus + Grafana | Helm chart + Person 3's values file |
| **observability** | ServiceMonitors + dashboard | Git folder `observability` |

Click the **s1** tile: the tree shows Deployments → ReplicaSets → Pods for every service.

🗣 *"Terraform installs ArgoCD and tells it which Git folders to follow. ArgoCD checks the main branch every 60 seconds and applies whatever is there. Nobody runs kubectl apply: a deployment is a merged pull request. Self-heal is on, so if someone changes the cluster by hand, ArgoCD reverts it."*

**Likely question: "Doesn't self-heal fight the HPA?"** *"It would, so the s1 Application ignores `spec.replicas` on Deployments. The HPA owns the replica count."*

Press **Ctrl+C** in Cloud Shell when done.

---

## Step 4. My three services ✅

**Clicks:** **Workloads** → **Namespace** dropdown → **`s1`**.

| Row | Type | Pods | Job |
|---|---|---|---|
| **farm-registry** | Deployment | 2/2 | farms, plots, crops (Cloud SQL) |
| **sensor-registry** | Deployment | 2/2 | sensors and their status (Cloud SQL) |
| **irrigation-controller** | Deployment | 1/1 | every 30 s decides which plots to water |

Click **farm-registry** → **Details** → **Annotations**: `argocd.argoproj.io/tracking-id`. That proves ArgoCD deployed it.

🗣 *"These are my three services, all stateless Deployments, deployed by ArgoCD. Farm Registry and Sensor Registry store their data in Cloud SQL. Irrigation Controller runs every 30 seconds: it reads the latest readings through Person 3's Partition Manager, waters plots that are below their crop's minimum moisture, sends the watering event to Kafka and a DRY_SOIL alert to Pub/Sub."*

**Irrigation rule (if asked):** water = `area_m2 × (target − moisture) × root_depth_cm ÷ 10` litres. At most once per **10 minutes** per plot.

---

## Step 5. The public URL ⏳

**Clicks:** Kubernetes Engine → **Gateways, Services & Ingress** → **Ingress** tab → **`s1-public`**.
- One **external IP address** (the load balancer).
- **7 paths**: `/farms`, `/plots`, `/crops` → farm-registry · `/sensors` → sensor-registry · `/irrigation` → irrigation-controller · `/readings` → telemetry-ingestion · `/analytics` → farm-analytics.

Show it answering (Cloud Shell, replace `<ip>`):
```bash
curl -s http://<ip>/farms | python3 -m json.tool | head -20
```
```bash
curl -s http://<ip>/irrigation/recommendations | python3 -m json.tool | head -30
```

🗣 *"One GKE Ingress is one Google HTTP load balancer, with one public IP for every REST service. Each path goes to a different service."*

Gotcha: a brand-new Ingress needs ~5 minutes before every path works (Google's 404 page until then).

---

## Step 6. Storage 1: Cloud SQL ⏳

**Clicks:** search bar → **SQL** → instance **`s1-sql-…`** (random suffix).
- **Overview:** PostgreSQL **16**, `db-f1-micro`, zone `us-central1-a`.
- **Databases** (left menu): **`farm_registry`**, **`sensor_registry`**.
- **Users** (left menu): the service accounts `s1-farm-registry@…` and `s1-sensor-registry@…`, type **Cloud IAM service account**. No password users for the apps.
- **Connections → Networking:** public IP on, **no authorized networks**.

🗣 *"Storage product one: Cloud SQL Postgres, for relational data. A plot must belong to a farm and grow a known crop, so foreign keys make sense. Each registry has its own database. There are no passwords anywhere: each registry logs in as its own Google service account through IAM database authentication."*

**Why the random suffix?** Cloud SQL reserves an instance name for days after it's deleted.

---

## Step 7. Storage 2: Firestore ✅ (page) ⏳ (irrigation_state contents)

**Clicks:** search bar → **Firestore** → **Firestore Studio** → **Panel view** → `(default)`.
Collections: `alerts`, `farm_summaries`, **`irrigation_state`**, `ring`.
Click **`irrigation_state`** → one document per watered plot (e.g. `farm1-plot2`) with the time it was last watered.

🗣 *"Storage product two: Firestore, for small documents written by many stateless pods. Irrigation Controller stores a watering cooldown per plot here. Claiming a plot is a Firestore transaction, so even with two replicas or a restart a plot is never watered twice in 10 minutes. Person 3's ring membership and Person 2's alerts and summaries live here too."*

---

## Step 8. Storage 3: Cloud Storage ⏳

**Clicks:** ☰ → **Cloud Storage** → **Buckets**:
| Bucket | Holds | Rule |
|---|---|---|
| `…-s1-archive` | raw alert payloads from the Alert function | **Lifecycle: delete after 30 days** |
| `…-s1-artifacts` | Flink job jar, Cloud Function source zip | kept |
| `…-s1-dataproc-staging`, `…-temp` | Dataproc working files | made by the cluster stack |
| `…-tfstate` | Terraform state (Step 1) | versioned |

Click **`…-s1-archive`** → **Lifecycle** tab: the 30-day delete rule.

🗣 *"Storage product three: Cloud Storage, for cheap durable files. The alert archive deletes itself after 30 days, and Dataproc and Cloud Run read the code they run from the artifacts bucket. The sensor readings themselves are not in any of these: they're on Person 3's Sensor Store nodes."*

---

## Step 9. Security: secrets and service accounts ⏳

**Clicks:** search bar → **Secret Manager**.
- **`s1-runtime-config`**: project IDs, topic and bucket names (from Terraform).
- **`kafka-client`**, **`kafka-client-properties`**: Aiven Kafka connection details.

Then search bar → **IAM** → **Service accounts**: one per workload, `s1-partition-manager`, `s1-farm-registry`, `s1-sensor-registry`, `s1-irrigation-controller`, `s1-farm-analytics`, `s1-grafana`, `s1-external-secrets`, … Click one → **Keys** tab: **no keys**.

🗣 *"Terraform writes every secret to Secret Manager. External Secrets copies them into Kubernetes Secrets, so the Git repo only says which secret goes where, never the value. Each workload has its own service account with only the roles it needs, and pods get it through Workload Identity, so no JSON key file exists anywhere."*

---

## Step 10. Images: Artifact Registry ⏳

**Clicks:** search bar → **Artifact Registry** → repository **`s1`** → e.g. **`farm-registry`**.
- Tags are **git commit hashes**, never `latest`.
- Repository → **Cleanup policies**: keep the newest **5** versions.

🗣 *"Images are tagged with the git commit. A new version only reaches the cluster through a Git change, so Git always says exactly what's running, and a rollback is just a git revert. The cleanup policy keeps 5 versions to stay inside the free storage."*

---

## Words not to mix up

| | Meaning |
|---|---|
| **Terraform** | creates **cloud resources** (cluster, SQL, buckets, …) |
| **ArgoCD** | deploys **Kubernetes objects** (pods, services) from Git into the cluster |
| **Stack** | one Terraform folder with its own state (`foundation`, `cluster`, …) |
| **State** | Terraform's record of what it created; in the `…-tfstate` bucket |
| **Synced** (ArgoCD) | cluster matches Git |
| **Healthy** (ArgoCD) | the objects are actually running fine |
| **Prune** | deleted from Git → deleted from the cluster |
| **Self-heal** | changed by hand in the cluster → reverted to Git |
| **GSA / KSA** | Google service account / Kubernetes service account; Workload Identity links them |
| **Ingress** | one Google HTTP load balancer with path rules |

---

## Short answers to basic questions

| Question | Answer |
|---|---|
| What is infrastructure as code? | Cloud resources defined in code files, so they're versioned, reviewed and recreated the same way every time. |
| Why six stacks? | Split by lifetime: the expensive cluster is destroyed every evening, the cheap data stays. |
| Where is Terraform state? | Private, versioned GCS bucket `<project>-tfstate`, one prefix per stack. |
| What is NOT in Terraform? | The project + billing link (Terraform needs a project to run in), Kubernetes workloads (that's ArgoCD), account sign-ups (Aiven, GitHub). |
| What is GitOps? | Git is the single source of truth for what runs; a tool (ArgoCD) makes the cluster match Git. |
| How does a deployment happen? | `tools/build_push.sh` builds and pushes the image, a PR changes the tag in `k8s/gke`, it's merged, ArgoCD applies it within 60 s. |
| How do you roll back? | `git revert` the commit; ArgoCD applies the old version. |
| Why three storage products? | Relational data → Cloud SQL; small shared docs with transactions → Firestore; cheap files → Cloud Storage. |
| How do registries log into Cloud SQL? | IAM database authentication as their own service account, via the Cloud SQL connector. No passwords. |
| How are secrets handled? | Secret Manager → External Secrets → Kubernetes Secret. Never in Git. |
| Why no Cloud NAT? | It charges per hour; nodes have public IPs (firewalled) instead. |
| Why Aiven Kafka? | Free plan, managed. Only on DigitalOcean clouds; New York is nearest to Iowa. Powers off after 24 h idle. |
| What did cost control look like? | $50 credit: zonal cluster, no NAT, single-node Dataproc with 2 h idle delete, `db-f1-micro` HDD, destroy cluster after each session, budget alerts. |
| What does the Irrigation Controller do? | Every 30 s: average each plot's fresh readings, water plots below the crop minimum (Kafka `irrigation`), alert on dry soil / silent sensors (Pub/Sub `alerts`). |

---

## Design document, Part A (pages 5–8): numbers to remember

| Section | Remember |
|---|---|
| 1 Architecture | 1 project, `us-central1`; GKE zonal 2–4 × `e2-standard-2`; VPC `s1-vpc`, subnet `10.10.0.0/20`; Dataplane V2; Dataproc single node, Flink 1.17, idle delete 2 h; Aiven free plan `do-nyc`; Cloud Run function; Artifact Registry keeps 5. |
| 2 Terraform | 6 stacks; state in versioned bucket; `terraform_remote_state` links stacks; 9 pitfalls handled (e.g. Postgres 16 `ENTERPRISE`, Dataproc `internal_ip_only = false`, SQL random suffix, POST needs `-d ''` (411)). |
| 3 ArgoCD | 4 Applications; polls every **60 s**; prune + selfHeal; ignores `/spec/replicas` for HPAs; images tagged with commit. |
| 4 Storage | Cloud SQL (registries) · Firestore (ring, cooldown, alerts, summaries) · Cloud Storage (archive 30 days, artifacts, Dataproc). |
| 5 Services | Verified on GKE: 4 apps Synced/Healthy; seeded **5 farms / 20 plots / 200 sensors**; watered **5 rice plots** once, **5 DRY_SOIL** alerts, 5 Kafka events over mutual TLS. |
| 7 Security | one GSA per workload, no JSON keys; Alert function internal-only; teammates get viewer + container.developer + dataproc.editor. |
| 8 Cost | destroy cluster = saves ~90% of hourly cost; ~15 min to start a session. |

---

## Practice on your own

1. Make sure the cluster is up: **Kubernetes Engine → Clusters** shows `s1-gke`. If not, `export PROJECT=s1-agri-ams-686974 && infra/scripts/up.sh` (~20 min).
2. Read the opening line out loud.
3. Do steps 1 → 10, saying each 🗣 line **out loud** while you click. Aim for under 10 minutes.
4. On the first run, fix any ⏳ step whose button name differs and change it to ✅.
5. Close this file, do it again from memory.
6. Answer 3 random questions from the table out loud.
7. When finished: `infra/scripts/down.sh`.
