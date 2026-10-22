"""signup: create an account request."""
from ..errors import ValidationError

MAX_EMAIL = 254


def _name(payload):
    name = payload.get("name")
    if not isinstance(name, str):
        raise ValidationError("name", "must be a string")
    name = name.strip()
    if not 1 <= len(name) <= 50:
        raise ValidationError("name", "must have 1 to 50 characters")
    return name


def _age(payload):
    age = payload.get("age")
    if isinstance(age, bool) or not isinstance(age, int):
        raise ValidationError("age", "must be an integer")
    if age < 13 or age > 120:
        raise ValidationError("age", "must be between 13 and 120")
    return age


def _email(payload):
    email = payload.get("email")
    if not isinstance(email, str):
        raise ValidationError("email", "must be a string")
    email = email.strip().lower()
    if len(email) > MAX_EMAIL:
        raise ValidationError("email", "is too long")
    if "@" not in email or "." not in email:
        raise ValidationError("email", "is not a valid email")
    return email


def handle(payload):
    return {
        "email": _email(payload),
        "age": _age(payload),
        "name": _name(payload),
    }
