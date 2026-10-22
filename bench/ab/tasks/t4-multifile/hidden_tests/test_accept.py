import unittest

from shop.cart import Cart, add_item
from shop.errors import ValidationError
from shop.pricing import apply_discount
from shop.shipping import shipping_cost


class AcceptTest(unittest.TestCase):
    def assertInvalid(self, field, fn, *args):
        with self.assertRaises(ValidationError) as cm:
            fn(*args)
        self.assertEqual(cm.exception.field, field)

    def test_error_type(self):
        self.assertTrue(issubclass(ValidationError, ValueError))

    def test_add_item(self):
        for bad_qty in (0, -2, 1.5, "3", True, None):
            self.assertInvalid("qty", add_item, Cart(), "SKU-1", bad_qty)
        for bad_sku in ("", "   ", None, 42):
            self.assertInvalid("sku", add_item, Cart(), bad_sku, 1)
        cart = Cart()
        try:
            add_item(cart, "SKU-1", -1)
        except ValidationError:
            pass
        self.assertEqual(cart.lines, {})

    def test_apply_discount(self):
        for bad in (-1, 100.5, 150, "10", None):
            self.assertInvalid("percent", apply_discount, 1000, bad)
        for bad in (-5, 10.5, "100", None):
            self.assertInvalid("price_cents", apply_discount, bad, 10)
        self.assertEqual(apply_discount(1999, 12.5), 1749)

    def test_shipping_cost(self):
        for bad in (0, -1.5, "2", None):
            self.assertInvalid("weight_kg", shipping_cost, bad, "domestic")
        for bad in ("mars", "", None):
            self.assertInvalid("zone", shipping_cost, 1, bad)

    def test_valid_input_unchanged(self):
        cart = Cart()
        self.assertEqual(add_item(cart, "SKU-1", 2), 2)
        self.assertEqual(apply_discount(1000, 0), 1000)
        self.assertEqual(apply_discount(1000, 100), 0)
        self.assertEqual(shipping_cost(2.2, "regional"), 1400)


if __name__ == "__main__":
    unittest.main()
