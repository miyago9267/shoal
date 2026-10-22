"""Application wiring: router + store + token registry."""
from .handlers import admin, reports, tickets
from .http import error
from .router import Router, make_request
from .store import Store
from .tokens import TokenRegistry


class App:
    def __init__(self, store=None, tokens=None):
        self.store = store or Store()
        self.tokens = tokens or TokenRegistry()
        self.router = Router()
        tickets.register(self.router)
        admin.register(self.router)
        reports.register(self.router)

    def handle(self, method, path, headers=None, body=None):
        request = make_request(method, path, headers=headers, body=body)
        try:
            return self.router.dispatch(request, self)
        except Exception:  # never leak internals to clients
            return error(500, "internal error")


def build_app(store=None, tokens=None):
    return App(store=store, tokens=tokens)
