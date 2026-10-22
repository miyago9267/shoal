"""Structured event logging."""

LEVELS = {10: "debug", 20: "info", 30: "warn", 40: "error"}
NAMES = set(LEVELS.values())

events = []
_sink = None


def _default_sink(name, fields):
    events.append((name, fields))


def set_sink(fn):
    """Install ``fn(name, fields)`` as the receiver of every event."""
    global _sink
    _sink = fn


def reset_sink():
    global _sink
    _sink = None


def event(name, /, **fields):
    """Emit one event. ``level`` is a string and defaults to "info"."""
    if not name or "." not in name:
        raise ValueError("event name must look like module.action: %r" % (name,))
    fields.setdefault("level", "info")
    if fields["level"] not in NAMES:
        raise ValueError("bad level: %r" % (fields["level"],))
    (_sink or _default_sink)(name, dict(fields))
