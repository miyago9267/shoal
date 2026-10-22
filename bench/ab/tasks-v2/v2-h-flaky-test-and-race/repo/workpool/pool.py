"""Thread-based worker pool with graceful shutdown."""
import queue
import threading

from .errors import HandlerFailed, PoolClosed
from .retry import NO_RETRY
from .stats import PoolStats, Timer

_POLL = 0.005


class WorkerPool:
    def __init__(self, handler, workers=4, retry=None, name="pool"):
        if workers < 1:
            raise ValueError("workers must be >= 1")
        self._handler = handler
        self._retry = retry or NO_RETRY
        self._queue = queue.Queue()
        self._closing = threading.Event()
        self._stats = PoolStats()
        self.errors = []
        self._errors_lock = threading.Lock()
        self._threads = [
            threading.Thread(target=self._worker, name=f"{name}-{i}", daemon=True)
            for i in range(workers)
        ]
        for thread in self._threads:
            thread.start()

    # public API ------------------------------------------------------------
    def submit(self, item):
        if self._closing.is_set():
            raise PoolClosed("pool is shutting down")
        self._stats.incr("submitted")
        self._queue.put(item)

    def shutdown(self, wait=True, timeout=None):
        """Stop accepting work; with ``wait`` block until workers exit."""
        self._closing.set()
        if wait:
            for thread in self._threads:
                thread.join(timeout)

    def stats(self):
        return self._stats.snapshot()

    @property
    def closed(self):
        return self._closing.is_set()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.shutdown(wait=True)
        return False

    # workers -----------------------------------------------------------------
    def _worker(self):
        while not self._closing.is_set():
            try:
                item = self._queue.get(timeout=_POLL)
            except queue.Empty:
                continue
            try:
                self._run_one(item)
            finally:
                self._queue.task_done()

    def _run_one(self, item):
        attempt = 1
        with Timer() as timer:
            while True:
                try:
                    self._handler(item)
                except Exception as exc:  # handler bugs must not kill the worker
                    if self._retry.should_retry(exc, attempt):
                        self._stats.incr("retried")
                        self._retry.sleep(attempt)
                        attempt += 1
                        continue
                    with self._errors_lock:
                        self.errors.append(HandlerFailed(item, exc, attempt))
                    self._stats.incr("failed")
                    break
                else:
                    self._stats.incr("processed")
                    break
        self._stats.add_busy(timer.elapsed)
