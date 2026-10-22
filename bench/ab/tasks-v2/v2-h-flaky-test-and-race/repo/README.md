# workpool

A small thread-based worker pool used by our ingestion jobs.

    from workpool import WorkerPool

    pool = WorkerPool(handler=process, workers=4)
    for item in items:
        pool.submit(item)
    pool.shutdown()          # waits until every submitted item was handled
    print(pool.stats())      # {"submitted": n, "processed": n, "failed": 0, ...}

Guarantees:

- `submit()` after `shutdown()` has started raises `PoolClosed`.
- `shutdown(wait=True)` returns only after every item that was accepted by
  `submit()` has been handled (successfully or not); `processed + failed`
  then equals `submitted`.
- Handler exceptions never kill a worker. They are recorded in
  `pool.errors` and counted as `failed`. An optional `RetryPolicy` re-runs
  failing items before giving up.

`workpool.batch.map_unordered(fn, items, workers)` is a convenience helper on
top of the pool; `python3 -m workpool.cli N` runs a small demo.

Run tests: `python3 -m unittest discover -s tests -t .`
