import unittest

from ops import syncer


class SyncerTest(unittest.TestCase):
    def test_no_drift(self):
        self.assertEqual(syncer.reconcile(3, 3, lambda n: n), 0)

    def test_push_capped(self):
        got = []
        syncer.reconcile(0, 500, lambda n: got.append(n) or n)
        self.assertEqual(got, [syncer.MAX_PUSH])

    def test_worst(self):
        self.assertEqual(syncer.worst([(1, 2), (9, 1)]), 8)
