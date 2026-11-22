# P3 Viva Runbook: S1 Smart Agriculture

16 Nov 2026 · Mrudul (Person 3)

## How to use this runbook

The demo takes about 12 minutes: 10 minutes live on your laptop, then 2 minutes of GKE screenshots. The GKE cluster is torn down between sessions, so the live part runs on Docker Desktop Kubernetes and the GKE part is shown from the 16 Nov screenshots.

Your tasks are (f) consistent hashing, (c) GKE + autoscalers + load test, and (h) Prometheus, Grafana and logging. Your services are Partition Manager and Sensor Store.

| Part | What you show | Where | Time |
| --- | --- | --- | --- |
| 1 | The hashing concept (`demo.py`) | Laptop, no cluster | 1 min |
| 2 | The system running on Kubernetes | Laptop cluster | 1 min |
| 3 | Writes and where data lives | Laptop cluster | 1 min |
| 4 | Autoscaling under load (k6 + Grafana) | Laptop cluster | 5 min |
| 5 | A node joins the ring | Laptop cluster | 2 min |
| 6 | A node fails | Laptop cluster | 1 min |
| 7 | The same system on GKE | Screenshots | 2 min |

Every command below is for **PowerShell, opened in the repo folder** (`s1-smart-agriculture`), unless the step says otherwise. Each step has the command, what it does, what you should see, and what to say.

The laptop commands come from `docs/p3-demo-script.md`, `k8s/README.md` and `observability/README.md`. Rehearse once before the viva.

## Setup the day before

Do this once, the evening before, and rehearse the whole demo at least once. It takes about 20 minutes.

**Tools you need on the laptop:** Docker Desktop with Kubernetes enabled (Settings → Kubernetes → Enable), `kubectl`, `helm`, `k6`, and Python with the Partition Manager requirements installed. Check them:

```powershell
docker version; kubectl version --client; helm version; k6 version; python --version
```

**1. Get the latest code.**

```powershell
git checkout main; git pull
```

**2. Point kubectl at the laptop cluster.** This matters: your kubectl was last pointed at GKE, which no longer exists, so every command would fail.

```powershell
kubectl config use-context docker-desktop
```

```powershell
kubectl get nodes
```

You should see one node, `docker-desktop`, with status `Ready`.

**3. Build the two images.** Kubernetes on Docker Desktop uses the same local images.

```powershell
docker compose build sensor-store-0 partition-manager
```

**4. Deploy the app.** This creates the `s1` namespace, 4 Sensor Store pods, 2 Partition Manager pods, the autoscaler and metrics-server.

```powershell
kubectl apply -k k8s/local
```

```powershell
kubectl get pods -n s1 -w
```

Wait until all 6 pods show `1/1 Running`, then press Ctrl+C.

**5. Install Prometheus and Grafana.**

```powershell
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
```

```powershell
helm repo update
```

```powershell
helm install monitoring prometheus-community/kube-prometheus-stack --version 92.14.1 -n monitoring --create-namespace -f observability/kube-prometheus-stack-values.yaml
```

```powershell
kubectl apply -f observability/servicemonitors.yaml
```

```powershell
kubectl apply -f observability/dashboards/s1-dashboard.yaml
```

If `helm install` says the release already exists, it is installed from an earlier session and you can skip it.

**6. Check Grafana.** Open http://localhost:3000, log in with `admin` / `admin`, and open the dashboard "S1 Smart Agriculture: partitioning and scaling".

**7. Install the Python packages for the offline demo.**

```powershell
pip install -r services/partition-manager/requirements.txt
```

**8. Put the GKE screenshots in one folder** you can open quickly, in order: `01` to `15`.

You can leave the cluster running overnight. If you restart the laptop, start Docker Desktop and wait for the pods to return to `Running`.

## Five minutes before the examiner

Open **two PowerShell windows** in the repo folder. Window 1 is for kubectl and pmctl. Window 2 is only for k6.

**In window 1, run these checks:**

```powershell
kubectl config use-context docker-desktop
```

```powershell
kubectl get pods -n s1
```

