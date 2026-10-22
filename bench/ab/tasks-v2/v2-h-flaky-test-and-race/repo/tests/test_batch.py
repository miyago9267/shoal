import unittest

from workpool.batch import chunked
from workpool.retry import RetryPolicy


class BatchTest(unittest.TestCase):
    def test_chunked(self):
        self.assertEqual(list(chunked(range(5), 2)), [[0, 1], [2, 3], [4]])
        with self.assertRaises(ValueError):
            list(chunked([1], 0))

    def test_retry_policy(self):
        policy = RetryPolicy(attempts=3, backoff=0.1, retry_on=(OSError,))
        self.assertTrue(policy.should_retry(OSError(), 1))
        self.assertFalse(policy.should_retry(OSError(), 3))
        self.assertFalse(policy.should_retry(ValueError(), 1))
        self.assertAlmostEqual(policy.delay(3), 0.4)


if __name__ == "__main__":
    unittest.main()
