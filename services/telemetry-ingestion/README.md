# Telemetry Ingestion

Accepts individual readings or batches at `POST /readings`. Each reading is validated, written
through Partition Manager (`WriteReading`), then published to Kafka topic `readings` using
`sensor_id` as the record key. A `202` means both operations completed for every reading.

## Run locally

The normal local setup runs this service in Docker Compose on `http://localhost:8084`:

```bash
docker compose up --build -d
curl -X POST http://localhost:8084/readings \
  -H 'Content-Type: application/json' \
  -d '{"sensor_id":"farm1-plot1-s1","farm_id":"farm1","plot_id":"farm1-plot1","moisture_pct":24.2,"temperature_c":27.1,"timestamp_ms":1762480000000}'
```

It also exposes `/healthz` on port 8080 and Prometheus `/metrics` on port 8000.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PARTITION_MANAGER_ADDR` | `partition-manager:50051` | Partition Manager gRPC address |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Kafka brokers |
| `KAFKA_SECURITY_PROTOCOL` | `PLAINTEXT` | `PLAINTEXT` locally or `SSL` in GKE |
| `KAFKA_SSL_CA_PEM`, `KAFKA_SSL_CERT_PEM`, `KAFKA_SSL_KEY_PEM` | unset | Required for `SSL`, provided by Kubernetes Secret `kafka-client` |
| `READINGS_TOPIC` | `readings` | Destination topic |
| `GRPC_WRITE_ATTEMPTS` | `3` | Bounded total WriteReading attempts |
| `GRPC_RETRY_BASE_SECONDS` | `0.05` | Exponential retry delay base |
| `KAFKA_DELIVERY_TIMEOUT_SECONDS` | `5` | Kafka acknowledgement timeout |

## Failure and duplicate behavior

Storage runs before Kafka publication. A transient gRPC failure is retried up to the configured
attempt limit; `INVALID_ARGUMENT` and other non-transient gRPC statuses are not retried. The
Partition Manager write is safe to repeat because readings are keyed by sensor and timestamp.

Kafka acknowledgement is required before a reading is counted as successful. If Kafka fails
after storage succeeded, the API returns `503` with `stored_not_published` and failure details;
the client may retry the request. That retry can store the same reading again and can publish a
duplicate Kafka record if the prior publish succeeded but its acknowledgement was lost. Kafka
producer idempotence covers producer-session retries, not client retries or restarts. Consumers
should deduplicate on `(sensor_id, timestamp_ms)` when duplicate processing would matter.
Successful entries in a partially failed batch are reported in the counts; retrying the entire
batch can duplicate those entries too.
