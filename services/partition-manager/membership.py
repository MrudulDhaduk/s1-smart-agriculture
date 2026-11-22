"""
membership.py - where the list of ring nodes lives, so every Partition Manager copy agrees.

The membership is one small record:   {"version": 3, "nodes": ["sensor-store-0", ...]}
`version` goes up by 1 on every change, so a copy can tell "has anything changed?" cheaply.

Two places it can live (chosen with MEMBERSHIP_BACKEND):
    file       a JSON file on a shared volume   (local docker-compose, tests)
    firestore  one Firestore document           (GKE, the real deployment)

Changes use save_if(expected_version, ...): a compare-and-set. It saves only if the
stored version is still the one the caller read, so two router pods changing the ring
at the same moment cannot silently overwrite each other (a "lost update").
"""

import json
import os
import threading
import uuid

try:
    import fcntl  # Linux/macOS: a lock that also works between processes (pods sharing the file)
except ImportError:  # Windows: only the in-process lock below
    fcntl = None


class FileMembership:
    def __init__(self, path, initial_nodes):
        self.path = path
        self.lock = threading.Lock()
        if not os.path.exists(path):
            self.save(1, initial_nodes)

    def load(self):
        with self.lock, open(self.path) as f:
            data = json.load(f)
        return data["version"], data["nodes"]

    def save(self, version, nodes):
        tmp = f"{self.path}.{uuid.uuid4().hex}.tmp"  # unique name: two pods may save at the same moment
        with self.lock:
            with open(tmp, "w") as f:
                json.dump({"version": version, "nodes": nodes}, f)
                f.flush()
                os.fsync(f.fileno())    # really on disk before we swap it in (survives a power cut)
            os.replace(tmp, self.path)  # atomic: readers never see a half-written file

    def save_if(self, expected_version, version, nodes):
        """Save only if the stored version is still expected_version. Returns True if saved."""
        with open(f"{self.path}.lock", "a") as lock_file:
            if fcntl:
                fcntl.flock(lock_file, fcntl.LOCK_EX)  # held until the file is closed
            current, _ = self.load()
            if current != expected_version:
                return False
            self.save(version, nodes)
            return True


class FirestoreMembership:
    def __init__(self, initial_nodes, collection="ring", document="membership"):
        from google.cloud import firestore  # imported here so local runs don't need it

        self.firestore = firestore
        self.client = firestore.Client()
        self.doc = self.client.collection(collection).document(document)
        if not self.doc.get().exists:
            self.save(1, initial_nodes)

    def load(self):
        data = self.doc.get().to_dict()
        return data["version"], data["nodes"]

    def save(self, version, nodes):
        self.doc.set({"version": version, "nodes": nodes})

    def save_if(self, expected_version, version, nodes):
        """Save only if the stored version is still expected_version, inside a Firestore
        transaction (Firestore retries it if the document changes before it commits)."""

        @self.firestore.transactional
        def run(transaction):
            data = self.doc.get(transaction=transaction).to_dict()
            if data["version"] != expected_version:
                return False
            transaction.set(self.doc, {"version": version, "nodes": nodes})
            return True

        return run(self.client.transaction())


def from_env():
    initial = [n for n in os.environ.get("INITIAL_NODES", "").split(",") if n]
    if os.environ.get("MEMBERSHIP_BACKEND", "file") == "firestore":
        return FirestoreMembership(initial)
    return FileMembership(os.environ.get("MEMBERSHIP_FILE", "./membership.json"), initial)
