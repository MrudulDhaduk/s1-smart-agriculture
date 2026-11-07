// k6 load test: hammer Partition Manager with WriteReading calls so its HPA scales out.
//
//   k6 run loadtest/pm-write.js                         (from the repo root; PM at localhost:50051)
//   k6 run -e PM_ADDR=host:port loadtest/pm-write.js    (somewhere else)
//
// Shape: ramp up to 40 virtual users (VUs), hold, ramp down. Each VU is like one busy
// sensor gateway sending readings as fast as it can.
import grpc from 'k6/net/grpc';
import { check } from 'k6';

const client = new grpc.Client();
client.load(['../contracts'], 'partition_manager.proto');   // the same contract the services use

const ADDR = __ENV.PM_ADDR || 'localhost:50051';

export const options = {
  stages: [
    { duration: '30s', target: 10 },   // warm up
    { duration: '2m', target: 40 },    // climb: CPU rises, HPA starts adding pods
    { duration: '2m', target: 40 },    // hold: watch the new pods take traffic
    { duration: '30s', target: 0 },    // stop: after ~60 s HPA scales back in
  ],
  thresholds: {
    checks: ['rate>0.95'],                 // at least 95% of writes must succeed
    grpc_req_duration: ['p(95)<1000'],     // 95% of writes faster than 1 s
  },
};

function rand(n) {
  return 1 + Math.floor(Math.random() * n);
}

export default function () {
  // gRPC keeps one long-lived connection, and Kubernetes balances CONNECTIONS, not requests.
  // Reconnecting every 200 calls lets new pods (added by the HPA) receive traffic too.
  if (__ITER % 200 === 0) {
    if (__ITER > 0) client.close();
    client.connect(ADDR, { plaintext: true });
  }

  const farm = `farm${rand(50)}`;
  const plot = `${farm}-plot${rand(10)}`;
  const res = client.invoke('s1.PartitionManager/WriteReading', {
    reading: {
      sensor_id: `${plot}-s${rand(10)}`,     // 5,000 different sensors
      farm_id: farm,
      plot_id: plot,
      moisture_pct: 10 + Math.random() * 50,
      temperature_c: 18 + Math.random() * 20,
      timestamp_ms: Date.now(),
    },
  });

  check(res, {
    'status is OK': (r) => r && r.status === grpc.StatusOK,
    'stored on a majority of replicas': (r) => r && r.message && r.message.ok === true,
  });
}
