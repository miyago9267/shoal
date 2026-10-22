# logpipe

Summarises proxy access logs per user and per plan.

```sh
python3 -m logpipe access.log users.csv          # text report
python3 -m logpipe access.log users.csv --json   # machine-readable
```

## Input

Access log, one request per line:

```
2026-10-01T12:00:03Z req=7f3a91 user=42 status=200 bytes=5120 path=/api/items ms=12
```

`bytes` may be `-` (no body, counts as 0). Lines that do not parse are
skipped and counted in `skipped`.

The proxy retries failed upstream calls and then logs the same request again:
both lines carry the same `req` id, usually a second or two apart. A request is
counted once per `req` id (the first line wins).

Users file: CSV with header `id,name,plan`. Requests from ids that are not in
the file are reported under user `unknown` and plan `none`.

## Pipeline

`logpipe.pipeline.run(lines, users_csv)` takes an iterable of log lines and the
users CSV text and returns a dict:

```python
{
  "total_requests": int, "total_bytes": int, "skipped": int,
  "users": {name: {"requests": int, "bytes": int, "errors": int, "sessions": int}},
  "plans": {plan: {"requests": int, "bytes": int}},
}
```

`errors` counts responses with status >= 500. A session is a run of requests
from one user with no gap longer than 30 minutes.

Stages, in order: `parse` -> `enrich` (join users) -> `sessionize` ->
`aggregate` -> `report`.

## Tests

```sh
python3 -m unittest discover -s tests -t .
```
