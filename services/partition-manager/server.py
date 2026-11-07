"""
Partition Manager - the router in front of the Sensor Store nodes.

Callers (Telemetry Ingestion, Irrigation Controller) only talk to this service.
For every reading it asks the hash ring "which 3 nodes?" and forwards the call.

    WriteReading  -> send to all 3 replicas, reply once 2 of 3 confirm (majority) AND the
                     primary has answered; a slow non-primary keeps writing in the background
    GetLatest     -> ask the primary node; if it is down, ask the next replica
    AddNode       -> copy the sensors the new node now owns, update membership, clean up
    RemoveNode    -> the same in reverse

The service keeps NO data of its own (stateless), so Kubernetes can run many copies
and the HPA can add or remove them. The ring membership lives outside, in
membership.py (a file locally, Firestore on GKE), and every copy re-reads it every
REFRESH_SECONDS.

Settings (environment variables):
    INITIAL_NODES        nodes to start with       "sensor-store-0,sensor-store-1,..."
    NODE_ADDRESS         how to reach a node       default "{node}:50052"
                         (on GKE: "{node}.sensor-store:50052")
    MEMBERSHIP_BACKEND   file | firestore          default file
    VNODES / REPLICAS    ring settings             default 100 / 3
    REFRESH_SECONDS      membership re-read period default 5
    GRPC_PORT            default 50051
    METRICS_PORT         default 8000 (0 = off)
"""

import json
import os
import signal
import sys
import threading
import time
from concurrent import futures

import grpc
from prometheus_client import Counter, Gauge, Histogram, start_http_server

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "gen"))
import partition_manager_pb2 as pm  # noqa: E402  (generated from contracts/)
import partition_manager_pb2_grpc as pm_grpc  # noqa: E402
import sensor_store_pb2 as ss  # noqa: E402
import sensor_store_pb2_grpc as ss_grpc  # noqa: E402

import membership as membership_lib  # noqa: E402
from ring import HashRing  # noqa: E402

TIMEOUT = 2.0  # seconds to wait for one Sensor Store call

# ---------- metrics (Prometheus scrapes these from :8000/metrics) ----------
REQUESTS = Counter("pm_requests_total", "gRPC requests handled", ["method", "status"])
LATENCY = Histogram("pm_request_latency_seconds", "Time to handle a request", ["method"])
REPLICA_WRITES = Counter("pm_replica_writes_total", "Writes sent to each node", ["node", "result"])
RING_VERSION = Gauge("pm_ring_version", "Membership version this copy is using")
RING_NODES = Gauge("pm_ring_nodes", "Number of nodes on the ring")
REBALANCES = Counter("pm_rebalance_events_total", "Membership changes handled", ["type"])
MOVED = Counter("pm_rebalance_sensors_moved_total", "Sensors copied to a new owner during rebalancing")
REBALANCE_SECONDS = Gauge("pm_last_rebalance_seconds", "How long the last rebalance took")


class InvalidRequest(ValueError):
    """The caller sent something wrong: answer INVALID_ARGUMENT, not a server error."""


def log(level, message, **fields):
    """One JSON object per line on stdout; Cloud Logging picks it up as structured logs."""
    print(json.dumps({"service": "partition-manager", "level": level, "message": message, **fields}),
          flush=True)


