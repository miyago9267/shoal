import json
import os
import tempfile
import unittest

from kvsvc.handler import Handler
from kvsvc.snapshot import load_snapshot, save_snapshot
from kvsvc.store import KVStore


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = KVStore(clock=self.clock)
        self.h = Handler(self.store)

    def do(self, op, **fields):
        return self.h.handle({"op": op, **fields})

    def stats(self):
        response = self.do("stats")
        self.assertTrue(response["ok"], response)
        return {k: response[k] for k in ("hits", "misses", "expired", "keys")}


class TtlTest(Base):
    def test_expires_at_deadline(self):
        self.assertEqual(self.do("set", key="a", value=1, ttl=10), {"ok": True})
        self.clock.now = 1009.5
        self.assertEqual(self.do("get", key="a"), {"ok": True, "value": 1})
        self.clock.now = 1010.0
        self.assertEqual(self.do("get", key="a")["error"], "not_found")

    def test_expired_key_is_missing_everywhere(self):
        self.store.set("gone", "x", ttl=5)
        self.store.set("stay", "y")
        self.clock.now += 5
        self.assertEqual(self.do("exists", key="gone"), {"ok": True, "exists": False})
        self.assertEqual(self.do("keys"), {"ok": True, "keys": ["stay"]})
        self.assertEqual(self.do("mget", keys=["gone", "stay"]),
                         {"ok": True, "values": {"gone": None, "stay": "y"}})
        self.assertEqual(len(self.store), 1)
        self.assertNotIn("gone", self.store)
        self.assertEqual(self.do("delete", key="gone")["error"], "not_found")

    def test_float_ttl(self):
        self.store.set("f", 1, ttl=0.25)
        self.clock.now += 0.2
        self.assertIn("f", self.store)
        self.clock.now += 0.1
        self.assertNotIn("f", self.store)

    def test_set_without_ttl_clears_expiry(self):
        self.do("set", key="a", value=1, ttl=5)
        self.do("set", key="a", value=2)
        self.clock.now += 100
        self.assertEqual(self.do("get", key="a"), {"ok": True, "value": 2})
        self.assertEqual(self.do("ttl", key="a"), {"ok": True, "ttl": None})

    def test_incr_keeps_expiry_and_restarts_after(self):
        self.do("set", key="n", value=5, ttl=10)
        self.clock.now += 4
        self.assertEqual(self.do("incr", key="n", by=2), {"ok": True, "value": 7})
        self.assertEqual(self.do("ttl", key="n"), {"ok": True, "ttl": 6})
        self.clock.now += 6
        self.assertEqual(self.do("incr", key="n"), {"ok": True, "value": 1})
        self.assertEqual(self.do("ttl", key="n"), {"ok": True, "ttl": None})
        self.clock.now += 1000
        self.assertEqual(self.do("get", key="n"), {"ok": True, "value": 1})

    def test_ttl_op(self):
        self.do("set", key="a", value=1, ttl=30)
        self.clock.now += 12
        self.assertEqual(self.do("ttl", key="a"), {"ok": True, "ttl": 18})
        self.assertEqual(self.do("ttl", key="missing")["error"], "not_found")
        self.clock.now += 18
        self.assertEqual(self.do("ttl", key="a")["error"], "not_found")

    def test_bad_ttl(self):
        for ttl in (0, -1, "10", True, [5]):
            with self.subTest(ttl=ttl):
                response = self.do("set", key="a", value=1, ttl=ttl)
                self.assertEqual(response.get("error"), "bad_request", response)
        self.assertEqual(self.do("exists", key="a"), {"ok": True, "exists": False})


class StatsTest(Base):
    def test_counts(self):
        self.assertEqual(self.stats(), {"hits": 0, "misses": 0, "expired": 0, "keys": 0})
        self.do("set", key="a", value=1)
        self.do("set", key="b", value=2, ttl=10)
        self.do("set", key="c", value=3, ttl=10)
        self.do("get", key="a")                       # hit
        self.do("get", key="b")                       # hit
        self.do("get", key="nope")                    # miss
        self.do("mget", keys=["a", "b", "zz"])        # 2 hits, 1 miss
        self.assertEqual(self.stats(), {"hits": 4, "misses": 2, "expired": 0, "keys": 3})
        self.clock.now += 10
        self.do("get", key="b")                       # miss (expired)
        self.do("get", key="b")                       # miss, b still counted once
        self.assertEqual(self.stats(), {"hits": 4, "misses": 4, "expired": 2, "keys": 1})

    def test_untouched_expiry_is_counted_once(self):
        for i in range(5):
            self.store.set(f"k{i}", i, ttl=1 + i)
        self.clock.now += 3
        self.assertEqual(self.stats()["expired"], 3)
        self.assertEqual(self.stats()["keys"], 2)
        self.do("keys")
        self.do("exists", key="k0")
        self.assertEqual(self.stats()["expired"], 3)

    def test_overwrite_or_delete_before_expiry_not_counted(self):
        self.store.set("a", 1, ttl=5)
        self.store.set("b", 1, ttl=5)
        self.store.set("c", 1, ttl=5)
        self.do("set", key="a", value=2)
        self.do("delete", key="b")
        self.clock.now += 50
        self.assertEqual(self.stats(), {"hits": 0, "misses": 0, "expired": 1, "keys": 1})

    def test_set_over_expired_key_still_counts_it(self):
        self.store.set("a", 1, ttl=5)
        self.clock.now += 6
        self.do("set", key="a", value=2, ttl=5)
        self.do("incr", key="z")
        self.assertEqual(self.stats()["expired"], 1)
        self.clock.now += 5
        self.assertEqual(self.stats(), {"hits": 0, "misses": 0, "expired": 2, "keys": 1})


class SnapshotTest(Base):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "snap.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_expiry_survives_restore(self):
        self.store.set("short", "s", ttl=10)
        self.store.set("long", "l", ttl=100)
        self.store.set("dead", "d", ttl=1)
        self.store.set("forever", "f")
        self.clock.now += 2
        self.assertEqual(save_snapshot(self.store, self.path), 3)
        with open(self.path, encoding="utf-8") as fh:
            self.assertNotIn("dead", fh.read())

        later = Clock(self.clock.now + 5)
        restored = load_snapshot(self.path, clock=later)
        self.assertEqual(restored.keys(), ["forever", "long", "short"])
        h = Handler(restored)
        self.assertEqual(h.handle({"op": "ttl", "key": "short"}), {"ok": True, "ttl": 3})
        self.assertEqual(h.handle({"op": "stats"}),
                         {"ok": True, "hits": 0, "misses": 0, "expired": 0, "keys": 3})
        later.now += 3
        self.assertEqual(restored.keys(), ["forever", "long"])

        much_later = Clock(self.clock.now + 500)
        self.assertEqual(load_snapshot(self.path, clock=much_later).keys(), ["forever"])

    def test_handler_snapshot_skips_expired(self):
        h = Handler(self.store, snapshot_path=self.path)
        h.handle({"op": "set", "key": "a", "value": 1, "ttl": 1})
        h.handle({"op": "set", "key": "b", "value": 2})
        self.clock.now += 1
        self.assertEqual(h.handle({"op": "snapshot"}), {"ok": True, "count": 1})

    def test_old_snapshot_still_loads(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "entries": [
                {"key": "a", "value": 1, "updated_at": 5.0}]}, fh)
        restored = load_snapshot(self.path, clock=Clock(10 ** 9))
        self.assertEqual(restored.get("a"), 1)
        self.assertEqual(Handler(restored).handle({"op": "ttl", "key": "a"}),
                         {"ok": True, "ttl": None})
