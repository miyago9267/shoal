import unittest

from app.core import (CONFIG, Customer, Order, Product, ValidationError, configure,
                      format_money, order_total, to_cents)

PEN = Product("PEN-001", "Pen", 250)
BOOK = Product("BK-1001", "Book", 1200, taxable=False)


def order(*lines, coupon=None, completed=0):
    o = Order("O1", Customer("a@b.co", completed_orders=completed), coupon=coupon)
    for product, qty in lines:
        o.add(product, qty)
    return o


class PricingTest(unittest.TestCase):
    def setUp(self):
        self._saved = dict(CONFIG)

    def tearDown(self):
        CONFIG.clear()
        CONFIG.update(self._saved)

    def test_money(self):
        self.assertEqual(to_cents("12.345"), 1235)
        self.assertEqual(to_cents(3), 300)
        self.assertEqual(format_money(123456), "€1,234.56")
        self.assertEqual(format_money(-5, "USD"), "-$0.05")

    def test_plain_total_with_tax(self):
        b = order((PEN, 2)).breakdown()
        self.assertEqual((b.subtotal_cents, b.tax_cents, b.total_cents), (500, 100, 600))

    def test_untaxed_items(self):
        b = order((PEN, 2), (BOOK, 1)).breakdown()
        self.assertEqual(b.tax_cents, 100)
        self.assertEqual(b.total_cents, 1800)

    def test_bulk_and_coupon_stack(self):
        b = order_total(order((PEN, 10), coupon="welcome10"))
        self.assertEqual([name for name, _ in b.discounts], ["bulk", "coupon"])
        self.assertEqual(b.discount_cents, 125 + 238)

    def test_unknown_coupon(self):
        with self.assertRaises(ValidationError):
            order((PEN, 1), coupon="NOPE").total_cents()

    def test_configure(self):
        configure(tax_rate="0.10")
        self.assertEqual(order((PEN, 2)).total_cents(), 550)
        with self.assertRaises(KeyError):
            configure(colour="red")


if __name__ == "__main__":
    unittest.main()
