import unittest

from utilkit import paths


class PathsSmoke(unittest.TestCase):
    def test_slashes(self):
        self.assertEqual(paths.normalize("a//b///c"), "a/b/c")
        self.assertEqual(paths.normalize("/a//b"), "/a/b")

    def test_is_inside(self):
        self.assertTrue(paths.is_inside("/srv", "/srv/data"))
        self.assertFalse(paths.is_inside("/srv", "/srvx"))
