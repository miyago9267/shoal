import unittest

from fmtkit import cstrings


class CstringsTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(cstrings.parse(b"ab\0cd\0"), ["ab", "cd"])

    def test_empty_input(self):
        self.assertEqual(cstrings.parse(b""), [])

    def test_latin1(self):
        self.assertEqual(cstrings.parse(b"caf\xe9\0"), ["caf\u00e9"])

    def test_roundtrip(self):
        self.assertEqual(cstrings.parse(cstrings.join(["a", "", "b"])), ["a", "", "b"])
