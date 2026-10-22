import importlib
import os
import pkgutil
import subprocess
import sys
import unittest
from collections import Counter

PUBLIC = [
    "CONFIG", "configure", "get_setting",
    "ShopError", "ValidationError", "OutOfStockError", "UnknownProductError",
    "OrderStateError",
    "to_cents", "format_money",
    "validate_sku", "validate_quantity", "validate_email",
    "Product", "LineItem", "Customer", "Order", "PriceBreakdown",
    "DISCOUNT_RULES", "register_discount", "apply_discounts", "compute_tax",
    "order_total",
    "Inventory",
    "OrderService",
    "sales_summary", "top_products", "render_invoice",
    "order_to_dict", "order_from_dict",
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fresh_python(code):
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)


class PackageShapeTest(unittest.TestCase):
    def test_core_is_a_package_with_four_modules(self):
        import app.core
        self.assertTrue(hasattr(app.core, "__path__"), "app.core must be a package")
        subs = [m.name for m in pkgutil.iter_modules(app.core.__path__)]
        self.assertGreaterEqual(len(subs), 4, subs)

    def test_every_submodule_imports_first_in_a_fresh_interpreter(self):
        import app.core
        for info in pkgutil.iter_modules(app.core.__path__):
            name = f"app.core.{info.name}"
            done = fresh_python(f"import {name}")
            self.assertEqual(done.returncode, 0, f"{name}: {done.stderr[-800:]}")

    def test_public_names_spread_over_modules(self):
        import app.core
        owners = Counter()
        for name in PUBLIC:
            obj = getattr(app.core, name)
            module = getattr(obj, "__module__", None)
            if module and callable(obj):
                owners[module] += 1
        self.assertGreaterEqual(len(owners), 4, owners)
        self.assertLessEqual(max(owners.values()), len(PUBLIC) // 2, owners)
        self.assertNotIn("app.core", owners, "definitions should live in submodules")


class PublicImportTest(unittest.TestCase):
    def test_every_public_name_imports(self):
        for name in PUBLIC:
            done = fresh_python(f"from app.core import {name}")
            self.assertEqual(done.returncode, 0, f"{name}: {done.stderr[-400:]}")

    def test_star_import_and_all(self):
        import app.core
        self.assertTrue(set(PUBLIC) <= set(app.core.__all__))
        ns = {}
        exec("from app.core import *", ns)
        for name in PUBLIC:
            self.assertIn(name, ns)

    def test_consumers_still_import(self):
        for mod in ("app.api", "app.catalog", "app.cli"):
            done = fresh_python(f"import {mod}")
            self.assertEqual(done.returncode, 0, f"{mod}: {done.stderr[-400:]}")


class BehaviourTest(unittest.TestCase):
    def setUp(self):
        import app.core as core
        self.core = core
        self._saved = dict(core.CONFIG)
        self._rules = dict(core.DISCOUNT_RULES)

    def tearDown(self):
        self.core.CONFIG.clear()
        self.core.CONFIG.update(self._saved)
        self.core.DISCOUNT_RULES.clear()
        self.core.DISCOUNT_RULES.update(self._rules)

    def order(self, qty=2, coupon=None, completed=0):
        c = self.core
        o = c.Order("O1", c.Customer("a@b.co", completed_orders=completed), coupon=coupon)
        o.add(c.Product("PEN-001", "Pen", 250), qty)
        return o

    def test_registered_discount_is_used_by_pricing(self):
        c = self.core

        @c.register_discount("flat1")
        def flat(order, running):
            return 100

        b = self.order().breakdown()
        self.assertIn(("flat1", 100), b.discounts)
        self.assertEqual(b.total_cents, 480)
        with self.assertRaises(ValueError):
            c.register_discount("flat1")(flat)

    def test_configure_reaches_pricing_and_validation(self):
        c = self.core
        c.configure(tax_rate="0.10", max_quantity=3)
        self.assertEqual(c.get_setting("tax_rate"), "0.10")
        self.assertEqual(self.order(2).total_cents(), 550)
        with self.assertRaises(c.ValidationError):
            self.order(4)

    def test_loyalty_bulk_coupon(self):
        b = self.core.order_total(self.order(10, coupon="FIVEOFF", completed=5))
        self.assertEqual([n for n, _ in b.discounts], ["bulk", "loyalty", "coupon"])
        self.assertEqual(b.discount_cents, 125 + 71 + 500)
        self.assertEqual(b.total_cents, round((2500 - 696) * 1.2))

    def test_order_total_type_check(self):
        with self.assertRaises(TypeError):
            self.core.order_total("O1")

    def test_errors_hierarchy(self):
        c = self.core
        for err in (c.ValidationError, c.OutOfStockError, c.UnknownProductError,
                    c.OrderStateError):
            self.assertTrue(issubclass(err, c.ShopError))
        self.assertEqual(c.OutOfStockError("PEN-001", 3, 1).available, 1)
        with self.assertRaises(c.ValidationError):
            c.validate_email("nope")
        with self.assertRaises(c.ValidationError):
            c.Product("bad", "x", 1)

    def test_service_inventory_reports(self):
        c = self.core
        inv = c.Inventory()
        inv.add_product(c.Product("PEN-001", "Pen", 250), 10)
        inv.add_product(c.Product("BK-1001", "Book", 1200, taxable=False), 2)
        svc = c.OrderService(inv)
        seen = []
        svc.on("shipped", lambda e, o: seen.append(o.order_id))
        o1 = svc.new_order(c.Customer("x@y.io"))
        svc.add_item(o1.order_id, "PEN-001", 4)
        svc.add_item(o1.order_id, "BK-1001", 1)
        svc.place(o1.order_id)
        o2 = svc.new_order(c.Customer("z@y.io"))
        svc.add_item(o2.order_id, "BK-1001", 2)
        with self.assertRaises(c.OutOfStockError):
            svc.place(o2.order_id)
        svc.ship(o1.order_id)
        self.assertEqual(seen, [o1.order_id])
        self.assertEqual(inv.on_hand("PEN-001"), 6)
        self.assertEqual(inv.low_stock(5), ["BK-1001"])
        with self.assertRaises(c.UnknownProductError):
            inv.product("ZZ-999")
        summary = c.sales_summary(svc.orders.values())
        self.assertEqual(summary["orders"], 1)
        self.assertEqual(summary["revenue_cents"], 1000 * 12 // 10 + 1200)
        self.assertEqual(c.top_products(svc.orders.values()), [("PEN-001", 4), ("BK-1001", 1)])
        self.assertEqual(svc.by_state("shipped"), [o1])

    def test_serialisation_and_invoice(self):
        c = self.core
        o = self.order(3)
        data = c.order_to_dict(o)
        again = c.order_from_dict(data)
        self.assertIsInstance(again, c.Order)
        self.assertIsInstance(again.items[0], c.LineItem)
        self.assertEqual(c.order_to_dict(again), data)
        self.assertIn("TOTAL", c.render_invoice(again))
        self.assertEqual(c.format_money(c.to_cents("1234.5")), "€1,234.50")

    def test_price_breakdown_fields(self):
        b = self.order().breakdown()
        self.assertIsInstance(b, self.core.PriceBreakdown)
        self.assertEqual((b.subtotal_cents, b.discount_cents, b.tax_cents, b.total_cents),
                         (500, 0, 100, 600))


if __name__ == "__main__":
    unittest.main()
