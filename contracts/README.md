# contracts/ (shared, all 3 people)

The agreements between services. Build against these. **Change them only if all 3 people agree.**

## Files

| File | What it defines | Who calls it |
|---|---|---|
| `reading.proto` | The one shape of a sensor reading | Everyone |
| `partition_manager.proto` | Partition Manager gRPC API | Telemetry Ingestion (P2) writes, Irrigation Controller (P1) reads |
| `sensor_store.proto` | Sensor Store gRPC API (internal) | **Only** Partition Manager |
| `kafka/readings.example.json` | A message on the Kafka `readings` topic | Telemetry Ingestion produces, Flink consumes |

## Who calls what

```
Telemetry Ingestion (P2) --WriteReading--> Partition Manager (P3) --Put--> 3 Sensor Store nodes
Irrigation Controller (P1) --GetLatest---> Partition Manager (P3) --GetLatest--> primary node (fallback: next replica)
```

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
4. The REST specs for the public APIs (registries, ingestion endpoint) still need to be added here by P1 and P2.
