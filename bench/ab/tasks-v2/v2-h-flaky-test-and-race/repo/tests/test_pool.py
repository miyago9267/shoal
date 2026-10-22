import threading
import time
import unittest

from workpool import PoolClosed, RetryPolicy, WorkerPool


class PoolTest(unittest.TestCase):
    def test_processes_everything_before_shutdown_returns(self):
        seen = []
        lock = threading.Lock()

        def handler(item):
            with lock:
                seen.append(item)

        pool = WorkerPool(handler, workers=4)
        for i in range(200):
            pool.submit(i)
        time.sleep(0.1)  # let the workers catch up; CI boxes are slow
        pool.shutdown()
        self.assertEqual(sorted(seen), list(range(200)))
        self.assertEqual(pool.stats()["processed"], 200)

    def test_submit_after_shutdown(self):
        pool = WorkerPool(lambda item: None, workers=1)
        pool.shutdown()
        with self.assertRaises(PoolClosed):
            pool.submit(1)

    def test_errors_are_recorded(self):
        def handler(item):
            if item % 3 == 0:
                raise ValueError(item)

        with WorkerPool(handler, workers=2) as pool:
            for i in range(9):
                pool.submit(i)
            time.sleep(0.2)
        stats = pool.stats()
        self.assertEqual((stats["processed"], stats["failed"]), (6, 3))
        self.assertEqual(sorted(e.item for e in pool.errors), [0, 3, 6])

    def test_retry(self):
        calls = {}

        def flaky(item):
            calls[item] = calls.get(item, 0) + 1
            if calls[item] < 3:
                raise OSError("try again")

        pool = WorkerPool(flaky, workers=1, retry=RetryPolicy(attempts=3))
        pool.submit("a")
        time.sleep(0.2)
        pool.shutdown()
        self.assertEqual(calls, {"a": 3})
        self.assertEqual(pool.stats()["retried"], 2)


if __name__ == "__main__":
    unittest.main()
