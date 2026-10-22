import os
import shutil
import tempfile
import unittest

from filesrv import serve_file


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class ServeFileTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        write(os.path.join(self.root, "index.html"), b"<h1>home</h1>")
        write(os.path.join(self.root, "style.css"), b"body{}")
        write(os.path.join(self.root, "docs", "guide", "intro.txt"), b"intro")
        write(os.path.join(self.root, "my notes.txt"), b"notes")
        write(os.path.join(self.root, "blob.unknownext"), b"\x00\x01")

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_root_serves_index(self):
        resp = serve_file(self.root, "/")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.body, b"<h1>home</h1>")
        self.assertTrue(resp.content_type.startswith("text/html"))

    def test_nested_file(self):
        resp = serve_file(self.root, "/docs/guide/intro.txt")
        self.assertEqual((resp.status, resp.body), (200, b"intro"))

    def test_query_string_ignored(self):
        resp = serve_file(self.root, "/style.css?v=3")
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.content_type.startswith("text/css"))

    def test_percent_encoded_name(self):
        resp = serve_file(self.root, "/my%20notes.txt")
        self.assertEqual((resp.status, resp.body), (200, b"notes"))

    def test_unknown_type(self):
        resp = serve_file(self.root, "blob.unknownext")
        self.assertEqual(resp.content_type, "application/octet-stream")

    def test_missing_file(self):
        self.assertEqual(serve_file(self.root, "/nope.txt").status, 404)

    def test_method_not_allowed(self):
        self.assertEqual(serve_file(self.root, "/", method="POST").status, 405)

    def test_head_has_no_body(self):
        resp = serve_file(self.root, "/style.css", method="HEAD")
        self.assertEqual((resp.status, resp.body), (200, b""))
        self.assertEqual(resp.headers["Content-Length"], "6")


if __name__ == "__main__":
    unittest.main()
