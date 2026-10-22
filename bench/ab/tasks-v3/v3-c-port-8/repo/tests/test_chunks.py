import unittest

from fmtkit import chunks
from fmtkit.errors import ParseError


class ChunksTest(unittest.TestCase):
    def test_parse(self):
        data = chunks.chunk(b"DATA", b"xyz") + chunks.chunk(b"END ")
        got = chunks.parse(data)
        self.assertEqual(chunks.tags(got), [b"DATA", b"END "])

    def test_missing_end(self):
        with self.assertRaises(ParseError):
            chunks.parse(chunks.chunk(b"DATA", b"xyz"))

    def test_bad_crc(self):
        data = bytearray(chunks.chunk(b"END "))
        data[-1] ^= 1
        with self.assertRaises(ParseError):
            chunks.parse(bytes(data))
