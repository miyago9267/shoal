import unittest

from kvsvc.handler import Handler
from kvsvc.store import KVStore


class HandlerTest(unittest.TestCase):
    def setUp(self):
        self.h = Handler(KVStore(clock=lambda: 0.0))

    def test_round_trip(self):
        self.assertEqual(self.h.handle({"op": "set", "key": "a", "value": [1, 2]}), {"ok": True})
        self.assertEqual(self.h.handle({"op": "get", "key": "a"}), {"ok": True, "value": [1, 2]})
        self.assertEqual(self.h.handle({"op": "exists", "key": "a"}),
                         {"ok": True, "exists": True})

    def test_errors(self):
        self.assertEqual(self.h.handle({"op": "get", "key": "zz"})["error"], "not_found")
        self.assertEqual(self.h.handle({"op": "get"})["error"], "bad_request")
        self.assertEqual(self.h.handle({"op": "nope"})["error"], "bad_request")
        self.assertEqual(self.h.handle({"op": "snapshot"})["error"], "no_snapshot_path")
        self.assertEqual(self.h.handle({"op": "incr", "key": "n", "by": "2"})["error"],
                         "bad_request")

    def test_mget_and_keys(self):
        self.h.handle({"op": "set", "key": "a", "value": 1})
        self.h.handle({"op": "incr", "key": "b", "by": 3})
        self.assertEqual(self.h.handle({"op": "mget", "keys": ["a", "b", "c"]}),
                         {"ok": True, "values": {"a": 1, "b": 3, "c": None}})
        self.assertEqual(self.h.handle({"op": "keys"}), {"ok": True, "keys": ["a", "b"]})
