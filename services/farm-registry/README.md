# Farm Registry

**Owner:** Person 1
**Role:** Registers farms, plots and crop details. A plot's crop sets the moisture band the Irrigation Controller aims for.
**Talks to:** Users via REST (public URL through the Ingress); called by Sensor Registry and Irrigation Controller. Stores data in Cloud SQL (Postgres, database `farm_registry`).
**API:** [contracts/rest/README.md](../../contracts/rest/README.md), or `/docs` on a running instance.

## Data

`crops (name, min_moisture_pct, target_moisture_pct, root_depth_cm)` ← `plots (plot_id, farm_id, crop, area_m2, …)` → `farms (farm_id, name, location)`.
Foreign keys keep plots consistent with farms and crops; the default crops (wheat, rice, maize, tomato) are inserted on first start.

## Database login

| Where | How |
|---|---|
| GKE | `SQL_INSTANCE_CONNECTION_NAME` set → Cloud SQL Python connector, IAM database login as the pod's Google service account `s1-farm-registry` (Workload Identity). No password exists. |
| Docker Compose | `DATABASE_URL=postgresql+pg8000://…` to the local Postgres container |
| Tests / quick run | default SQLite file in `/tmp` |

## Run locally

```bash
docker compose up --build -d farm-registry          # http://localhost:8081/docs
cd services/farm-registry && python -m pytest -q    # needs: pip install -r requirements.txt pytest httpx
```
