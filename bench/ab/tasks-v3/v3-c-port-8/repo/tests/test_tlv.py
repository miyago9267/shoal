import unittest

from fmtkit import tlv
from fmtkit.errors import ParseError


class TlvTest(unittest.TestCase):
    def test_parse(self):
        data = b"\x01\x00\x02ab\x02\x00\x00"
        self.assertEqual(tlv.parse(data), [(1, b"ab"), (2, b"")])

    def test_roundtrip(self):
        items = [(7, b"xyz"), (9, b"")]
        self.assertEqual(tlv.parse(tlv.dump(items)), items)

    def test_find(self):
        self.assertEqual(tlv.find([(1, b"a"), (2, b"b"), (1, b"c")], 1), [b"a", b"c"])

    def test_truncated(self):
        with self.assertRaises(ParseError):
            tlv.parse(b"\x01\x00\x05ab")
        with self.assertRaises(ParseError):
            tlv.parse(b"\x01\x00")
