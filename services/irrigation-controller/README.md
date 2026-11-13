# Irrigation Controller

**Owner:** Person 1
**Role:** Recommends and triggers watering from the current soil readings; raises dry-soil and silent-sensor alerts.
**Talks to:**
- Farm Registry and Sensor Registry over **REST** (plots, crop moisture bands, active sensors)
- Partition Manager over **gRPC** `GetLatest` (newest reading per sensor; never a Sensor Store directly)
- Kafka topic `irrigation` (**queue**): one event per watering decision, for Farm Analytics / Flink
- Pub/Sub topic `alerts` (**queue**): `DRY_SOIL`, `SENSOR_SILENT`, consumed by the Alert function
- Firestore `irrigation_state/{plot_id}`: watering cooldown shared by all replicas

**API:** [contracts/rest/README.md](../../contracts/rest/README.md). Message formats: `contracts/kafka/irrigation.example.json`, `contracts/pubsub/alert.example.json`.

## The decision

For each plot: average the readings of its active sensors that are at most 5 minutes old, compare with the
plot's crop (from Farm Registry):

- average ≥ crop minimum → `OK`
- average < crop minimum → `WATER` with `litres = area_m2 × (target − average) × root_depth_cm / 10`
  (1 % of 1 m² × 1 cm of soil is 0.1 L), plus a `DRY_SOIL` alert (`CRITICAL` if 10 points below the minimum)
- no fresh reading → `NO_DATA`; sensors without a fresh reading → one `SENSOR_SILENT` alert for the plot
- watered within the last 10 minutes → `COOLDOWN` (Firestore transaction, so two replicas never both water)

A cycle runs every 30 s and on `POST /irrigation/evaluate`; `GET /irrigation/recommendations` shows the
same assessment without acting.

## Settings

See the top of `backends.py`. Locally everything falls back to stand-ins (in-memory cooldown, alerts and
events written to the log), so the service runs with only Docker; on GKE the `k8s/gke` overlay switches to
Firestore, Pub/Sub and Aiven Kafka.

## Run locally

```bash
docker compose up --build -d                       # whole stack, incl. Partition Manager and Kafka
python tools/seed_registries.py                    # farms, plots, 200 sensors
docker compose exec partition-manager python pmctl.py write 2000
curl -s localhost:8083/irrigation/recommendations | python -m json.tool
cd services/irrigation-controller && python -m pytest -q
```
