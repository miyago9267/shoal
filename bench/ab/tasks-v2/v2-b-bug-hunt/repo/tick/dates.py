"""Calendar-date handling. Due dates are stored as UTC epoch seconds."""
import re
from datetime import date, datetime, timedelta, timezone

_OFFSET = re.compile(r"^([+-])(\d{2}):?(\d{2})$")


def parse_tz(text):
    """``+08:00`` / ``-0530`` / ``Z`` -> a fixed-offset tzinfo."""
    if text in ("Z", "UTC", "utc"):
        return timezone.utc
    match = _OFFSET.match(text or "")
    if not match:
        raise ValueError(f"bad UTC offset {text!r} (expected e.g. +08:00)")
    sign, hours, minutes = match.groups()
    delta = timedelta(hours=int(hours), minutes=int(minutes))
    return timezone(-delta if sign == "-" else delta)


def parse_due(text, tz):
    """``YYYY-MM-DD`` in ``tz`` -> UTC epoch seconds of that local midnight."""
    try:
        day = date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"bad date {text!r} (expected YYYY-MM-DD)") from None
    local_midnight = datetime(day.year, day.month, day.day, tzinfo=tz)
    return int(local_midnight.timestamp())


def due_date(epoch):
    """The calendar date a stored due timestamp refers to."""
    return datetime.fromtimestamp(epoch, timezone.utc).date()


def format_due(epoch, tz):
    if epoch is None:
        return "-"
    return due_date(epoch).isoformat()


def today(tz, now=None):
    now = now if now is not None else datetime.now(timezone.utc)
    return now.astimezone(tz).date()


def days_until(epoch, tz, now=None):
    """Whole days from today (in ``tz``) to the due date; negative if overdue."""
    return (datetime.fromtimestamp(epoch, tz).date() - today(tz, now)).days
