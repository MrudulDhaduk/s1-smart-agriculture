# infra/ (Person 1)

Terraform for every cloud resource (task a). The code is split into stacks by **lifetime**, each with its own
state, so the expensive stack can be destroyed every evening without touching the data.
Design rationale: [docs/p1-infrastructure-storage.md](../docs/p1-infrastructure-storage.md).

| Stack | Creates | Lifetime |
|---|---|---|
| `bootstrap/` | Project APIs, the Terraform state bucket, budget alerts (optional) | Once per project |
| `foundation/` | VPC + subnet + firewall, Artifact Registry `s1`, Firestore `(default)`, Cloud SQL (Postgres, IAM login), GCS buckets, Pub/Sub topic `alerts`, one service account per workload, IAM, runtime config in Secret Manager | Whole project (cheap) |
| `kafka/` | Aiven Kafka (free plan, DigitalOcean New York `do-nyc`), topics `readings` `results` `irrigation`, app user + ACL, connection details in Secret Manager | Whole project (free) |
| `serverless/` | Alert function (Cloud Run function, Pub/Sub trigger). Needs `services/alert-function/main.py` (Person 2) | Whole project (free when idle) |
| `cluster/` | GKE zonal cluster + autoscaling node pool, Dataproc single-node Flink + its buckets, Workload Identity bindings | **Only while working** |
| `platform/` | ArgoCD + Applications: `s1` (k8s/gke), `external-secrets`, `monitoring`, `observability` | With the cluster |

Apply order: `bootstrap` → `foundation` → `kafka` → `serverless` → `cluster` → `platform`. Destroy in reverse.
State: `gs://<project>-tfstate/s1/<stack>/`, versioned and private.

## One-time setup on your machine

```bash
export PATH="$HOME/google-cloud-sdk/bin:$PATH"
gcloud auth login
gcloud auth application-default login                 # credentials Terraform uses
gcloud config set project <project-id>
gcloud auth application-default set-quota-project <project-id>
gcloud auth configure-docker us-central1-docker.pkg.dev   # push images
export PROJECT=<project-id>
export AIVEN_TOKEN=<token>                            # only for the kafka stack (Aiven Console > User > Tokens)
```

In each stack: `cp terraform.tfvars.example terraform.tfvars` and fill it in (`*.tfvars` is git-ignored).

## Bootstrap a new project (first run only)

The state bucket does not exist yet, so bootstrap starts with local state and then moves it into the bucket it created:

```bash
cd infra/bootstrap
printf 'terraform {\n  backend "local" {}\n}\n' > backend_override.tf
terraform init && terraform apply
rm backend_override.tf
terraform init -migrate-state -force-copy -backend-config=bucket=$PROJECT-tfstate
rm -f terraform.tfstate terraform.tfstate.backup     # now safely in the bucket
```

## Every other stack

```bash
cd infra/<stack>
terraform init -backend-config=bucket=$PROJECT-tfstate
terraform plan -out=tfplan
terraform apply tfplan
```

## Daily routine (credit: $50)

```bash
time infra/scripts/up.sh      # cluster + platform: GKE, Dataproc, ArgoCD (~15 min); prints ArgoCD login
infra/scripts/down.sh         # ArgoCD off -> delete app namespaces (LB, disks) -> destroy GKE + Dataproc
```

- Not working on Flink? `enable_dataproc = false` in `cluster/terraform.tfvars`. Dataproc also deletes itself after 2 h without a job.
- Several days off? `sql_activation_policy = "NEVER"` in `foundation/terraform.tfvars` + apply (Cloud SQL stops, data kept).
- Aiven free Kafka powers off after 24 h without traffic: power it on in the Aiven Console before a session (Terraform cannot).
- Kafka stack notes: the free plan is offered only on DigitalOcean clouds, so the stack reads `aiven_service_plan_list` and
  takes the first of `preferred_clouds` that offers the plan (`do-nyc`, nearest to GKE in Iowa); without an explicit cloud
  Aiven uses the project default and fails with `Invalid cloud`. `kafka_version` is left to Aiven's default (a pinned
  `4.0` was rejected). The token is read from `AIVEN_TOKEN` only, so run this stack from a shell where it is exported.
- Check Billing → Reports after every session; budget alerts only warn.

## Check a session works (measured 13 Nov)

`up.sh` takes about 20 min the first time: cluster ~6 min (Dataproc is the slowest), ArgoCD ~3 min, all four
Applications Synced/Healthy ~5 min later, and the Ingress needs ~5 more minutes before every path answers
(until then some requests get Google's default 404 page).

```bash
kubectl -n argocd get applications                      # 4 x Synced Healthy
IP=$(kubectl -n s1 get ingress s1-public -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
python tools/seed_registries.py --base http://$IP        # 5 farms, 20 plots, 200 sensors (via Cloud SQL)
kubectl -n s1 exec deploy/partition-manager -- python pmctl.py write 2000
curl -s http://$IP/irrigation/recommendations | python -m json.tool
curl -s -X POST -d '' http://$IP/irrigation/evaluate     # -d '': Google's load balancer rejects a POST without Content-Length (411)
```

## Deploying an app change (GitOps)

```bash
tools/build_push.sh farm-registry      # build, push <registry>/farm-registry:<commit>, set newTag in k8s/gke
git add k8s/gke/kustomization.yaml && git commit -m "Deploy farm-registry <commit>"   # then PR -> merge
```

ArgoCD polls `main` every 60 s and applies `k8s/gke`. Nobody runs `kubectl apply`.
Before the P1 PRs are merged, `platform/terraform.tfvars` can set `repo_revision = "p1/infra-and-services"` to test the
branch; set it back to `main` afterwards. The Argo charts come from `oci://ghcr.io/argoproj/argo-helm`: the classic
chart repository serves its files from GitHub release assets, which kept resetting connections from our network.

## Hooks for the other services

| Who | What Terraform provides |
|---|---|
| Partition Manager | Firestore `(default)`; GSA `s1-partition-manager` (`datastore.user`, publisher on `alerts`) bound to KSA `s1/partition-manager` |
| Farm / Sensor Registry | Cloud SQL databases `farm_registry`, `sensor_registry`; IAM DB login as GSA `s1-farm-registry` / `s1-sensor-registry` |
| Irrigation Controller | GSA with Firestore + publisher on `alerts`; Kafka credentials (Secret `kafka-client`) |
| Telemetry Ingestion / Farm Analytics | Kafka credentials: Kubernetes Secret `kafka-client` (envFrom), GSA `s1-farm-analytics` (Firestore) for KSA `s1/farm-analytics` |
| Alert function | GSA `s1-alert-function`: Firestore write, create objects in the `archive` bucket; deployed by `serverless/` |
| Flink job | Dataproc `s1-flink` (Flink 1.17, image 2.2); jar in the `artifacts` bucket; Kafka client properties in Secret Manager `kafka-client-properties`; logs reach Cloud Logging when submitted with `gcloud dataproc jobs submit flink` |
| Grafana | GSA `s1-grafana` (`logging.viewer`, `monitoring.viewer`) bound to KSA `monitoring/monitoring-grafana` |

A pod uses its GSA when its Kubernetes ServiceAccount has the annotation `iam.gke.io/gcp-service-account: <GSA email>`
(`k8s/gke/workload-identity.yaml`).

## What is not in Terraform, and why

- **Creating the project and linking billing:** done once by hand; every stack needs an existing project to run against.
- **Kubernetes workloads:** deployed only by ArgoCD from `k8s/gke` (task d). Terraform installs ArgoCD itself, nothing else in the cluster.
- **Account sign-ups** (Aiven, GitHub): they come before any API exists.
