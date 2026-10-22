"""Read-only snapshot of cache counters."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    evictions: int
    size: int

    @property
    def requests(self):
        return self.hits + self.misses

    @property
    def hit_rate(self):
        return self.hits / self.requests if self.requests else 0.0
