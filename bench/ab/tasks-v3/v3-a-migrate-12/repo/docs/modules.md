# Module notes

Short notes on what each module does and what callers rely on. The logging
behaviour is described in `docs/migration.md`; this file is about the rest.

## billing
`charge(account, cents)` refuses non-positive amounts and amounts above the
account limit, otherwise adds to `balance`. `refund` never goes below zero.
`statement` is sorted by account id and formats money with two decimals.

## inventory
`restock` takes `(sku, qty)` pairs, skips non-positive quantities and returns
the number of SKUs it touched. `take` raises `KeyError` for unknown SKUs and
`ValueError` when stock is short. `LOW_WATER` is the threshold for "low".

## mailer
`send` tries the transport up to `MAX_ATTEMPTS` times, retrying only on
`OSError`. Other exceptions propagate. `send_batch` returns the delivered count.

## scheduler
`tick` runs due jobs in list order. A job that finishes can unblock a later job
in the same tick through its `after` list. Paused jobs never run.

## authn
`login` never raises for bad credentials. Locked users are rejected before the
password is looked at.

## cache
Least-recently-used eviction: both `get` and `put` refresh recency. The
`verbose` flag only controls hit/miss chatter; evictions are always reported.

## importer
CSV-ish `name,qty,price` rows. Bad rows are skipped, never fatal.

## exporter
Writes non-empty documents in name order through the caller's writer.

## syncer
`reconcile` pushes `min(drift, MAX_PUSH)` items and returns what the pusher
reports it moved.

## backup
At most one backup per `MIN_INTERVAL`. The copy callable may raise; the error
propagates after the cleanup message is written.

## notifier
Tries every channel; one failing channel never stops the others.

## reports
`rows` is a generator. Callers that stop early (see `head`) never see the
closing message.
