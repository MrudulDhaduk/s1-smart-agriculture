"""
pmctl.py - a small command-line remote control for the Partition Manager (for demos and testing).

    python pmctl.py ring                          show nodes and version
    python pmctl.py write 1000                    send 1000 fake readings (200 sensors)
    python pmctl.py latest farm1-plot1-s1         newest reading of a sensor
    python pmctl.py where farm1-plot1-s1          which nodes hold this sensor
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--addr", default="localhost:50051")
    p.add_argument("command", choices=["ring", "write", "latest", "where", "add-node", "remove-node"])
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
        for r in stub.GetLatest(pm.GetLatestRequest(sensor_ids=[a.arg])).readings:
            print(f"{r.sensor_id}: moisture {r.moisture_pct}%  temp {r.temperature_c}C  at {r.timestamp_ms}")
    elif a.command == "where":
        # Same ring, same MD5 -> the same answer the Partition Manager computes. Nothing is written.
        state = stub.GetRing(pm.GetRingRequest())
        ring = HashRing(vnodes=state.vnodes, replicas=state.replicas)
        for n in state.nodes:
            ring.add_node(n)
        print(f"{a.arg} -> {ring.get_nodes(a.arg)} (primary first)")
    elif a.command == "add-node":
        show_ring(stub.AddNode(pm.NodeRequest(node=a.arg), timeout=300))
    elif a.command == "remove-node":
        show_ring(stub.RemoveNode(pm.NodeRequest(node=a.arg), timeout=300))


if __name__ == "__main__":
    main()
