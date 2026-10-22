"""Serve files from a static root directory."""
import mimetypes
import os
from dataclasses import dataclass, field

from .paths import resolve_path

DEFAULT_TYPE = "application/octet-stream"


@dataclass
class Response:
    status: int
    body: bytes = b""
    headers: dict = field(default_factory=dict)

    @property
    def content_type(self):
        return self.headers.get("Content-Type", "")


def _error(status, message):
    body = message.encode("utf-8")
    return Response(status, body, {"Content-Type": "text/plain; charset=utf-8"})


def guess_type(path):
    ctype, _ = mimetypes.guess_type(path)
    if ctype is None:
        return DEFAULT_TYPE
    if ctype.startswith("text/"):
        return ctype + "; charset=utf-8"
    return ctype


def serve_file(root, request_path, method="GET"):
    """Serve ``request_path`` relative to ``root`` and return a Response."""
    if method not in ("GET", "HEAD"):
        return _error(405, "method not allowed")
    path = resolve_path(root, request_path)
    if not os.path.isfile(path):
        return _error(404, "not found")
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return _error(500, "could not read file")
    headers = {"Content-Type": guess_type(path), "Content-Length": str(len(data))}
    if method == "HEAD":
        data = b""
    return Response(200, data, headers)
