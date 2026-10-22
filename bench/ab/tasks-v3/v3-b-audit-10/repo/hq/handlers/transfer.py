"""transfer: move money between two accounts."""
from ..errors import ValidationError

MAX_CENTS = 1_000_000


def _account(payload, field):
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(field, "must be a non-empty string")
    return value.strip()


def _amount(payload):
    amount = payload.get("amount_cents")
    if amount is None:
        raise ValidationError("amount_cents", "is required")
    if not isinstance(amount, int):
        raise ValidationError("amount_cents", "must be an integer")
    if amount < 1 or amount > MAX_CENTS:
        raise ValidationError("amount_cents", "must be between 1 and %d" % MAX_CENTS)
    return amount


def handle(payload):
    src = _account(payload, "src")
    dst = _account(payload, "dst")
    if src == dst:
        raise ValidationError("dst", "must differ from src")
    amount = _amount(payload)
    return {
        "src": src,
        "dst": dst,
        "amount_cents": amount,
        "fee_cents": amount // 100,
    }
