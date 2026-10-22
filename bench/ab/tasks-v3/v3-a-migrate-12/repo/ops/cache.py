"""Cache: small FIFO-by-recency cache with optional chatty logging."""
from .legacy import legacy_log


class Cache:
    def __init__(self, capacity, verbose=False):
        self.capacity = capacity
        self.verbose = verbose
        self.hits = 0
        self.misses = 0
        self._data = {}

    def get(self, key):
        if key in self._data:
            self.hits += 1
            value = self._data.pop(key)
            self._data[key] = value
            if self.verbose:
                legacy_log("hit %s" % key, 10)
            return value
        self.misses += 1
        if self.verbose:
            legacy_log("miss %s" % key, 10)
        return None

    def put(self, key, value):
        self._data.pop(key, None)
        self._data[key] = value
        evicted = []
        while len(self._data) > self.capacity:
            oldest = next(iter(self._data))
            del self._data[oldest]
            evicted.append(oldest)
        if evicted:
            legacy_log("evicted: " + ", ".join(evicted), 20)

    def keys(self):
        return list(self._data)

    def __len__(self):
        return len(self._data)

    def ratio(self):
        seen = self.hits + self.misses
        return self.hits / seen if seen else 0.0
