# Task: migrate the `ops` package off `legacy_log`

Twelve modules in `ops/` still log through the deprecated
`ops.legacy.legacy_log(msg, level)`. Move every one of them to
`ops.log.event(name, **fields)` following `docs/migration.md`, so that the
modules no longer touch `ops.legacy` at all. Behaviour other than logging must
not change. The modules are independent; do not edit `ops/legacy.py` or
`ops/log.py`.

Each call site becomes exactly one event with the name, fields and level below
(`level` is always a string; the field `level` may be omitted when it is
"info"). Every other value keeps its original type.

| module | event | fields | level |
|---|---|---|---|
| billing | `billing.rejected` | cents | warn |
| billing | `billing.declined` | account (the id), cents, limit | error |
| billing | `billing.charged` | account, cents (raw int) | info |
| billing | `billing.refunded` | account, cents (the amount actually refunded) | info |
| inventory | `inventory.restock` (once per delivery applied) | sku, qty, on_hand | info |
| inventory | `inventory.low` | sku, on_hand | warn |
| inventory | `inventory.restock_done` (always, once) | skus (count touched) | info |
| mailer | `mailer.attempt` | to, attempt | info on attempt 1, warn after |
| mailer | `mailer.gave_up` | to, attempts | error |
| scheduler | `scheduler.skip` | job, reason (`"paused"`), or reason (`"waiting"`) plus dep | debug |
| scheduler | `scheduler.run` | job | info |
| authn | `authn.locked` | user | warn |
| authn | `authn.failed` | user, error (the exception text) | error |
| authn | `authn.ok` | user | info |
| cache | `cache.hit`, `cache.miss` | key | debug, only when the cache is verbose |
| cache | `cache.evicted` | keys (a list, in eviction order) | info, always |
| importer | `importer.bad_row` | row, reason (the text after `row N: `) | warn |
| importer | `importer.done` | imported, total | error when nothing was imported, else info |
| exporter | `exporter.empty` | name | warn |
| exporter | `exporter.wrote` | name, size (bytes returned by the writer) | info |
| syncer | `syncer.drift` | local, remote, drift | info, warn above 5, error above 50 |
| syncer | `syncer.pushed` | count | info |
| backup | `backup.skipped` | name, age_days (float) | warn |
| backup | `backup.attempt_finished` | name | debug |
| backup | `backup.done` | name, secs (float) | info |
| notifier | `notifier.channel_error` | channel, error | error |
| notifier | `notifier.sent` | user, channel | info |
| notifier | `notifier.dropped` | user, channel_count | warn |
| reports | `reports.start` | name, rows | info |
| reports | `reports.row_skipped` | index | debug |
| reports | `reports.end` | name, emitted | info |

Each event fires exactly where its `legacy_log` call fired before: same
conditions, same order, same number of times (once per loop iteration where the
old call was inside a loop, nothing for a generator until it is iterated).
