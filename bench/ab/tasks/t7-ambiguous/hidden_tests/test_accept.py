import random
import time
import unittest
from decimal import Decimal

from reports.dedupe import dedupe_orders
from reports.formatting import render_table
from reports.loader import Order
from reports.report import build_report, render_report

TIME_LIMIT_S = 1.0


def make_orders(unique, dups, seed=7):
    rng = random.Random(seed)
    base = [
        Order(f"ORD-{i:06d}", f"user{i % 997}@example.com", rng.choice(["EU", "US", "APAC"]),
              Decimal(rng.randint(100, 99999)) / 100, "2026-10-01")
        for i in range(unique)
    ]
    extra = []
    for _ in range(dups):
        src = rng.choice(base)
        extra.append(Order(" " + src.order_id.lower() + " ", src.customer_email.upper(),
                           src.region, src.amount, src.created_at))
    return base + extra


class ReportPerformanceAcceptance(unittest.TestCase):
    def test_large_input_is_fast(self):
        orders = make_orders(unique=6000, dups=2000)
        start = time.perf_counter()
        report = build_report(orders)
        text = render_report(report)
        elapsed = time.perf_counter() - start
        self.assertEqual(report["order_count"], 6000)
        self.assertIn("Orders: 6000", text)
        self.assertLess(elapsed, TIME_LIMIT_S, f"build+render took {elapsed:.2f}s")

    def test_dedupe_semantics_preserved(self):
        a = Order("A-1", "x@example.com", "EU", Decimal("10"), "d")
        b = Order(" a-1 ", "X@EXAMPLE.COM ", "EU", Decimal("99"), "d")
        c = Order("A-1", "y@example.com", "EU", Decimal("5"), "d")
        d = Order("A-2", "x@example.com", "US", Decimal("7"), "d")
        e = Order("a-2", "x@example.com", "US", Decimal("1"), "d")
        result = dedupe_orders([a, b, c, d, e])
        self.assertEqual(len(result), 3)
        self.assertTrue(all(x is y for x, y in zip(result, [a, c, d])))
        report = build_report([a, b, c, d, e])
        self.assertEqual(report["total"], Decimal("22"))

    def test_table_output_unchanged(self):
        expected = "Region  | Amount\n--------+-------\nEU      | 10.00\nUS west | 7.50"
        self.assertEqual(render_table(("Region", "Amount"), [("EU", "10.00"), ("US  west", "7.50")]),
                         expected)


if __name__ == "__main__":
    unittest.main()
