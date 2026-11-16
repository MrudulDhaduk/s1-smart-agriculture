# contracts/ (shared, all 3 people)

The agreements between services. Build against these. **Change them only if all 3 people agree.**

## Files

| File | What it defines | Who calls it |
|---|---|---|
| `reading.proto` | The one shape of a sensor reading | Everyone |
| `partition_manager.proto` | Partition Manager gRPC API | Telemetry Ingestion (P2) writes, Irrigation Controller (P1) reads |
| `sensor_store.proto` | Sensor Store gRPC API (internal) | **Only** Partition Manager |
| `kafka/readings.example.json` | A message on the Kafka `readings` topic | Telemetry Ingestion produces, Flink consumes |
| `kafka/irrigation.example.json` | A watering decision on the Kafka `irrigation` topic (key = `plot_id`) | Irrigation Controller (P1) produces, Flink / Farm Analytics (P2) consume |
| `kafka/results.example.json` | A one-minute farm summary on the Kafka `results` topic | Flink produces, Farm Analytics consumes |
| `pubsub/alert.example.json` | An alert on the Pub/Sub topic `alerts` (attributes `type`, `farm_id`) | Irrigation Controller (P1) and Partition Manager (P3) publish, Alert function (P2) consumes |
| `rest/README.md` | REST APIs of Farm Registry, Sensor Registry, Irrigation Controller, Telemetry Ingestion | Users, services, sensor simulator |

## Who calls what

```
Telemetry Ingestion (P2) --WriteReading--> Partition Manager (P3) --Put--> 3 Sensor Store nodes
Irrigation Controller (P1) --GetLatest---> Partition Manager (P3) --GetLatest--> primary node (fallback: next replica)
Irrigation Controller (P1) --REST--> Farm Registry (plots, crop thresholds), Sensor Registry (active sensors)
Sensor Registry (P1) --REST--> Farm Registry (does the plot exist?)
Irrigation Controller (P1) --Kafka "irrigation"--> Flink / Farm Analytics (P2)   water use per farm
Irrigation Controller (P1) --Pub/Sub "alerts"--> Alert function (P2) --> Firestore "alerts" + GCS archive
```

### Alert types (`type` field and Pub/Sub attribute)

| type | Raised by | When |
|---|---|---|
| `DRY_SOIL` | Irrigation Controller | a plot's average moisture is below its crop's minimum (`severity` CRITICAL when 10 points below) |
| `SENSOR_SILENT` | Irrigation Controller | active sensors of a plot sent no reading for 5 minutes (`sensor_ids` lists them) |
| `STORAGE_NODE_DOWN` | Partition Manager (optional) | a Sensor Store node stops answering (`sensor_ids` empty, node name in `message`) |

`alert_id` is deterministic (`<type>-<plot or node>-<detected_at_ms>`), so a redelivered message can be
stored idempotently under that id.

## Kafka `results` summary

Flink produces one JSON summary per farm and one-minute tumbling **event-time** window. The window uses
the event timestamps from readings (`timestamp_ms`) and irrigation events (`decided_at_ms`); its start
is inclusive and its end is exclusive. `farm_id`, `window_start_ms`, and `window_end_ms` are required.
Timestamps are Unix milliseconds. `readings`, `sensors`, `watering_events`, and `water_litres` are
also present in every result.

When `readings` is greater than zero, `avg_moisture_pct`, `min_moisture_pct`, and `max_moisture_pct`
are numeric moisture percentages. When `readings` is zero, all three are JSON `null`. A window can
contain irrigation events only, readings only, or both. A window with no events produces no result;
Flink does not emit zero-filled summaries for entirely empty windows.

This contract matches the current Flink producer: it unions readings and irrigation events, assigns
event-time timestamps, groups by farm into one-minute tumbling windows, serializes the required fields,
and leaves the nullable moisture fields unset when there are no readings. Farm Analytics requires the
three identity/window fields, validates the end is after the start, accepts nullable statistics, and
requires those statistics to be numeric with readings and null without readings. It accepts
irrigation-only, readings-only, and mixed results; it does not synthesize summaries for absent windows.
The consumer also checks counts and moisture range/order consistency as additional validation.

## Rules

- **Partition key = `sensor_id`.** All readings of one sensor live on the same 3 nodes.
- **Same field names everywhere.** The Kafka JSON uses exactly the fields of `Reading` in `reading.proto`.
- **Time = `timestamp_ms`**, Unix milliseconds, set by the sensor (or the simulator).
- **A write succeeds when 2 of 3 replicas confirm** (`WriteReadingResponse.ok`).

## Addresses inside Kubernetes

| Service | gRPC | Metrics (Prometheus) |
|---|---|---|
| Partition Manager | `partition-manager:50051` | `:8000/metrics` |
| Sensor Store node *i* | `sensor-store-<i>.sensor-store:50052` | `:8000/metrics` |

## To agree on the call (15 min)

1. Are the `Reading` fields enough? (P2: anything else from sensors? P1: anything Irrigation Controller needs?)
2. P1: Irrigation Controller calls `PartitionManager.GetLatest` (not Sensor Store). OK?
3. P2: Telemetry Ingestion calls `PartitionManager.WriteReading` **and** publishes the same reading as JSON to Kafka `readings`. OK?
4. The REST specs for the public APIs: registries and Irrigation Controller are in `rest/README.md` (P1); Telemetry Ingestion's `POST /readings` contract is documented there by P2.
