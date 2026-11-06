# pytest runs this first: make sure the gRPC code is generated from contracts/ for both services.
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for service in ("partition-manager", "sensor-store"):
    gen = os.path.join(ROOT, "services", service, "gen")
    if not os.path.exists(os.path.join(gen, "sensor_store_pb2.py")):
        subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "gen_protos.py"), gen])
sys.path.insert(0, os.path.join(HERE, "gen"))  # so tests can import the generated modules
