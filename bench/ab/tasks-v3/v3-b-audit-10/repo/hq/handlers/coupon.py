"""coupon: define a discount coupon."""
import re

from ..errors import ValidationError

_CODE = re.compile(r"^[A-Z0-9]{4,12}$")


def _code(payload):
    code = payload.get("code")
    if not isinstance(code, str):
        raise ValidationError("code", "must be a string")
    if not _CODE.match(code):
        raise ValidationError("code", "must be 4 to 12 of A-Z0-9")
    return code


def _percent(payload):
    percent = payload.get("percent")
    if isinstance(percent, bool) or not isinstance(percent, int):
        raise ValidationError("percent", "must be an integer")
    if not 1 <= percent <= 90:
        raise ValidationError("percent", "must be between 1 and 90")
    return percent


def _max_uses(payload):
    uses = payload.get("max_uses")
    if uses is None:
        return None
    if isinstance(uses, bool) or not isinstance(uses, int):
        raise ValidationError("max_uses", "must be an integer")
    if uses < 1:
        raise ValidationError("max_uses", "must be at least 1")
    return uses


def handle(payload):
    return {
        "code": _code(payload),
        "percent": _percent(payload),
        "max_uses": _max_uses(payload),
    }
