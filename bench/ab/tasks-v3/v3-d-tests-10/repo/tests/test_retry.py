import unittest

from utilkit import retry


class RetrySmoke(unittest.TestCase):
    def test_doubling(self):
        self.assertEqual(retry.backoff_delays(3, base=1), [1, 2, 4])

    def test_should_retry(self):
        self.assertTrue(retry.should_retry(KeyError("x"), [KeyError, OSError]))
        self.assertFalse(retry.should_retry(ValueError("x"), [KeyError]))

    def test_total(self):
        self.assertEqual(retry.total_delay([1, 2, 3]), 6)
