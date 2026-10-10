"""Flush queued notifications through a transport callable.

flush() drains one batch, renders each message with its channel template, rate
limits per channel, and sends. A transport that raises sends the message back to
the queue with a longer wait; after MAX_ATTEMPTS the message is dead-lettered
into FAILED instead of being retried.
"""

from notifications import channels, queue
from notifications.ratelimit import Limiter
from notifications.templates import render

MAX_ATTEMPTS = 4
BACKOFF_BASE_S = 2.0
FAILED = []

_limiter = Limiter()


def backoff_seconds(attempts):
    """Exponential backoff: 2, 4, 8 ... seconds, capped at 5 minutes."""
    return min(BACKOFF_BASE_S * (2 ** max(attempts - 1, 0)), 300.0)


def flush(transport, batch=10, now=None):
    """Send one batch; returns a dict with sent, deferred, retried and failed counts."""
    stats = {"sent": 0, "deferred": 0, "retried": 0, "failed": 0}
    for msg in queue.drain(batch):
        channel = channels.get(msg["channel"])
        if not _limiter.allow(msg["channel"], channel.per_minute, now):
            queue.requeue(msg)
            msg["attempts"] -= 1  # a rate-limit deferral is not a failed attempt
            stats["deferred"] += 1
            continue
        try:
            transport(msg["channel"], msg["to"], render(msg))
        except Exception as exc:  # transport errors are retried, not raised
            msg["last_error"] = type(exc).__name__
            if msg["attempts"] + 1 >= MAX_ATTEMPTS:
                FAILED.append(msg)
                stats["failed"] += 1
            else:
                msg["not_before"] = (now or 0) + backoff_seconds(msg["attempts"] + 1)
                queue.requeue(msg)
                stats["retried"] += 1
            continue
        stats["sent"] += 1
    return stats


def flush_all(transport, now=None):
    """Keep flushing until nothing but deferred messages remains."""
    total = {"sent": 0, "deferred": 0, "retried": 0, "failed": 0}
    while queue.depth():
        stats = flush(transport, now=now)
        for key, value in stats.items():
            total[key] += value
        if stats["sent"] == 0 and stats["failed"] == 0:
            break  # only deferrals or retries left; wait for the next tick
    return total


def reset():
    """Clear sender state (tests only)."""
    del FAILED[:]
    _limiter.reset()
