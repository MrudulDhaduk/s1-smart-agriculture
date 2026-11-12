# REST APIs (Person 1's services)

JSON in, JSON out. On GKE all three sit behind one public HTTP load balancer (Ingress `s1-public`);
inside the cluster use the Service names. Each service also serves its OpenAPI page at `/docs`.

| Service | Inside the cluster | Docker Compose (from your laptop) | Public paths (Ingress) |
|---|---|---|---|
| Farm Registry | `http://farm-registry` | `http://localhost:8081` | `/farms`, `/plots`, `/crops` |
| Sensor Registry | `http://sensor-registry` | `http://localhost:8082` | `/sensors` |
| Irrigation Controller | `http://irrigation-controller` | `http://localhost:8083` | `/irrigation` |

IDs follow the sensor naming already used by Partition Manager: farm `farm7`, plot `farm7-plot2`
(always starts with its farm id), sensor `farm7-plot2-s3` (always starts with its plot id).

Errors: `404` unknown id, `409` id already exists, `422` invalid body (FastAPI's standard error format),
`503` a dependency is down.

## Farm Registry

| Method and path | Body / query | Returns |
|---|---|---|
| `GET /crops` | | `[Crop]` |
| `POST /crops` | `Crop` | `201 Crop` |
| `GET /farms` | | `[Farm]` |
| `POST /farms` | `{farm_id, name, location?}` | `201 Farm` |
| `GET /farms/{farm_id}` | | `Farm` with its `plots` |
| `POST /farms/{farm_id}/plots` | `{plot_id, crop, area_m2, name?, planted_on?}` | `201 Plot` |
| `GET /plots` | `?farm_id=` (optional) | `[Plot]`, each with its `crop` details |
| `GET /plots/{plot_id}` | | `Plot` with its `crop` details |

```json
Crop: {"name": "tomato", "min_moisture_pct": 25.0, "target_moisture_pct": 35.0, "root_depth_cm": 40.0}
Plot: {"plot_id": "farm7-plot2", "farm_id": "farm7", "name": "North field", "area_m2": 1200.0,
       "planted_on": "2026-10-01", "crop": {Crop}}
```

## Sensor Registry

| Method and path | Body / query | Returns |
|---|---|---|
| `GET /sensors` | `?farm_id=&plot_id=&status=` (all optional) | `[Sensor]` |
| `POST /sensors` | `{sensor_id, plot_id, kind?, depth_cm?}` | `201 Sensor` (`422` if the plot is unknown to Farm Registry) |
| `GET /sensors/{sensor_id}` | | `Sensor` |
| `PATCH /sensors/{sensor_id}` | `{status}`: `active`, `inactive` or `faulty` | `Sensor` |

```json
Sensor: {"sensor_id": "farm7-plot2-s3", "farm_id": "farm7", "plot_id": "farm7-plot2",
         "kind": "soil-moisture", "depth_cm": 20.0, "status": "active", "installed_at_ms": 1762480000000}
```

## Irrigation Controller

| Method and path | Query | Returns |
|---|---|---|
| `GET /irrigation/recommendations` | `?farm_id=` (optional) | per-plot status, no side effects |
| `POST /irrigation/evaluate` | `?farm_id=` (optional) | runs one control cycle now: waters dry plots (Kafka `irrigation`) and raises alerts (Pub/Sub `alerts`) |

A control cycle also runs on its own every 30 s.

```json
{"plot_id": "farm7-plot2", "farm_id": "farm7", "crop": "tomato", "sensors": 10, "fresh_readings": 9,
 "moisture_pct": 18.2, "min_pct": 25.0, "target_pct": 35.0, "decision": "WATER", "water_litres": 80640.0}
```

`decision` is `WATER`, `OK`, `NO_DATA` (no fresh reading from any sensor) or `COOLDOWN` (watered in the
last 10 minutes).
