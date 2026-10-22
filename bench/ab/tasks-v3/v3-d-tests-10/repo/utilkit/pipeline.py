"""Glue helpers that run a utility over many inputs and collect the outcomes."""


def safe(fn, *args, default=None):
    """Call ``fn`` and return ``default`` instead of ValueError/TypeError."""
    try:
        return fn(*args)
    except (ValueError, TypeError):
        return default


def batch(fn, items):
    """Apply ``fn`` to each item; returns (results, errors) keyed by index."""
    results = {}
    errors = {}
    for index, item in enumerate(items):
        try:
            results[index] = fn(item)
        except (ValueError, TypeError, KeyError) as exc:
            errors[index] = "%s: %s" % (type(exc).__name__, exc)
    return results, errors


def table(rows, headers=None):
    """Left-aligned plain text table; ``rows`` are sequences of values."""
    rows = [[str(c) for c in row] for row in rows]
    if headers:
        rows = [list(headers)] + rows
    if not rows:
        return ""
    widths = [max(len(r[i]) for r in rows if i < len(r)) for i in range(max(map(len, rows)))]
    lines = []
    for r in rows:
        cells = [r[i].ljust(widths[i]) if i < len(r) else " " * widths[i] for i in range(len(widths))]
        lines.append("  ".join(cells).rstrip())
    return "\n".join(lines)


def summary(results, errors):
    total = len(results) + len(errors)
    return "%d ok, %d failed of %d" % (len(results), len(errors), total)


def first_error(errors):
    if not errors:
        return None
    index = min(errors)
    return index, errors[index]


def partition(items, predicate):
    yes, no = [], []
    for item in items:
        (yes if predicate(item) else no).append(item)
    return yes, no
