# Person 3: GCP Console demo (practice sheet)

Only my part: (f) consistent hashing, (c) GKE + HPA + k6, (h) monitoring and logging.
My services: **Partition Manager** and **Sensor Store**.
Everything is clicked in the console. The only typing is one block in **Cloud Shell** (the `>_` icon at the top right) to start the load test.

Marked ✅ = checked on the live console. Marked ⏳ = not checked yet, so the exact button may look slightly different.

---

## My opening line (learn by heart)

> "I'm Person 3. I did the main concept for S1, **data partitioning using consistent hashing**. I also did **GKE with autoscaling and a k6 load test**, and **monitoring with Prometheus, Grafana and Cloud Logging**. My two services are **Partition Manager** and **Sensor Store**."

---

## Step 1. The cluster ✅

**Clicks:** project **S1 Smart Agriculture** → ☰ → **Kubernetes Engine** → **Clusters** → click **`s1-gke`**.
- **Details:** Location `us-central1-a` (zonal).
- **Nodes** tab: node pool **`main`**, machine `e2-standard-2`, autoscaling **2–4 nodes**.

🗣 *"This is our GKE cluster, `s1-gke`, a zonal cluster in us-central1-a, created by Terraform. One node pool of e2-standard-2 machines that autoscales from 2 to 4 VMs. ArgoCD deploys our services onto it."*

If the clusters list is empty: the cluster is destroyed after every session to save credit (`infra/scripts/down.sh`).

---

## Step 2. My two services ✅

**Clicks:** left menu **Workloads** → **Namespace** dropdown at the top → **`s1`**.

| Row | Type | Pods | Owner |
|---|---|---|---|
| **partition-manager** | Deployment | 2/2 | **me** |
| **sensor-store** | Stateful Set | 4/4 | **me** |
| telemetry-ingestion, farm-analytics | Deployment | | Person 2 |
| farm-registry, sensor-registry, irrigation-controller | Deployment | | Person 1 |

🗣 *"These are all our services on GKE, in the `s1` namespace. Mine are these two. **partition-manager** is a Deployment with 2 pods. It's the router that holds the consistent-hash ring. **sensor-store** is a StatefulSet with 4 pods, the 4 storage nodes on the ring."*

### 2a. Click `partition-manager` → Deployment details ✅
Tabs: *Overview · Details · Observability · **Scaling** · Revision history · Events · Logs · App Errors · YAML*

**Overview tab, the 3 graphs (CPU, Memory, Disk).** Each graph has up to 3 lines:
- **Red** = the **limit** (the most the pods may use). CPU: 0.5 core per pod × 2 pods = **1 core**.
- **Green** = the **request** (what each pod is guaranteed). CPU: 0.1 core × 2 = **0.2 core**.
- **Blue** = **actual usage**. Close to 0 when idle.

**Below the graphs:**
- **Replicas:** "2 updated, 2 ready, 2 available".
- **Horizontal Pod Autoscaler: OK**. The autoscaler is attached.

🗣 *"Partition Manager is stateless, so it's a Deployment. Right now there are 2 pods, using almost no CPU. The autoscaler is attached. When load comes, it adds pods."*

### 2b. Scaling tab ✅ (the best page for autoscaling)
**Clicks:** still on partition-manager → **Scaling** tab.

**Top box, left to right:**
| Box | Shows | Meaning |
|---|---|---|
| Active scaling strategy | ✅ **HPA**, ⛔ VPA | HPA is on. VPA is off. |
| Cooldown duration | **Scale down window: 60 sec** | waits 60 s before removing pods |
| Pods | **2 of 2** | current pod count |
| CPU utilization | ~3% | average CPU, as % of the request |
| Memory utilization | ~37% | |

**"Horizontal Pod Autoscaler" box:** Name `partition-manager`, **Min replicas 2**, **Max replicas 6**, **CPU utilization: 3% out of 50%** (the bar).

- **HPA** (Horizontal) = changes the **number of pods**. ← we use this
- **VPA** (Vertical) = changes the **size (CPU/memory) of each pod**. Not used.

🗣 *"This is the autoscaler on Partition Manager. It keeps average CPU at 50% of each pod's request. Right now it's 3% of 50%, so it stays at the minimum of 2 pods. Minimum 2 so one pod can die without an outage, maximum 6 as our cost ceiling. Scale-down waits 60 seconds so it doesn't flap up and down."*

The HPA formula (if asked): `desired pods = ceil(current pods × current CPU ÷ target CPU)`.
Example: 2 pods at 150% → `ceil(2 × 150 ÷ 50)` = **6**.

### 2c. Click `sensor-store` ✅ (top part) / ⏳ (Managed pods)
**Clicks:** ← back to **Workloads** → **sensor-store** → opens **Stateful Set details**.
Tabs: *Details · Scaling · Events · Revision history · Logs · YAML* (no Overview tab here).

