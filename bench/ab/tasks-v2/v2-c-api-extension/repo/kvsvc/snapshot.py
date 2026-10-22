"""Save and restore a KVStore as a JSON file."""
import json
import os
import time

from .errors import KVError
from .store import Entry, KVStore

VERSION = 1


def save_snapshot(store, path):
    """Atomically write every entry of ``store``; returns the entry count."""
    entries = [
        {"key": key, "value": entry.value, "updated_at": entry.updated_at}
        for key, entry in store.entries()
    ]
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": VERSION, "entries": entries}, fh)
    os.replace(tmp, path)
    return len(entries)


def load_snapshot(path, clock=time.time):
    """Build a new KVStore from ``path``."""
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError) as exc:
        raise KVError(f"cannot read snapshot {path}: {exc}") from exc
    if payload.get("version") != VERSION:
        raise KVError(f"unsupported snapshot version {payload.get('version')!r}")
    store = KVStore(clock=clock)
    for item in payload.get("entries", []):
        store.load_entry(item["key"], Entry(item["value"], item.get("updated_at", 0.0)))
    return store
