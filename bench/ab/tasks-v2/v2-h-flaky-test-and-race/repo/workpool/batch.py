"""Helpers built on top of WorkerPool."""
import threading

from .pool import WorkerPool


def map_unordered(fn, items, workers=4, retry=None):
    """Apply ``fn`` to every item in parallel; return ``(results, errors)``.

    ``results`` maps each item to its return value; ``errors`` lists the
    ``HandlerFailed`` records of items that kept failing.
    """
    results = {}
    lock = threading.Lock()

    def handler(item):
        value = fn(item)
        with lock:
            results[item] = value

    pool = WorkerPool(handler, workers=workers, retry=retry, name="map")
    with pool:
        for item in items:
            pool.submit(item)
    return results, list(pool.errors)


def chunked(items, size):
    if size < 1:
        raise ValueError("size must be >= 1")
    chunk = []
    for item in items:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
