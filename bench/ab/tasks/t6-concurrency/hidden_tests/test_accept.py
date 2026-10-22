import itertools
import sys
import threading
import unittest

from ttlcache import Cache

THREADS = 8
ROUNDS = 3000


class ThreadSafetyAcceptance(unittest.TestCase):
    def setUp(self):
        self._interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)  # force frequent thread switches

    def tearDown(self):
        sys.setswitchinterval(self._interval)

    def _run(self, work):
        errors = []
        barrier = threading.Barrier(THREADS)

        def wrapper():
            try:
                barrier.wait()
                work()
            except BaseException as exc:  # noqa: BLE001
                errors.append(repr(exc))

        threads = [threading.Thread(target=wrapper, daemon=True) for _ in range(THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertFalse(any(t.is_alive() for t in threads), "worker threads hung (deadlock?)")
        self.assertEqual(errors, [])

    def test_concurrent_incr_loses_nothing(self):
        cache = Cache(max_size=16)

        def work():
            for _ in range(ROUNDS):
                cache.incr("counter")

        self._run(work)
        self.assertEqual(cache.get("counter"), THREADS * ROUNDS)

    def test_stats_count_every_request(self):
        cache = Cache(max_size=64)
        cache.set("present", 1)

        def work():
            for _ in range(ROUNDS):
                cache.get("present")
                cache.get("absent")

        self._run(work)
        stats = cache.stats()
        self.assertEqual(stats.hits, THREADS * ROUNDS)
        self.assertEqual(stats.misses, THREADS * ROUNDS)

    def test_concurrent_set_respects_bounds_and_counts_evictions(self):
        cache = Cache(max_size=50)
        keys = itertools.count()

        def work():
            for _ in range(ROUNDS):
                k = next(keys)
                cache.set(k, k)
                cache.get(k - 1)

        self._run(work)
        self.assertLessEqual(len(cache), 50)
        self.assertEqual(cache.stats().evictions, THREADS * ROUNDS - len(cache))

    def test_api_unchanged(self):
        cache = Cache(max_size=2, default_ttl=None)
        cache.set("a", 1)
        self.assertEqual(cache.incr("a", 2), 3)
        self.assertEqual(cache.get_or_set("b", lambda: 7), 7)
        self.assertIn("b", cache)
        self.assertTrue(cache.delete("b"))
        self.assertEqual(cache.stats().size, 1)


if __name__ == "__main__":
    unittest.main()
