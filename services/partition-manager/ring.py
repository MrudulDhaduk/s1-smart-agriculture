"""
ring.py - a consistent hashing ring (the core concept of S1).

Big idea:
  - Imagine a circle of numbers from 0 up to 2^128 (a "ring").
  - Every storage node is placed on the circle at a few spots ("virtual nodes").
  - Every sensor key is also placed on the circle (by hashing its ID).
  - A key belongs to the first node you meet walking CLOCKWISE from the key.
  - With replication, the key is also copied to the next 1-2 DIFFERENT nodes clockwise.
"""

import bisect
import hashlib


def hash_key(text: str) -> int:
    """Turn any text into a big number (its position on the ring).

    We use MD5 instead of Python's built-in hash() because hash() gives a
    DIFFERENT answer every time Python restarts. Two copies of the Partition
    Manager must agree on where a key lives, so the answer must never change.
    (MD5 is not used for security here, only to spread keys evenly.)
    """
    return int(hashlib.md5(text.encode()).hexdigest(), 16)


class HashRing:
    def __init__(self, vnodes: int = 100, replicas: int = 3):
        self.vnodes = vnodes        # how many spots each node gets on the circle
        self.replicas = replicas    # how many different nodes store each key
        self.nodes = set()          # the real nodes, e.g. {"store-0", "store-1"}
        self._positions = []        # sorted list of every spot on the circle
        self._owner = {}            # spot on the circle -> which real node it belongs to

    def add_node(self, node: str) -> None:
        """Put a new node on the ring at `vnodes` spots."""
        if node in self.nodes:  # already on the ring: adding again must not duplicate its spots
            return
        self.nodes.add(node)
        for i in range(self.vnodes):
            spot = hash_key(f"{node}#{i}")       # e.g. "store-3#0", "store-3#1", ...
            bisect.insort(self._positions, spot)  # insert while keeping the list sorted
            self._owner[spot] = node

    def remove_node(self, node: str) -> None:
        """Take a node off the ring (all of its spots disappear)."""
        self.nodes.discard(node)
        self._positions = [s for s in self._positions if self._owner[s] != node]
        self._owner = {s: n for s, n in self._owner.items() if n != node}

    def get_nodes(self, key: str) -> list:
        """Return the nodes that should store `key`, primary first.

        Walk clockwise from the key's spot and collect DIFFERENT real nodes
        until we have `replicas` of them (or run out of nodes).
        """
        if not self._positions:
            return []
        want = min(self.replicas, len(self.nodes))
        start = bisect.bisect_right(self._positions, hash_key(key))  # first spot after the key
        result = []
        i = start
        while len(result) < want:
            spot = self._positions[i % len(self._positions)]  # % wraps around the circle
            node = self._owner[spot]
            if node not in result:      # skip extra spots of a node we already picked
                result.append(node)
            i += 1
        return result

    def get_node(self, key: str) -> str:
        """The primary node for `key` (the first one clockwise)."""
        nodes = self.get_nodes(key)
        return nodes[0] if nodes else None
