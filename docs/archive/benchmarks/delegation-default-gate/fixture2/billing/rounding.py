"""Money rounding used everywhere in billing.

The shop rounds half-up to two decimals at every step that produces a stored
amount. Rounding only at the end would change totals by a cent on large
invoices, so each helper rounds its own result.
"""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value):
    """Round a Decimal (or int) to cents, half-up."""
    if not isinstance(value, Decimal):
        value = Decimal(value)
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def cents(value):
    """Convert a money amount to an integer number of cents."""
    return int(money(value) * 100)


def from_cents(value):
    """Convert an integer number of cents to a money amount."""
    return money(Decimal(value) / 100)


def split_evenly(amount, parts):
    """Split amount into parts that add up exactly; extra cents go first."""
    if parts <= 0:
        raise ValueError("parts must be positive")
    total = cents(amount)
    base, extra = divmod(total, parts)
    return [from_cents(base + (1 if i < extra else 0)) for i in range(parts)]


def is_money(value):
    """True when value already has at most two decimals."""
    return money(value) == Decimal(value)
