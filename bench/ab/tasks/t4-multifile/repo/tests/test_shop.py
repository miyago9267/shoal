import unittest

from shop.cart import Cart, add_item, remove_item
from shop.pricing import apply_discount, line_total
from shop.shipping import shipping_cost


class CartTest(unittest.TestCase):
    def test_add_accumulates(self):
        cart = Cart()
        add_item(cart, "SKU-1", 2)
        self.assertEqual(add_item(cart, "SKU-1"), 3)
        add_item(cart, "SKU-2", 4)
        self.assertEqual(cart.total_units(), 7)
        remove_item(cart, "SKU-1")
        self.assertEqual(cart.lines, {"SKU-2": 4})


class PricingTest(unittest.TestCase):
    def test_discount(self):
        self.assertEqual(apply_discount(1999, 10), 1799)
        self.assertEqual(apply_discount(1000, 0), 1000)
        self.assertEqual(apply_discount(1000, 100), 0)
        self.assertEqual(line_total(250, 4, 25), 750)


class ShippingTest(unittest.TestCase):
    def test_cost(self):
        self.assertEqual(shipping_cost(0.5, "domestic"), 500)
        self.assertEqual(shipping_cost(1, "domestic"), 500)
        self.assertEqual(shipping_cost(2.2, "regional"), 900 + 2 * 250)
        self.assertEqual(shipping_cost(3, "international"), 1800 + 2 * 600)


if __name__ == "__main__":
    unittest.main()
