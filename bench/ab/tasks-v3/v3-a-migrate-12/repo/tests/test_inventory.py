import unittest

from ops import inventory


class InventoryTest(unittest.TestCase):
    def test_restock_counts(self):
        stock = {}
        n = inventory.restock(stock, [("a", 3), ("b", 0), ("c", 9)])
        self.assertEqual(n, 2)
        self.assertEqual(stock, {"a": 3, "c": 9})

    def test_low_items(self):
        self.assertEqual(inventory.low_items({"a": 1, "b": 9}), ["a"])

    def test_take(self):
        stock = {"a": 4}
        self.assertEqual(inventory.take(stock, "a", 3), 1)
        with self.assertRaises(ValueError):
            inventory.take(stock, "a", 3)

    def test_merge(self):
        self.assertEqual(inventory.merge({"a": 1}, {"a": 2, "b": 1}), {"a": 3, "b": 1})
