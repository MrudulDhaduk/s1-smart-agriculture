# Person 3: live demo script

About 10 minutes. Every command, what to say while it runs, and what should appear.
Commands are for PowerShell in the repo folder, on the laptop Kubernetes cluster (Docker Desktop).
On GKE the commands are the same apart from the addresses.

## 0. Before the examiner arrives (5 minutes earlier)

```powershell
kubectl get nodes                                   # docker-desktop  Ready
kubectl get pods -n s1                              # 2 partition-manager + 4 sensor-store, all 1/1 Running
kubectl get pods -n monitoring                      # all Running
kubectl exec -n s1 deploy/partition-manager -- python pmctl.py ring    # version, 4 nodes
```

- If the ring shows 5 nodes from an earlier rehearsal, reset with a clean deploy (see the end of this file).
- Open Grafana at http://localhost:3000, dashboard "S1 Smart Agriculture", time range "Last 15 minutes".
- Open a second PowerShell window in the repo folder for k6.
- Make a shortcut in window 1: `function pmctl { kubectl exec -n s1 deploy/partition-manager -- python pmctl.py @args }`

## 1. The concept, offline (1 minute)

```powershell
cd services\partition-manager
python demo.py
cd ..\..
```

**Say:** "With `hash % N`, adding a fifth node moved 80% of the sensors. My ring moved 18%, all of it to the new node, which is close to the minimum of 1/5. Part 2 is virtual nodes: with one spot per node one node got 62% of the data, with 100 spots every node is close to fair. Part 3 is replication: with 3 copies a crashed node loses nothing."

## 2. The system running on Kubernetes (1 minute)

```powershell
kubectl get pods -n s1
kubectl get hpa -n s1
```

**Say:** "Partition Manager is a Deployment of identical stateless pods with an HPA from 2 to 6. Sensor Store is a StatefulSet: each pod has a fixed name, which is its name on the ring, and its own disk."

## 3. Writes and where data lives (1 minute)

```powershell
pmctl write 2000
pmctl where farm1-plot1-s1
pmctl stats
```

**Say:** "Every reading goes to its 3 nodes in parallel and counts as stored once 2 confirm. `where` shows a sensor's primary and two replicas. The stats add up to 3 copies per sensor, spread evenly."

## 4. Autoscaling under load (5 minutes, the main event)

Window 2:
```powershell
k6 run loadtest/pm-write.js
```

Point at Grafana, row by row:
- **Traffic:** "Requests climb to about 150 per second, error rate stays at 0, and this is p95 latency."
- **Scaling:** "CPU passes the 50% target, so the HPA adds pods. It went from 2 straight to 6 because the formula `ceil(2 × 341 ÷ 50)` asked for 14 and 6 is our cost ceiling."
- **Partitioning:** "Writes per ring node: four almost identical lines. That is the hash ring spreading load evenly."

When k6 ends: "Scale-down waits 60 seconds to avoid flapping, then returns to 2 pods."

## 5. A node joins (2 minutes, the S1 concept live)

Wait until the HPA is back to 2 pods, so no pod is being removed while the rebalance runs.

```powershell
kubectl scale statefulset sensor-store -n s1 --replicas=5
kubectl get pods -n s1 -w          # Ctrl+C when sensor-store-4 is 1/1 Running
pmctl add-node sensor-store-4
pmctl stats
```

**Say:** "Kubernetes created the machine, but it holds nothing until my Partition Manager puts it on the ring. The rebalance copies only the sensors the new node now owns, switches every router pod to ring version 2, then deletes the old copies." Point at Grafana: ring version 2, 5 nodes, sensors moved, and 5 even bars.

## 6. A node fails (1 minute)

```powershell
pmctl where farm1-plot1-s1                         # note the primary, e.g. sensor-store-1
kubectl delete pod sensor-store-1 -n s1             # use the primary from the line above
pmctl latest farm1-plot1-s1
kubectl get pods -n s1
```

**Say:** "I killed the primary. The read still worked because the Partition Manager fell back to the next replica. Kubernetes also recreated `sensor-store-1` with the same name and the same disk, so its data is still there."

## Questions to expect

| Question | Short answer |
|---|---|
| Why not `hash % N`? | When N changes almost every key moves: (N−1)/N of them. The ring moves about 1/N, the minimum. |
| Why virtual nodes? | One spot per node makes each node's share one random gap. Many spots average the luck out, and a joining node takes a little from everyone. |
| Why MD5 and not Python `hash()`? | `hash()` changes every time Python starts; router replicas must agree. MD5 is deterministic. Not used for security. |
| What if 2 nodes die? 3 nodes? | 3 copies survive any 2 failures. A 3rd can lose data, about a quarter of sensors with only 4 nodes. |
| Why no HPA on Sensor Store? | It is stateful. An autoscaled pod would not be on the ring, and removing one would delete a partition. It scales by adding ring nodes. |
| What does 341% CPU mean? | Percent of the pod's CPU request (0.1 core): about 0.34 of a core. |
| Why did it stop at 6 pods? | `maxReplicas: 6` is our cost ceiling. Scale-up is immediate; scale-down waits 60 s. |
| Why a headless Service? | The router must reach one specific ring node, not a random pod. |
| What breaks in your design? | Section 7 of `docs/p3-concept-scaling-monitoring.md`: 5-second membership window, no hinted handoff, slow sequential rebalancing. |

## Reset after a rehearsal

```powershell
kubectl delete -k k8s/local                                  # deletes namespace s1, including the Sensor Store disks
kubectl wait --for=delete namespace/s1 --timeout=180s        # wait until it is really gone
kubectl apply -k k8s/local
kubectl apply -f observability/servicemonitors.yaml
```

The ring file lives in a folder on the Docker Desktop machine; if `pmctl ring` still shows 5 nodes after the reset, run
`kubectl exec -n s1 deploy/partition-manager -- rm /ring/membership.json` and then `kubectl rollout restart deployment/partition-manager -n s1`.