You should see 2 `partition-manager` pods and 4 `sensor-store` pods, all `1/1 Running`.

```powershell
kubectl get pods -n monitoring
```

All should be `Running`.

**Make the `pmctl` shortcut** (window 1). It runs the admin tool inside a Partition Manager pod, so you can type `pmctl ring` and not the long command:

```powershell
function pmctl { kubectl exec -n s1 deploy/partition-manager -- python pmctl.py @args }
```

```powershell
pmctl ring
```

You should see `version 1 | 4 nodes | vnodes=100 replicas=3` and the four node names. If it shows 5 nodes from a rehearsal, reset first (last section of this doc).

**Open in the browser:**

- Grafana at http://localhost:3000, dashboard "S1 Smart Agriculture", time range **Last 15 minutes**, refresh **10s**.
- The folder with your GKE screenshots.
- `docs/p3-concept-scaling-monitoring.md` on GitHub, in case the examiner asks about the design.

## Part 1: The concept, offline (1 minute)

This shows why consistent hashing is needed, with no cluster involved. Run in window 1:

```powershell
cd services\partition-manager
```

```powershell
python demo.py
```

```powershell
cd ..\..
```

**What it does:** it places sensors on nodes two ways, plain `hash % N` and the hash ring, then adds a fifth node and counts how many sensors had to move. It then shows the effect of virtual nodes and of keeping 3 copies.

**What you should see:** three parts. Part 1 compares the sensors moved. Part 2 compares 1 spot per node with 100 spots per node. Part 3 shows a node crashing with no data lost.

**Say:** "With `hash % N`, adding a fifth node moved about 80% of the sensors. My ring moved about 18%, all of it to the new node, which is close to the minimum of 1/5. Part 2 is virtual nodes: with one spot per node, one node got 62% of the data; with 100 spots every node is close to fair. Part 3 is replication: with 3 copies, a crashed node loses nothing."

Read the exact percentages off your screen when you say this, in case they differ slightly from the ones written here.

## Part 2: The system running on Kubernetes (1 minute)

Run in window 1:

```powershell
kubectl get pods -n s1
```

**What it does:** lists the running pods of the app. You should see 2 `partition-manager-...` pods and `sensor-store-0` to `sensor-store-3`.

```powershell
kubectl get hpa -n s1
```

**What it does:** shows the Horizontal Pod Autoscaler: current CPU against the 50% target, minimum 2 pods, maximum 6, and 2 replicas now.

**Say:** "Partition Manager is a Deployment of identical stateless pods, with an autoscaler from 2 to 6. Sensor Store is a StatefulSet: each pod has a fixed name, which is its name on the ring, and its own disk. Sensor Store has no autoscaler, because it is stateful. It scales by adding a node to the ring."

## Part 3: Writes and where data lives (1 minute)

Run in window 1:

```powershell
pmctl write 2000
```

**What it does:** sends 2,000 fake sensor readings through Partition Manager, which stores each on 3 Sensor Store nodes.

```powershell
pmctl where farm1-plot1-s1
```

**What it does:** asks the ring which 3 nodes hold this sensor. The first one listed is the primary. **Note the primary's name; you need it in Part 6.**

```powershell
pmctl stats
```

**What it does:** shows how many sensors each node stores.

**Say:** "Every reading goes to its 3 nodes in parallel and counts as stored once 2 confirm, which is a majority. `where` shows a sensor's primary and two replicas. The stats add up to 3 copies per sensor, spread evenly across the nodes."

## Part 4: Autoscaling under load (5 minutes, the main event)

**Window 1:** start watching the autoscaler, so the examiner sees it change live.

```powershell
kubectl get hpa -n s1 -w
```

**What it does:** prints a new line every time the autoscaler's CPU reading or pod count changes. Leave it running.

**Window 2:** start the load test.

```powershell
k6 run loadtest/pm-write.js
```

**What it does:** k6 sends gRPC `WriteReading` calls to Partition Manager at `localhost:50051`. It ramps to 40 virtual users over 2.5 minutes, holds for 2 minutes, then stops. Total 5 minutes.

