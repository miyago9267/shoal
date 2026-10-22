import unittest

from fmtkit import kv
from fmtkit.errors import ParseError


class KvTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(kv.parse(b"a=1\nb = two \n"), {"a": "1", "b": "two"})

    def test_blank_lines(self):
        self.assertEqual(kv.parse(b"\n\na=1\n\n"), {"a": "1"})

    def test_missing_equals(self):
        with self.assertRaises(ParseError):
            kv.parse(b"a=1\nnope\n")

    def test_render(self):
        self.assertEqual(kv.parse(kv.render({"x": "y", "z": "w"})), {"x": "y", "z": "w"})
