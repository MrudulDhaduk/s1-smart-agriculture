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
