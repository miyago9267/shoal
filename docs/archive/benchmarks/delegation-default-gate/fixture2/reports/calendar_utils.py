"""Date helpers for the reports package. Weeks start on Monday."""

from datetime import timedelta

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def week_start(day):
    """Monday of the week that contains day."""
    return day - timedelta(days=day.weekday())


def weekday_name(offset):
    """Short weekday name for an offset 0..6 from Monday."""
    return WEEKDAYS[offset % 7]


def week_range(day):
    """(Monday, Sunday) of the week that contains day."""
    start = week_start(day)
    return start, start + timedelta(days=6)


def previous_weeks(day, count):
    """Mondays of the count weeks before the week of day, newest first."""
    start = week_start(day)
    return [start - timedelta(days=7 * n) for n in range(1, count + 1)]


def iso_label(day):
    """Label like 2026-W41 for the ISO week of day."""
    year, week, _ = day.isocalendar()
    return "%d-W%02d" % (year, week)
