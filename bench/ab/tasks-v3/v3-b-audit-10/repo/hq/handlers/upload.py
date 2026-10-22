"""upload: accept metadata for a file upload."""
from ..errors import ValidationError

ALLOWED_TYPES = {"image/png", "image/jpeg", "text/plain", "application/pdf"}
MAX_SIZE = 10 * 1024 * 1024


def _filename(payload):
    name = payload.get("filename")
    if not isinstance(name, str):
        raise ValidationError("filename", "must be a string")
    if not 1 <= len(name) <= 100:
        raise ValidationError("filename", "must have 1 to 100 characters")
    if "\0" in name:
        raise ValidationError("filename", "contains a NUL byte")
    if name.startswith("../") or name == "..":
        raise ValidationError("filename", "must not be a path")
    return name


def _size(payload):
    size = payload.get("size")
    if isinstance(size, bool) or not isinstance(size, int):
        raise ValidationError("size", "must be an integer")
    if size < 1 or size > MAX_SIZE:
        raise ValidationError("size", "must be between 1 and %d" % MAX_SIZE)
    return size


def _content_type(payload):
    ctype = payload.get("content_type")
    if ctype not in ALLOWED_TYPES:
        raise ValidationError("content_type", "is not allowed")
    return ctype


def handle(payload):
    return {
        "filename": _filename(payload),
        "size": _size(payload),
        "content_type": _content_type(payload),
    }
