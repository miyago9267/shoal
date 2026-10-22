"""Pattern based router: ``/tickets/{id}`` style placeholders."""
import re

from .http import Request, error

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class Route:
    def __init__(self, method, pattern, handler):
        self.method = method.upper()
        self.pattern = pattern
        self.handler = handler
        regex = _PLACEHOLDER.sub(r"(?P<\1>[^/]+)", pattern)
        self._regex = re.compile("^" + regex + "$")

    def match(self, method, path):
        if method.upper() != self.method:
            return None
        found = self._regex.match(path)
        return found.groupdict() if found else None


class Router:
    def __init__(self):
        self._routes = []

    def add(self, method, pattern, handler):
        self._routes.append(Route(method, pattern, handler))

    def route(self, method, pattern):
        def decorator(fn):
            self.add(method, pattern, fn)
            return fn
        return decorator

    def routes(self):
        """Every registered ``(method, pattern)`` pair, in registration order."""
        return [(r.method, r.pattern) for r in self._routes]

    def dispatch(self, request, context):
        path_matched = False
        for route in self._routes:
            if route._regex.match(request.path):
                path_matched = True
            params = route.match(request.method, request.path)
            if params is None:
                continue
            request.params = params
            return route.handler(request, context)
        if path_matched:
            return error(405, "method not allowed")
        return error(404, "not found")


def make_request(method, path, headers=None, body=None):
    path, _, raw_query = path.partition("?")
    query = {}
    for part in filter(None, raw_query.split("&")):
        key, _, value = part.partition("=")
        query[key] = value
    return Request(method, path, headers=headers, body=body, query=query)
