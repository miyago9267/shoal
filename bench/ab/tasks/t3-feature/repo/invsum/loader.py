"""Read and validate inventory rows from CSV."""
import csv

REQUIRED = ("sku", "category", "quantity", "unit_price")


def load_rows(path):
    """Return a list of dicts with typed ``quantity`` and ``unit_price``."""
    rows = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"missing columns: {', '.join(missing)}")
        for lineno, raw in enumerate(reader, start=2):
            try:
                rows.append({
                    "sku": raw["sku"].strip(),
                    "category": raw["category"].strip() or "uncategorized",
                    "quantity": int(raw["quantity"]),
                    "unit_price": float(raw["unit_price"]),
                })
            except ValueError:
                raise ValueError(f"line {lineno}: bad number") from None
    return rows
