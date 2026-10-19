"""Sliding-window rate limiter keyed by channel."""

import time
from collections import defaultdict, deque

WINDOW_S = 60.0


class Limiter:
    """Allows at most per_minute events per key in any 60 second window."""

    def __init__(self):
        self._events = defaultdict(deque)

    def allow(self, key, per_minute, now=None):
        """Record an event and return True when it is within the limit."""
        now = time.time() if now is None else now
        window = self._events[key]
        while window and now - window[0] >= WINDOW_S:
            window.popleft()
        if len(window) >= per_minute:
            return False
        window.append(now)
        return True

    def remaining(self, key, per_minute, now=None):
        """How many more events fit in the current window."""
        now = time.time() if now is None else now
        window = self._events[key]
        live = sum(1 for t in window if now - t < WINDOW_S)
        return max(per_minute - live, 0)

    def reset(self):
        """Forget all events."""
        self._events.clear()
