"""Item catalog with a few demo products and simple lookups."""

ITEMS = [
    {
        "sku": "a1",
        "name": "Desk lamp",
        "on_hand": 9,
        "supplier": "acme",
        "case_pack": 6,
    },
    {
        "sku": "b2",
        "name": "Notebook",
        "on_hand": 2,
        "incoming": 1,
        "supplier": "initech",
        "case_pack": 12,
    },
    {
        "sku": "c3",
        "name": "Umbrella",
        "on_hand": 14,
        "reserved": 4,
        "seasonal": True,
        "supplier": "globex",
        "case_pack": 10,
    },
    {"sku": "d4", "name": "Mug", "on_hand": 0, "supplier": "acme", "case_pack": 24},
    {"sku": "e5", "name": "Poster", "on_hand": 40, "discontinued": True},
]


def by_sku(sku):
    """Return the catalog item for a SKU or None."""
    for item in ITEMS:
        if item["sku"] == sku:
            return item
    return None


def active_items():
    """Items that are still sold."""
    return [i for i in ITEMS if not i.get("discontinued")]


def adjust(sku, delta):
    """Change on-hand stock by delta (receipts positive, shrinkage negative)."""
    item = by_sku(sku)
    if item is None:
        raise KeyError(sku)
    item["on_hand"] = max(item["on_hand"] + delta, 0)
    return item["on_hand"]


def receive(sku, qty):
    """Book a supplier delivery: stock goes up, incoming goes down."""
    item = by_sku(sku)
    if item is None:
        raise KeyError(sku)
    item["on_hand"] += qty
    item["incoming"] = max(item.get("incoming", 0) - qty, 0)
    return item


def total_units():
    """Sum of on-hand units over active items."""
    return sum(i["on_hand"] for i in active_items())
