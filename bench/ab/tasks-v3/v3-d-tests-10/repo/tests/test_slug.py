import unittest

from utilkit import slug


class SlugSmoke(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(slug.slugify("Hello World"), "hello-world")

    def test_is_slug(self):
        self.assertTrue(slug.is_slug("a-b"))
        self.assertFalse(slug.is_slug("-a"))

    def test_unique(self):
        self.assertEqual(slug.unique_slug("a", {"a", "a-2"}), "a-3")