**What you should see in window 1:** CPU climbs far above 50%, and `REPLICAS` jumps from 2 to 6 within about a minute.

**While it runs, switch to Grafana and point at each row:**

| Row | Say |
| --- | --- |
| Traffic | "Requests climb to about 150 per second, the error rate stays at 0, and this is p95 latency." |
| Scaling | "CPU passes the 50% target, so the autoscaler adds pods. It goes from 2 straight to 6: the formula `ceil(2 × 341 ÷ 50)` asks for 14, and 6 is our cost ceiling." |
| Partitioning | "Writes per ring node: four almost identical lines. That is the hash ring spreading load evenly." |

Use the CPU percentage you see on screen in place of 341 if it differs.

**When k6 ends**, it prints a summary. Point at `checks` (should be 100%) and the p95 duration.

**Say:** "Scale-down waits 60 seconds to avoid flapping, then returns to 2 pods."

Wait in window 1 until `REPLICAS` is back to 2, then press **Ctrl+C** to stop the watch. Part 5 needs the pod count to be back at 2 first.

**Why k6 reconnects every 200 calls**, if asked: gRPC keeps one long connection and Kubernetes balances connections, not requests. Without reconnecting, the new pods would get no traffic.

## Part 5: A node joins the ring (2 minutes)

This is the S1 concept live: a new node takes over only its share of the data. Run in window 1, after the autoscaler is back to 2 pods.

```powershell
kubectl scale statefulset sensor-store -n s1 --replicas=5
```

**What it does:** asks Kubernetes for a fifth Sensor Store pod, `sensor-store-4`, with its own new disk.

```powershell
kubectl get pods -n s1 -w
```

Wait until `sensor-store-4` shows `1/1 Running`, then press Ctrl+C.

```powershell
pmctl add-node sensor-store-4
```

**What it does:** puts the new node on the ring and rebalances. It copies the sensors the new node now owns, switches every router pod to ring version 2, catches up on anything written meanwhile, then deletes the old copies.

```powershell
pmctl stats
```

**What you should see:** 5 nodes, each with a similar count. Every old node gave up a share; the new node holds about as much as the others.

**Say:** "Kubernetes created the machine, but it holds nothing until my Partition Manager puts it on the ring. The rebalance copies only the sensors the new node now owns, switches every router pod to ring version 2, then deletes the old copies. Only about one fifth of the data moved, not all of it."

**Point at Grafana, Partitioning row:** ring version 2, 5 ring nodes, sensors moved above 0, and 5 even bars.

## Part 6: A node fails (1 minute)

Run in window 1:

```powershell
pmctl where farm1-plot1-s1
```

**What it does:** shows the sensor's 3 nodes again. The first one is the primary. The ring changed in Part 5, so read the name off the screen now.

```powershell
kubectl delete pod sensor-store-1 -n s1
```

**What it does:** kills that node. **Replace `sensor-store-1` with the primary from the line above.**

```powershell
pmctl latest farm1-plot1-s1
```

**What it does:** reads the sensor's latest reading. It should still return moisture and temperature, although the primary is down.

```powershell
kubectl get pods -n s1
```

**What you should see:** the deleted pod is already back, with the same name and a young age.

**Say:** "I killed the primary. The read still worked because Partition Manager fell back to the next replica. Kubernetes also recreated the pod with the same name and the same disk, so its data is still there. Writes kept working too, because they only need 2 of the 3 copies."

## Part 7: The same system on GKE (2 minutes, screenshots)

**Say first:** "The GKE cluster is created by Terraform for each work session and destroyed afterwards to save credit. These are from our session on 16 November, on project `s1-agri-ams-686974`, deployed by ArgoCD from the `main` branch. I ran it from Google Cloud Shell."

Show the screenshots in this order. The screenshots are kept outside the repo. Two of the files have unnumbered names: `before picture.png` is the "before" shot, and `Screenshot 2026-11-16 172447.png` is the autoscaler peak.

