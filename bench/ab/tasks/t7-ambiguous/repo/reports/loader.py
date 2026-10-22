"""Load order rows exported from the shop backend."""
import csv
from dataclasses import dataclass
from decimal import Decimal

REQUIRED = ("order_id", "customer_email", "region", "amount", "created_at")


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_email: str
    region: str
    amount: Decimal
    created_at: str


def parse_row(row):
    missing = [name for name in REQUIRED if not row.get(name)]
    if missing:
        raise ValueError("row missing fields: " + ", ".join(missing))
    return Order(
        order_id=row["order_id"],
        customer_email=row["customer_email"],
        region=row["region"].strip().upper(),
        amount=Decimal(row["amount"]),
        created_at=row["created_at"],
    )


def load_orders(fh):
    """Parse every row of a CSV export into Order records."""
    return [parse_row(row) for row in csv.DictReader(fh)]
