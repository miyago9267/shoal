"""Serve JSON-lines requests on stdin: ``python3 -m kvsvc [--snapshot FILE]``."""
import argparse
import json
import os
import sys

from .handler import Handler
from .snapshot import load_snapshot
from .store import KVStore


def main(argv=None):
    parser = argparse.ArgumentParser(prog="kvsvc")
    parser.add_argument("--snapshot", help="load from and save to this file")
    args = parser.parse_args(argv)
    if args.snapshot and os.path.exists(args.snapshot):
        store = load_snapshot(args.snapshot)
    else:
        store = KVStore()
    handler = Handler(store, snapshot_path=args.snapshot)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            response = {"ok": False, "error": "bad_request", "message": "invalid JSON"}
        else:
            response = handler.handle(request)
        print(json.dumps(response), flush=True)
    return 0


sys.exit(main())
