"""Validation helpers shared by the handlers."""
import re

from .errors import ValidationError

_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?")


def require(payload, field):
    """Return ``payload[field]`` or raise when it is missing or None."""
    value = payload.get(field)
    if value is None:
        raise ValidationError(field, "is required")
    return value


def str_field(payload, field, min_len=1, max_len=None, required=True):
    """Return the stripped string at ``field``; None for an absent optional."""
    value = payload.get(field)
    if value is None:
        if required:
            raise ValidationError(field, "is required")
        return None
    if not isinstance(value, str):
        raise ValidationError(field, "must be a string")
    value = value.strip()
    if len(value) < min_len:
        raise ValidationError(field, "must have at least %d characters" % min_len)
    if max_len is not None and len(value) > max_len:
        raise ValidationError(field, "must have at most %d characters" % max_len)
    return value


def int_field(payload, field, lo=None, hi=None, default=None):
    """Return an int in ``[lo, hi]``; bool is rejected."""
    value = payload.get(field)
    if value is None:
        if default is not None:
            return default
        raise ValidationError(field, "is required")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(field, "must be an integer")
    if lo is not None and value < lo:
        raise ValidationError(field, "must be at least %d" % lo)
    if hi is not None and value > hi:
        raise ValidationError(field, "must be at most %d" % hi)
    return value


def choice_field(payload, field, options, default=None):
    value = payload.get(field)
    if value is None:
        if default is not None:
            return default
        raise ValidationError(field, "is required")
    if value not in options:
        raise ValidationError(field, "must be one of %s" % ", ".join(sorted(options)))
    return value


def is_email(text):
    """Strict email shape check used by the newer handlers."""
    if not isinstance(text, str) or len(text) > 254:
        return False
    if text.count("@") != 1:
        return False
    local, domain = text.split("@")
    if not local or " " in text:
        return False
    labels = domain.split(".")
    if len(labels) < 2:
        return False
    return all(_LABEL.fullmatch(label) for label in labels)


def email_field(payload, field):
    value = str_field(payload, field).lower()
    if not is_email(value):
        raise ValidationError(field, "is not a valid email")
    return value


def list_field(payload, field, min_items=0, max_items=None, required=True):
    value = payload.get(field)
    if value is None:
        if required:
            raise ValidationError(field, "is required")
        return None
    if not isinstance(value, list):
        raise ValidationError(field, "must be a list")
    if len(value) < min_items:
        raise ValidationError(field, "needs at least %d items" % min_items)
    if max_items is not None and len(value) > max_items:
        raise ValidationError(field, "allows at most %d items" % max_items)
    return value
