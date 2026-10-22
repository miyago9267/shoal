"""LRU cache with optional per-entry expiry."""
import time
from collections import OrderedDict

from .stats import CacheStats

_MISSING = object()


class Cache:
    """Bounded LRU cache. Entries may expire after ``ttl`` seconds."""

    def __init__(self, max_size=1024, default_ttl=None, clock=time.monotonic):
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._clock = clock
        self._data = OrderedDict()  # key -> (value, expires_at or None)
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _lookup(self, key):
        entry = self._data.get(key)
        if entry is None:
            return _MISSING
        value, expires_at = entry
        if expires_at is not None and self._clock() >= expires_at:
            del self._data[key]
            return _MISSING
        self._data.move_to_end(key)
        return value

    def get(self, key, default=None):
        value = self._lookup(key)
        if value is _MISSING:
            self._misses += 1
            return default
        self._hits += 1
        return value

    def set(self, key, value, ttl=None):
        ttl = self.default_ttl if ttl is None else ttl
        expires_at = None if ttl is None else self._clock() + ttl
        self._data[key] = (value, expires_at)
        self._data.move_to_end(key)
        while len(self._data) > self.max_size:
            self._data.popitem(last=False)
            self._evictions += 1

    def delete(self, key):
        return self._data.pop(key, None) is not None

    def incr(self, key, delta=1):
        """Add ``delta`` to a numeric entry, starting from 0 when missing."""
        current = self.get(key, 0)
        self.set(key, current + delta)
        return current + delta

    def get_or_set(self, key, factory, ttl=None):
        """Return the cached value, computing and storing it on a miss."""
        value = self._lookup(key)
        if value is not _MISSING:
            self._hits += 1
            return value
        self._misses += 1
        value = factory()
        self.set(key, value, ttl)
        return value

    def clear(self):
        self._data.clear()

    def stats(self):
        return CacheStats(self._hits, self._misses, self._evictions, len(self._data))

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return self._lookup(key) is not _MISSING
