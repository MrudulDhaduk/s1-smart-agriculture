# Person 1: code walkthrough and live-change playbook

Companion to `docs/p1-console-demo.md`. Two parts:
1. **Code → what it creates → where to see it** (console page, ArgoCD, logs, curl).
2. **Live changes**: if the examiner says "change X now", the safest way to do it, with the commands.

Person 1 = Saravanasudharsan S · (a) Terraform · (d) ArgoCD · (g) three storage products · services Farm Registry, Sensor Registry, Irrigation Controller.
Project `s1-agri-ams-686974`, region `us-central1`, zone `us-central1-a`.

⏳ Written from the code on `main`, not yet rehearsed live. **Rehearse every recipe in Part 2 once before the viva** and fix anything that behaves differently.

---

# Part 1. Code → console

## 1.1 Terraform (`infra/`)

| File | Creates | See it in the console |
|---|---|---|
| `infra/bootstrap/main.tf` | Turns on the project APIs, the **state bucket** `s1-agri-ams-686974-tfstate` (versioned), **budget alerts** at 30/60/80% | **Cloud Storage → Buckets** · **Billing → Budgets & alerts** · **APIs & Services → Enabled APIs** |
| `infra/foundation/network.tf` | VPC **`s1-vpc`**, subnet `s1-us-central1` (`10.10.0.0/20` nodes, `10.20.0.0/16` pods, `10.30.0.0/20` services), firewall **`s1-allow-internal`** | **VPC network → VPC networks** · **→ Firewall** |
| `infra/foundation/registry.tf` | Artifact Registry repo **`s1`**, cleanup policy: keep newest 5 | **Artifact Registry → s1** |
| `infra/foundation/firestore.tf` | Firestore database **`(default)`** | **Firestore** |
| `infra/foundation/sql.tf` | Cloud SQL **`s1-sql-<random>`**, Postgres 16, `db-f1-micro`, HDD, zonal, IAM login on; databases `farm_registry`, `sensor_registry`; IAM users | **SQL → instance → Databases / Users / Connections** |
| `infra/foundation/storage.tf` | Buckets **`…-s1-archive`** (delete after 30 days) and **`…-s1-artifacts`** | **Cloud Storage → Buckets → Lifecycle** |
| `infra/foundation/pubsub.tf` | Pub/Sub topic **`alerts`**, who may publish | **Pub/Sub → Topics → alerts** |
| `infra/foundation/iam.tf` | One service account per workload (`s1-farm-registry`, `s1-sensor-registry`, `s1-irrigation-controller`, `s1-partition-manager`, `s1-farm-analytics`, `s1-grafana`, `s1-external-secrets`, …) with only their roles; teammates get viewer + container.developer + dataproc.editor | **IAM & Admin → Service accounts** · **→ IAM** |
| `infra/foundation/runtime_config.tf` | Secret **`s1-runtime-config`** (project, topic, bucket names as JSON) | **Secret Manager** |
| `infra/kafka/main.tf`, `secrets.tf` | Aiven Kafka (free plan, `do-nyc`), topics `readings`, `results`, `irrigation`, app user; secrets **`kafka-client`**, **`kafka-client-properties`** | **Aiven console** (not GCP) · **Secret Manager** |
| `infra/serverless/function.tf` | Cloud Run function **`alert-service`**, Pub/Sub trigger, internal-only | **Cloud Run** (or Cloud Run functions) → `alert-service` → **Triggers** |
| `infra/cluster/gke.tf` | GKE **`s1-gke`** + node pool **`main`** (2–4 × e2-standard-2), Dataplane V2, Workload Identity | **Kubernetes Engine → Clusters** |
| `infra/cluster/dataproc.tf` | Dataproc **`s1-flink`** (single node, Flink 1.17, idle delete 2 h) + staging/temp buckets | **Dataproc → Clusters** |
| `infra/cluster/workload_identity.tf` | "Kubernetes SA `s1/farm-registry` may act as Google SA `s1-farm-registry`" bindings | **IAM → Service accounts → one → Permissions** |
| `infra/platform/argocd.tf` | ArgoCD (Helm) + 4 Applications: `s1`, `external-secrets`, `monitoring`, `observability` | **ArgoCD UI** (Cloud Shell, see 2.0) |
| `infra/scripts/up.sh` / `down.sh` | Start: apply `cluster` + `platform`. Stop: delete app namespaces (so GKE frees the load balancer and disks), destroy `platform` + `cluster` | Clusters page appears / disappears |

