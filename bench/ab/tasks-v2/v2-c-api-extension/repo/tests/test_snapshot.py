import os
import tempfile
import unittest

from kvsvc.handler import Handler
from kvsvc.snapshot import load_snapshot, save_snapshot
from kvsvc.store import KVStore


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "snap.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        store = KVStore(clock=lambda: 5.0)
        store.set("a", "x")
        store.incr("n", 2)
        self.assertEqual(save_snapshot(store, self.path), 2)
        again = load_snapshot(self.path)
        self.assertEqual((again.get("a"), again.get("n")), ("x", 2))

    def test_handler_snapshot_op(self):
        h = Handler(KVStore(), snapshot_path=self.path)
        h.handle({"op": "set", "key": "k", "value": True})
        self.assertEqual(h.handle({"op": "snapshot"}), {"ok": True, "count": 1})
        self.assertTrue(load_snapshot(self.path).get("k"))
