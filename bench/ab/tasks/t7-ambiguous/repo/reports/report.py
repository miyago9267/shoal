"""Build the daily sales summary."""
from collections import defaultdict
from decimal import Decimal

from .dedupe import dedupe_orders
from .formatting import render_table


def build_report(orders, top_n=5):
    orders = dedupe_orders(orders)
    by_region = defaultdict(lambda: Decimal("0"))
    by_customer = defaultdict(lambda: Decimal("0"))
    for order in orders:
        by_region[order.region] += order.amount
        by_customer[order.customer_email.strip().lower()] += order.amount
    top = sorted(by_customer.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    return {
        "order_count": len(orders),
        "total": sum(by_region.values(), Decimal("0")),
        "by_region": dict(sorted(by_region.items())),
        "top_customers": top,
    }


def render_report(report):
    region_rows = [(r, f"{amt:.2f}") for r, amt in report["by_region"].items()]
    customer_rows = [(e, f"{amt:.2f}") for e, amt in report["top_customers"]]
    parts = [
        f"Orders: {report['order_count']}",
        f"Total: {report['total']:.2f}",
        "",
        render_table(("Region", "Amount"), region_rows),
        "",
        render_table(("Customer", "Amount"), customer_rows),
    ]
    return "\n".join(parts)
