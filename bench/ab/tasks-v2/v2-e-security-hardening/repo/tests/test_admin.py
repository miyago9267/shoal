import unittest

from tests.helpers import ADMIN, BOB, make_app


class AdminTest(unittest.TestCase):
    def setUp(self):
        self.app, self.admin, self.bob, self.cy = make_app()

    def test_list_users_admin_only(self):
        self.assertEqual(self.app.handle("GET", "/admin/users", headers=BOB).status, 403)
        resp = self.app.handle("GET", "/admin/users", headers=ADMIN)
        self.assertEqual([u["name"] for u in resp.body["users"]], ["ada", "bob", "cy"])

    def test_deactivate_revokes_tokens(self):
        path = f"/admin/users/{self.bob['id']}/deactivate"
        self.assertEqual(self.app.handle("POST", path, headers=ADMIN).status, 204)
        self.assertEqual(self.app.handle("GET", "/me", headers=BOB).status, 401)

    def test_admin_changes_role(self):
        path = f"/admin/users/{self.cy['id']}/role"
        resp = self.app.handle("POST", path, headers=ADMIN, body={"role": "admin"})
        self.assertEqual(resp.body["role"], "admin")

    def test_summary(self):
        self.app.handle("POST", "/tickets", headers=BOB, body={"title": "a"})
        resp = self.app.handle("GET", "/admin/reports/summary", headers=ADMIN)
        self.assertEqual(resp.body, {"total": 1, "by_status": {"open": 1}})

    def test_audit_export_for_admin(self):
        self.app.handle("POST", "/tickets", headers=BOB, body={"title": "a"})
        resp = self.app.handle("GET", "/admin/reports/audit?limit=5", headers=ADMIN)
        self.assertEqual(resp.body["entries"][0]["action"], "ticket.create")


if __name__ == "__main__":
    unittest.main()
