import unittest

from fmtkit import bitmap
from fmtkit.errors import ParseError


class BitmapTest(unittest.TestCase):
    def test_parse(self):
        got = bitmap.parse(b"\x00\x02\x00\x02\x01\x02\x03\x04")
        self.assertEqual(got["pixels"], b"\x01\x02\x03\x04")
        self.assertEqual(bitmap.row(got, 1), b"\x03\x04")

    def test_histogram(self):
        got = bitmap.parse(b"\x00\x02\x00\x01\x07\x07")
        self.assertEqual(bitmap.histogram(got), {7: 2})

    def test_header_cut(self):
        with self.assertRaises(ParseError):
            bitmap.parse(b"\x00\x02\x00")
