import unittest

from ttlcache import Cache


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class CacheTests(unittest.TestCase):
    def test_get_set(self):
        cache = Cache()
        cache.set("a", 1)
        self.assertEqual(cache.get("a"), 1)
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("b", "dflt"), "dflt")

    def test_lru_eviction(self):
        cache = Cache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")
        cache.set("c", 3)
        self.assertIn("a", cache)
        self.assertNotIn("b", cache)
        self.assertEqual(cache.stats().evictions, 1)

    def test_ttl_expiry(self):
        clock = FakeClock()
        cache = Cache(default_ttl=10, clock=clock)
        cache.set("a", 1)
        clock.now += 9
        self.assertEqual(cache.get("a"), 1)
        clock.now += 1
        self.assertIsNone(cache.get("a"))
        self.assertEqual(len(cache), 0)

    def test_incr(self):
        cache = Cache()
        self.assertEqual(cache.incr("n"), 1)
        self.assertEqual(cache.incr("n", 5), 6)
        self.assertEqual(cache.get("n"), 6)

    def test_get_or_set(self):
        cache = Cache()
        calls = []
        self.assertEqual(cache.get_or_set("k", lambda: calls.append(1) or 42), 42)
        self.assertEqual(cache.get_or_set("k", lambda: calls.append(1) or 99), 42)
        self.assertEqual(len(calls), 1)

    def test_stats(self):
        cache = Cache()
        cache.set("a", 1)
        cache.get("a")
        cache.get("missing")
        stats = cache.stats()
        self.assertEqual((stats.hits, stats.misses, stats.size), (1, 1, 1))
        self.assertEqual(stats.hit_rate, 0.5)

    def test_delete_and_clear(self):
        cache = Cache()
        cache.set("a", 1)
        self.assertTrue(cache.delete("a"))
        self.assertFalse(cache.delete("a"))
        cache.set("b", 2)
        cache.clear()
        self.assertEqual(len(cache), 0)


if __name__ == "__main__":
    unittest.main()