| Show | What it shows | Say |
| --- | --- | --- |
| `before picture.png` | Both autoscalers idle: 2 pods each, CPU 4% and 6% | "Two autoscalers on GKE: Partition Manager and Telemetry Ingestion, both 2 to 6 pods at a 50% CPU target." |
| `02-k6-running.png` | k6 running inside the cluster, 40 virtual users | "I ran k6 as a Kubernetes Job inside the cluster. A port-forward would send all traffic to one pod, so the new pods would get none." |
| `Screenshot 2026-11-16 172447.png` | Partition Manager CPU up to 292%, pods 2 → 5 → 6 | "CPU went to 292% of the request and the autoscaler went from 2 to 5 to 6 pods, the maximum." |
| `03-k6-summary.png` | 42,401 writes, checks 100% (84,802 of 84,802), p95 777 ms | "42,401 writes in 5 minutes, about 141 per second, none failed. p95 latency was 777 ms, under the 1 second threshold." |
| `04-grafana-traffic-scaling.png` | About 150 requests per second, 0% errors, pods 2 → 6 → 2 | "The same test in Grafana: the request rate, zero errors, and the pod count going up and coming back." |
| `05-grafana-partitioning.png` | Sensors per node 3.52K to 3.91K, equal write rates, ring version 1 with 4 nodes | "The four ring nodes got almost identical write rates and hold nearly equal numbers of sensors. That is consistent hashing with virtual nodes." |
| `06-hpa-after.png` | Both autoscalers back at 2 pods | "After the load, it scaled back in to 2." |
| `07-telemetry-hpa-peak.png` | Telemetry Ingestion CPU 74%, pods 2 → 3; Partition Manager at 4 | "The second autoscaler. I sent readings through the public load balancer with our sensor simulator. Telemetry Ingestion reached 74% CPU and scaled out, and Partition Manager scaled again because every reading goes on to it." |
| `08-hpa-final.png` | Both back to 2 pods | "And both returned to 2." |
| `10`, `11`, `12` | `sensor-store-1` was primary; deleted; read still returned moisture 38.6%; pod back in 69 s | "The node failure test on GKE: I deleted the primary, the read still worked from a replica, and Kubernetes brought the pod back in about 69 seconds." |
| `09-cloud-logging-all-services.png` | 1,541 JSON log entries from the `s1` namespace | "Centralised logging: every service writes one JSON object per line and Cloud Logging collects them. One query searches all services." |
| `13-cloud-logging-replica-failure.png` | 213 `replica write failed` warnings | "These are the 213 warnings Partition Manager logged while that node was down, each with the node and the sensor ID." |
| Node join on GKE (22 Nov, no screenshot needed: say the numbers) | Before 139, 153, 156, 152 = 600 copies; after adding `sensor-store-4`: 111, 123, 130, 126, 110 = 600; after removing it: 139, 153, 156, 152 again | "On GKE I added a fifth node: only 110 of 600 copies moved, 18%, all onto the new node, and none were lost. Removing it put every copy back exactly where it was, because the ring is deterministic." |
| `14-cloud-logging-dataproc.png` | 5,157 Dataproc cluster log entries in one hour | "Logs from the Dataproc cluster that runs Flink arrive in the same place, outside GKE." |
| `15-farm-analytics-flink-result.png` | `farm1`: 192 readings from 40 sensors in one 1-minute window, avg moisture 33.3% | "End to end: readings sent through Telemetry Ingestion went through Kafka and Flink and appear in Farm Analytics about 12 seconds after the window closed." |

**Be honest about these if asked:**

- Telemetry Ingestion needed 7 simulator processes to pass 50% CPU. One Python process could not load it enough.
- Sensor IDs are logged only on warnings, not on every successful write. Flink job logs are under `resource.type="cloud_dataproc_job"` (filter by job id), not `cloud_dataproc_cluster`; Alert Service logs are under `resource.type="cloud_run_revision"`, service `alert-service`. Both were checked on 22 Nov.

The file `08-telemetry-hpa-after.png` shows lines from before the peak, not after it. Leave it out, and use `08-hpa-final.png` for the end state.

