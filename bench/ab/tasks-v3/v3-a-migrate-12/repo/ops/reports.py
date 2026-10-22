"""Reports: stream rows of a report, skipping empty ones."""
from .legacy import legacy_log


def rows(name, source):
    """Generator over ``source``; ``None`` rows are skipped.

    Nothing is logged until the first row is requested, and the closing
    message only appears when the generator is exhausted.
    """
    legacy_log("report %s starting (%d rows)" % (name, len(source)), 20)
    emitted = 0
    for index, row in enumerate(source):
        if row is None:
            legacy_log("skipped empty row %d" % index, 10)
            continue
        emitted += 1
        yield row
    legacy_log("report %s done: %d rows" % (name, emitted), 20)


def summarize(name, source):
    return list(rows(name, source))


def count_empty(source):
    return sum(1 for r in source if r is None)


def head(name, source, n):
    out = []
    for row in rows(name, source):
        out.append(row)
        if len(out) == n:
            break
    return out
