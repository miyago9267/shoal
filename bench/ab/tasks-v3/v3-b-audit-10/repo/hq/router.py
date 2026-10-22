"""Dispatch a payload to the named handler."""
from .errors import UnknownHandler, ValidationError
from .handlers import HANDLERS


def dispatch(name, payload):
    """Run handler ``name``; non-dict payloads are rejected up front."""
    try:
        handler = HANDLERS[name]
    except KeyError:
        raise UnknownHandler(name) from None
    if not isinstance(payload, dict):
        raise ValidationError("payload", "must be an object")
    return handler(payload)


def names():
    return sorted(HANDLERS)