## If the examiner wants GKE live

This only works if Person 1 has started the cluster for the viva (`infra/scripts/up.sh`, about 15 to 20 minutes). Agree on this with Person 1 beforehand. Your laptop blocks the GKE login plugin, so use **Google Cloud Shell**: open https://console.cloud.google.com, pick project `s1-agri-ams-686974`, and click the `>_` icon at the top right. Run these there, not in PowerShell.

**1. Connect and check.**

```bash
gcloud container clusters get-credentials s1-gke --zone us-central1-a --project s1-agri-ams-686974
```

```bash
kubectl get pods -n s1
```

```bash
kubectl exec -n s1 deploy/partition-manager -- python pmctl.py ring
```

You should see 14 pods `Running` and a ring with 4 nodes. On GKE the ring membership is a Firestore document, not a file.

**2. Get the repo** (skip if the folder is still there from last time; then run `cd s1-smart-agriculture && git pull`).

```bash
git clone https://github.com/MrudulDhaduk/s1-smart-agriculture.git && cd s1-smart-agriculture
```

**3. Watch the autoscalers** in a second Cloud Shell tab (the **+** button).

```bash
kubectl get hpa -n s1 -w
```

**4. Run the load test inside the cluster** (first tab).

```bash
kubectl create configmap k6-script -n s1 --from-file=loadtest/pm-write.js
```

```bash
kubectl create configmap k6-contracts -n s1 --from-file=contracts/partition_manager.proto --from-file=contracts/reading.proto
```

```bash
kubectl apply -f loadtest/k6-gke.yaml
```

```bash
kubectl logs -n s1 job/k6-pm-write -f
```

To run it a second time, delete the old job first: `kubectl delete job k6-pm-write -n s1`.

**5. Load Telemetry Ingestion** through the public address. Get the address with `kubectl get ingress s1-public -n s1`, then replace `<ingress-ip>`:

```bash
for i in 1 2 3 4 5 6 7; do python3 tools/simulate_sensors.py --url http://<ingress-ip> --rate 500 --batch 50 --duration 240 > /dev/null 2>&1 & done; wait
```

**6. Grafana** (third tab). Grafana rejects queries from the Cloud Shell address until you trust it, and ArgoCD would undo that change, so pause its self-healing for the monitoring app first.

```bash
kubectl -n argocd patch application monitoring --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":false}}}}'
```

```bash
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:3000
```

Click **Web Preview** (eye icon) → **Change port** → `3000`. Copy the hostname from the browser address bar (the part between `https://` and the next `/`). Press Ctrl+C, then run this with your hostname in place of `<hostname>`:

```bash
kubectl set env deploy/monitoring-grafana -n monitoring -c grafana GF_SECURITY_CSRF_TRUSTED_ORIGINS=<hostname>
```

```bash
kubectl rollout status deploy/monitoring-grafana -n monitoring
```

Start the port-forward again and refresh the browser tab. Log in with `admin` / `admin`.

**7. Cloud Logging.** Open https://console.cloud.google.com/logs/query?project=s1-agri-ams-686974, set the range to the last hour, and run:

```
resource.type="k8s_container"
resource.labels.namespace_name="s1"
jsonPayload.service:*
```

Tell Person 1 when you finish, so they can tear the cluster down.

## Viva questions and short answers

