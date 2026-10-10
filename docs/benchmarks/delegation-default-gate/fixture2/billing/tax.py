"""Tax rules: rates by region and item kind, exemptions and reverse charge."""

from decimal import Decimal

from billing.rounding import money

# Rates by region, then by tax kind. A missing kind falls back to "standard".
RATES = {
    "TW": {
        "standard": Decimal("0.05"),
        "reduced": Decimal("0.00"),
        "digital": Decimal("0.05"),
    },
    "DE": {
        "standard": Decimal("0.19"),
        "reduced": Decimal("0.07"),
        "digital": Decimal("0.19"),
    },
    "US-CA": {
        "standard": Decimal("0.0725"),
        "reduced": Decimal("0.0725"),
        "digital": Decimal("0.00"),
    },
}

DEFAULT_REGION = "TW"

# Customers with a valid business id in these regions are charged no tax on
# cross-border sales; the invoice carries a reverse-charge note instead.
REVERSE_CHARGE_REGIONS = {"DE"}


class UnknownRegion(KeyError):
    """Raised when a region has no rate table."""


def rate_for(region, kind="standard"):
    """Tax rate for an item kind in a region."""
    try:
        table = RATES[region]
    except KeyError:
        raise UnknownRegion(region)
    return table.get(kind, table["standard"])


def tax_for(amount, region=DEFAULT_REGION, kind="standard"):
    """Tax on a single (already discounted) amount."""
    return money(amount * rate_for(region, kind))


def is_reverse_charge(seller_region, buyer_region, buyer_has_business_id):
    """True when the sale is cross-border B2B into a reverse-charge region."""
    return (
        buyer_has_business_id
        and buyer_region != seller_region
        and buyer_region in REVERSE_CHARGE_REGIONS
    )


def tax_lines(amounts, kinds, region=DEFAULT_REGION, exempt=False):
    """Tax per line for parallel lists of amounts and tax kinds.

    Tax is computed per line (not on the invoice total) because lines can have
    different kinds, then rounded per line by tax_for.
    """
    if len(amounts) != len(kinds):
        raise ValueError("amounts and kinds must be the same length")
    if exempt:
        return [money(0) for _ in amounts]
    return [tax_for(a, region, k) for a, k in zip(amounts, kinds)]


def effective_rate(amounts, kinds, region=DEFAULT_REGION):
    """Blended rate over a set of lines, for display only."""
    total = sum(amounts, Decimal("0"))
    if total == 0:
        return Decimal("0")
    taxed = sum(tax_lines(amounts, kinds, region), Decimal("0"))
    return (taxed / total).quantize(Decimal("0.0001"))
