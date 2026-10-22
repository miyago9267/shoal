import unittest

from notes.http import handle
from tests.support import seeded


class HttpTest(unittest.TestCase):
    def test_list_page(self):
        svc = seeded(5)
        status, body = handle(svc, "GET", "/notes", {"limit": "2"})
        self.assertEqual(status, 200)
        self.assertEqual([n["title"] for n in body["items"]], ["note 5", "note 4"])

    def test_create_get_delete(self):
        svc = seeded(0)
        status, note = handle(svc, "POST", "/notes", body={"title": "hi", "tags": ["a"]})
        self.assertEqual((status, note["tags"]), (201, ["a"]))
        self.assertEqual(handle(svc, "GET", f"/notes/{note['id']}")[0], 200)
        self.assertEqual(handle(svc, "DELETE", f"/notes/{note['id']}")[0], 204)
        self.assertEqual(handle(svc, "GET", f"/notes/{note['id']}")[0], 404)

    def test_errors(self):
        svc = seeded(1)
        self.assertEqual(handle(svc, "GET", "/notes", {"limit": "abc"})[0], 400)
        self.assertEqual(handle(svc, "GET", "/notes", {"limit": "500"})[0], 400)
        self.assertEqual(handle(svc, "POST", "/notes", body={})[0], 400)
        self.assertEqual(handle(svc, "PUT", "/notes")[0], 405)
        self.assertEqual(handle(svc, "GET", "/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
