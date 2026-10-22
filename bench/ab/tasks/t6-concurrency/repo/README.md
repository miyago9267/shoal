# ttlcache

In-memory LRU cache with optional per-entry TTL, used by the API gateway to
cache upstream lookups and count rate-limit hits.

```python
from ttlcache import Cache

cache = Cache(max_size=1000, default_ttl=30)
cache.set("user:1", {"name": "Ada"})
cache.get("user:1")
cache.incr("requests:/login")
cache.stats().hit_rate
```

Run the tests with `python3 -m unittest discover -s tests -t .`.
