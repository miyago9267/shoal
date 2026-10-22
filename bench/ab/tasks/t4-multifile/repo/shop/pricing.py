"""Price arithmetic. Prices are integer cents."""


def apply_discount(price_cents, percent):
    """Return the discounted price, rounded to the nearest cent."""
    return round(price_cents * (100 - percent) / 100)


def line_total(unit_cents, qty, percent=0):
    return apply_discount(unit_cents * qty, percent)
