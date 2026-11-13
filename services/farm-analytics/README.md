# Farm Analytics

Consumes Flink's proposed Kafka `results` JSON, validates each window, persists an idempotent farm summary, and serves `GET /analytics/farms/{farm_id}`. The accepted message fields are `farm_id`, `window_start_ms`, `window_end_ms`, `readings`, `sensors`, `avg_moisture_pct`, `min_moisture_pct`, `max_moisture_pct`, `watering_events`, and `water_litres` (exactly the handoff proposal in `.handoff/P2_HANDOFF.md` section 4.3). No shared contract was changed.

## Run locally

`docker compose up --build -d kafka farm-analytics` starts the service with the local in-memory repository. For persistence across restarts and production behavior set `ANALYTICS_STORE=firestore`; GKE uses this with Workload Identity. Set `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_SECURITY_PROTOCOL`, and, for SSL, `KAFKA_SSL_CA_PEM`, `KAFKA_SSL_CERT_PEM`, and `KAFKA_SSL_KEY_PEM`. The local defaults are `kafka:9092` and PLAINTEXT.

Publish a sample from the repository root:

```sh
docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic results <<'EOF'
{"farm_id":"farm7","window_start_ms":1762479960000,"window_end_ms":1762480020000,"readings":120,"sensors":20,"avg_moisture_pct":24.5,"min_moisture_pct":12.0,"max_moisture_pct":41.0,"watering_events":2,"water_litres":80.5}
EOF
curl http://localhost:8085/analytics/farms/farm7
curl http://localhost:8005/metrics
```

In production, every window is recorded in `farm_summaries/{farm_id}/processed_windows/{start}_{end}` in the same Firestore transaction as its total updates. Kafka commits only after successful persistence. An older unique window contributes to cumulative totals but cannot replace the latest-window fields. Invalid JSON/schema records are logged and committed to avoid blocking a partition; Firestore errors leave the message uncommitted for redelivery.

Unit tests: `cd services/farm-analytics && PYTHONPATH=../web-common python -m pytest -q`.
