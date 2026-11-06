# Sensor Store

**Owner:** Person 3 (Mrudul)
**Role:** one storage node of the ring. Each node (`sensor-store-0`, `-1`, ...) keeps the readings of the sensors the ring assigned to it, in a SQLite file on its own disk.
**Talks to:** nobody. Only the Partition Manager calls it, via gRPC (`contracts/sensor_store.proto`).

## Files

| File | What it is |
|---|---|
| `server.py` | The gRPC service: store, latest, history, list/delete sensors (for rebalancing), metrics |
| `Dockerfile` | Builds the image (build from the repo root) |

## Metrics (`:8000/metrics`)

- `ss_requests_total`, `ss_request_latency_seconds`: RPS, errors, latency per method
- `ss_sensors_stored`: **keys per node** (the Grafana panel that shows the partitioning)
- `ss_readings_stored`: total readings on this node

Run it with the rest of the system: see `services/partition-manager/README.md`.
