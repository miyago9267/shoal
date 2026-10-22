Please add key expiry (TTL) and a `stats` operation to `kvsvc`. The store, the request handler and
the snapshot files must all agree on what is live and what has expired; all time comes from the
store's clock.

TTL:

- `set` accepts an optional `ttl` field: a positive number of seconds (int or float). Anything else
  (zero, negative, non-numeric, boolean) is a `bad_request`. In Python: `KVStore.set(key, value, ttl=None)`.
- A key set at time `t` with `ttl` T expires at `t + T`; from that instant on it behaves exactly like
  a missing key for every operation (`get`, `delete`, `exists`, `incr`, `mget`, `keys`, `len(store)`,
  `key in store`, snapshots).
- `set` without `ttl` removes any previous expiry. `incr` on a live key keeps its expiry; `incr` on a
  missing or expired key starts from 0 with no expiry.
- New op `{"op": "ttl", "key": k}` returns `{"ok": true, "ttl": seconds_left}` (`null` when the key
  has no expiry) or `not_found`.

Stats:

- New op `{"op": "stats"}` returns `{"ok": true, "hits": h, "misses": m, "expired": e, "keys": n}`.
- `hits` / `misses` count key lookups by `get` and `mget` (each key in an `mget` counts once) that
  found / did not find a live value. Expired keys are misses.
- `expired` is the number of keys whose TTL has run out, each key counted once, whether or not
  anyone touched it afterwards. A key that is deleted or overwritten before its TTL runs out does not
  count. `keys` is the number of live keys.
- Counters are runtime state: a store freshly loaded from a snapshot starts at zero.

Snapshots:

- Snapshots keep each key's expiry, so a key restored with `load_snapshot(path, clock=...)` expires at
  the same absolute time as before. Expired keys are never written, and keys that have already expired
  by the time a snapshot is loaded are dropped. Existing snapshot files (without expiry information)
  must keep loading.

Update the README for the new fields and ops.
