import unittest

from tests.helpers import BOB, CY, make_app


class TicketTest(unittest.TestCase):
    def setUp(self):
        self.app, self.admin, self.bob, self.cy = make_app()

    def test_requires_login(self):
        self.assertEqual(self.app.handle("GET", "/tickets").status, 401)

    def test_create_and_list(self):
        resp = self.app.handle("POST", "/tickets", headers=BOB, body={"title": "printer"})
        self.assertEqual(resp.status, 201)
        listed = self.app.handle("GET", "/tickets", headers=BOB).body["tickets"]
        self.assertEqual([t["title"] for t in listed], ["printer"])
        self.assertEqual(self.app.handle("GET", "/tickets", headers=CY).body["tickets"], [])

    def test_other_users_ticket_is_hidden(self):
        tid = self.app.handle("POST", "/tickets", headers=BOB, body={"title": "x"}).body["id"]
        self.assertEqual(self.app.handle("GET", f"/tickets/{tid}", headers=CY).status, 404)
        self.assertEqual(self.app.handle("GET", f"/tickets/{tid}", headers=BOB).status, 200)

    def test_status_update(self):
        tid = self.app.handle("POST", "/tickets", headers=BOB, body={"title": "x"}).body["id"]
        resp = self.app.handle("POST", f"/tickets/{tid}/status", headers=BOB,
                               body={"status": "closed"})
        self.assertEqual(resp.body["status"], "closed")
        bad = self.app.handle("POST", f"/tickets/{tid}/status", headers=BOB,
                              body={"status": "lost"})
        self.assertEqual(bad.status, 400)

    def test_unknown_route(self):
        self.assertEqual(self.app.handle("GET", "/nope", headers=BOB).status, 404)
        self.assertEqual(self.app.handle("PUT", "/tickets", headers=BOB).status, 405)


if __name__ == "__main__":
    unittest.main()
