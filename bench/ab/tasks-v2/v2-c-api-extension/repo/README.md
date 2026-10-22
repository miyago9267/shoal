# kvsvc

An in-memory key-value service. The store lives in `kvsvc.store`, the request
layer in `kvsvc.handler`, and JSON snapshots in `kvsvc.snapshot`.
`python3 -m kvsvc --snapshot data.json` serves JSON-lines requests on stdin.

## Requests

Every request is a JSON object with an `op`. Every response has `ok`; failed
responses carry `error` (`bad_request`, `not_found`, `wrong_type` or
`no_snapshot_path`).

| op         | fields                    | response                                   |
|------------|---------------------------|--------------------------------------------|
| `ping`     |                           | `{"ok": true, "pong": true}`               |
| `get`      | `key`                     | `{"ok": true, "value": ...}` or not_found  |
| `set`      | `key`, `value`            | `{"ok": true}`                             |
| `delete`   | `key`                     | `{"ok": true}` or not_found                |
| `exists`   | `key`                     | `{"ok": true, "exists": bool}`             |
| `incr`     | `key`, optional `by` (int)| `{"ok": true, "value": int}`               |
| `mget`     | `keys` (list)             | `{"ok": true, "values": {key: value/null}}`|
| `keys`     | optional `prefix`         | `{"ok": true, "keys": [sorted keys]}`      |
| `snapshot` |                           | `{"ok": true, "count": n}`                 |

Keys are non-empty strings; values are any JSON value. `incr` treats a missing
key as 0 and fails with `wrong_type` when the value is not an integer.

## Python API

```python
from kvsvc.store import KVStore
from kvsvc.handler import Handler
from kvsvc.snapshot import save_snapshot, load_snapshot

store = KVStore()                 # KVStore(clock=...) takes a () -> float seconds
handler = Handler(store, snapshot_path="data.json")
handler.handle({"op": "set", "key": "a", "value": 1})
save_snapshot(store, "data.json")
store = load_snapshot("data.json")   # load_snapshot(path, clock=...)
```

The clock is used for `updated_at` bookkeeping and makes time-dependent
behaviour testable.

## Snapshot format

```json
{"version": 1, "entries": [{"key": "a", "value": 1, "updated_at": 1700000000.0}]}
```

## Tests

```sh
python3 -m unittest discover -s tests -t .
```
