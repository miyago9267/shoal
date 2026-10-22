"""Syncer: compare two counters and push the difference."""
from .legacy import legacy_log

MAX_PUSH = 100


def reconcile(local, remote, push):
    """Push the drift (capped at MAX_PUSH) through ``push(n) -> count``."""
    drift = abs(local - remote)
    if drift == 0:
        return 0
    level = 20
    if drift > 5:
        level = 30
    if drift > 50:
        level = 40
    legacy_log("drift %d (local=%d remote=%d)" % (drift, local, remote), level)
    count = push(min(drift, MAX_PUSH))
    legacy_log("pushed %d items" % count, 20)
    return count


def plan(pairs):
    return [(a, b, abs(a - b)) for a, b in pairs if a != b]


def worst(pairs):
    return max((abs(a - b) for a, b in pairs), default=0)
