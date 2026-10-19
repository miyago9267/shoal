"""Sales velocity: units sold per day from the sales log."""

from datetime import date, timedelta

# (sku, date, qty) rows; the real tool loads these from the orders export.
SALES = []

WINDOW_DAYS = 28
MIN_DAYS_OF_HISTORY = 7


def record(sku, day, qty):
    """Append a sales row."""
    SALES.append((sku, day, qty))


def _rows(sku, start, end):
    return [q for s, d, q in SALES if s == sku and start <= d <= end]


def history_days(sku):
    """Days between the first and last sale of a SKU (0 when unknown)."""
    days = [d for s, d, _ in SALES if s == sku]
    if not days:
        return 0
    return (max(days) - min(days)).days + 1


def daily_sales(sku, seasonal=False, today=None):
    """Average units per day over the last WINDOW_DAYS; None without enough history.

    Seasonal items also look at the same window a year earlier and use the
    larger of the two numbers, so a restock is not missed before the season.
    """
    if history_days(sku) < MIN_DAYS_OF_HISTORY:
        return None
    today = today or max(d for s, d, _ in SALES if s == sku)
    start = today - timedelta(days=WINDOW_DAYS - 1)
    recent = sum(_rows(sku, start, today)) / float(WINDOW_DAYS)
    if not seasonal:
        return recent
    last_year = today - timedelta(days=365)
    base = sum(_rows(sku, last_year - timedelta(days=WINDOW_DAYS - 1), last_year))
    return max(recent, base / float(WINDOW_DAYS))


def trend(sku, today=None):
    """Ratio of the last 7 days' sales to the 28 day average (1.0 = flat)."""
    today = today or date.today()
    week = sum(_rows(sku, today - timedelta(days=6), today)) / 7.0
    month = sum(_rows(sku, today - timedelta(days=WINDOW_DAYS - 1), today)) / float(
        WINDOW_DAYS
    )
    if month == 0:
        return 1.0
    return week / month


def reset():
    """Clear the sales log (tests only)."""
    del SALES[:]
