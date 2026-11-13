#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
job_dir="$repo_root/services/flink-job"
log_file="$(mktemp -t s1-flink-smoke.XXXXXX)"
result_file="$(mktemp -t s1-flink-results.XXXXXX)"
group="flink-smoke-$(date +%s)"
farm="flink-smoke-$(date +%s)"
idle_suffix="$(date +%s)"
idle_readings_topic="flink-smoke-readings-$idle_suffix"
idle_irrigation_topic="flink-smoke-irrigation-$idle_suffix"
idle_results_topic="flink-smoke-results-$idle_suffix"
cleanup() {
  status=$?
  if [[ -n "${observer_pid:-}" ]]; then kill "$observer_pid" 2>/dev/null || true; wait "$observer_pid" 2>/dev/null || true; fi
  if [[ -n "${job_pid:-}" ]]; then kill "$job_pid" 2>/dev/null || true; wait "$job_pid" 2>/dev/null || true; fi
  if [[ "$status" -ne 0 && -f "$log_file" ]]; then cat "$log_file"; fi
  rm -f "$log_file" "$result_file"
  return "$status"
}
trap cleanup EXIT INT TERM

wait_for_farm_result() {
  local farm_id="$1"
  local attempt
  for attempt in $(seq 1 45); do
    if rg --quiet "\"farm_id\":\"$farm_id\"" "$result_file"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

cd "$job_dir"
repo_args=()
if [[ -n "${MAVEN_REPO_LOCAL:-}" ]]; then repo_args+=("-Dmaven.repo.local=$MAVEN_REPO_LOCAL"); fi
mvn "${repo_args[@]}" -q -DskipTests package
KAFKA_BOOTSTRAP_SERVERS=localhost:29092 KAFKA_SECURITY_PROTOCOL=PLAINTEXT KAFKA_GROUP_ID="$group" \
  mvn "${repo_args[@]}" -q exec:java -Dexec.mainClass=edu.s1.agriculture.FlinkJob >"$log_file" 2>&1 &
job_pid=$!
sleep 10
if ! kill -0 "$job_pid" 2>/dev/null; then cat "$log_file"; exit 1; fi
docker compose -f "$repo_root/docker-compose.yml" exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic results --property print.key=true --property key.separator=$'\t' \
  >"$result_file" 2>/dev/null &
observer_pid=$!
sleep 2

times="$(python3 -c 'import time; b=((int(time.time()*1000)//60000)+1)*60000; print(b, b+1000, b+500, b+30000, b+130000)')"
read -r base t1 t2 ti advance <<<"$times"
cat <<EOF | docker compose -f "$repo_root/docker-compose.yml" exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic readings --producer-property partitioner.class=org.apache.kafka.clients.producer.RoundRobinPartitioner
{"sensor_id":"$farm-s1","farm_id":"$farm","plot_id":"plot-1","moisture_pct":30,"temperature_c":24,"timestamp_ms":$t1}
{"sensor_id":"$farm-s2","farm_id":"$farm","plot_id":"plot-1","moisture_pct":10,"temperature_c":25,"timestamp_ms":$t2}
{"sensor_id":"$farm-progress-1","farm_id":"$farm","plot_id":"plot-1","moisture_pct":40,"temperature_c":26,"timestamp_ms":$advance}
{"sensor_id":"$farm-progress-2","farm_id":"$farm","plot_id":"plot-1","moisture_pct":40,"temperature_c":26,"timestamp_ms":$advance}
{"sensor_id":"$farm-progress-3","farm_id":"$farm","plot_id":"plot-1","moisture_pct":40,"temperature_c":26,"timestamp_ms":$advance}
EOF
cat <<EOF | docker compose -f "$repo_root/docker-compose.yml" exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic irrigation --producer-property partitioner.class=org.apache.kafka.clients.producer.RoundRobinPartitioner
{"event_id":"$farm-water","farm_id":"$farm","plot_id":"plot-1","crop":"tomato","action":"WATER","water_litres":15,"decided_at_ms":$ti}
{"event_id":"$farm-progress-1","farm_id":"$farm","plot_id":"plot-1","crop":"tomato","action":"WATER","water_litres":0,"decided_at_ms":$advance}
{"event_id":"$farm-progress-2","farm_id":"$farm","plot_id":"plot-1","crop":"tomato","action":"WATER","water_litres":0,"decided_at_ms":$advance}
{"event_id":"$farm-progress-3","farm_id":"$farm","plot_id":"plot-1","crop":"tomato","action":"WATER","water_litres":0,"decided_at_ms":$advance}
EOF

# Do not inject the late record until we have observed the first window's output.
if ! wait_for_farm_result "$farm"; then echo "Timed out waiting for the initial farm window output"; exit 1; fi

late_ts=$((base + 20000))
printf '{"sensor_id":"%s-late","farm_id":"%s","plot_id":"plot-1","moisture_pct":1,"temperature_c":24,"timestamp_ms":%s}\n' "$farm" "$farm" "$late_ts" |
  docker compose -f "$repo_root/docker-compose.yml" exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic readings --producer-property partitioner.class=org.apache.kafka.clients.producer.RoundRobinPartitioner

# Ensure the event-time window has fired before checking that a late event was dropped.
sleep 3
python3 -c 'import json,sys; farm=sys.argv[1]; base=int(sys.argv[2]); rows=[]
for line in open(sys.argv[3]):
    try:
        key,raw=line.rstrip("\n").split("\t",1); row=json.loads(raw)
        if key == farm and row["window_start_ms"] == base: rows.append(row)
    except (ValueError,KeyError,json.JSONDecodeError): pass
assert len(rows) == 1, f"Late event unexpectedly changed/re-emitted the closed window: {rows}"
assert rows[0]["readings"] == 2 and rows[0]["watering_events"] == 1 and rows[0]["water_litres"] == 15.0, rows[0]
print("Verified combined and late-event output:", json.dumps(rows[0], sort_keys=True))' "$farm" "$base" "$result_file"

# Use a separate empty irrigation topic so unrelated local producers cannot keep that input active.
kill "$observer_pid" 2>/dev/null || true; wait "$observer_pid" 2>/dev/null || true; observer_pid=""
kill "$job_pid" 2>/dev/null || true; wait "$job_pid" 2>/dev/null || true; job_pid=""
docker compose -f "$repo_root/docker-compose.yml" exec -T kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --create --if-not-exists --topic "$idle_irrigation_topic" --partitions 2 --replication-factor 1 >/dev/null
docker compose -f "$repo_root/docker-compose.yml" exec -T kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --create --if-not-exists --topic "$idle_readings_topic" --partitions 2 --replication-factor 1 >/dev/null
docker compose -f "$repo_root/docker-compose.yml" exec -T kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --create --if-not-exists --topic "$idle_results_topic" --partitions 2 --replication-factor 1 >/dev/null
: >"$result_file"
KAFKA_BOOTSTRAP_SERVERS=localhost:29092 KAFKA_SECURITY_PROTOCOL=PLAINTEXT KAFKA_GROUP_ID="$group-idle" \
  READINGS_TOPIC="$idle_readings_topic" IRRIGATION_TOPIC="$idle_irrigation_topic" RESULTS_TOPIC="$idle_results_topic" \
  mvn "${repo_args[@]}" -q exec:java -Dexec.mainClass=edu.s1.agriculture.FlinkJob >"$log_file" 2>&1 &
job_pid=$!
sleep 10
if ! kill -0 "$job_pid" 2>/dev/null; then cat "$log_file"; exit 1; fi
docker compose -f "$repo_root/docker-compose.yml" exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic "$idle_results_topic" --property print.key=true --property key.separator=$'\t' \
  >"$result_file" 2>/dev/null &
observer_pid=$!
sleep 2
idle_farm="${farm}-readings-only"
idle_first=$((base + 181000))
idle_advance=$((base + 251000))
cat <<EOF | docker compose -f "$repo_root/docker-compose.yml" exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic "$idle_readings_topic" --producer-property partitioner.class=org.apache.kafka.clients.producer.RoundRobinPartitioner
{"sensor_id":"$idle_farm-s1","farm_id":"$idle_farm","plot_id":"plot-2","moisture_pct":26,"temperature_c":23,"timestamp_ms":$idle_first}
{"sensor_id":"$idle_farm-progress-1","farm_id":"$idle_farm","plot_id":"plot-2","moisture_pct":26,"temperature_c":23,"timestamp_ms":$idle_advance}
{"sensor_id":"$idle_farm-progress-2","farm_id":"$idle_farm","plot_id":"plot-2","moisture_pct":26,"temperature_c":23,"timestamp_ms":$idle_advance}
EOF

if ! wait_for_farm_result "$idle_farm"; then echo "Timed out waiting for the idle-input window output"; exit 1; fi
python3 -c 'import json,sys; idle_farm=sys.argv[1]; idle_start=int(sys.argv[2]); idle=[]
for line in open(sys.argv[3]):
    try:
        key,raw=line.rstrip("\n").split("\t",1); row=json.loads(raw)
        if key == idle_farm and row["window_start_ms"] == idle_start: idle.append(row)
    except (ValueError,KeyError,json.JSONDecodeError): pass
assert len(idle) == 1, f"No output after irrigation input became idle: {idle}"
assert idle[0]["readings"] == 1 and idle[0]["watering_events"] == 0 and idle[0]["water_litres"] == 0.0, idle[0]
print("Verified idle-input output:", json.dumps(idle[0], sort_keys=True))' "$idle_farm" "$((base + 180000))" "$result_file"

echo "Kafka integration passed for farm_id=$farm."
