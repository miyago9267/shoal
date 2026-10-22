# Moving from legacy_log to log.event

## Why

`legacy_log(msg, level)` produces free text. Nobody can filter or count it, and
the interesting values are baked into the sentence. `log.event(name, **fields)`
keeps the values apart so a sink can index them.

## Conventions

1. The event name is `<module>.<action>`; the exact names are fixed per call
   site and listed in the task description, so dashboards keep working.
2. Every value that was interpolated into the old message becomes a keyword
   field with its original type. Never pass a pre-formatted string where the
   old code had a number (`cents=1250`, not `amount="12.50"`). Values that were
   only presentation (a prefix such as `[export]`, a money format) are dropped.
3. The old numeric level becomes the `level` field as a string:
   10 -> "debug", 20 -> "info", 30 -> "warn", 40 -> "error". `log.event`
   defaults `level` to "info" when it is not passed.
4. The condition under which a message was logged must not change. A call that
   only fired when `verbose` was true still only fires then; a level that was
   computed stays computed.
5. Do not leave `legacy_log` calls behind. After the migration the module must
   not append anything to `ops.legacy.records`.

## Worked examples

A formatted message loses its formatting and keeps its values:

    # before
    legacy_log("copied %s (%d bytes)" % (name, size), 20)
    # after
    log.event("files.copied", name=name, size=size)

A computed level stays computed, but as a string:

    # before
    level = 20 if ok else 40
    legacy_log("check %s" % name, level)
    # after
    level = "info" if ok else "error"
    log.event("checks.ran", name=name, level=level)

A call in a loop stays in the loop, one event per iteration. A call guarded by
a flag stays guarded:

    for item in items:
        log.event("batch.item", item=item)
    if verbose:
        log.event("batch.detail", count=len(items), level="debug")

Keyword calls such as `legacy_log(level=30, msg=...)` are ordinary calls and
migrate the same way. `name` is positional-only on `log.event`, so a field
called `name=` is fine.

## Checklist per module

1. Swap the import (`from . import log`).
2. Convert each call site, one event each.
3. Delete helpers that only existed to prefix or format log text.
4. Run the module tests; they check behaviour, not log output.

## Sinks

`log.set_sink(fn)` installs `fn(name, fields)`; `log.reset_sink()` restores the
default sink that appends `(name, fields)` to `log.events`. The sink receives a
fresh dict, so it can keep it.
