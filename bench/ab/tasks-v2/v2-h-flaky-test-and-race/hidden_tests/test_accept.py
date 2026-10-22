import sys
import threading
import time
import unittest

from workpool import PoolClosed, RetryPolicy, WorkerPool
from workpool.batch import map_unordered
from workpool.pipeline import Pipeline, Stage

JOIN_TIMEOUT = 20


class Recorder:
    def __init__(self, delay=0.0, fail=lambda item: False):
        self.items = []
        self.lock = threading.Lock()
        self.delay = delay
        self.fail = fail

    def __call__(self, item):
        if self.delay:
            time.sleep(self.delay)
        if self.fail(item):
            raise ValueError(item)
        with self.lock:
            self.items.append(item)


def shutdown_bounded(test, pool, **kwargs):
    """Run shutdown in a helper thread so a hang fails instead of blocking CI."""
    t = threading.Thread(target=pool.shutdown, kwargs=kwargs, daemon=True)
    t.start()
    t.join(JOIN_TIMEOUT)
    test.assertFalse(t.is_alive(), "shutdown() did not return")


class TinySwitchInterval:
    def __enter__(self):
        self.old = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)

    def __exit__(self, *exc):
        sys.setswitchinterval(self.old)


class ShutdownDrainTest(unittest.TestCase):
    def test_backlog_is_drained_on_shutdown(self):
        rec = Recorder(delay=0.001)
        pool = WorkerPool(rec, workers=2)
        for i in range(120):
            pool.submit(i)
        shutdown_bounded(self, pool)
        self.assertEqual(sorted(rec.items), list(range(120)))
        stats = pool.stats()
        self.assertEqual((stats["submitted"], stats["processed"], stats["failed"]), (120, 120, 0))

    def test_stress_immediate_shutdown(self):
        with TinySwitchInterval():
            for round_no in range(25):
                rec = Recorder()
                pool = WorkerPool(rec, workers=4)
                for i in range(300):
                    pool.submit(i)
                shutdown_bounded(self, pool)
                self.assertEqual(len(rec.items), 300, f"round {round_no} dropped items")
                self.assertEqual(sorted(rec.items), list(range(300)))

    def test_failures_and_retries_are_accounted(self):
        calls = {}
        lock = threading.Lock()

        def handler(item):
            with lock:
                calls[item] = calls.get(item, 0) + 1
                n = calls[item]
            time.sleep(0.0005)
            if item % 5 == 0 or (item % 7 == 0 and n < 2):
                raise OSError(item)

        pool = WorkerPool(handler, workers=3, retry=RetryPolicy(attempts=2))
        for i in range(70):
            pool.submit(i)
        shutdown_bounded(self, pool)
        stats = pool.stats()
        self.assertEqual(stats["submitted"], 70)
        self.assertEqual(stats["failed"], 14)
        self.assertEqual(stats["processed"], 56)
        self.assertEqual(sorted(e.item for e in pool.errors), list(range(0, 70, 5)))

    def test_context_manager_drains(self):
        rec = Recorder(delay=0.001)
        with WorkerPool(rec, workers=3) as pool:
            for i in range(60):
                pool.submit(i)
        self.assertEqual(sorted(rec.items), list(range(60)))
        self.assertTrue(pool.closed)

    def test_shutdown_nowait_then_wait_and_twice(self):
        rec = Recorder(delay=0.001)
        pool = WorkerPool(rec, workers=2)
        for i in range(50):
            pool.submit(i)
        pool.shutdown(wait=False)
        with self.assertRaises(PoolClosed):
            pool.submit(999)
        shutdown_bounded(self, pool)
        shutdown_bounded(self, pool)
        self.assertEqual(sorted(rec.items), list(range(50)))

    def test_idle_pool_shuts_down_quickly(self):
        pool = WorkerPool(Recorder(), workers=8)
        started = time.monotonic()
        shutdown_bounded(self, pool)
        self.assertLess(time.monotonic() - started, 2.0)


class ConcurrentSubmitTest(unittest.TestCase):
    def test_every_accepted_item_is_processed(self):
        with TinySwitchInterval():
            for round_no in range(60):
                rec = Recorder()
                pool = WorkerPool(rec, workers=3)
                accepted = []
                acc_lock = threading.Lock()

                def producer(base):
                    for i in range(10_000):
                        try:
                            pool.submit(base + i)
                        except PoolClosed:
                            return
                        with acc_lock:
                            accepted.append(base + i)

                producers = [threading.Thread(target=producer, args=(k * 100_000,))
                             for k in range(3)]
                for p in producers:
                    p.start()
                time.sleep(0.002)
                shutdown_bounded(self, pool)
                for p in producers:
                    p.join(JOIN_TIMEOUT)
                    self.assertFalse(p.is_alive())
                processed = set(rec.items)
                missing = [i for i in accepted if i not in processed]
                self.assertEqual(missing, [], f"round {round_no}: accepted but never handled")
                self.assertEqual(pool.stats()["submitted"], pool.stats()["processed"])


class HigherLevelTest(unittest.TestCase):
    def test_map_unordered_returns_everything(self):
        def slow_square(n):
            time.sleep(0.0005)
            return n * n

        for _ in range(3):
            results, errors = map_unordered(slow_square, range(150), workers=4)
            self.assertEqual(errors, [])
            self.assertEqual(results, {n: n * n for n in range(150)})

    def test_pipeline_close_without_sleeping(self):
        pipe = Pipeline([
            Stage("parse", int, workers=2),
            Stage("slow", lambda n: (time.sleep(0.0005), n * 2)[1], workers=2),
            Stage("odd", lambda n: n if n % 4 == 2 else None, workers=2),
        ])
        pipe.feed(str(i) for i in range(200))
        out = pipe.close()
        self.assertEqual(sorted(out), [i * 2 for i in range(200) if i % 2 == 1])


if __name__ == "__main__":
    unittest.main()
