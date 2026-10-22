"""Thread-safe counters reported by ``WorkerPool.stats()``."""
import threading
import time


class PoolStats:
    FIELDS = ("submitted", "processed", "failed", "retried")

    def __init__(self):
        self._lock = threading.Lock()
        self._counts = dict.fromkeys(self.FIELDS, 0)
        self._busy_seconds = 0.0

    def incr(self, name, amount=1):
        with self._lock:
            self._counts[name] += amount

    def add_busy(self, seconds):
        with self._lock:
            self._busy_seconds += seconds

    def snapshot(self):
        with self._lock:
            data = dict(self._counts)
            data["busy_seconds"] = round(self._busy_seconds, 6)
        return data


class Timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.perf_counter() - self.start
        return False
