"""
pmctl.py - a small command-line remote control for the Partition Manager (for demos and testing).

    python pmctl.py ring                          show nodes and version
    python pmctl.py write 1000                    send 1000 fake readings (200 sensors)
    python pmctl.py latest farm1-plot1-s1         newest reading of a sensor
    python pmctl.py where farm1-plot1-s1          which nodes hold this sensor
    python pmctl.py stats                         how many sensors each node holds
    python pmctl.py repair                        make every node hold exactly what the ring says
    python pmctl.py add-node sensor-store-4       join a node and rebalance
    python pmctl.py remove-node sensor-store-2    remove a node and rebalance

Add --addr host:port to talk to a Partition Manager somewhere else (default localhost:50051).
Inside docker-compose:  docker compose exec partition-manager python pmctl.py ring
"""

import argparse
import os
import random
import sys
import time

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen"))
import partition_manager_pb2 as pm  # noqa: E402
import partition_manager_pb2_grpc as pm_grpc  # noqa: E402
import reading_pb2  # noqa: E402
import sensor_store_pb2 as ss  # noqa: E402
import sensor_store_pb2_grpc as ss_grpc  # noqa: E402
import transfer  # noqa: E402
from ring import HashRing  # noqa: E402

SENSORS = [f"farm{f}-plot{p}-s{s}" for f in range(1, 6) for p in range(1, 5) for s in range(1, 11)]  # 200


def fake_reading(sensor_id):
    farm, plot, _ = sensor_id.split("-")
    return reading_pb2.Reading(sensor_id=sensor_id, farm_id=farm, plot_id=f"{farm}-{plot}",
                               moisture_pct=round(random.uniform(10, 60), 1),
                               temperature_c=round(random.uniform(18, 38), 1),
                               timestamp_ms=int(time.time() * 1000) + random.randint(0, 999))


def show_ring(r):
    print(f"version {r.version} | {len(r.nodes)} nodes | vnodes={r.vnodes} replicas={r.replicas}")
    for n in r.nodes:
        print("  ", n)


def repair(stub, address_of=None):
    """Anti-entropy (like Cassandra's `nodetool repair`): compare what each node HOLDS with what
    the ring says it SHOULD hold. Copy missing sensors, delete extra copies. Safe to run any time,
    because storing a reading twice changes nothing (INSERT OR REPLACE)."""
    state = stub.GetRing(pm.GetRingRequest())
    ring = HashRing(vnodes=state.vnodes, replicas=state.replicas)
    for n in state.nodes:
        ring.add_node(n)
    if address_of is None:
        template = os.environ.get("NODE_ADDRESS", "{node}:50052")
        address_of = lambda n: template.format(node=n)  # noqa: E731
    nodes = {n: ss_grpc.SensorStoreStub(grpc.insecure_channel(address_of(n))) for n in state.nodes}

    held = {}
    for n, node in nodes.items():
        try:
            held[n] = set(node.ListSensors(ss.ListSensorsRequest(), timeout=30).sensor_ids)
        except grpc.RpcError:
            print(f"  {n} is DOWN, skipping it")

    copied = deleted = 0
    for sensor in set().union(*held.values()):
        owners = ring.get_nodes(sensor)
        holders = [n for n in held if sensor in held[n]]
        missing = [n for n in owners if n in held and sensor not in held[n]]
        if missing:
            transfer.copy_history(nodes.get, sensor, sources=holders, targets=missing, timeout=30)
            copied += len(missing)
        if all(o in held for o in owners):  # only clean up when every owner is alive and has a copy
            for n in holders:
                if n not in owners:
                    nodes[n].DeleteSensor(ss.DeleteSensorRequest(sensor_id=sensor), timeout=30)
                    deleted += 1
    print(f"repair done: {copied} missing copies made, {deleted} extra copies removed")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--addr", default="localhost:50051")
    p.add_argument("command", choices=["ring", "write", "latest", "where", "stats", "repair", "add-node", "remove-node"])
    p.add_argument("arg", nargs="?")
    a = p.parse_args()
    stub = pm_grpc.PartitionManagerStub(grpc.insecure_channel(a.addr))

    if a.command == "ring":
        show_ring(stub.GetRing(pm.GetRingRequest()))
    elif a.command == "write":
        n, ok = int(a.arg or 100), 0
        for i in range(n):
            reply = stub.WriteReading(pm.WriteReadingRequest(reading=fake_reading(SENSORS[i % len(SENSORS)])))
            ok += reply.ok
        print(f"{ok} of {n} writes succeeded (majority of replicas confirmed)")
    elif a.command == "latest":
        readings = stub.GetLatest(pm.GetLatestRequest(sensor_ids=[a.arg])).readings
        if not readings:
            print(f"{a.arg}: no readings stored")
        for r in readings:
            print(f"{r.sensor_id}: moisture {r.moisture_pct}%  temp {r.temperature_c}C  at {r.timestamp_ms}")
    elif a.command == "where":
        # Same ring, same MD5 -> the same answer the Partition Manager computes. Nothing is written.
        state = stub.GetRing(pm.GetRingRequest())
        ring = HashRing(vnodes=state.vnodes, replicas=state.replicas)
        for n in state.nodes:
            ring.add_node(n)
        print(f"{a.arg} -> {ring.get_nodes(a.arg)} (primary first)")
    elif a.command == "stats":
        # Ask every node on the ring directly: "how many sensors do you hold?"
        state = stub.GetRing(pm.GetRingRequest())
        address = os.environ.get("NODE_ADDRESS", "{node}:50052")
        print(f"ring version {state.version}")
        for n in state.nodes:
            try:
                node = ss_grpc.SensorStoreStub(grpc.insecure_channel(address.format(node=n)))
                count = len(node.ListSensors(ss.ListSensorsRequest(), timeout=2).sensor_ids)
                print(f"  {n}: {count:4} sensors  " + "#" * (count // 5))
            except grpc.RpcError:
                print(f"  {n}: DOWN")
    elif a.command == "repair":
        repair(stub)
    elif a.command == "add-node":
        show_ring(stub.AddNode(pm.NodeRequest(node=a.arg), timeout=1800))
    elif a.command == "remove-node":
        show_ring(stub.RemoveNode(pm.NodeRequest(node=a.arg), timeout=1800))


if __name__ == "__main__":
    try:
        main()
    except grpc.RpcError as e:  # show the server's reason in one line instead of a long traceback
        sys.exit(f"error ({e.code().name}): {e.details()}")
