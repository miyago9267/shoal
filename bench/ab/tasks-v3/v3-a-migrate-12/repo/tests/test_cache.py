import unittest

from ops.cache import Cache


class CacheTest(unittest.TestCase):
    def test_hit_miss(self):
        c = Cache(2)
        c.put("a", 1)
        self.assertEqual(c.get("a"), 1)
        self.assertIsNone(c.get("b"))
        self.assertEqual((c.hits, c.misses), (1, 1))

    def test_eviction_order(self):
        c = Cache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.get("a")
        c.put("c", 3)
        self.assertEqual(c.keys(), ["a", "c"])

    def test_ratio(self):
        c = Cache(1)
        self.assertEqual(c.ratio(), 0.0)
