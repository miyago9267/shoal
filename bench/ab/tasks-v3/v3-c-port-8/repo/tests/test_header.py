import unittest

from fmtkit import header
from fmtkit.errors import ParseError


class HeaderTest(unittest.TestCase):
    def test_parse(self):
        data = header.build(2, 0x0005, b"hello")
        got = header.parse(data)
        self.assertEqual(got, {"version": 2, "flags": 5, "payload": b"hello"})
        self.assertTrue(header.has_flag(got, 0))
        self.assertTrue(header.has_flag(got, 2))
        self.assertFalse(header.has_flag(got, 1))

    def test_bad_magic(self):
        with self.assertRaises(ParseError):
            header.parse(b"XXXX" + bytes(7))

    def test_short_payload(self):
        data = header.build(1, 0, b"hello")[:-2]
        with self.assertRaises(ParseError):
            header.parse(data)
