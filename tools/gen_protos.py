"""
gen_protos.py - turn the .proto contracts into Python code.

    python tools/gen_protos.py services/partition-manager/gen

Creates reading_pb2.py, partition_manager_pb2_grpc.py, ... in the given folder.
The Dockerfiles run this during the build, so you only run it by hand when
running a service directly on your laptop (without Docker).
"""

import os
import sys

from grpc_tools import protoc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACTS = os.path.join(ROOT, "contracts")
PROTOS = ["reading.proto", "partition_manager.proto", "sensor_store.proto"]


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    args = ["protoc", f"-I{CONTRACTS}", f"--python_out={out_dir}", f"--grpc_python_out={out_dir}"]
    if protoc.main(args + PROTOS) != 0:
        sys.exit("protoc failed")
    print(f"generated gRPC code in {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "gen")
