import unittest

from ops import backup


class BackupTest(unittest.TestCase):
    def test_runs(self):
        self.assertTrue(backup.run("db", lambda n: 1.25, now=1000))

    def test_rate_limited(self):
        self.assertFalse(backup.run("db", lambda n: 1.0, now=1000, last_run=900))

    def test_copy_error_propagates(self):
        def boom(name):
            raise RuntimeError("disk")

        with self.assertRaises(RuntimeError):
            backup.run("db", boom, now=1000)

    def test_due(self):
        self.assertEqual(backup.due({"a": 0, "b": 90000}, 100000), ["a"])