🗣 *"Each folder is one Terraform stack with its own state. Stacks read each other's outputs with `terraform_remote_state`, for example the cluster stack takes the subnet and service accounts from foundation."*

## 1.2 GitOps (`k8s/`)

| File | What it says | See it |
|---|---|---|
| `k8s/base/kustomization.yaml` | The list of every manifest of the app | ArgoCD → `s1` tile → the tree |
| `k8s/base/farm-registry/deployment.yaml` | 2 replicas, readiness `/healthz` (includes DB check), liveness `/livez`, CPU request 50m | **Workloads → farm-registry** |
| `k8s/base/sensor-registry/deployment.yaml` | same pattern | **Workloads → sensor-registry** |
| `k8s/base/irrigation-controller/deployment.yaml` | 1 replica, `EVAL_INTERVAL_S=30` | **Workloads → irrigation-controller → Details → env** |
| `k8s/gke/kustomization.yaml` | base + GKE extras; **one image line per service with the git-commit tag** | ArgoCD → s1 → a Deployment → image |
| `k8s/gke/workload-identity.yaml` | annotation `iam.gke.io/gcp-service-account` on each Kubernetes SA | Object Browser → ServiceAccount → YAML |
| `k8s/gke/gcp-env.yaml` | Pods read Secret `gcp-config` (+ `kafka-client`); registries log into SQL as `DB_IAM_USER`, no password | **Workloads → farm-registry → YAML** |
| `k8s/gke/external-secrets.yaml` | `ClusterSecretStore gcp-secret-manager`; ExternalSecrets `gcp-config` ← `s1-runtime-config`, `kafka-client` ← `kafka-client` | **Secrets & ConfigMaps** (namespace s1) |
| `k8s/gke/ingress.yaml` | Ingress **`s1-public`**, 7 paths | **Gateways, Services & Ingress → Ingress** |

## 1.3 My services (`services/`)

| File | Does | See it |
|---|---|---|
| `services/farm-registry/app.py` | REST: `GET/POST /crops`, `GET/POST /farms`, `GET /farms/{id}`, `POST /farms/{id}/plots`, `GET /plots`, `GET /plots/{id}`. Tables `crops`, `farms`, `plots` (foreign keys) | `curl http://<ip>/farms` · Logs Explorer `container_name="farm-registry"` |
| `services/sensor-registry/app.py` | REST: `GET/POST /sensors`, `GET /sensors/{id}`, status `active`/`inactive`/`faulty`. **Checks the plot exists by calling Farm Registry** | `curl http://<ip>/sensors?plot_id=farm1-plot1` |
| `services/irrigation-controller/app.py` | Background loop every `EVAL_INTERVAL_S`; `GET /irrigation/recommendations` (dry run), `POST /irrigation/evaluate` (run a cycle now). Metrics `irrigation_*` | curl · Logs: `control cycle`, `alert published` |
| `services/irrigation-controller/controller.py` | The rules: plots → active sensors → latest readings (gRPC to Partition Manager) → average fresh ones (≤ 5 min old) → below crop minimum = **water** (`area × deficit × depth ÷ 10` L) + `DRY_SOIL` alert; silent sensors = `SENSOR_SILENT`; **10-minute cooldown** | Firestore `irrigation_state` · Pub/Sub `alerts` |
| `services/irrigation-controller/backends.py` | Cloud vs laptop switches: `STATE_BACKEND` (memory/firestore), `ALERTS_BACKEND` (log/pubsub), Kafka on/off | env vars in the Deployment YAML |
| `services/web-common/` | Shared: JSON logs, DB engine (Cloud SQL connector + IAM), health checks | — |
| `services/*/test_*.py` | Tests: farm-registry 5, sensor-registry 4, irrigation-controller 7 | `pytest` |

## 1.4 Tools (`tools/`)

