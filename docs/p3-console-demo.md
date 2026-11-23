# Person 3: GCP Console demo (practice sheet)

Only my part: (f) consistent hashing, (c) GKE + HPA + k6, (h) monitoring and logging.
My services: **Partition Manager** and **Sensor Store**.
Everything is clicked in the console. The only typing is one block in **Cloud Shell** (the `>_` icon at the top right) to start the load test.

Marked ✅ = checked on the live console.

All steps below were checked live on 22 Nov 2026.

## The 10-minute run order (practise exactly this)

| # | Min | Console page | Point at | Key line |
|---|---|---|---|---|
| 0 | 0:30 | — | — | Opening line (below) |
| 1 | 1 | Kubernetes Engine → **Clusters** → `s1-gke` → Nodes | zone, node pool 2–4 | "Our GKE cluster, made by Terraform" |
| 2 | 1 | **Workloads**, namespace `s1` | partition-manager = Deployment 2/2, sensor-store = Stateful Set 4/4 | "Router + 4 ring nodes" |
| 3 | 1 | partition-manager → **Scaling** tab | HPA ✅, min 2, max 6, "3% out of 50%", 60 s cooldown | "Keeps CPU at 50%" |
| 4 | 1 | sensor-store → scroll to **Managed pods** + **Exposing services** | fixed names 0–3, headless service | "Name = place on the ring" |
| 5 | 0:30 | Kubernetes Resources → **Storage** | `data-sensor-store-0..3` Bound | "One disk per node" |
| 6 | 1 | **Firestore** → ring → membership | 4 nodes + version | "Routers re-read it every 5 s" |
| 6b | 2 | **Cloud Shell**: Step 4b (node join), then undo | 5/5 pods, Firestore 5 nodes, stats | "Only ~1/5 moved" |
| 7 | 0:30 | **Cloud Shell**: paste the Step 5 block | — | "k6 runs inside the cluster" |
| 8 | 2 | partition-manager → **Scaling**, Refresh | Pods 2 → 6, "218% out of 50%" | "HPA scaled to the max of 6" |
| 9 | 1 | *while k6 runs:* sensor-store → `sensor-store-1` → **Delete** → Refresh | new Created time, same name | "Same name, same disk" |
| 10 | 0:30 | Cloud Shell: `kubectl logs -n s1 job/k6-pm-write --tail=40` | checks 100%, ~150/s, p95 | "No write failed, even with a node down" |
| 11 | 1 | **Logs Explorer**, Warning query | "read failed, trying next replica" at the kill time | "Replica fallback, in the logs" |
| 12 | — | partition-manager → **Scaling** (a few min later) | back to 2 of 2 | "Scales back in" |
| 13 | *if asked* | **Grafana** (Cloud Shell, see the Grafana section) | 4 rows, equal bars per ring node | "Prometheus pulls metrics every 15 s" |

**After the demo:** in Cloud Shell `kubectl delete job k6-pm-write -n s1`, then tell Person 1 to run `infra/scripts/down.sh`.

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

### 2c. Click `sensor-store` ✅
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

## Step 4b. A 5th node joins the ring (the S1 concept, live)

**When:** right after Step 4 and **before** the k6 test. The HPA must be at 2 pods (a pod removed mid-rebalance would interrupt it), and the less data the faster the rebalance (copies one sensor at a time; k6 leaves ~5,000 sensors, which can take many minutes).

**Cloud Shell:**
```bash
pmctl() { kubectl exec -n s1 deploy/partition-manager -- python pmctl.py "$@"; }
pmctl write 2000 && pmctl stats
```
`stats` shows 4 nodes with roughly equal counts (each sensor counted on its 3 owners).

ArgoCD would scale the StatefulSet straight back to the 4 replicas in Git (it only ignores replicas on **Deployments**), so pause self-heal on the `s1` app first:
```bash
kubectl -n argocd patch application s1 --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":false}}}}'
```
1. Kubernetes creates the machine:
```bash
kubectl scale statefulset sensor-store -n s1 --replicas=5
kubectl rollout status statefulset sensor-store -n s1
```
2. My Partition Manager puts it on the ring and rebalances (the command waits until done):
```bash
pmctl add-node sensor-store-4 && pmctl stats
```

