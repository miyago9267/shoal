"""Restock decisions.

An item needs restocking when the stock we can count on (on hand plus incoming
supplier shipments minus reservations) would not last through the supplier lead
time plus a safety margin at the item's recent sales velocity.
"""

from inventory import suppliers, velocity

# Used when an item has no sales history yet (new SKU): a fixed floor.
DEFAULT_REORDER_LEVEL = 5
SAFETY_DAYS = 3
MAX_COVER_DAYS = 60


def available(item):
    """Units we can promise: on hand + incoming - reserved (never negative)."""
    count = item["on_hand"] + item.get("incoming", 0) - item.get("reserved", 0)
    return max(count, 0)


def reorder_point(item):
    """Stock level at or below which a reorder is due.

    With sales history: daily velocity x (supplier lead days + SAFETY_DAYS).
    Without history: DEFAULT_REORDER_LEVEL. Items flagged "seasonal" use the
    velocity of the same weeks last year when it is higher.
    """
    daily = velocity.daily_sales(item["sku"], seasonal=item.get("seasonal", False))
    if daily is None:
        return DEFAULT_REORDER_LEVEL
    lead = suppliers.lead_days(item.get("supplier"))
    return int(round(daily * (lead + SAFETY_DAYS)))


def needs_restock(item):
    """True when available stock is at or below the reorder point."""
    if item.get("discontinued"):
        return False
    return available(item) <= reorder_point(item)


def order_quantity(item):
    """How many units to order: refill to MAX_COVER_DAYS of cover, in case packs."""
    daily = velocity.daily_sales(item["sku"], seasonal=item.get("seasonal", False))
    if daily is None:
        target = DEFAULT_REORDER_LEVEL * 4
    else:
        target = int(round(daily * MAX_COVER_DAYS))
    missing = max(target - available(item), 0)
    pack = item.get("case_pack", 1)
    packs = -(-missing // pack)  # ceiling division
    return packs * pack


def restock_list(items):
    """(sku, quantity) pairs for every item that needs restocking, urgent first."""
    due = [i for i in items if needs_restock(i)]
    due.sort(key=lambda i: available(i) - reorder_point(i))
    return [(i["sku"], order_quantity(i)) for i in due]
