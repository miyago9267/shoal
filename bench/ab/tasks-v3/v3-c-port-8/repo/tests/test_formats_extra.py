import unittest

from fmtkit import bitmap, chunks, cstrings, header, kv, pascal, tables, tlv
from fmtkit.errors import ParseError


class TolerantFormatsTest(unittest.TestCase):
    def test_cstrings_consecutive_nuls(self):
        self.assertEqual(cstrings.parse(b"\0\0x"), ["", "", "x"])

    def test_kv_later_keys_win(self):
        self.assertEqual(kv.parse(b"a=1\na=2\n"), {"a": "2"})

    def test_bitmap_padding(self):
        self.assertEqual(bitmap.parse(b"\x00\x02\x00\x01\x05")["pixels"], b"\x05\x00")

    def test_bitmap_too_large(self):
        with self.assertRaises(ParseError):
            bitmap.parse(b"\xff\xff\xff\xff")

    def test_tables_last_reserved_optional(self):
        data = (1).to_bytes(4, "big") + b"\x00\x09\x01\x01z"
        self.assertEqual(tables.parse(data), [{"id": 9, "flag": 1, "name": "z"}])


class StrictFormatsTest(unittest.TestCase):
    def test_tlv_zero_records(self):
        self.assertEqual(tlv.parse(b""), [])

    def test_header_extra_ignored(self):
        self.assertEqual(header.parse(header.build(1, 0, b"a") + b"zz")["payload"], b"a")

    def test_pascal_empty(self):
        self.assertEqual(pascal.parse(b"\x00\x00"), [])

    def test_chunks_end_only(self):
        self.assertEqual(chunks.parse(chunks.chunk(b"END ")), [(b"END ", b"")])

    def test_chunks_stops_at_end(self):
        data = chunks.chunk(b"END ") + b"\xff\xff"
        self.assertEqual(len(chunks.parse(data)), 1)