**Show in the console:**
- **Workloads → sensor-store**: **5/5** pods, `sensor-store-4` new.
- **Storage**: `data-sensor-store-4` Bound.
- **Firestore → ring → membership**: **version +1**, **5 nodes**.
- `pmctl stats`: every old node gave up a share, `sensor-store-4` received ~3/5 of the sensors (it's one of 3 owners), total still 3 copies per sensor.
- Grafana row 3: ring version, 5 nodes, sensors moved, 5 bars.

🗣 *"Kubernetes created the machine, but it holds nothing until my Partition Manager puts it on the ring. The rebalance copies only the sensors the new node now owns, switches the ring version in Firestore, waits until every router pod uses it, catches up, then deletes the old copies. Only about a fifth of the data moved."*

**Undo (in this order):**
```bash
pmctl remove-node sensor-store-4 && pmctl stats
kubectl scale statefulset sensor-store -n s1 --replicas=4
kubectl -n argocd patch application s1 --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":true}}}}'
```
Remove from the ring **first**, then scale down. Removing restores exactly the original placement (the ring is deterministic). The version goes up once more.

If asked why self-heal was paused: *"Git says 4 Sensor Store replicas. For the demo I paused ArgoCD's auto-revert on the app, otherwise it would remove the 5th node. A permanent change would be a Git commit."*

---

## Step 5. Autoscaling under load ⭐ ✅

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
3. The test runs ~5 min. A few minutes after it ends, replicas go back to **2**. ✅ Seen 22 Nov: back to **2 of 2**.

**Seen live on 22 Nov ✅:** Pods **6 of 6**, CPU utilization **256%** (top box) and **"218% out of 50%"** (HPA box), bar orange.
- The two CPU numbers differ a little because they're sampled at slightly different times. Both are far above 50%.
- Even at 6 pods CPU is still above 50%. The formula would ask for `ceil(6 × 218 ÷ 50)` = 27 pods, but **max is 6**, so it stays at 6.

🗣 *"k6 runs as a Job inside the cluster and sends about 150 writes per second. CPU goes past the 50% target, so the HPA adds pods, up to our maximum of 6. When the load stops it waits, so it doesn't flap, then scales back to 2."*

**k6 result (22 Nov, with `sensor-store-1` deleted in the middle) ✅** (Cloud Shell: `kubectl logs -n s1 job/k6-pm-write --tail=40`):
| | |
|---|---|
| Writes | **45,333** in 5 min = **151 per second** |
| Checks | **100%** (90,666 of 90,666): "status is OK" + "stored on a majority of replicas" |
| Latency | avg 187 ms, **p95 578 ms**, max 1.23 s |
| Virtual users | up to 40 |

🗣 *"45,000 writes in 5 minutes, about 150 per second, and 100% of checks passed, even though I killed a storage node in the middle. p95 latency was 578 milliseconds."*
**p95** = 95% of requests were faster than this.

Why k6 runs inside the cluster: from outside, a port-forward would send all traffic to one pod, so the new pods would get none.

---

## Step 6. A storage node fails ✅

**Clicks:** **Workloads** → **sensor-store** → **Managed pods** → click **`sensor-store-1`** → **Delete** (top) → confirm.
Go back to **sensor-store** → click **Refresh**. Within about a minute **`sensor-store-1` is back**, with the same name.

**Seen live on 22 Nov ✅** (done **during** the k6 load test, which is better):
- `sensor-store-0`, `-2`, `-3`: Created on **2:01 PM** (old)
- `sensor-store-1`: Created on **7:06 PM** ← brand new pod, **same name**

**"Why is Restarts 0?"** Restarts counts a *container* restarting inside the same pod. I deleted the whole pod, so the StatefulSet created a **new pod** with the same name and re-attached disk `data-sensor-store-1`. The **Created on** time is the proof.

**What makes Restarts go up?** Only the **container crashing inside the same pod** (app crash, out of memory, failed health check). Kubernetes restarts it in place, same pod, Restarts +1.
| You delete... | What happens | Restarts |
|---|---|---|
| the **pod** | new pod, same name, same disk | stays **0** (new pod) |
| the **disk** (PVC, in GKE **Storage**) | blocked while a pod uses it (stays "Terminating") | no change |
| a node from **Firestore** `ring/membership` | the **ring** changes, routers stop sending data to it. Pods untouched | no change. **Don't do this in the demo** |

Firestore holds **no disks**. It only holds the ring membership list. The disks are in **Kubernetes Engine → Storage**.

**Tip:** do this while k6 is running. Writes keep succeeding (2 of 3 copies is enough), and it creates the warnings shown in Step 7.

🗣 *"I killed a storage node. Kubernetes recreated it with the same name and the same disk. No data was lost meanwhile: each reading has 3 copies, writes only need 2 of the 3 to confirm, and reads fall back to the next replica."*

### 6b. Proving "all writes stayed green while a node was dead"

Note the time you click Delete (e.g. 19:02). Then show these 3 proofs:

**Proof 1, the k6 summary (strongest).** Cloud Shell, after k6 finishes:
```bash
kubectl logs -n s1 job/k6-pm-write --tail=20
```
Point at the **green ✓** lines:
- `✓ status is OK` and `✓ stored on a majority of replicas`. A failed write would show **✗** in red.
- `✓ checks: 100.00% 90666 out of 90666`. Every single write passed, including the ones during the kill.

🗣 *"Every write is checked twice: the call succeeded, and the data was stored on a majority of replicas, 2 of 3. 100% passed, including the minutes when sensor-store-1 was dead."*

**Proof 2, the Job status in the console.** **Workloads** → row **`k6-pm-write`** (Type: Job) → Status **OK / Completed**.
The script has **thresholds**: checks must be above 95% and p95 under 1 s. If a threshold breaks, k6 exits with an error and the Job shows **Failed**. Green = the thresholds passed.

**Proof 3, no errors in the logs.** **Logs Explorer**, Last 1 hour:
```
resource.type="k8s_container"
resource.labels.namespace_name="s1"
resource.labels.container_name="partition-manager"
severity>=ERROR
```
→ **No results** (or none around the kill time). Partition Manager logs `request failed` at ERROR level whenever it rejects a request, so zero means no write was rejected.
Then change `ERROR` to `WARNING` to show the node **was** really down: the `read failed, trying next replica` warnings at exactly the kill time.

🗣 *"Warnings, yes: the node was down and my router noticed. Errors, none: no request failed, because it fell back to the other replicas."*

**Live while it runs (optional):** in Cloud Shell, `kubectl logs -n s1 job/k6-pm-write -f` shows the completed-writes counter still climbing right after the kill, with `0 interrupted iterations`.

---

## Step 7. Centralised logging ✅

**Clicks:** search bar → **Logs Explorer** → time **Last 1 hour** → paste the query → **Run query**.

```
resource.type="k8s_container"
resource.labels.namespace_name="s1"
resource.labels.container_name="partition-manager"
severity>=WARNING
```

**Exact clicks ✅:** top search bar → type **logs explorer** → open **Logs Explorer** (under Observability → Logging) → top right time button → **Last 1 hour** → make sure **Show query** toggle is on → paste the query in the black box → **Run query** (blue, top right).

**Seen live on 22 Nov ✅:** 4 results, severity **Warning** (yellow !), all from `partition-manager`:
`read failed, trying next replica` at 19:02–19:06, exactly while `sensor-store-1` was down.
- **Timeline** (the orange bars) = when the warnings happened.
- Click the **▸** on a row to open it. You'll see the JSON log with `node: sensor-store-1` and the error.
- On other runs you may also see `replica write failed` (with `node` and `sensor_id`). Same idea, for writes.

Where do reads come from during the test? k6 only writes. The reads come from **Irrigation Controller**, which keeps asking Partition Manager for the latest reading of each sensor.
**All services in one query ✅:**
```
resource.type="k8s_container"
resource.labels.namespace_name="s1"
jsonPayload.service:*
```
Seen on 22 Nov: **272 results** in 1 hour. Left **Fields** panel → **Container name**: `irrigation-controller` 254, `partition-manager` 16, `sensor-store` 2. Only services that logged in that hour show up.
Severity icons: blue **i** = Info (e.g. "control cycle"), yellow **!** = Warning (e.g. "alert published").

🗣 *"One query searches every service. On the left, Cloud Logging lets me break the results down by container name."*

🗣 *"Every service logs one JSON object per line, and Cloud Logging collects them. Here Partition Manager logged 'read failed, trying next replica' exactly while sensor-store-1 was down. That's the replica fallback working: the read didn't fail, it went to the next copy. We picked Cloud Logging because Flink on Dataproc and the Cloud Function are outside GKE, and it collects all of them in one place."*

---

## Grafana (only if he asks)

Grafana runs inside the cluster, so it has no page in the GCP console. Open it through **Cloud Shell**. ✅ walked live on 23 Nov.

**Open it (one time per session):**
1. Cloud Shell: stop ArgoCD from undoing the next change (it would revert it):
```bash
kubectl -n argocd patch application monitoring --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":false}}}}'
```
2. Start the tunnel:
```bash
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:3000
```
3. Press **Ctrl+C**. Trust Cloud Shell's preview address (Cloud Shell keeps it in `$WEB_HOST`; check with `echo "3000-$WEB_HOST"`. If that prints only `3000-`, copy the hostname from the preview tab's address bar instead):
```bash
kubectl set env deploy/monitoring-grafana -n monitoring -c grafana GF_SECURITY_CSRF_TRUSTED_ORIGINS="3000-$WEB_HOST"
```
4. Wait for the new Grafana pod and reopen the tunnel, then **Web Preview** (eye icon) → **Change port** → `3000`:
```bash
kubectl rollout status deploy/monitoring-grafana -n monitoring && kubectl port-forward -n monitoring svc/monitoring-grafana 3000:3000
```
"**origin not allowed**" at login = step 3 didn't match the address. Not a wrong password.
5. Refresh the preview tab → log in **`admin` / `admin`** → ☰ **Dashboards** → **S1 Smart Agriculture: partitioning and scaling** → time range (top right) **Last 30 minutes**, refresh **10s**.

