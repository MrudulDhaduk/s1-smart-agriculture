# S1 Flink farm window job

Consumes the team's Kafka `readings` and `irrigation` JSON contracts, joins both event types by `farm_id`, and emits one JSON result per farm and one-minute event-time window to `results`. The topic key is `farm_id`. This is a stateful Flink DataStream job; aggregation happens in a keyed tumbling-window operator.

## Build and tests

Requires JDK 11 and Maven 3.8+. From this directory:

```sh
mvn test
mvn package
```

The deployable artifact is `services/flink-job/target/flink-job-1.0.0.jar` (relative to the repository root). Flink runtime and client libraries are `provided`; the Kafka connector, Jackson, and Secret Manager client are shaded into the jar. The test suite includes JSON validation and a real local Flink mini-cluster pipeline test with event-time windows, out-of-order timestamps, boundary cases, distinct sensors, combined readings/watering, and water totals.

## Local run

Start the existing Kafka service without stopping other compose services:

```sh
docker compose up -d kafka
```

Run continuously against the laptop-published broker. No credentials are needed locally:

```sh
KAFKA_BOOTSTRAP_SERVERS=localhost:29092 \
KAFKA_SECURITY_PROTOCOL=PLAINTEXT \
mvn exec:java -Dexec.mainClass=edu.s1.agriculture.FlinkJob
```

Optional topic overrides are `READINGS_TOPIC`, `IRRIGATION_TOPIC`, and `RESULTS_TOPIC`. `KAFKA_GROUP_ID` defaults to `s1-flink-job`; use a new value if you need to replay all retained input from earliest offsets. For each topic the application uses its own group id (`<group>-readings` and `<group>-irrigation`).

Inspect keyed output from another terminal:

```sh
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic results --from-beginning \
  --property print.key=true --property key.separator=$'\t'
```

Expected message shape (numbers are examples):

```json
{"farm_id":"farm7","window_start_ms":1762480000000,"window_end_ms":1762480060000,"readings":2,"sensors":2,"avg_moisture_pct":22.4,"min_moisture_pct":21.4,"max_moisture_pct":23.4,"watering_events":1,"water_litres":12.5}
```

For a deterministic Kafka exercise, use input timestamps aligned to a minute boundary and send events to **both** topics with event times after the tested window. With the 10-second out-of-order bound, a window ending at `W` is emitted after its input watermark exceeds `W` (roughly after observing timestamps later than `W + 10s`). Advance both streams; otherwise one active input can hold back the union watermark. If one side has no records for 30 seconds it is marked idle. The `scripts/local-kafka-smoke.sh` helper demonstrates the full local flow and checks numerical results without deleting Kafka volumes.

Run the smoke check from any directory in the repository with `services/flink-job/scripts/local-kafka-smoke.sh`. It starts the Maven Flink job, writes an out-of-order pair of readings plus a WATER event and watermark-advancing records to the existing Kafka service, then validates the result. It stops only the job it started; it leaves Kafka and its volumes running.

## Event time, lateness, and data policy

Each source extracts `timestamp_ms` (readings) or `decided_at_ms` (irrigation) and assigns bounded-out-of-orderness watermarks of 10 seconds. Each input source marks idle partitions after 30 seconds; this prevents an unused partition or temporarily quiet input from holding back the union watermark. The window is a UTC epoch-aligned tumbling minute: `[window_start_ms, window_end_ms)`. Events on the exact end boundary belong to the next window.

Malformed JSON, missing/blank farm or sensor/event IDs, missing required numbers, non-finite numeric values, non-positive timestamps, and negative water litres are dropped. The job does not deduplicate: repeated source messages count repeatedly, and `sensors` is the distinct sensor ID cardinality within that window. Flink's event-time window default allowed lateness is zero; records arriving after the watermark has passed the window are discarded. A farm/window is output when it has at least one valid input event; an empty window has no record. A readings-only or irrigation-only window is emitted with zero values for the other side's metrics (moisture extrema and average are zero when there are no readings).

## Dataproc configuration and submission

The handoff specifies Dataproc image 2.2 (Flink 1.17.0, Java 11). On Dataproc, `KAFKA_CLIENT_PROPERTIES_SECRET` must name the Secret Manager version, for example `projects/s1-agri-ams-686974/secrets/kafka-client-properties/versions/latest`. The Dataproc service account reads that secret using Application Default Credentials; its Java `.properties` contents (including `bootstrap.servers`, SSL protocol, and inline PEM settings) are loaded in memory and never logged. Do not pass credentials as command-line arguments or commit them.

Build, upload, then submit through the Dataproc Jobs API (do not SSH to the cluster):

```sh
mvn package
gcloud storage cp target/flink-job-1.0.0.jar \
  gs://s1-agri-ams-686974-s1-artifacts/flink/flink-job-1.0.0.jar
gcloud dataproc jobs submit flink --cluster=s1-flink --region=us-central1 \
  --jar=gs://s1-agri-ams-686974-s1-artifacts/flink/flink-job-1.0.0.jar \
  -- --KAFKA_CLIENT_PROPERTIES_SECRET projects/s1-agri-ams-686974/secrets/kafka-client-properties/versions/latest
```

The secret resource identifier is passed as a main-program argument after `--`; `--properties` is for Flink configuration keys and is not used for this app setting. Confirm syntax with `gcloud dataproc jobs submit flink --help`. The secret resource identifier is not a secret; its payload is. Flink logs go to the Dataproc job logs in Cloud Logging when submitted this way. No job has been submitted by this implementation.

## Limitations

- Delivery is at least once; duplicate input events are counted again. A durable deduplication policy needs agreed event identity/retention semantics.
- Late events after window closure are dropped; there is no side output or correction stream.
- Sensor distinct counting stores a set of sensor IDs per open farm window (exact, not approximate), so memory scales with sensors and window concurrency.
- Kafka source starts at earliest offsets for a new group and has no checkpoint storage configured here. Set up Dataproc checkpointing and stable savepoints before production restarts.
- Local Docker/Kafka integration needs a running Docker daemon and the repository compose Kafka service.
