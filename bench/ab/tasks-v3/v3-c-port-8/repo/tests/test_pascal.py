import unittest

from fmtkit import pascal
from fmtkit.errors import ParseError


class PascalTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(pascal.parse(b"\x00\x02\x01a\x02bc"), ["a", "bc"])

    def test_roundtrip(self):
        self.assertEqual(pascal.parse(pascal.build(["x", "", "caf\u00e9"])), ["x", "", "caf\u00e9"])

    def test_trailing(self):
        with self.assertRaises(ParseError):
            pascal.parse(b"\x00\x01\x01ax")

    def test_cut_short(self):
        with self.assertRaises(ParseError):
            pascal.parse(b"\x00\x01\x05ab")
