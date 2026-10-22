"""The in-memory store."""
import time
from dataclasses import dataclass

from .errors import NotFound, WrongType

_MISSING = object()


@dataclass
class Entry:
    value: object
    updated_at: float


class KVStore:
    """A dict of key -> Entry with a pluggable clock (``() -> float`` seconds)."""

    def __init__(self, clock=time.time):
        self._clock = clock
        self._data = {}

    def now(self):
        return self._clock()

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data

    def get(self, key, default=_MISSING):
        entry = self._data.get(key)
        if entry is None:
            if default is _MISSING:
                raise NotFound(key)
            return default
        return entry.value

    def set(self, key, value):
        self._data[key] = Entry(value, self.now())

    def delete(self, key):
        if key not in self._data:
            raise NotFound(key)
        del self._data[key]

    def incr(self, key, by=1):
        entry = self._data.get(key)
        current = 0 if entry is None else entry.value
        if not isinstance(current, int) or isinstance(current, bool):
            raise WrongType(key)
        current += by
        if entry is None:
            self._data[key] = Entry(current, self.now())
        else:
            entry.value = current
            entry.updated_at = self.now()
        return current

    def keys(self, prefix=""):
        return sorted(key for key in self._data if key.startswith(prefix))

    def entries(self):
        """``(key, Entry)`` pairs in key order (used by snapshots)."""
        return [(key, self._data[key]) for key in sorted(self._data)]

    def load_entry(self, key, entry):
        """Insert an entry as-is (used when restoring a snapshot)."""
        self._data[key] = entry
