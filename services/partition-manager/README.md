# Partition Manager

**Owner:** Person 3 (Mrudul)
**Role:** the router in front of the Sensor Store nodes. Runs the consistent hashing ring (virtual nodes, replication factor 3), sends every reading to its 3 nodes, reads with fallback, and rebalances data when a node joins or leaves.
**Talks to:** Telemetry Ingestion and Irrigation Controller call it via gRPC (`contracts/partition_manager.proto`); it calls Sensor Store nodes via gRPC.

## Files

| File | What it is |
|---|---|
| `ring.py` | The hash ring (pure Python, no network) |
| `server.py` | The gRPC service: routing, quorum writes, read fallback, rebalancing, metrics |
| `membership.py` | Where the node list lives: a JSON file locally, Firestore on GKE |
| `pmctl.py` | Command-line remote control for demos |
| `demo.py` | Offline demo: 80% vs 18% moved, balance, crash survival |
| `test_ring.py` | 8 unit tests for the ring |
| `test_integration.py` | 4 end-to-end tests: real gRPC, 5 stores, crashes, add/remove node |

## Run everything with Docker (from the repo root)

```powershell
docker compose up --build -d                                         # start 1 Partition Manager + 5 Sensor Stores
docker compose exec partition-manager python pmctl.py ring           # 4 nodes on the ring
docker compose exec partition-manager python pmctl.py write 2000     # send fake readings
docker compose exec partition-manager python pmctl.py where farm1-plot1-s1
docker compose exec partition-manager python pmctl.py add-node sensor-store-4   # join + rebalance
docker compose stop sensor-store-1                                    # crash a node...
docker compose exec partition-manager python pmctl.py latest farm1-plot1-s1     # ...reads still work
docker compose down -v                                                # stop and wipe
```

Metrics: http://localhost:8000/metrics

## Run the tests (no Docker needed)

```powershell
pip install -r requirements.txt
python -m pytest -v
```
