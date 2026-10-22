import unittest

from utilkit import wrap


class WrapSmoke(unittest.TestCase):
    def test_single_paragraph(self):
        self.assertEqual(wrap.wrap("aaa bbb ccc", 7), "aaa bbb\nccc")

    def test_bad_width(self):
        with self.assertRaises(ValueError):
            wrap.wrap("x", 0)

    def test_indent(self):
        self.assertEqual(wrap.indent("a\n\nb", "> "), "> a\n\n> b")