**Details tab, graphs** (totals for all 4 pods):
- **CPU:** green line at **0.4** = request 0.1 core × 4 pods. **No red line**, because Sensor Store has no CPU limit. Blue (usage) near 0.
- **Memory:** red ≈ **1,000 MiB** = limit 256 MiB × 4. Green **500 MiB** = request 128 MiB × 4. Blue = usage.

**Below the graphs:**
- **Annotations:** `argocd.argoproj.io/tracking-id: s1:apps/StatefulSet:s1/sensor-store`. This proves **ArgoCD deployed it** from Git, not someone typing kubectl.
- **Label selector:** `app = sensor-store`.

**Scroll down → Pod specification:** Restart policy **Always** (Kubernetes restarts a crashed container).

**Scroll down → Managed pods ✅:** `sensor-store-0`, `-1`, `-2`, `-3`, all **Running**, Restarts **0**.
Point out the names: **fixed numbers 0–3**, not random letters like Deployment pods (`partition-manager-7f9c…`).

**Scroll down → Exposing services ✅:** `sensor-store`, Type **Cluster IP**, **Endpoints empty**.
That's because it is a **headless Service** (`clusterIP: None`). It doesn't load-balance. Each pod gets its own DNS name, e.g. `sensor-store-2.sensor-store`, so Partition Manager can reach **one specific ring node**.

🗣 *"Sensor Store is stateful, so it's a StatefulSet. Each pod has a fixed name, which is its name on the hash ring, and its own disk. It has no autoscaler. If the HPA added a pod it wouldn't be on the ring, and removing one would lose its share of the data. I add storage nodes on purpose, through the ring."*

---

## Step 3. Each storage node has its own disk ✅

**Clicks:** left menu → scroll to **Kubernetes Resources** → **Storage** → Namespace **`s1`** → tab **Persistent volume claims**.

| Column | Shows | Meaning |
|---|---|---|
| Name | `data-sensor-store-0` … `-3` | one disk claim per ring node (name = `data-` + pod name) |
| Phase | **Bound** | the claim is attached to a real disk |
| Volume | `pvc-…` | the actual Google persistent disk |
| Storage class | `standard-rwo` | GKE's default disk type, ReadWriteOnce = one pod at a time |

⚠️ If you see a **`data-sensor-store-4`** too: it's left over from a node-join test (scaled to 5 pods, then back to 4). Kubernetes **keeps the disk when a StatefulSet scales down**, on purpose, so data isn't lost by accident. If asked, say exactly that.

🗣 *"One disk per ring node. If a pod restarts, it gets the same disk back, so its data is still there."*

---

## Step 4. The ring membership in Firestore ✅

**Clicks:** top search bar → type **Firestore** → open it → left menu **Firestore Studio** → **Panel view** → column 1 `(default)` → click collection **`ring`** → column 2 click document **`membership`**.
Breadcrumb at the top reads: **Root › ring › membership**.

Shows:
- `nodes:` 0 `sensor-store-0`, 1 `sensor-store-1`, 2 `sensor-store-2`, 3 `sensor-store-3`
- `version:` a number (5 on 22 Nov)

