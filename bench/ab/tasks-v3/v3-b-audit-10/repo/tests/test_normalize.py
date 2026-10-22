import unittest

from hq import normalize


class NormalizeTest(unittest.TestCase):
    def test_squash(self):
        self.assertEqual(normalize.squash_spaces("  a \t b\n c "), "a b c")

    def test_title_case(self):
        self.assertEqual(normalize.title_case("the lord OF the rings"), "The Lord of the Rings")

    def test_ascii_fold(self):
        self.assertEqual(normalize.ascii_fold("caf\u00e9 cr\u00e8me"), "cafe creme")

    def test_initials(self):
        self.assertEqual(normalize.initials("ada  lovelace byron"), "AL")
        self.assertEqual(normalize.initials("ada lovelace byron", 3), "ALB")

    def test_truncate(self):
        self.assertEqual(normalize.truncate("abcdefgh", 6), "abc...")
        self.assertEqual(normalize.truncate("abc", 6), "abc")
        with self.assertRaises(ValueError):
            normalize.truncate("abc", 2)

    def test_mask_email(self):
        self.assertEqual(normalize.mask_email("alice@x.io"), "a***e@x.io")
        self.assertEqual(normalize.mask_email("ab@x.io"), "**@x.io")

    def test_slug(self):
        self.assertEqual(normalize.slug("  Caf\u00e9 & Bar!  "), "cafe-bar")
