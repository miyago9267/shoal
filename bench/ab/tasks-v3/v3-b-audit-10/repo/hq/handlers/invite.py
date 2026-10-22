"""invite: invite people to a workspace."""
from .. import validate
from ..errors import ValidationError

ROLES = {"viewer", "editor", "admin"}


def handle(payload):
    raw = validate.list_field(payload, "emails", min_items=1, max_items=20)
    emails = []
    seen = set()
    for item in raw:
        if not isinstance(item, str):
            raise ValidationError("emails", "must contain only strings")
        email = item.strip().lower()
        if not validate.is_email(email):
            raise ValidationError("emails", "bad email %r" % item)
        if email not in seen:
            seen.add(email)
            emails.append(email)
    role = validate.choice_field(payload, "role", ROLES, default="viewer")
    return {"emails": emails, "role": role}
