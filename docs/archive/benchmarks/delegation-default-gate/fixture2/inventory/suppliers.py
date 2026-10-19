"""Supplier lead times and minimum order values."""

SUPPLIERS = {
    "acme": {"lead_days": 5, "min_order": 200},
    "globex": {"lead_days": 12, "min_order": 500},
    "initech": {"lead_days": 3, "min_order": 0},
}

DEFAULT_LEAD_DAYS = 7


def lead_days(name):
    """Days from order to delivery; unknown suppliers get DEFAULT_LEAD_DAYS."""
    if name is None:
        return DEFAULT_LEAD_DAYS
    return SUPPLIERS.get(name, {}).get("lead_days", DEFAULT_LEAD_DAYS)


def min_order(name):
    """Minimum order value for a supplier (0 when unknown)."""
    return SUPPLIERS.get(name, {}).get("min_order", 0)


def group_by_supplier(items):
    """Map supplier name -> list of items, so one purchase order per supplier."""
    grouped = {}
    for item in items:
        grouped.setdefault(item.get("supplier"), []).append(item)
    return grouped


def meets_minimum(name, order_value):
    """True when an order is large enough for the supplier to accept."""
    return order_value >= min_order(name)
