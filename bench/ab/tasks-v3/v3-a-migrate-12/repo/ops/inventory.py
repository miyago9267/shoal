"""Inventory: stock levels per SKU."""
from .legacy import legacy_log

LOW_WATER = 5


def restock(stock, deliveries):
    """Apply ``deliveries`` (list of (sku, qty)); returns SKUs touched."""
    touched = 0
    for sku, qty in deliveries:
        if qty <= 0:
            continue
        stock[sku] = stock.get(sku, 0) + qty
        touched += 1
        legacy_log(f"restock {sku} +{qty} -> {stock[sku]}", 20)
        if stock[sku] < LOW_WATER:
            legacy_log(f"{sku} still low ({stock[sku]})", 30)
    legacy_log("restock finished: %d skus" % touched, 20)
    return touched


def take(stock, sku, qty):
    """Remove ``qty`` units; raises KeyError for unknown SKUs, ValueError if short."""
    have = stock[sku]
    if qty > have:
        raise ValueError("only %d of %s" % (have, sku))
    stock[sku] = have - qty
    return stock[sku]


def low_items(stock):
    return sorted(s for s, q in stock.items() if q < LOW_WATER)


def snapshot(stock):
    return dict(sorted(stock.items()))


def merge(a, b):
    out = dict(a)
    for sku, qty in b.items():
        out[sku] = out.get(sku, 0) + qty
    return out
