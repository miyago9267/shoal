"""profile: update a user profile."""
import re

from .. import validate
from ..errors import ValidationError

_TAG = re.compile(r"[a-z0-9-]{1,20}")
MAX_TAGS = 5


def _tags(payload):
    raw = validate.list_field(payload, "tags", max_items=MAX_TAGS, required=False)
    if raw is None:
        return []
    tags = []
    seen = set()
    for item in raw:
        if not isinstance(item, str):
            raise ValidationError("tags", "must contain only strings")
        tag = item.strip().lower()
        if not _TAG.fullmatch(tag):
            raise ValidationError("tags", "bad tag %r" % item)
        if tag in seen:
            raise ValidationError("tags", "duplicate tag %r" % item)
        seen.add(tag)
        tags.append(tag)
    return tags


def handle(payload):
    name = validate.str_field(payload, "name", 1, 50)
    bio = validate.str_field(payload, "bio", 0, 280, required=False) or None
    return {"name": name, "bio": bio, "tags": _tags(payload)}