Why step 4: Grafana refuses logins from an unknown web address. Cloud Shell's preview address is unknown to it, so we tell Grafana to trust it.

**The dashboard: 15 panels in 4 rows.** Data comes from **Prometheus**, which scrapes each pod's `/metrics` every 15 s.

| Row | Panel | What to say |
|---|---|---|
| **1 Traffic** (golden signals) | Requests per second | "~150 per second during k6" |
| | Error rate % | "Failed requests 0%. Failed replica writes jump only while a node is dead" |
| | WriteReading latency p50/p95/p99 | "p95 under 1 s" |
| **2 Scaling** | Partition Manager pods (current / desired / max) | "2 → 6 → 2. Desired goes above 6, the max line holds it" |
| | CPU per pod (millicores, target 50m) | "50m = 50% of the 0.1-core request" |
| **3 Partitioning** | Sensors stored per ring node (bars) | "Four almost equal bars = consistent hashing spreading data evenly" |
| | Writes per second per ring node | "Four almost identical lines" |
| | Ring (version, nodes, rebalance events, sensors moved) | "Version 5, 4 nodes" |
| **4 Cluster health** | App pods running / not ready / restarts | "All running" |
| | Machine CPU %, Machine memory % | "The VMs themselves" |

**For live lines:** start the k6 test (Step 5 block) in a **second Cloud Shell tab** after opening Grafana, and kill a node (Step 6) about 2 minutes in.

