"""Minimal request/response objects used by the router and handlers."""
import json


class Request:
    def __init__(self, method, path, headers=None, body=None, query=None):
        self.method = method.upper()
        self.path = path
        # Header names are case-insensitive; normalise once here.
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.body = body or {}
        self.query = query or {}
        self.params = {}
        self.user = None

    def header(self, name, default=None):
        return self.headers.get(name.lower(), default)


class Response:
    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body if body is not None else {}

    @property
    def ok(self):
        return 200 <= self.status < 300

    def json(self):
        return json.dumps(self.body, sort_keys=True)

    def __repr__(self):
        return f"Response({self.status}, {self.body!r})"


def ok(body=None):
    return Response(200, body)


def created(body=None):
    return Response(201, body)


def no_content():
    return Response(204, None)


def error(status, message):
    return Response(status, {"error": message})
