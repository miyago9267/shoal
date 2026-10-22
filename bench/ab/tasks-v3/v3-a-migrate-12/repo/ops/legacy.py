"""Deprecated logging API. New code must use ops.log.event."""

records = []

_VALID = {10, 20, 30, 40}


def legacy_log(msg, level):
    """Record ``msg`` at numeric ``level`` (10, 20, 30 or 40)."""
    if level not in _VALID:
        raise ValueError("bad level: %r" % (level,))
    records.append((level, msg))


def clear():
    del records[:]