**What reacts when you kill the node:** "failed replica writes %" bumps up while failed requests stay at 0; that node's line in "Writes per second per ring node" dips; "App pods" dips and comes back.

🗣 *"This is Grafana. The data comes from Prometheus, which pulls each pod's metrics every 15 seconds. Row 1 is traffic, row 2 is autoscaling, row 3 is my consistent hashing, row 4 is cluster health."*

**Is pausing self-heal on `monitoring` risky?** No.
- It only affects the `monitoring` app (Prometheus + Grafana). The `s1` app (all services) keeps self-heal on.
- Auto-sync from Git still works; only "revert manual changes" is paused, so the one Grafana setting stays.
- The ArgoCD tile `monitoring` shows **OutOfSync** (expected) but **Healthy**.
- A killed pod **still comes back**: that's Kubernetes (the StatefulSet wants 4 pods), not ArgoCD.
- `down.sh` + `up.sh` recreate the Applications with self-heal on. To undo now:
```bash
kubectl -n argocd patch application monitoring --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":true}}}}'
```

**After the demo:** `kubectl delete job k6-pm-write -n s1`.

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
| What race condition did you fix? | **Lost update** on the ring membership. Two router pods change the ring at the same time, both read version 5, both write version 6, and one change silently overwrites the other. Fix: **compare-and-set**. Save only if the stored version is still the one I read, inside a Firestore **transaction**. The slower change is rejected with `ABORTED` and can be run again. (Commit `c6133ec`, 22 Nov.) |
| Why was the cluster list empty? | We destroy the cluster after each session to save credit. |

