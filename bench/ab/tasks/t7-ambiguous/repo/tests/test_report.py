import io
import unittest
from decimal import Decimal

from reports.dedupe import dedupe_orders
from reports.loader import load_orders
from reports.report import build_report, render_report

CSV = """order_id,customer_email,region,amount,created_at
A-1,ada@example.com,eu,10.00,2026-10-01
A-2,bob@example.com,us,5.50,2026-10-01
 a-1 ,ADA@example.com,eu,10.00,2026-10-01
A-3,ada@example.com,us ,2.25,2026-10-02
"""


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.orders = load_orders(io.StringIO(CSV))

    def test_loader_normalizes_region(self):
        self.assertEqual([o.region for o in self.orders], ["EU", "US", "EU", "US"])

    def test_dedupe_keeps_first(self):
        unique = dedupe_orders(self.orders)
        self.assertEqual([o.order_id for o in unique], ["A-1", "A-2", "A-3"])

    def test_build_report(self):
        report = build_report(self.orders)
        self.assertEqual(report["order_count"], 3)
        self.assertEqual(report["total"], Decimal("17.75"))
        self.assertEqual(report["by_region"], {"EU": Decimal("10.00"), "US": Decimal("7.75")})
        self.assertEqual(report["top_customers"][0], ("ada@example.com", Decimal("12.25")))

    def test_render_report(self):
        text = render_report(build_report(self.orders))
        self.assertIn("Orders: 3", text)
        self.assertIn("Total: 17.75", text)
        self.assertIn("EU     | 10.00", text)


if __name__ == "__main__":
    unittest.main()
