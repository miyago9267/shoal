import hmac
import re
import secrets
import sys
import unittest
from unittest import mock

from deskapi.app import build_app


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


class Fixture:
    def __init__(self):
        self.app = build_app()
        self.admin = self.app.store.add_user("ada", role="admin")
        self.agent = self.app.store.add_user("bob", role="agent")
        self.victim = self.app.store.add_user("cy", role="agent")
        self.app.tokens.issue("adm", "admin-secret-1", self.admin["id"])
        self.app.tokens.issue("bob", "bob-secret-22", self.agent["id"])
        self.app.tokens.issue("cy", "cy-secret-333", self.victim["id"])
        self.ticket = self.app.store.add_ticket(self.victim["id"], "vpn down")
        self.ADMIN = bearer("adm.admin-secret-1")
        self.AGENT = bearer("bob.bob-secret-22")

    def admin_routes(self):
        routes = [(m, p) for m, p in self.app.router.routes() if p.startswith("/admin")]
        assert routes, "no admin routes registered"
        return routes

    def fill(self, pattern):
        target = self.ticket["id"] if "/tickets/" in pattern else self.victim["id"]
        return re.sub(r"\{\w+\}", str(target), pattern)

    def body_for(self, pattern):
        return {"role": "admin"} if pattern.endswith("/role") else {}


class AdminAuthorizationTest(unittest.TestCase):
    def test_every_admin_route_rejects_agents(self):
        for method, pattern in Fixture().admin_routes():
            fx = Fixture()
            path = fx.fill(pattern)
            resp = fx.app.handle(method, path, headers=fx.AGENT, body=fx.body_for(pattern))
            self.assertEqual(resp.status, 403, f"{method} {pattern} -> {resp.status}")
            self.assertEqual(fx.victim["role"], "agent")
            self.assertTrue(fx.victim["active"])
            self.assertIn(fx.ticket["id"], fx.app.store.tickets)

    def test_spoofed_role_header_is_ignored(self):
        for method, pattern in Fixture().admin_routes():
            fx = Fixture()
            headers = dict(fx.AGENT, **{"X-Role": "admin"})
            resp = fx.app.handle(method, fx.fill(pattern), headers=headers,
                                 body=fx.body_for(pattern))
            self.assertEqual(resp.status, 403, f"{method} {pattern} with X-Role")

    def test_every_admin_route_requires_login(self):
        for method, pattern in Fixture().admin_routes():
            fx = Fixture()
            resp = fx.app.handle(method, fx.fill(pattern), headers={"X-Role": "admin"},
                                 body=fx.body_for(pattern))
            self.assertEqual(resp.status, 401, f"{method} {pattern} -> {resp.status}")

    def test_admin_still_allowed_everywhere(self):
        for method, pattern in Fixture().admin_routes():
            fx = Fixture()
            resp = fx.app.handle(method, fx.fill(pattern), headers=fx.ADMIN,
                                 body=fx.body_for(pattern))
            self.assertTrue(resp.ok, f"{method} {pattern} -> {resp.status} {resp.body}")

    def test_role_change_and_audit_for_admin(self):
        fx = Fixture()
        resp = fx.app.handle("POST", f"/admin/users/{fx.victim['id']}/role",
                             headers=fx.ADMIN, body={"role": "admin"})
        self.assertEqual(resp.body["role"], "admin")
        audit = fx.app.handle("GET", "/admin/reports/audit", headers=fx.ADMIN)
        self.assertEqual(audit.body["entries"][-1]["action"], "user.role")

    def test_agent_endpoints_unaffected(self):
        fx = Fixture()
        self.assertEqual(fx.app.handle("GET", "/me", headers=fx.AGENT).body["name"], "bob")
        created = fx.app.handle("POST", "/tickets", headers=fx.AGENT, body={"title": "x"})
        self.assertEqual(created.status, 201)
        tid = fx.ticket["id"]
        self.assertEqual(fx.app.handle("GET", f"/tickets/{tid}", headers=fx.AGENT).status, 404)
        self.assertEqual(fx.app.handle("GET", f"/tickets/{tid}", headers=fx.ADMIN).status, 200)


class ConstantTimeTokenTest(unittest.TestCase):
    """Token secrets must be compared with a constant-time primitive."""

    def _spy_all(self, stack, calls):
        real = hmac.compare_digest

        def spy(a, b):
            calls.append((a, b))
            return real(a, b)

        stack.enter_context(mock.patch.object(hmac, "compare_digest", spy))
        stack.enter_context(mock.patch.object(secrets, "compare_digest", spy))
        for name, module in list(sys.modules.items()):
            if not name.startswith("deskapi") or module is None:
                continue
            for attr, value in list(vars(module).items()):
                if value is real:
                    stack.enter_context(mock.patch.object(module, attr, spy))

    def _resolve_with_spy(self, token):
        from contextlib import ExitStack
        fx = Fixture()
        calls = []
        with ExitStack() as stack:
            self._spy_all(stack, calls)
            resp = fx.app.handle("GET", "/me", headers=bearer(token))
        return resp, calls

    def test_valid_token_uses_compare_digest(self):
        resp, calls = self._resolve_with_spy("bob.bob-secret-22")
        self.assertEqual(resp.status, 200)
        self.assertTrue(calls, "token secret was not compared with compare_digest")

    def test_wrong_secret_of_other_length_uses_compare_digest(self):
        resp, calls = self._resolve_with_spy("bob.x")
        self.assertEqual(resp.status, 401)
        self.assertTrue(calls, "length mismatch short-circuits before a constant-time compare")

    def test_wrong_secret_same_length_rejected(self):
        resp, calls = self._resolve_with_spy("bob.bob-secret-23")
        self.assertEqual(resp.status, 401)
        self.assertTrue(calls)

    def test_non_ascii_token_rejected_not_crashing(self):
        fx = Fixture()
        resp = fx.app.handle("GET", "/me", headers=bearer("bob.bob-sécret-22"))
        self.assertEqual(resp.status, 401)


if __name__ == "__main__":
    unittest.main()