| File | Does |
|---|---|
| `tools/build_push.sh <svc>` | Builds the image, pushes `…/s1/<svc>:<git commit>`, rewrites the tag in `k8s/gke/kustomization.yaml`. Refuses if the service has uncommitted changes |
| `tools/seed_registries.py --base http://<ip>` | 4 crops, 5 farms, 20 plots, 200 sensors. Safe to run twice (409 = already there) |
| `tools/simulate_sensors.py` | Sends fake readings to Telemetry Ingestion (Person 2's entry point) |

## 1.5 What about Grafana?

**Grafana has no Person 1 panels.** Prometheus only scrapes Partition Manager and Sensor Store (`observability/servicemonitors.yaml`). My services do expose `/metrics` on port 8000 (`http_requests_total`, `irrigation_*`), but nothing scrapes them.
If asked: *"My services expose Prometheus metrics, but our dashboard focuses on the partitioning concept. My evidence is in ArgoCD, the console pages and Cloud Logging. Adding a ServiceMonitor is a one-file Git change."* (That's recipe **2.9** below.)

My "dashboards" are therefore:
| Show | Where |
|---|---|
| Everything is deployed from Git | **ArgoCD UI**: 4 tiles Synced + Healthy |
| Services running | **Kubernetes Engine → Workloads** |
| Services working | **Logs Explorer**: `control cycle`, `alert published` |
| Data stored | **Firestore** `irrigation_state` · **SQL** databases · **Cloud Storage** archive |
| Cost | **Billing → Reports** |

---

# Part 2. Live changes during the demo

## 2.0 Set up before the examiner arrives (Cloud Shell)

```bash
gcloud container clusters get-credentials s1-gke --zone us-central1-a --project s1-agri-ams-686974
cd ~/s1-smart-agriculture 2>/dev/null && git checkout main && git pull || { git clone https://github.com/MrudulDhaduk/s1-smart-agriculture.git && cd s1-smart-agriculture; }
export PROJECT=s1-agri-ams-686974
export IP=$(kubectl -n s1 get ingress s1-public -o jsonpath='{.status.loadBalancer.ingress[0].ip}'); echo $IP
kubectl -n argocd get applications            # 4 x Synced Healthy
```

**ArgoCD UI** in a second Cloud Shell tab (`+`):
```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
kubectl -n argocd port-forward svc/argocd-server 8080:80
```
→ **Web Preview → Preview on port 8080** → user `admin`, the password above.

**Terraform** needs the git-ignored `terraform.tfvars` in each stack you'll touch. Copy yours into Cloud Shell before the viva (or recreate from `terraform.tfvars.example`), then once:
```bash
terraform -chdir=infra/foundation init -backend-config=bucket=$PROJECT-tfstate
```

**Have ready:** a teammate who can approve a PR quickly (team rule: no direct push to `main`, 1 approval).

## 2.1 Golden rules (say them out loud, they score points)

1. **Kubernetes changes go through Git**, never `kubectl apply`. Edit → branch → PR → merge → ArgoCD applies within 60 s.
2. **Cloud changes go through Terraform**: always `plan` first and **read it**. Only `apply` if it says `0 to destroy` and no `must be replaced`.
3. **Never** touch the `cluster` or `platform` stack live. It would recreate the cluster in the middle of the demo.
4. Pick the **smallest change that proves the point**: an env var, a label, a new farm. Not a code rewrite.
5. If a change will take longer than 2 minutes (image build), **explain the steps and offer to show it**, don't freeze in silence.

## 2.2 Which recipe for which request?

| Examiner asks | Recipe | Time |
|---|---|---|
| "Add a farm / plot / sensor" | 2.3 data via REST | 1 min |
| "Change a setting of a service" | 2.4 GitOps config change | 3–5 min |
| "What if someone changes the cluster by hand?" | 2.5 self-heal | 1 min |
| "Roll back" | 2.6 git revert | 3–5 min |
| "Change the code / add a field" | 2.7 code change + new image | 10–15 min |
| "Add/change a cloud resource" | 2.8 Terraform | 3–5 min |
| "Scale a service" | 2.4 warning + 2.5 | 1 min |
| "Show your services in Grafana" | 2.9 ServiceMonitor | 5 min |

## 2.3 Add data (no deploy needed)

```bash
curl -s -X POST http://$IP/farms -H 'Content-Type: application/json' -d '{"farm_id":"farm9","name":"Viva Farm","location":"Pilani"}'
curl -s -X POST http://$IP/farms/farm9/plots -H 'Content-Type: application/json' -d '{"plot_id":"farm9-plot1","crop":"rice","area_m2":100}'
curl -s -X POST http://$IP/sensors -H 'Content-Type: application/json' -d '{"sensor_id":"farm9-plot1-s1","plot_id":"farm9-plot1"}'
curl -s http://$IP/farms/farm9 | python3 -m json.tool
```
Show the rules work:
- Plot with an unknown crop → **error** (foreign key / validation).
- Sensor on a plot that doesn't exist → **error**: Sensor Registry asked Farm Registry and got 404.
```bash
curl -s -X POST http://$IP/sensors -H 'Content-Type: application/json' -d '{"sensor_id":"farm99-plot1-s1","plot_id":"farm99-plot1"}'
```
Run the controller now: `curl -s -X POST -d '' http://$IP/irrigation/evaluate | python3 -m json.tool` (the `-d ''` is needed: Google's load balancer rejects a POST without a body length, error 411).

🗣 *"Data goes through the REST APIs into Cloud SQL. The registries enforce the relations: a plot needs a real farm and crop, a sensor needs a real plot."*

## 2.4 Change a service setting via GitOps (the main GitOps demo)

**Good example:** Irrigation Controller cycle from 30 s to 15 s.

```bash
git checkout main && git pull
git checkout -b p1/viva-eval-15s
sed -i 's/EVAL_INTERVAL_S, value: "30"/EVAL_INTERVAL_S, value: "15"/' k8s/base/irrigation-controller/deployment.yaml
git diff
git commit -am "Irrigation Controller: evaluate every 15 s (viva demo)"
git push -u origin p1/viva-eval-15s
```
Then on **GitHub**: open the PR → teammate approves → **Merge**.
Then in **ArgoCD**: `s1` tile goes **OutOfSync** → **Syncing** → **Synced** (≤ 60 s; click **Refresh** to skip the wait). In the console: **Workloads → irrigation-controller** shows a new pod (rolling update), and Logs Explorer shows `control cycle` every 15 s.

🗣 *"I didn't touch the cluster. I changed one line in Git. After the merge, ArgoCD noticed main had changed and rolled it out. Git is now the record of who changed what and when."*

⚠️ **Trap: replica counts.** The `s1` Application **ignores `spec.replicas`** on Deployments (so it doesn't fight the HPA). So a Git change of only `replicas: 2 → 3` **stays "Synced" and is not rolled out**. If asked to scale a service:
- say so (it's a deliberate trade-off for the HPAs), and
- for a quick demo: `kubectl scale deploy farm-registry -n s1 --replicas=3`. ArgoCD **won't** revert this one, for the same reason. Scale it back to 2 afterwards.

## 2.5 Show self-heal (1 minute, very convincing)

Change something by hand that **is** in Git:
```bash
kubectl set env deploy/irrigation-controller -n s1 EVAL_INTERVAL_S=5
```
Watch **ArgoCD**: `s1` turns **OutOfSync** for a moment, then **Synced** again. Check:
```bash
kubectl get deploy irrigation-controller -n s1 -o jsonpath='{.spec.template.spec.containers[0].env}' | python3 -m json.tool | grep -A1 EVAL
```
→ back to `"30"` (or whatever Git says).

🗣 *"Someone changed the cluster by hand. Self-heal is on, so ArgoCD put it back to what Git says. Manual drift can't survive."*

## 2.6 Roll back

```bash
git checkout main && git pull
git log --oneline -5                       # find the merge commit of the change
git checkout -b p1/revert-viva
git revert -m 1 <merge-commit>             # for a normal (non-merge) commit: git revert <commit>
git push -u origin p1/revert-viva
```
PR → approve → merge → ArgoCD applies the old version.

🗣 *"A rollback is a git revert. Because images are tagged with the commit and never `latest`, reverting the tag line brings back exactly the old code."*

Don't use ArgoCD's **History → Rollback** button: ArgoCD refuses it while auto-sync is on, and Git would win anyway.

## 2.7 Code change with a new image (explain, show if time allows)

Example: add a `soil_type` field to farms. Steps:
```bash
git checkout -b p1/viva-soil-type
# 1. edit services/farm-registry/app.py (FarmIn model + farms table)
cd services/farm-registry && python3 -m pytest -q && cd ../..     # 2. tests must pass
git commit -am "Farm Registry: soil_type"                          # 3. build_push refuses uncommitted code
gcloud auth configure-docker us-central1-docker.pkg.dev -q         #    (one time)
tools/build_push.sh farm-registry                                  # 4. build + push :<commit>, updates k8s/gke tag
git commit -am "Deploy farm-registry <commit>"                     # 5. the tag change
git push -u origin p1/viva-soil-type                               # 6. PR → approve → merge → ArgoCD
```
Watch: **Artifact Registry → s1 → farm-registry** shows the new tag; ArgoCD rolls the Deployment; **Workloads** shows new pods one by one (2 replicas = no downtime).

⚠️ A **new database column** isn't added to an existing table automatically. Unless the app migrates it, prefer a change that doesn't alter tables (e.g. a new read-only endpoint or a log line) for a live demo.

🗣 *"Code change, test, commit, build an image tagged with that commit, change the tag in Git, merge. ArgoCD deploys it. Every running version maps to exactly one commit."*

## 2.8 Terraform change (cloud resource)

**Safe example:** add a label to the archive bucket. In `infra/foundation/storage.tf`, inside `resource "google_storage_bucket" "b"` add:
```hcl
  labels = { owner = "person1", purpose = "viva" }
```
Then:
```bash
terraform -chdir=infra/foundation plan
```
**Read the plan out loud:** `~ update in-place`, `Plan: 0 to add, 2 to change, 0 to destroy`. Then:
```bash
terraform -chdir=infra/foundation apply
```
Type `yes`. Show it: **Cloud Storage → bucket → Configuration → Labels**. Then commit the `.tf` change on a branch + PR like any code.

Other safe ones: Artifact Registry `keep_count` 5 → 6 (`registry.tf`), a new Pub/Sub topic (`pubsub.tf`, `0 to destroy`).

🗣 *"Every cloud resource is code. I change the code, Terraform shows me the plan, exactly what will change and that nothing will be destroyed, and only then I apply."*

⛔ Stop and explain instead of applying if the plan shows **`destroy`**, **`must be replaced`**, anything in Cloud SQL's `settings` (restarts the database), or anything you didn't expect.

## 2.9 Add my services to Prometheus (one-file Git change)

Add to `observability/servicemonitors.yaml` (copy the Partition Manager block, change name and label), e.g. for `irrigation-controller`, port name of the metrics port. Check the Service's port names first:
```bash
kubectl get svc irrigation-controller -n s1 -o yaml | grep -A3 ports
```
Branch → PR → merge → ArgoCD `observability` app syncs → in Grafana **Explore**, query `irrigation_cycles_total`.
⏳ Rehearse this one before offering it: the Service must expose the metrics port (8000) with a name.

## 2.10 If something goes wrong

| Problem | Do |
|---|---|
| ArgoCD stays OutOfSync | Click **Refresh**, then **Sync**. Check the app's **Events** / error message |
| Pod in `CreateContainerConfigError` | A Secret is missing: check **Secrets & ConfigMaps** for `gcp-config`, `kafka-client`; External Secrets may still be copying. Wait 1 min |
| Pod `ImagePullBackOff` | The tag in `k8s/gke/kustomization.yaml` doesn't exist in Artifact Registry: re-run `tools/build_push.sh` or revert |
| Ingress gives Google's 404 | New Ingress: wait ~5 min |
| `POST` returns 411 | Add `-d ''` to curl |
| Terraform `Error acquiring the state lock` | Someone else is running Terraform. Wait. Never force-unlock during the demo |
| Terraform wants to replace something | Don't apply. Explain why (e.g. a name change forces a new resource) |
| PR can't be merged | Need 1 approval: ask the teammate. Never push straight to `main` |
| Anything you can't fix in 30 s | Say what the step would show, move on, come back at the end |

---

# Part 3. Quick answers about the code

| Question | Answer |
|---|---|
| Why is Terraform split into stacks? | Different lifetimes: destroy the expensive cluster daily, keep the data. Smaller blast radius per `apply`. |
| How do stacks talk to each other? | `terraform_remote_state` reads another stack's outputs from the state bucket. |
| Why did you write `edition = "ENTERPRISE"`? | Postgres 16 defaults to Enterprise Plus, which has no small machines. |
| Why a random suffix on the SQL instance? | A deleted instance's name is reserved for days. |
| Why are ArgoCD apps created with a Helm chart (`argocd-apps`)? | Terraform can't plan Application objects before ArgoCD's CRDs exist. |
| How does a pod get Google credentials? | Workload Identity: Kubernetes SA annotated with a Google SA; Terraform binds them. No key files. |
| How does the controller avoid watering twice? | Claiming a plot is a Firestore transaction with a 10-minute cooldown, shared by all replicas. |
| Why does Sensor Registry call Farm Registry? | To check the plot exists. Each service owns its own database, so it asks instead of joining tables. |
| What's in `k8s/base` vs `k8s/gke`? | base = environment-neutral app. gke = images with commit tags, Workload Identity, secrets, Ingress. |