class PartitionManager(pm_grpc.PartitionManagerServicer):
    def __init__(self, membership, node_address="{node}:50052", vnodes=100, replicas=3,
                 refresh_seconds=5.0, address_overrides=None):
        self.membership = membership
        self.node_address = node_address
        self.address_overrides = address_overrides or {}  # only used by tests
        self.vnodes, self.replicas = vnodes, replicas
        self.refresh_seconds = refresh_seconds
        self.stubs = {}
        self.admin_lock = threading.Lock()  # one membership change at a time
        self.pool = futures.ThreadPoolExecutor(max_workers=32)
        self.version, self.ring = 0, HashRing(vnodes, replicas)
        self.refresh()
        threading.Thread(target=self._refresh_loop, args=(refresh_seconds,), daemon=True).start()

    # ---------- ring and membership ----------
    def build_ring(self, nodes):
        ring = HashRing(self.vnodes, self.replicas)
        for n in nodes:
            ring.add_node(n)
        return ring

    def refresh(self):
        """Re-read membership; rebuild the ring only if the version changed."""
        version, nodes = self.membership.load()
        if version != self.version:
            self.ring = self.build_ring(nodes)  # swap in one step, so readers never see half a ring
            self.version = version
            RING_VERSION.set(version)
            RING_NODES.set(len(nodes))
            log("INFO", "ring updated", version=version, nodes=nodes)

    def _refresh_loop(self, every):
        while True:
            time.sleep(every)
            try:
                self.refresh()
            except Exception as e:
                log("ERROR", "membership refresh failed", error=str(e))

    def stub(self, node):
        if node not in self.stubs:
            address = self.address_overrides.get(node) or self.node_address.format(node=node)
            self.stubs[node] = ss_grpc.SensorStoreStub(grpc.insecure_channel(address))
        return self.stubs[node]

    def ring_state(self):
        return pm.RingState(version=self.version, nodes=sorted(self.ring.nodes),
                            vnodes=self.vnodes, replicas=self.replicas)

    # ---------- metrics wrapper ----------
    def _observe(self, method, fn, context):
        start = time.time()
        try:
            result = fn()
            REQUESTS.labels(method, "ok").inc()
            return result
        except InvalidRequest as e:  # the caller's mistake: not counted as a server error
            REQUESTS.labels(method, "invalid").inc()
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            REQUESTS.labels(method, "error").inc()
            log("ERROR", "request failed", method=method, error=str(e))
            context.abort(grpc.StatusCode.INTERNAL, str(e))
        finally:
            LATENCY.labels(method).observe(time.time() - start)

    # ---------- data path ----------
    def WriteReading(self, request, context):
        def run():
            reading = request.reading
            if not reading.sensor_id:
                raise InvalidRequest("sensor_id is required")
            if reading.timestamp_ms <= 0:  # it is half of the primary key; 0 would overwrite other readings
                raise InvalidRequest("timestamp_ms is required")
            nodes = self.ring.get_nodes(reading.sensor_id)
            if not nodes:
                raise RuntimeError("ring has no nodes")
            needed = len(nodes) // 2 + 1  # majority: 2 of 3
            calls = {}
            for n in nodes:  # send to all replicas in parallel; each call returns a future
                call = self.pool.submit(self.stub(n).Put, ss.PutRequest(readings=[reading]), timeout=TIMEOUT)
                # Runs whenever THIS replica finishes, even after we have already replied.
                call.add_done_callback(lambda c, n=n: self._record_replica_write(n, reading.sensor_id, c))
                calls[call] = n
            # Rule: reply once a majority has confirmed AND the primary has answered.
            # Reads go to the primary, so waiting for it means a read right after "ok" sees
            # this reading (read-your-writes). A slow NON-primary replica is not waited for.
            # If the primary fails, any majority is enough (reads then fail over to the others).
            primary = nodes[0]
            acks = failures = 0
            primary_answered = False
            for call in futures.as_completed(calls):  # receipts in the order they ARRIVE
                if call.exception() is None:
                    acks += 1
                else:
                    failures += 1
                if calls[call] == primary:
                    primary_answered = True
                if (acks >= needed and primary_answered) or failures > len(nodes) - needed:
                    break  # decided: reply now; any slower replica keeps writing in the background
            return pm.WriteReadingResponse(ok=acks >= needed, nodes=nodes, acks=acks)
        return self._observe("WriteReading", run, context)

    def _record_replica_write(self, node, sensor_id, call):
        """Metrics + log for one replica write, including ones that finish after the reply."""
        if call.exception() is None:
            REPLICA_WRITES.labels(node, "ok").inc()
        else:
            REPLICA_WRITES.labels(node, "failed").inc()
            log("WARNING", "replica write failed", node=node, sensor_id=sensor_id, error=str(call.exception()))

    def GetLatest(self, request, context):
        def run():
            # Try each sensor's primary first. A sensor is retried on its next replica when the
            # node FAILED, and also when the node answered but did not have it (for example a
            # node that came back with an empty disk). Otherwise that would be a silent miss.
            pending = {s: self.ring.get_nodes(s) for s in request.sensor_ids}
            found = []
            for attempt in range(self.replicas):
                by_node = {}
                for sensor, owners in pending.items():
                    if attempt < len(owners):
                        by_node.setdefault(owners[attempt], []).append(sensor)
                retry = {}
                for node, sensors in by_node.items():
                    try:
                        reply = self.stub(node).GetLatest(ss.StoreLatestRequest(sensor_ids=sensors),
                                                          timeout=TIMEOUT)
                        found.extend(reply.readings)
                        got = {r.sensor_id for r in reply.readings}
                        retry.update({s: pending[s] for s in sensors if s not in got})
                    except Exception as e:
                        log("WARNING", "read failed, trying next replica", node=node, error=str(e))
                        retry.update({s: pending[s] for s in sensors})
                pending = retry
                if not pending:
                    break
            return pm.GetLatestResponse(readings=found)
        return self._observe("GetLatest", run, context)

    def GetHistory(self, request, context):
        def run():
            limit = request.limit or 100
            answered = False
            for node in self.ring.get_nodes(request.sensor_id):
                try:
                    reply = self.stub(node).GetHistory(
                        ss.StoreHistoryRequest(sensor_id=request.sensor_id, from_ms=request.from_ms,
                                               to_ms=request.to_ms, limit=limit), timeout=TIMEOUT)
                    answered = True
                    if reply.readings:  # an empty answer may just mean this replica lacks the data
                        return pm.GetHistoryResponse(readings=reply.readings)
                except Exception as e:
                    log("WARNING", "history read failed, trying next replica", node=node, error=str(e))
            if answered:
                return pm.GetHistoryResponse()  # replicas answered, nobody has readings in that range
            raise RuntimeError("all replicas failed")
        return self._observe("GetHistory", run, context)

    # ---------- membership changes + rebalancing ----------
    def AddNode(self, request, context):
        return self._observe("AddNode", lambda: self._change(request.node, add=True), context)

    def RemoveNode(self, request, context):
        return self._observe("RemoveNode", lambda: self._change(request.node, add=False), context)

    def GetRing(self, request, context):
        return self._observe("GetRing", self.ring_state, context)

    def _change(self, node, add):
        with self.admin_lock:
            version, nodes = self.membership.load()
            if (node in nodes) == add:  # already there / already gone: nothing to do
                return self.ring_state()
            new_nodes = nodes + [node] if add else [n for n in nodes if n != node]
            old_ring, new_ring = self.build_ring(nodes), self.build_ring(new_nodes)

            start = time.time()
            moves = self._copy_moved_sensors(old_ring, new_ring)       # 1. copy data to the new owners
            self.membership.save(version + 1, new_nodes)               # 2. switch to the new ring...
            self.refresh()
            time.sleep(self.refresh_seconds + 1)                       #    ...and wait until EVERY router pod has it
            self._copy_moved_sensors(old_ring, new_ring, only=moves)   # 3. catch-up: copy readings written via the old ring
            self._delete_old_copies(old_ring, new_ring, moves)         # 4. only now remove copies nobody owns

            seconds = time.time() - start
            REBALANCES.labels("add" if add else "remove").inc()
            REBALANCE_SECONDS.set(seconds)
            log("INFO", "rebalance finished", change="add" if add else "remove", node=node,
                version=version + 1, sensors_moved=len(moves), seconds=round(seconds, 2))
            return self.ring_state()

    def _all_sensors(self, ring):
        sensors = set()
        for n in ring.nodes:
            try:
                sensors.update(self.stub(n).ListSensors(ss.ListSensorsRequest(), timeout=TIMEOUT).sensor_ids)
            except Exception as e:
                log("WARNING", "could not list sensors (node down?)", node=n, error=str(e))
        return sensors

    def _copy_moved_sensors(self, old_ring, new_ring, only=None):
        """For every sensor whose owner list changed, copy its readings to the new owners."""
        moves = {}
        for sensor in (only if only is not None else self._all_sensors(old_ring)):
            old, new = old_ring.get_nodes(sensor), new_ring.get_nodes(sensor)
            gained = [n for n in new if n not in old]
            if not gained:
                continue
            readings = self._read_all(sensor, old)
            for n in gained:
                self.stub(n).Put(ss.PutRequest(readings=readings), timeout=TIMEOUT * 5)
            moves[sensor] = (old, new)
            if only is None:
                MOVED.inc()
        return moves

    def _read_all(self, sensor, owners):
        for n in owners:  # any live old owner has the full history
            try:
                return self.stub(n).GetHistory(ss.StoreHistoryRequest(sensor_id=sensor, limit=0),
                                               timeout=TIMEOUT * 5).readings
            except Exception:
                continue
        return []

    def _delete_old_copies(self, old_ring, new_ring, moves):
        for sensor, (old, new) in moves.items():
            for n in old:
                if n not in new:
                    try:
                        self.stub(n).DeleteSensor(ss.DeleteSensorRequest(sensor_id=sensor), timeout=TIMEOUT)
                    except Exception:
                        pass  # the node may be dead; that is often why it was removed


