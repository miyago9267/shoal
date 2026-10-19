"""Weekly sales summary.

An order is a dict: {"id": str, "placed": date, "total": float, "status": str,
"channel": str}. weekly_summary() turns a list of orders into the numbers shown
on the Monday dashboard: per-day totals, the week sum, the best day, the
week-over-week change and the share of each sales channel.
"""

from collections import defaultdict
from datetime import timedelta

from reports import calendar_utils

COUNTED = ("paid", "shipped")


def counted(orders):
    """Orders that count towards revenue (cancelled and refunded ones do not)."""
    return [o for o in orders if o["status"] in COUNTED]


def by_day(orders, week_start):
    """Totals per ISO weekday offset 0..6 for the week starting at week_start."""
    week_end = week_start + timedelta(days=6)
    totals = defaultdict(float)
    for order in counted(orders):
        if week_start <= order["placed"] <= week_end:
            totals[(order["placed"] - week_start).days] += order["total"]
    return {day: round(totals[day], 2) for day in range(7)}


def by_channel(orders, week_start):
    """Revenue share per sales channel within the week (fractions summing to 1)."""
    week_end = week_start + timedelta(days=6)
    totals = defaultdict(float)
    for order in counted(orders):
        if week_start <= order["placed"] <= week_end:
            totals[order["channel"]] += order["total"]
    grand = sum(totals.values())
    if grand == 0:
        return {}
    return {name: round(value / grand, 4) for name, value in sorted(totals.items())}


def week_over_week(orders, week_start):
    """Percentage change of this week's revenue against the previous week."""
    this_week = sum(by_day(orders, week_start).values())
    last_week = sum(by_day(orders, week_start - timedelta(days=7)).values())
    if last_week == 0:
        return None
    return round((this_week - last_week) / last_week * 100, 1)


def weekly_summary(orders, today):
    """The summary dict for the week that contains today (weeks start on Monday)."""
    week_start = calendar_utils.week_start(today)
    days = by_day(orders, week_start)
    total = round(sum(days.values()), 2)
    best_offset = max(days, key=lambda d: (days[d], -d))
    return {
        "week_start": week_start,
        "days": days,
        "sum": total,
        "best_day": calendar_utils.weekday_name(best_offset) if total else None,
        "wow_percent": week_over_week(orders, week_start),
        "channels": by_channel(orders, week_start),
        "order_count": len(
            [
                o
                for o in counted(orders)
                if week_start <= o["placed"] <= week_start + timedelta(days=6)
            ]
        ),
    }
