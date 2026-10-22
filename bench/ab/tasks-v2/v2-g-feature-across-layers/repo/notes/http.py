"""Framework-free JSON request handler."""
import re

from .service import DEFAULT_LIMIT, NotFound

_NOTE_PATH = re.compile(r"^/notes/(\d+)$")


def _int_param(query, name, default):
    raw = query.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None


def handle(service, method, path, query=None, body=None):
    """Return ``(status, body)`` for one request."""
    query = query or {}
    body = body or {}
    try:
        if path == "/notes" and method == "GET":
            return _list(service, query)
        if path == "/notes" and method == "POST":
            note = service.create_note(body.get("title"), body.get("body", ""),
                                       body.get("tags", ()))
            return 201, note.to_dict()
        match = _NOTE_PATH.match(path)
        if match and method == "GET":
            return 200, service.get_note(int(match.group(1))).to_dict()
        if match and method == "DELETE":
            service.delete_note(int(match.group(1)))
            return 204, {}
        if path == "/notes" or match:
            return 405, {"error": "method not allowed"}
        return 404, {"error": "not found"}
    except NotFound:
        return 404, {"error": "note not found"}
    except ValueError as exc:
        return 400, {"error": str(exc)}


def _list(service, query):
    limit = _int_param(query, "limit", DEFAULT_LIMIT)
    offset = _int_param(query, "offset", 0)
    notes, total = service.list_notes(tag=query.get("tag"), limit=limit, offset=offset)
    return 200, {"items": [n.to_dict() for n in notes], "total": total}