**Why the version is not 1:** it goes up by 1 every time a node joins or leaves the ring. Firestore is **not deleted** with the cluster (it's in the long-lived Terraform stack), so the number keeps counting across sessions. Version 5 = started at 1, then 4 changes (my node-join tests: add `sensor-store-4`, remove it, ...).

**The other collections** (`alerts`, `farm_summaries`, `irrigation_state`) belong to Person 1 and 2. Only `ring` is mine.

🗣 *"This is the ring membership: which storage nodes are on the ring, plus a version number. Every Partition Manager pod re-reads it every 5 seconds, so all router pods agree on the same ring. It can't live in pod memory because the autoscaler adds and removes those pods. The version is 5 because I've tested adding and removing a fifth node. Each change bumps it by one, and Firestore keeps it between sessions."*

---

## Step 5. Autoscaling under load ⭐ ⏳

**Open Cloud Shell** (`>_`, top right) and paste:

```bash
gcloud container clusters get-credentials s1-gke --zone us-central1-a --project s1-agri-ams-686974
cd ~/s1-smart-agriculture 2>/dev/null && git pull || { git clone https://github.com/MrudulDhaduk/s1-smart-agriculture.git && cd s1-smart-agriculture; }
kubectl delete job k6-pm-write -n s1 --ignore-not-found
kubectl delete configmap k6-script k6-contracts -n s1 --ignore-not-found
kubectl create configmap k6-script -n s1 --from-file=loadtest/pm-write.js
kubectl create configmap k6-contracts -n s1 --from-file=contracts/partition_manager.proto --from-file=contracts/reading.proto
kubectl apply -f loadtest/k6-gke.yaml
```

**Then in the console:**
1. **Workloads**: a new row **`k6-pm-write`** (a Job) appears. That's the load test.
2. Click **partition-manager** → **Scaling** tab. Click **Refresh** (top) every ~30 s:
   - **CPU utilization** bar goes past **50%** (e.g. "290% out of 50%").
   - **Pods** goes **2 of 2 → 6 of 6**.
   - (The **Overview** tab shows the same as graphs: the blue CPU line climbs.)
3. The test runs ~5 min. A few minutes after it ends, replicas go back to **2**.

🗣 *"k6 runs as a Job inside the cluster and sends about 150 writes per second. CPU goes past the 50% target, so the HPA adds pods, up to our maximum of 6. When the load stops it waits, so it doesn't flap, then scales back to 2."*

Why k6 runs inside the cluster: from outside, a port-forward would send all traffic to one pod, so the new pods would get none.

---

## Step 6. A storage node fails ⏳

**Clicks:** **Workloads** → **sensor-store** → **Managed pods** → click **`sensor-store-1`** → **Delete** (top) → confirm.
Go back to **sensor-store**. Within about a minute **`sensor-store-1` is back**, with the same name and a young age.

🗣 *"I killed a storage node. Kubernetes recreated it with the same name and the same disk. No data was lost meanwhile: each reading has 3 copies, writes only need 2 of the 3 to confirm, and reads fall back to the next replica."*

---

## Step 7. Centralised logging ⏳

**Clicks:** search bar → **Logs Explorer** → time **Last 1 hour** → paste the query → **Run query**.

```
resource.type="k8s_container"
resource.labels.namespace_name="s1"
resource.labels.container_name="partition-manager"
severity>=WARNING
```

Shows **`replica write failed`** warnings from when `sensor-store-1` was down.
To show every service, remove the last two lines and add `jsonPayload.service:*`.

🗣 *"Every service logs one JSON object per line, and Cloud Logging collects them. Here Partition Manager logged failed replica writes while that node was down. We picked Cloud Logging because Flink on Dataproc and the Cloud Function are outside GKE, and it collects all of them in one place."*

---

## Grafana (only if he asks)

Grafana runs inside the cluster, not in the GCP console. Steps are in `docs/p3-viva-runbook.md`, section "If the examiner wants GKE live", step 6.

---

## Words not to mix up

| | Meaning |
|---|---|
| **Node** (Kubernetes) | a **VM** in the cluster (2–4 `e2-standard-2`) |
| **Pod** | one running copy of a service; runs on a node |
| **Ring node** | one **Sensor Store pod** placed on the hash ring |
| **HPA** | adds/removes **pods** (Partition Manager 2→6) |
| **Cluster autoscaler** | adds/removes **nodes/VMs** (2→4) |
| **Deployment** | stateless, identical pods (Partition Manager) |
| **StatefulSet** | fixed names + own disk per pod (Sensor Store) |
| **Ring version** | goes up each time a node joins/leaves the ring |

---

## Short answers to basic questions

| Question | Answer |
|---|---|
| What is consistent hashing? | Nodes and sensors are hashed onto a circle. A sensor belongs to the next node clockwise. |
| Why not `hash % N`? | Every sensor's node depends on N, so changing N moves almost everything (~80%). On the ring a new node takes only the arc before it, ~1/N (~18%). |
| Why virtual nodes? | 100 spots per node spread data evenly. With 1 spot, one node got 62%. |
| Why 3 copies? | One node can die and nothing is lost. A write is OK when 2 of 3 confirm. |
| Node vs pod? | Node = VM. Pod = one running copy of a service, running on a node. |
| Why no HPA on Sensor Store? | It's stateful. An autoscaled pod wouldn't be on the ring; removing one loses its data. |
| Why did it stop at 6 pods? | `maxReplicas: 6`, our cost ceiling. |
| What does 300% CPU mean? | 3× the pod's CPU **request** (0.1 core), so ~0.3 core. |
| Where is the ring stored? | Firestore, collection `ring`, document `membership`. |
| Push or pull for Prometheus? | Pull: it scrapes each pod's `/metrics` every 15 s. |
| Why was the cluster list empty? | We destroy the cluster after each session to save credit. |

---

## Practice on your own

1. Ask Person 1 to start the cluster (`infra/scripts/up.sh`, ~20 min), or check that it's up: **Kubernetes Engine → Clusters**.
2. Read the opening line out loud.
3. Do steps 1 → 7 in order, saying each 🗣 line **out loud** while you click. Time yourself: aim for under 10 minutes.
4. Close this file and do it again from memory. Peek only when stuck.
5. Ask yourself 3 random questions from the table and answer them out loud.
6. When finished: tell Person 1, so they run `infra/scripts/down.sh`.