| Question | Short answer |
| --- | --- |
| Why not `hash % N`? | When N changes, almost every key moves: (N−1)/N of them. The ring moves about 1/N, the minimum. |
| Why virtual nodes? | With one spot per node, each node's share is one random gap. 100 spots average the luck out, and a joining node takes a little from everyone. |
| Why MD5 and not Python `hash()`? | `hash()` changes every time Python starts, and all router pods must agree. MD5 is deterministic. It is not used for security. |
| How are writes and reads done? | A write goes to all 3 replica nodes and succeeds when 2 confirm. A read asks the primary; if it is down, the next replica. |
| What if 2 nodes die? 3 nodes? | 3 copies survive any 2 failures. A third can lose data: about a quarter of sensors with only 4 nodes. |
| Is Partition Manager a router or a lookup service? | A router. Callers send reads and writes to it and it forwards them, so callers never need to know the ring. |
| Where does the ring membership live? | One record, `{version, nodes}`. In Firestore on GKE, a shared file on the laptop. Every router pod re-reads it every 5 seconds. It cannot live in pod memory because the autoscaler adds and removes pods. |
| Why no autoscaler on Sensor Store? | It is stateful. An autoscaled pod would not be on the ring, and removing one would delete a partition. It scales by adding ring nodes and rebalancing. |
| Which two services have autoscalers? | Partition Manager and Telemetry Ingestion. Both are stateless. |
| What does 341% CPU mean? | Percent of the pod's CPU request (0.1 core): about 0.34 of a core. |
| Why did it stop at 6 pods? | `maxReplicas: 6` is our cost ceiling. Scale-up is immediate; scale-down waits 60 seconds to avoid flapping. |
| Why a headless Service for Sensor Store? | The router must reach one specific ring node by name, not a random pod. |
| Why was GKE latency higher than the laptop? | p95 was 777 ms on GKE against 377 ms on the laptop. My explanation is small nodes, new pods starting, and Sensor Store pods on other machines. I did not measure the cause. |
| Why Cloud Logging and not Loki? | Flink runs on Dataproc and the Alert Service is a Cloud Function, both outside GKE. Cloud Logging collects all three natively. |
| Prometheus: push or pull? | Pull. It scrapes each pod's `/metrics` endpoint every 15 seconds. ServiceMonitors tell it which services to scrape. |
| How does it reach GKE? | Terraform creates the cluster and installs ArgoCD. ArgoCD deploys the `k8s/gke` folder from the `main` branch. That is Person 1's part. |
| What breaks in your design? | Router pods can disagree for up to 5 seconds after a membership change. There is no hinted handoff. Rebalancing is sequential and slow. Two membership changes at the same moment can overwrite each other. Section 7 of the design doc lists them. |

## If something breaks, and how to reset

| Problem | Fix |
| --- | --- |
| `kubectl` says it cannot connect, or mentions `gke-gcloud-auth-plugin` | It is pointed at GKE. Run `kubectl config use-context docker-desktop`. |
| `Unable to connect ... 127.0.0.1:6443` | Docker Desktop is not running, or Kubernetes is not enabled in its settings. Start it and wait 2 minutes. |
| `pmctl` is not recognised | You opened a new window. Paste the `function pmctl { ... }` line again. |
| The autoscaler shows `<unknown>` for CPU | metrics-server is still starting. Wait a minute and check `kubectl get hpa -n s1` again. |
| k6 cannot connect to `localhost:50051` | Check `kubectl get svc -n s1`. The Partition Manager LoadBalancer should show `localhost` as its external address. |
| Grafana panels are empty | Set the time range to Last 15 minutes and click Refresh. Check `kubectl get pods -n monitoring`. |
| `pmctl ring` shows 5 nodes before the demo | A rehearsal left the fifth node on the ring. Reset as below. |
| Something fails during the viva and you cannot fix it in 30 seconds | Move on to the GKE screenshots (Part 7) and say what the step would have shown. |

**Reset after a rehearsal** (window 1). This deletes the app and its data and deploys it fresh, so the ring starts again at version 1 with 4 nodes. It takes about 3 minutes.

```powershell
kubectl delete -k k8s/local
```

```powershell
kubectl wait --for=delete namespace/s1 --timeout=180s
```

```powershell
kubectl apply -k k8s/local
```

```powershell
kubectl apply -f observability/servicemonitors.yaml
```

```powershell
kubectl get pods -n s1 -w
```

Wait for all 6 pods to show `1/1 Running`, press Ctrl+C, then run `pmctl ring` to confirm 4 nodes.

**After the viva**, to free the laptop's memory:

```powershell
kubectl delete -k k8s/local
```

```powershell
helm uninstall monitoring -n monitoring
```
