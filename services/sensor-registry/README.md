# Sensor Registry

**Owner:** Person 1
**Role:** Manages soil-moisture sensors and which farm/plot they belong to, and whether each is active.
**Talks to:** Users via REST (public URL through the Ingress); calls Farm Registry over REST to check that a plot exists; called by Irrigation Controller. Stores data in Cloud SQL (Postgres, database `sensor_registry`).
**API:** [contracts/rest/README.md](../../contracts/rest/README.md), or `/docs` on a running instance.

## Design notes

- **Database per service.** Sensors and plots live in different databases, so "does this plot exist?" is a REST call to Farm Registry, not a foreign key. Farm Registry down → `503`, never a sensor on an unknown plot.
- **`sensor_id` is the hash-ring partition key** (Partition Manager). This service only stores metadata about sensors; their readings live on the Sensor Store nodes.
- `farm_id` is taken from Farm Registry's answer, not from the request, so it cannot disagree with the plot.

## Run locally

```bash
docker compose up --build -d sensor-registry        # http://localhost:8082/docs
cd services/sensor-registry && python -m pytest -q  # needs: pip install -r requirements.txt pytest
```