---

## Practice on your own

1. Ask Person 1 to start the cluster (`infra/scripts/up.sh`, ~20 min), or check that it's up: **Kubernetes Engine → Clusters**.
2. Read the opening line out loud.
3. Do steps 1 → 7 in order, saying each 🗣 line **out loud** while you click. Time yourself: aim for under 10 minutes.
4. Close this file and do it again from memory. Peek only when stuck.
5. Ask yourself 3 random questions from the table and answer them out loud.
6. When finished: tell Person 1, so they run `infra/scripts/down.sh`.

---

## Design document, Part C (pages 13–24): numbers to remember

| Section | Remember |
|---|---|
| 2 Consistent hashing | `% N` moved **80.2%**, ring **18.4%** (minimum 20%). 1 spot: one node got **62%** (6,204 of 10,000). 100 spots: ~2,500 each. 1 copy + crash: **74%** readable; 3 copies: **100%**; 3 of 4 dead: 71.8%. **MD5** (deterministic, not for security). Partition key **sensor_id** (not farm_id: hot keys). **22 tests** pass (9 unit + 13 end-to-end). |
| 3.2 Write/read | Write to 3 in parallel, OK when **2 of 3** confirm **and the primary answered** (W=2, R=1, read-your-writes). Read primary → next replica. **Router, not lookup.** |
| 3.3 Membership | `{version, nodes}` in Firestore, re-read every **5 s**. |
| 3.4 Rebalance | 4 steps: **Copy → Switch + wait → Catch up → Clean up**. Batches of 2,000 (gRPC 4 MB limit). Idempotent (`INSERT OR REPLACE`), `pmctl repair`. Earlier version left **26% misplaced** silently; final: **0**. GKE join: **110 of 600** copies moved (18%), none lost; ring v1 → v2 → v3. |
| 4.1 Kubernetes | Deployment / StatefulSet / headless Service / CPU requests / graceful shutdown / PDBs / topology spread / NetworkPolicy. |
| 4.2 HPA | MAPE loop: Monitor (metrics-server) → Analyse (vs 50%) → Plan (`ceil(pods × CPU ÷ target)`) → Execute (2–6). 60 s scale-down window. |
| 4.3 Laptop | 46,480 writes, ~155/s, 0 failed, p95 **377 ms**. 341% → `ceil(2×341÷50)=14`, capped at 6. |
| 4.4 GKE (16 Nov) | 42,401 writes, ~141/s, 0 failed, p95 **777 ms**. PM 2→5→6→2. Telemetry 74% CPU, 2→3→4→2. Node failure: pod back in **69 s**, **213** "replica write failed" warnings. |
| 5 Monitoring | Prometheus = **pull**, every **15 s**, ServiceMonitors. Grafana: **15 panels, 4 rows** (Traffic, Scaling, Partitioning, Cluster health). Logs: JSON per line, **1,541** entries. Loki rejected (Dataproc + Cloud Function are outside GKE). |
| 7 Limitations | 5 s disagreement window · no hinted handoff · slow sequential rebalance · rebalance inside an autoscaled pod · ListSensors 4 MB · no auth on AddNode · not machine-aware placement · **lost update (fixed: compare-and-set)** · counters in pod memory. |

**Why the ring is at version 5:** GKE join test v1 → 2 (add) → 3 (remove), then the compare-and-set test v3 → 4 → 5.

---

## Concepts explained (study notes)

### Rebalancing when a node joins (4 steps)
Example: sensor `farm1-plot1-s1` is on **[node0, node1, node2]**. After adding node4 its owners become **[node4, node1, node2]**: node4 gains a copy, node0 loses one. Only ~1/5 of sensors change like this.
Complication: Partition Manager pods re-read the ring only **every 5 s**, so for a few seconds some use the old ring and some the new.

