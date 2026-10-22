import unittest

from kvsvc.errors import NotFound, WrongType
from kvsvc.store import KVStore


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.store = KVStore(clock=lambda: self.now)

    def test_set_get_delete(self):
        self.store.set("a", {"x": 1})
        self.assertEqual(self.store.get("a"), {"x": 1})
        self.store.delete("a")
        with self.assertRaises(NotFound):
            self.store.get("a")
        self.assertIsNone(self.store.get("a", None))

    def test_incr(self):
        self.assertEqual(self.store.incr("n"), 1)
        self.assertEqual(self.store.incr("n", 5), 6)
        self.store.set("s", "text")
        with self.assertRaises(WrongType):
            self.store.incr("s")

    def test_keys_prefix(self):
        for key in ("user:2", "user:1", "job:1"):
            self.store.set(key, 0)
        self.assertEqual(self.store.keys("user:"), ["user:1", "user:2"])
        self.assertEqual(len(self.store), 3)

    def test_updated_at_uses_clock(self):
        self.store.set("a", 1)
        self.now = 150.0
        self.store.incr("b")
        self.assertEqual([e.updated_at for _, e in self.store.entries()], [100.0, 150.0])
