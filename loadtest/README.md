# loadtest/ (Person 3)

k6 scripts that generate sustained traffic to make the HPAs scale out (task c).

| Script | What it does |
|---|---|
| `pm-write.js` | gRPC `WriteReading` calls to Partition Manager: ramp to 40 virtual users over 2.5 min, hold 2 min, stop |

```powershell
k6 run loadtest/pm-write.js                          # Partition Manager at localhost:50051
k6 run -e PM_ADDR=host:port loadtest/pm-write.js     # somewhere else
```

Watch the scaling in a second window: `kubectl get hpa -n s1 -w`

Note: gRPC keeps one long-lived connection per client, and Kubernetes balances connections,
not individual requests. The script reconnects every 200 calls so pods added by the HPA get traffic.

## On GKE

Run k6 inside the cluster, not through `kubectl port-forward` (a port-forward sends all traffic
to one pod, so pods added by the HPA would get none). `k6-gke.yaml` is a Job that does this;
the commands to create its two ConfigMaps and start it are at the top of that file.

To load Telemetry Ingestion (its HPA) as well, drive the public URL with
`python tools/simulate_sensors.py --url http://<ingress-ip> --rate 200`. Each reading it accepts
also goes to Partition Manager, so that loads both autoscalers.
