import unittest

from ops import notifier


class NotifierTest(unittest.TestCase):
    def test_counts(self):
        def bad(u, t):
            raise RuntimeError("x")

        n = notifier.notify("u", "hi", {"mail": lambda u, t: None, "sms": bad})
        self.assertEqual(n, 1)

    def test_undelivered(self):
        self.assertEqual(notifier.undelivered({"a": 0, "b": 2}), ["a"])
