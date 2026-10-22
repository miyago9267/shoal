import os
import shutil
import tempfile
import unittest

from filesrv import serve_file

SECRET = b"TOP-SECRET-TOKEN-5f2c"


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class PathTraversalAcceptance(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.root = os.path.join(self.base, "public")
        write(os.path.join(self.root, "index.html"), b"home")
        write(os.path.join(self.root, "docs", "index.html"), b"docs home")
        write(os.path.join(self.root, "docs", "guide", "intro.txt"), b"intro")
        write(os.path.join(self.root, "v1..2.txt"), b"version notes")
        write(os.path.join(self.base, "secret.txt"), SECRET)
        write(os.path.join(self.base, "public_private", "key.txt"), SECRET)

    def tearDown(self):
        shutil.rmtree(self.base)

    def assertBlocked(self, request, root=None):
        resp = serve_file(root or self.root, request)
        self.assertIn(resp.status, (403, 404), request)
        self.assertNotIn(SECRET, resp.body, request)

    def assertServed(self, request, body, root=None):
        resp = serve_file(root or self.root, request)
        self.assertEqual((resp.status, resp.body), (200, body), request)

    def test_dotdot_segments_blocked(self):
        for req in ("../secret.txt", "/../secret.txt", "./../secret.txt",
                    "docs/../../secret.txt", "/docs/guide/../../../secret.txt",
                    "../secret.txt?download=1"):
            self.assertBlocked(req)

    def test_percent_encoded_traversal_blocked(self):
        for req in ("%2e%2e/secret.txt", "..%2fsecret.txt", "%2E%2E%2Fsecret.txt",
                    "/docs/%2e%2e/%2e%2e/secret.txt"):
            self.assertBlocked(req)

    def test_sibling_directory_with_same_prefix_blocked(self):
        self.assertBlocked("../public_private/key.txt")
        self.assertBlocked("/%2e%2e/public_private/key.txt")

    def test_root_with_trailing_separator(self):
        root = self.root + os.sep
        self.assertBlocked("../secret.txt", root=root)
        self.assertServed("docs/guide/intro.txt", b"intro", root=root)

    def test_legitimate_paths_still_served(self):
        self.assertServed("/", b"home")
        self.assertServed("/docs/", b"docs home")
        self.assertServed("docs/guide/intro.txt", b"intro")
        self.assertServed("/docs/guide/intro.txt", b"intro")
        self.assertServed("/docs/guide/../guide/intro.txt", b"intro")
        self.assertServed("/v1..2.txt", b"version notes")

    def test_missing_file_still_404(self):
        self.assertEqual(serve_file(self.root, "/docs/missing.txt").status, 404)


if __name__ == "__main__":
    unittest.main()
