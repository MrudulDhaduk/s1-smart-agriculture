"""
membership.py - where the list of ring nodes lives, so every Partition Manager copy agrees.

The membership is one small record:   {"version": 3, "nodes": ["sensor-store-0", ...]}
`version` goes up by 1 on every change, so a copy can tell "has anything changed?" cheaply.

Two places it can live (chosen with MEMBERSHIP_BACKEND):
    file       a JSON file on a shared volume   (local docker-compose, tests)
    firestore  one Firestore document           (GKE, the real deployment)
"""

import json
import os
import threading


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
        tmp = self.path + ".tmp"
        with self.lock:
            with open(tmp, "w") as f:
                json.dump({"version": version, "nodes": nodes}, f)
            os.replace(tmp, self.path)  # atomic: readers never see a half-written file


class FirestoreMembership:
    def __init__(self, initial_nodes, collection="ring", document="membership"):
        from google.cloud import firestore  # imported here so local runs don't need it

        self.doc = firestore.Client().collection(collection).document(document)
        if not self.doc.get().exists:
            self.save(1, initial_nodes)

    def load(self):
        data = self.doc.get().to_dict()
        return data["version"], data["nodes"]

    def save(self, version, nodes):
        self.doc.set({"version": version, "nodes": nodes})


def from_env():
    initial = [n for n in os.environ.get("INITIAL_NODES", "").split(",") if n]
    if os.environ.get("MEMBERSHIP_BACKEND", "file") == "firestore":
        return FirestoreMembership(initial)
    return FileMembership(os.environ.get("MEMBERSHIP_FILE", "./membership.json"), initial)
