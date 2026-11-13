#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
job_dir="$repo_root/services/flink-job"
log_file="$(mktemp -t s1-flink-smoke.XXXXXX)"
group="flink-smoke-$(date +%s)"
farm="flink-smoke-$(date +%s)"
cleanup() {
  status=$?
  if [[ -n "${job_pid:-}" ]]; then kill "$job_pid" 2>/dev/null || true; wait "$job_pid" 2>/dev/null || true; fi
  if [[ "$status" -ne 0 && -f "$log_file" ]]; then cat "$log_file"; fi
  rm -f "$log_file"
  return "$status"
}
trap cleanup EXIT INT TERM

cd "$job_dir"
repo_args=()
if [[ -n "${MAVEN_REPO_LOCAL:-}" ]]; then repo_args+=("-Dmaven.repo.local=$MAVEN_REPO_LOCAL"); fi
mvn "${repo_args[@]}" -q -DskipTests package
KAFKA_BOOTSTRAP_SERVERS=localhost:29092 KAFKA_SECURITY_PROTOCOL=PLAINTEXT KAFKA_GROUP_ID="$group" \
  mvn "${repo_args[@]}" -q exec:java -Dexec.mainClass=edu.s1.agriculture.FlinkJob >"$log_file" 2>&1 &
job_pid=$!
sleep 10
if ! kill -0 "$job_pid" 2>/dev/null; then cat "$log_file"; exit 1; fi

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

sleep 5
docker compose -f "$repo_root/docker-compose.yml" exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic results --from-beginning --timeout-ms 60000 \
  --property print.key=true --property key.separator=$'\t' 2>/dev/null |
  python3 -c 'import json,sys; farm=sys.argv[1]; rows=[]
for line in sys.stdin:
    try:
        key,raw=line.rstrip("\n").split("\t",1); row=json.loads(raw)
        if key == farm and row["window_start_ms"] == int(sys.argv[2]): rows.append(row)
    except (ValueError,KeyError,json.JSONDecodeError): pass
assert rows, "No completed result found. Check job log and wait for watermarks."
r=rows[0]
expected={"readings":2,"sensors":2,"avg_moisture_pct":20.0,"min_moisture_pct":10.0,"max_moisture_pct":30.0,"watering_events":1,"water_litres":15.0}
for k,v in expected.items(): assert r[k] == v, f"{k}: expected {v}, got {r[k]}"
print("Verified output:", json.dumps(r, sort_keys=True))' "$farm" "$base"

echo "Kafka integration passed for farm_id=$farm."
