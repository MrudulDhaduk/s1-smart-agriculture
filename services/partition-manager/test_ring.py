"""
test_ring.py - automatic checks that the hash ring behaves correctly.

Run from this folder:
    python -m pytest -v

Every test follows the same 3-step pattern:
    1. build a ring
    2. do something (add a node, remove a node, look up keys)
    3. assert = "this MUST be true, otherwise fail loudly"
"""

from collections import Counter

from ring import HashRing

NODES = ["store-0", "store-1", "store-2", "store-3"]
SENSORS = [f"farm{f}-plot{p}-s{s}" for f in range(20) for p in range(10) for s in range(10)]  # 2,000 keys


def make_ring(vnodes=100, replicas=3):
    ring = HashRing(vnodes=vnodes, replicas=replicas)
    for n in NODES:
        ring.add_node(n)
    return ring


def test_same_key_always_gets_same_nodes():
    # Two separate rings (like two Partition Manager replicas) must agree.
    ring_a, ring_b = make_ring(), make_ring()
    for key in SENSORS:
        assert ring_a.get_nodes(key) == ring_b.get_nodes(key)


def test_replicas_are_on_different_nodes():
    ring = make_ring(replicas=3)
    for key in SENSORS:
        nodes = ring.get_nodes(key)
        assert len(nodes) == 3
        assert len(set(nodes)) == 3   # no machine appears twice


def test_fewer_nodes_than_replicas_does_not_hang():
    ring = HashRing(vnodes=10, replicas=3)
    ring.add_node("store-0")
    ring.add_node("store-1")
    assert sorted(ring.get_nodes("farm1-plot1-s1")) == ["store-0", "store-1"]


def test_empty_ring_returns_nothing():
    ring = HashRing()
    assert ring.get_nodes("farm1-plot1-s1") == []
    assert ring.get_node("farm1-plot1-s1") is None


def test_adding_a_node_moves_about_one_fifth_and_only_to_the_new_node():
    ring = make_ring(replicas=1)
    before = {k: ring.get_node(k) for k in SENSORS}
    ring.add_node("store-4")
    moved = [k for k in SENSORS if ring.get_node(k) != before[k]]

    assert 0.10 < len(moved) / len(SENSORS) < 0.30           # fair share is 1/5 = 20%
    assert all(ring.get_node(k) == "store-4" for k in moved)   # old nodes never swap keys


def test_removing_a_node_only_moves_that_nodes_keys():
    ring = make_ring(replicas=1)
    before = {k: ring.get_node(k) for k in SENSORS}
    ring.remove_node("store-2")
    for k in SENSORS:
        if before[k] != "store-2":
            assert ring.get_node(k) == before[k]   # everyone else stays put
        assert ring.get_node(k) != "store-2"       # nothing points at the removed node


def test_virtual_nodes_keep_load_balanced():
    ring = make_ring(vnodes=100, replicas=1)
    counts = Counter(ring.get_node(k) for k in SENSORS)
    fair = len(SENSORS) / len(NODES)   # 500 each
    for n in NODES:
        assert 0.7 * fair < counts[n] < 1.3 * fair   # every node within 30% of fair


def test_reads_survive_one_node_crash_with_three_replicas():
    ring = make_ring(replicas=3)
    disk = {n: set() for n in NODES}
    for k in SENSORS:
        for n in ring.get_nodes(k):
            disk[n].add(k)

    disk["store-2"] = set()                      # store-2 crashes, data gone
    alive = {"store-0", "store-1", "store-3"}
    for k in SENSORS:
        assert any(n in alive and k in disk[n] for n in ring.get_nodes(k))
