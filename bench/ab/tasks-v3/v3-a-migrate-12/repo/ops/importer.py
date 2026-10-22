"""Importer: parse ``name,qty,price`` rows."""
from .legacy import legacy_log


def parse_rows(lines):
    """Return parsed rows; bad rows are reported and skipped."""
    rows = []
    for n, line in enumerate(lines, 1):
        parts = line.strip().split(",")
        if len(parts) != 3:
            legacy_log("row %d: expected 3 fields, got %d" % (n, len(parts)), 30)
            continue
        name, qty, price = parts
        try:
            qty = int(qty)
            price = float(price)
        except ValueError as exc:
            legacy_log("row %d: %s" % (n, exc), 30)
            continue
        rows.append({"name": name, "qty": qty, "price": price})
    legacy_log(
        "imported %d of %d rows" % (len(rows), len(lines)),
        40 if not rows else 20,
    )
    return rows


def total_value(rows):
    return round(sum(r["qty"] * r["price"] for r in rows), 2)


def by_name(rows):
    return {r["name"]: r for r in rows}


def split_lines(text):
    return [ln for ln in text.splitlines() if ln.strip()]