def wait_for_stop_signal():
    """Block until Kubernetes asks us to stop (SIGTERM, e.g. HPA scale-in) or Ctrl+C."""
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()


def serve(manager, port):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=32))
    pm_grpc.add_PartitionManagerServicer_to_server(manager, server)
    bound = server.add_insecure_port(f"[::]:{port}")
    server.start()
    log("INFO", "partition manager started", port=bound, version=manager.version,
        nodes=sorted(manager.ring.nodes))
    return server, bound


if __name__ == "__main__":
    metrics_port = int(os.environ.get("METRICS_PORT", "8000"))
    if metrics_port:
        start_http_server(metrics_port)
    manager = PartitionManager(
        membership=membership_lib.from_env(),
        node_address=os.environ.get("NODE_ADDRESS", "{node}:50052"),
        vnodes=int(os.environ.get("VNODES", "100")),
        replicas=int(os.environ.get("REPLICAS", "3")),
        refresh_seconds=float(os.environ.get("REFRESH_SECONDS", "5")),
    )
    server, _ = serve(manager, int(os.environ.get("GRPC_PORT", "50051")))
    wait_for_stop_signal()
    log("INFO", "shutting down: finishing in-flight requests")
    server.stop(grace=10).wait()  # stop accepting new calls, give running ones 10 s to finish
