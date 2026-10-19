"""In-memory outbound message queue.

Messages are dicts: {"id": str, "channel": str, "to": str, "body": str,
"priority": int, "attempts": int}. Lower priority numbers go first; within a
priority the queue is FIFO. Nothing is persisted: a process restart loses every
pending message, which is acceptable for the current single-process tool.
"""

import itertools
import time

PENDING = []
_SEQ = itertools.count(1)
DEDUPE_WINDOW_S = 60.0
_RECENT = {}

MAX_PENDING = 10000


class QueueFull(Exception):
    """Raised when MAX_PENDING messages are already waiting."""


def _dedupe_key(msg):
    return (msg["channel"], msg["to"], msg["body"])


def enqueue(msg, now=None):
    """Add a message; an identical one seen within DEDUPE_WINDOW_S is dropped.

    Returns True when the message was queued, False when it was a duplicate.
    """
    now = time.time() if now is None else now
    key = _dedupe_key(msg)
    last = _RECENT.get(key)
    if last is not None and now - last < DEDUPE_WINDOW_S:
        return False
    if len(PENDING) >= MAX_PENDING:
        raise QueueFull(len(PENDING))
    item = dict(msg)
    item.setdefault("priority", 5)
    item.setdefault("attempts", 0)
    item["seq"] = next(_SEQ)
    PENDING.append(item)
    _RECENT[key] = now
    return True


def _order(item):
    return (item["priority"], item["seq"])


def drain(batch=10):
    """Remove and return up to batch messages, best priority first."""
    PENDING.sort(key=_order)
    out = PENDING[:batch]
    del PENDING[:batch]
    return out


def requeue(item):
    """Put a failed message back, keeping its original sequence number."""
    item["attempts"] = item.get("attempts", 0) + 1
    PENDING.append(item)


def depth():
    """Number of messages waiting."""
    return len(PENDING)


def purge_recent(now=None, keep=DEDUPE_WINDOW_S):
    """Forget dedupe entries older than keep seconds."""
    now = time.time() if now is None else now
    for key in [k for k, t in _RECENT.items() if now - t >= keep]:
        del _RECENT[key]


def reset():
    """Clear all state (tests only)."""
    del PENDING[:]
    _RECENT.clear()
