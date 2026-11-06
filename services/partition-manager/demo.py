"""
demo.py - run this to SEE why consistent hashing matters.

    python demo.py

Part 1: add a 5th node. How many keys move?  (old way vs ring)
Part 2: are keys spread evenly?              (1 virtual node vs 100)
Part 3: a node crashes. Can we still read?   (1 copy vs 3 copies)
"""

from collections import Counter

from ring import HashRing, hash_key

# 10,000 fake sensors, named the way our farms would name them
SENSORS = [f"farm{f}-plot{p}-s{s}" for f in range(50) for p in range(20) for s in range(10)]
NODES = ["store-0", "store-1", "store-2", "store-3"]


def percent(part, whole):
    return f"{100 * part / whole:.1f}%"


def part1_how_many_keys_move():
    print("=" * 60)
    print("PART 1: we add a 5th node. How many sensors change node?")
    print("=" * 60)

    # Old way: node number = hash % N
    before = {k: hash_key(k) % 4 for k in SENSORS}
    after = {k: hash_key(k) % 5 for k in SENSORS}
    moved = sum(1 for k in SENSORS if before[k] != after[k])
    print(f"  hash % N   : {moved:5} of {len(SENSORS)} moved = {percent(moved, len(SENSORS))}")

    # Ring way
    ring = HashRing(vnodes=100, replicas=1)
    for n in NODES:
        ring.add_node(n)
    before = {k: ring.get_node(k) for k in SENSORS}
    ring.add_node("store-4")
    after = {k: ring.get_node(k) for k in SENSORS}
    moved = sum(1 for k in SENSORS if before[k] != after[k])
    print(f"  ring       : {moved:5} of {len(SENSORS)} moved = {percent(moved, len(SENSORS))}")

    # Where did the moved keys go?
    went_to = Counter(after[k] for k in SENSORS if before[k] != after[k])
    print(f"  ...and every moved key went to: {dict(went_to)}")
    print(f"  Best possible = the new node's fair share = 1/5 = 20.0%")
    print()


def part2_even_spread():
    print("=" * 60)
    print("PART 2: how evenly are 10,000 sensors spread over 4 nodes?")
    print("=" * 60)
    for vnodes in (1, 10, 100):
        ring = HashRing(vnodes=vnodes, replicas=1)
        for n in NODES:
            ring.add_node(n)
        counts = Counter(ring.get_node(k) for k in SENSORS)
        line = "  ".join(f"{n}={counts[n]:5}" for n in NODES)
        print(f"  vnodes={vnodes:3} : {line}   (perfect = 2500 each)")
    print()


def part3_node_crash():
    print("=" * 60)
    print("PART 3: store-2 crashes and loses its data. Can we still read?")
    print("=" * 60)
    for replicas in (1, 3):
        ring = HashRing(vnodes=100, replicas=replicas)
        for n in NODES:
            ring.add_node(n)

        # "Disk" of each node: which sensors it holds
        disk = {n: set() for n in NODES}
        for k in SENSORS:
            for n in ring.get_nodes(k):     # write to every replica
                disk[n].add(k)

        disk["store-2"] = set()              # crash: store-2's data is gone
        alive = {"store-0", "store-1", "store-3"}

        # Read: try each replica in order, skip dead nodes
        readable = sum(
            1 for k in SENSORS
            if any(n in alive and k in disk[n] for n in ring.get_nodes(k))
        )
        print(f"  replicas={replicas} : {readable:5} of {len(SENSORS)} readable = "
              f"{percent(readable, len(SENSORS))}")
    print()


if __name__ == "__main__":
    part1_how_many_keys_move()
    part2_even_spread()
    part3_node_crash()
