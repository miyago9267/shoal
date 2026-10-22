"""Shopping cart line items."""
from dataclasses import dataclass, field


@dataclass
class Cart:
    lines: dict = field(default_factory=dict)

    def total_units(self):
        return sum(self.lines.values())


def add_item(cart, sku, qty=1):
    """Add ``qty`` units of ``sku``; return the new quantity for that line."""
    cart.lines[sku] = cart.lines.get(sku, 0) + qty
    return cart.lines[sku]


def remove_item(cart, sku):
    """Drop a line entirely; missing SKUs are ignored."""
    cart.lines.pop(sku, None)
