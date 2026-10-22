"""search: parameters for a catalogue search."""
from ..errors import ValidationError

DEFAULT_LIMIT = 20


def _query(payload):
    query = payload.get("query")
    if not isinstance(query, str):
        raise ValidationError("query", "must be a string")
    if not query:
        raise ValidationError("query", "must not be empty")
    query = query.strip()
    if len(query) > 200:
        raise ValidationError("query", "is too long")
    return query


def _optional_int(payload, field, default, lo, hi):
    value = payload.get(field)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(field, "must be an integer")
    if value < lo or (hi is not None and value > hi):
        raise ValidationError(field, "is out of range")
    return value


def handle(payload):
    return {
        "query": _query(payload),
        "limit": _optional_int(payload, "limit", DEFAULT_LIMIT, 1, 100),
        "offset": _optional_int(payload, "offset", 0, 0, None),
    }
