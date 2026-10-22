"""Stage 1: turn raw log lines into Events."""
from datetime import datetime, timezone

from .model import Event

REQUIRED = ("req", "user", "status", "bytes", "path", "ms")


def parse_ts(text):
    stamp = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    return int(stamp.replace(tzinfo=timezone.utc).timestamp())


def parse_line(line):
    """One line -> Event, or None when the line is malformed."""
    parts = line.split()
    if len(parts) < 2:
        return None
    fields = {}
    for part in parts[1:]:
        key, sep, value = part.partition("=")
        if not sep:
            return None
        fields[key] = value
    if any(name not in fields for name in REQUIRED):
        return None
    try:
        return Event(
            ts=parse_ts(parts[0]),
            request_id=fields["req"],
            user_id=int(fields["user"]),
            status=int(fields["status"]),
            bytes=0 if fields["bytes"] == "-" else int(fields["bytes"]),
            path=fields["path"],
            ms=int(fields["ms"]),
        )
    except ValueError:
        return None


def parse(lines):
    """Returns ``(events, skipped)``; blank lines are ignored silently."""
    events, skipped = [], 0
    for line in lines:
        if not line.strip():
            continue
        event = parse_line(line)
        if event is None:
            skipped += 1
        else:
            events.append(event)
    return events, skipped
