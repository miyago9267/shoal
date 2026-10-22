"""Aggregate inventory rows and render them as a text table."""

COLUMNS = ("category", "items", "quantity", "value")


def summarize(rows, sort_by="category", min_quantity=0):
    """Group rows by category; return a list of dicts keyed by COLUMNS."""
    groups = {}
    for row in rows:
        g = groups.setdefault(row["category"], {
            "category": row["category"], "items": 0, "quantity": 0, "value": 0.0})
        g["items"] += 1
        g["quantity"] += row["quantity"]
        g["value"] += row["quantity"] * row["unit_price"]
    out = [g for g in groups.values() if g["quantity"] >= min_quantity]
    for g in out:
        g["value"] = round(g["value"], 2)
    reverse = sort_by != "category"
    return sorted(out, key=lambda g: (g[sort_by], g["category"]), reverse=reverse)


def format_table(summary):
    """Render the summary as an aligned table with a TOTAL footer."""
    header = ("Category", "Items", "Qty", "Value")
    body = [(g["category"], str(g["items"]), str(g["quantity"]), f"{g['value']:.2f}")
            for g in summary]
    total = ("TOTAL", str(sum(g["items"] for g in summary)),
             str(sum(g["quantity"] for g in summary)),
             f"{sum(g['value'] for g in summary):.2f}")
    widths = [max(len(r[i]) for r in [header, total, *body]) for i in range(4)]

    def line(cells):
        first = cells[0].ljust(widths[0])
        rest = [c.rjust(w) for c, w in zip(cells[1:], widths[1:])]
        return "  ".join([first, *rest])

    rule = "-" * len(line(header))
    return "\n".join([line(header), rule, *map(line, body), rule, line(total)])
