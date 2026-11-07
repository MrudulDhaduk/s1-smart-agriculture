"""
transfer.py - copy one sensor's readings to other Sensor Store nodes, in batches.

Used by rebalancing (server.py) and by `pmctl repair`.

Why batches: gRPC refuses messages bigger than 4 MB by default. One reading is about 66 bytes,
so a sensor reporting every 5 seconds passes 4 MB of history in under 4 days. Copying the whole
history in one message would then fail forever. Batches of 2,000 readings (~130 KB) never do.

Paging works from newest to oldest: fetch the newest 2,000 readings, then "everything older
than the oldest one I just got", and so on until a batch comes back short.
"""

import grpc

import sensor_store_pb2 as ss

BATCH = 2000  # readings per message


def copy_history(stub_of, sensor, sources, targets, timeout=10.0):
    """Copy every reading of `sensor` from one of `sources` to all `targets`.

    stub_of(node) returns that node's SensorStore stub.
    A source that is down, or alive but holding nothing for this sensor, is skipped and the
    next source is tried. A failure while WRITING to a target is raised to the caller, so a
    rebalance stops before it deletes anything. Returns how many readings were copied.
    """
    for source in sources:
        copied, to_ms, finished = 0, 0, False  # to_ms = 0 means "up to now"
        while True:
            try:
                batch = stub_of(source).GetHistory(
                    ss.StoreHistoryRequest(sensor_id=sensor, to_ms=to_ms, limit=BATCH),
                    timeout=timeout).readings
            except grpc.RpcError:
                break                                  # this source failed: try the next one
            if not batch:
                finished = True
                break
            for target in targets:
                stub_of(target).Put(ss.PutRequest(readings=batch), timeout=timeout)
            copied += len(batch)
            if len(batch) < BATCH or batch[-1].timestamp_ms <= 1:
                finished = True
                break
            to_ms = batch[-1].timestamp_ms - 1         # next page: everything older than this batch
        if finished and copied:
            return copied                              # complete history copied from this source
    return 0
