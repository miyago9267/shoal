"""Request validation and response helpers."""
from .errors import BadRequest


def ok(**fields):
    return {"ok": True, **fields}


def error(code, message=""):
    response = {"ok": False, "error": code}
    if message:
        response["message"] = message
    return response


def require_key(request, field="key"):
    key = request.get(field)
    if not isinstance(key, str) or not key:
        raise BadRequest(f"'{field}' must be a non-empty string")
    return key


def require_keys(request):
    keys = request.get("keys")
    if not isinstance(keys, list) or not all(isinstance(k, str) and k for k in keys):
        raise BadRequest("'keys' must be a list of non-empty strings")
    return keys


def optional_int(request, field, default):
    value = request.get(field, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BadRequest(f"'{field}' must be an integer")
    return value


def require_value(request):
    if "value" not in request:
        raise BadRequest("'value' is required")
    return request["value"]
