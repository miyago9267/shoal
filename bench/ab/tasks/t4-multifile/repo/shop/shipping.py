"""Shipping cost by parcel weight and destination zone."""

ZONES = {
    "domestic": (500, 120),
    "regional": (900, 250),
    "international": (1800, 600),
}


def shipping_cost(weight_kg, zone):
    """Cents to ship a parcel: zone base fee plus a per-started-kg rate."""
    base, per_kg = ZONES[zone]
    whole_kg = int(weight_kg) + (0 if float(weight_kg).is_integer() else 1)
    return base + per_kg * max(whole_kg - 1, 0)
