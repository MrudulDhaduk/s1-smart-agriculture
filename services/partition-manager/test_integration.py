"""
test_integration.py - the real services talking over real gRPC, all inside one Python process.

Starts 5 Sensor Store nodes + 1 Partition Manager on random ports, then checks the
behaviours the demo relies on: writes reach 3 nodes, reads survive a crash, and
adding/removing a node rebalances the data without losing any.

    python -m pytest -v test_integration.py
"""

import importlib.util
import os
from collections import Counter

import grpc
import pytest

import membership
import partition_manager_pb2 as pm
import partition_manager_pb2_grpc as pm_grpc
import pmctl
import sensor_store_pb2 as ss
from server import PartitionManager, serve

HERE = os.path.dirname(os.path.abspath(__file__))
NODES = [f"sensor-store-{i}" for i in range(5)]
SENSORS = pmctl.SENSORS  # 200 sensor ids

# load sensor-store/server.py under another name (both services have a server.py)
_spec = importlib.util.spec_from_file_location(
    "sensor_store_server", os.path.join(HERE, "..", "sensor-store", "server.py"))
store_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(store_server)


@pytest.fixture
def cluster(tmp_path):
    stores, addresses = {}, {}
    for n in NODES:
        server, port = store_server.serve(n, str(tmp_path / n), 0)
        stores[n], addresses[n] = server, f"localhost:{port}"
    ring_file = membership.FileMembership(str(tmp_path / "membership.json"), NODES[:4])  # store-4 starts outside
    manager = PartitionManager(ring_file, address_overrides=addresses, refresh_seconds=0.2)
    pm_server, port = serve(manager, 0)
    client = pm_grpc.PartitionManagerStub(grpc.insecure_channel(f"localhost:{port}"))
    for s in SENSORS:
        assert client.WriteReading(pm.WriteReadingRequest(reading=pmctl.fake_reading(s))).ok
    yield client, manager, stores, addresses
    pm_server.stop(0)
    for s in stores.values():
        s.stop(0)


def copies_per_sensor(manager, nodes):
    """How many nodes actually hold each sensor (asks every node directly)."""
    counts = Counter()
    for n in nodes:
        counts.update(manager.stub(n).ListSensors(ss.ListSensorsRequest()).sensor_ids)
    return counts


def all_readable(client):
    return len(client.GetLatest(pm.GetLatestRequest(sensor_ids=SENSORS)).readings) == len(SENSORS)


def test_every_reading_is_stored_on_three_nodes(cluster):
    client, manager, *_ = cluster
    counts = copies_per_sensor(manager, NODES)
    assert all(counts[s] == 3 for s in SENSORS)
    assert all_readable(client)


def test_reads_and_writes_survive_a_crashed_node(cluster):
    client, _, stores, _ = cluster
    stores["sensor-store-1"].stop(0)  # crash
    assert all_readable(client)
    replies = [client.WriteReading(pm.WriteReadingRequest(reading=pmctl.fake_reading(s))) for s in SENSORS]
    assert all(r.ok for r in replies)  # 2 of 3 is still a majority


def test_add_node_rebalances_without_losing_data(cluster):
    client, manager, *_ = cluster
    state = client.AddNode(pm.NodeRequest(node="sensor-store-4"))
    assert state.version == 2 and "sensor-store-4" in state.nodes

    counts = copies_per_sensor(manager, NODES)
    assert all(counts[s] == 3 for s in SENSORS)  # still exactly 3 copies: old ones were cleaned up
    on_new_node = manager.stub("sensor-store-4").ListSensors(ss.ListSensorsRequest()).sensor_ids
    assert 0.4 < len(on_new_node) / len(SENSORS) < 0.8  # holds ~3/5 of sensors (it is 1 of 3 owners)
    assert all_readable(client)


def test_remove_dead_node_restores_three_copies(cluster):
    client, manager, stores, _ = cluster
    stores["sensor-store-1"].stop(0)  # node dies...
    client.RemoveNode(pm.NodeRequest(node="sensor-store-1"))  # ...and is taken off the ring

    alive = ["sensor-store-0", "sensor-store-2", "sensor-store-3"]
    counts = copies_per_sensor(manager, alive)
    assert all(counts[s] == 3 for s in SENSORS)  # every sensor re-copied onto the 3 survivors
    assert all_readable(client)


def test_repair_finishes_an_interrupted_rebalance(cluster):
    # What happened on Docker Desktop: the pod doing AddNode was killed (HPA scale-in) after
    # copying data and switching the ring, but BEFORE deleting the old copies.
    client, manager, _, addresses = cluster
    old_ring = manager.build_ring(NODES[:4])
    new_ring = manager.build_ring(NODES)
    manager._copy_moved_sensors(old_ring, new_ring)      # step 1 done
    manager.membership.save(2, NODES)                     # step 2 done
    manager.refresh()                                     # ...pod killed here: no delete step
    assert sum(copies_per_sensor(manager, NODES).values()) > 3 * len(SENSORS)  # extra copies left

    pmctl.repair(client, address_of=addresses.get)

    counts = copies_per_sensor(manager, NODES)
    assert all(counts[s] == 3 for s in SENSORS)          # exactly 3 copies again
    for s in SENSORS:                                     # ...and on exactly the right nodes
        for n in NODES:
            holds = s in manager.stub(n).ListSensors(ss.ListSensorsRequest()).sensor_ids
            assert holds == (n in new_ring.get_nodes(s))
    assert all_readable(client)
