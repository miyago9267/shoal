"""schedule: book a time slot."""
import datetime
import re

from ..errors import ValidationError

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _date(payload):
    value = payload.get("date")
    if not isinstance(value, str):
        raise ValidationError("date", "must be a string")
    value = value.strip()
    if not _DATE.fullmatch(value):
        raise ValidationError("date", "must look like YYYY-MM-DD")
    try:
        datetime.date(int(value[:4]), int(value[5:7]), int(value[8:]))
    except ValueError:
        raise ValidationError("date", "is not a real date") from None
    return value


def _int(payload, field, lo, hi):
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(field, "must be an integer")
    if not lo <= value <= hi:
        raise ValidationError(field, "must be between %d and %d" % (lo, hi))
    return value


def handle(payload):
    date = _date(payload)
    hour = _int(payload, "hour", 0, 24)
    duration = _int(payload, "duration_min", 1, 480)
    return {
        "date": date,
        "hour": hour,
        "duration_min": duration,
        "end_minute": hour * 60 + duration,
    }
