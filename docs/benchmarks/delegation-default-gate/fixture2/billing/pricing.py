"""Line-level pricing: unit price, quantity discounts and promotional codes.

Every amount in this package is a Decimal in the shop currency. A "line" is a
dict: {"sku": str, "unit_price": Decimal, "qty": int, "tax_kind": str}.
"""

from decimal import Decimal

from billing.rounding import money

# Quantity breaks apply to the whole line, highest matching break wins.
QTY_BREAKS = [
    (100, Decimal("0.15")),
    (50, Decimal("0.10")),
    (10, Decimal("0.05")),
]

# Promotional codes: percentage off the discounted subtotal, with a cap.
PROMOS = {
    "WELCOME5": {"percent": Decimal("0.05"), "cap": Decimal("20.00")},
    "SPRING10": {"percent": Decimal("0.10"), "cap": Decimal("50.00")},
    "STAFF": {"percent": Decimal("0.25"), "cap": Decimal("200.00")},
}


class UnknownPromo(ValueError):
    """Raised when a promotional code is not in PROMOS."""


def qty_discount_rate(qty):
    """Return the quantity discount rate for a line quantity."""
    for threshold, rate in QTY_BREAKS:
        if qty >= threshold:
            return rate
    return Decimal("0")


def line_gross(line):
    """Price of a line before any discount."""
    return money(line["unit_price"] * line["qty"])


def line_net(line):
    """Price of a line after the quantity discount, before tax."""
    gross = line_gross(line)
    rate = qty_discount_rate(line["qty"])
    return money(gross - gross * rate)


def subtotal(lines):
    """Sum of line_net over all lines."""
    return money(sum((line_net(line) for line in lines), Decimal("0")))


def promo_discount(code, amount):
    """Discount for a promo code applied to amount (never more than the cap)."""
    if code is None:
        return Decimal("0.00")
    try:
        promo = PROMOS[code.upper()]
    except KeyError:
        raise UnknownPromo(code)
    raw = money(amount * promo["percent"])
    return min(raw, promo["cap"])


def spread_discount(lines, discount):
    """Allocate a promo discount over the lines in proportion to their net.

    The last line absorbs the rounding remainder so the parts always add up to
    the discount exactly. Tax is computed on the discounted line amounts.
    """
    nets = [line_net(line) for line in lines]
    total = sum(nets, Decimal("0"))
    if total == 0 or discount == 0:
        return [Decimal("0.00") for _ in lines]
    shares = []
    allocated = Decimal("0.00")
    for index, net in enumerate(nets):
        if index == len(nets) - 1:
            share = discount - allocated
        else:
            share = money(discount * net / total)
            allocated += share
        shares.append(share)
    return shares


def describe_pricing():
    """Human readable summary of the pricing rules (used by the CLI help)."""
    parts = ["qty>=%d: %s%%" % (t, (r * 100).normalize()) for t, r in QTY_BREAKS]
    parts.append("promos: " + ", ".join(sorted(PROMOS)))
    return "; ".join(parts)