1. **Copy:** copy every sensor whose owners gain a node to that node (`farm1-plot1-s1` → node4). All routers are still on the old ring, nothing breaks.
2. **Switch + wait:** save the new ring to Firestore (version + 1, compare-and-set), then **wait 6 s** so every router pod has it.
3. **Catch up:** re-scan everything and copy what slow routers wrote to old owners during the wait, plus brand-new sensors.
4. **Clean up:** only now delete copies from nodes that no longer own them (node0). Only if the copy really arrived.

**Where do reads go during the 6-second wait?** Each router reads from the primary **on its own ring**: old-ring pods → node0, new-ring pods → node4. **Both have the data** (copied before the switch, deleted only after). Side effect: for a few seconds a read can return the **previous** reading instead of the newest one. Nothing is lost; step 3 fixes it. That's known limitation #1 ("routers can disagree for up to 5 s").

**Why the order matters:** the first version had no wait and no full re-scan → zero errors but **26% of sensors misplaced**. Now: **0**.

🗣 *"Copy the sensors the new node owns, switch the ring version and wait until every router has it, copy what was written through the old ring meanwhile, and only then delete old copies."*

### The race condition: compare-and-set (notebook analogy)
| Analogy | Real thing |
|---|---|
| Shared notebook | **Firestore** |
| The one page | document **`ring/membership`** |
| Page number | field **`version`** |
| List on the page | field **`nodes`** (`sensor-store-0` … `-3`) |
| People reading every 5 s | **Partition Manager pods** |
| "Add node4" / "Remove node3" | `pmctl add-node sensor-store-4` / `pmctl remove-node sensor-store-3` (gRPC **AddNode** / **RemoveNode**) |
| "Still the page I read?" | **compare-and-set** (`save_if` in `membership.py`) |
| Check and write in one go | **Firestore transaction** |
| "Rejected, try again" | gRPC **`ABORTED`** + WARNING `membership change rejected` |

**Bug:** two pods both read version 5, both write version 6, the second overwrites the first (node4 vanishes). A **lost update**.
**Fix:** save only if the version is still 5. The slower pod sees 6, is rejected with ABORTED, the admin re-runs it, and it writes version 7. Both changes kept.
Commit `c6133ec` (22 Nov), test `test_concurrent_ring_change_is_rejected_not_lost`. Testing it took the ring 3 → 4 → 5, which is why Firestore shows **version 5**.

🗣 *"Two Partition Manager pods could change the ring at the same time and overwrite each other. Now the save is a compare-and-set in a Firestore transaction: it only writes if the version is still the one it read. Otherwise it returns ABORTED and you run it again."*

### Where things live in the code (look at branch `main`)
| Thing | File |
|---|---|
| Hash ring: MD5, 100 virtual nodes, 3 owners (`get_nodes`) | `services/partition-manager/ring.py` |
| 80% vs 18% demo | `services/partition-manager/demo.py` |
| Ring membership + `save_if` (compare-and-set) | `services/partition-manager/membership.py` |
| Router: re-read every 5 s (`refresh`), `WriteReading` (2 of 3), `GetLatest` (fallback), `_change` (4-step rebalance), `MembershipConflict`, JSON `log()` | `services/partition-manager/server.py` |
| Copy in batches of 2,000 | `services/partition-manager/transfer.py` |
| Admin tool | `services/partition-manager/pmctl.py` |
| Tests (9 + 13) | `test_ring.py`, `test_integration.py` |
| Storage node (SQLite): `Put`, `GetLatest`, `ListSensors`, `DeleteSensor` | `services/sensor-store/server.py` |
| gRPC contracts | `contracts/partition_manager.proto`, `sensor_store.proto`, `reading.proto` |
| Deployment / HPA | `k8s/base/partition-manager/deployment.yaml`, `hpa.yaml` |
| StatefulSet / headless Service / NetworkPolicy | `k8s/base/sensor-store/statefulset.yaml`, `service.yaml`, `networkpolicy.yaml` |
| k6 test (checks, thresholds) / runs as a Job | `loadtest/pm-write.js`, `loadtest/k6-gke.yaml` |
| Prometheus + Grafana settings / what to scrape / dashboard | `observability/kube-prometheus-stack-values.yaml`, `servicemonitors.yaml`, `dashboards/make_dashboard.py` |
