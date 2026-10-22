import sys
import unittest

# The old reader is retired: importing it must fail for every parser.
sys.modules["fmtkit.reader"] = None

from fmtkit import (  # noqa: E402
    bitmap, chunks, cstrings, header, kv, pascal, tables, tlv,
)
from fmtkit.errors import ParseError  # noqa: E402


def row(ident, flag, name, reserved=b"\x00\x00"):
    return ident.to_bytes(2, "big") + bytes([flag, len(name)]) + name + reserved


class TestTlv(unittest.TestCase):
    def test_big_endian_length(self):
        self.assertEqual(tlv.parse(b"\x05\x00\x03abc\x06\x00\x00"), [(5, b"abc"), (6, b"")])
        data = b"\x01\x01\x00" + b"x" * 256
        self.assertEqual(tlv.parse(data), [(1, b"x" * 256)])

    def test_empty(self):
        self.assertEqual(tlv.parse(b""), [])

    def test_truncated(self):
        for data in (b"\x01", b"\x01\x00", b"\x01\x00\x03ab", b"\x01\x00\x01a\x02"):
            with self.assertRaises(ParseError, msg=repr(data)):
                tlv.parse(data)


class TestCstrings(unittest.TestCase):
    def test_terminated_and_trailing(self):
        self.assertEqual(cstrings.parse(b"ab\0cd\0"), ["ab", "cd"])
        self.assertEqual(cstrings.parse(b"ab\0cd"), ["ab", "cd"])

    def test_empty_strings(self):
        self.assertEqual(cstrings.parse(b"\0\0a\0"), ["", "", "a"])

    def test_latin1_high_bytes(self):
        self.assertEqual(cstrings.parse(b"caf\xe9\0\xff\xfe"), ["caf\u00e9", "\u00ff\u00fe"])

    def test_nothing(self):
        self.assertEqual(cstrings.parse(b""), [])


class TestHeader(unittest.TestCase):
    def test_big_endian_fields(self):
        data = b"FMT1" + b"\x03" + b"\x01\x02" + b"\x00\x00\x00\x02" + b"hi"
        self.assertEqual(header.parse(data), {"version": 3, "flags": 0x0102, "payload": b"hi"})

    def test_extra_bytes_ignored(self):
        data = header.build(1, 0, b"ab") + b"junk"
        self.assertEqual(header.parse(data)["payload"], b"ab")

    def test_errors(self):
        good = header.build(1, 7, b"abc")
        for data in (b"", b"FMT", b"FMX1" + good[4:], good[:5], good[:8], good[:-1]):
            with self.assertRaises(ParseError, msg=repr(data)):
                header.parse(data)


class TestKv(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(kv.parse(b"a=1\r\nb = x=y \n\nc="), {"a": "1", "b": "x=y", "c": ""})

    def test_unterminated_last_line(self):
        self.assertEqual(kv.parse(b"a=1\nb=2"), {"a": "1", "b": "2"})

    def test_latin1(self):
        self.assertEqual(kv.parse(b"name=caf\xe9\n"), {"name": "caf\u00e9"})

    def test_bad_line(self):
        with self.assertRaises(ParseError):
            kv.parse(b"a=1\nbroken")

    def test_empty(self):
        self.assertEqual(kv.parse(b""), {})


class TestPascal(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(pascal.parse(b"\x00\x03\x01a\x00\x02\xe9z"), ["a", "", "\u00e9z"])
        self.assertEqual(pascal.parse(b"\x00\x00"), [])

    def test_errors(self):
        for data in (b"", b"\x00", b"\x00\x01", b"\x00\x01\x03ab", b"\x00\x02\x01a", b"\x00\x01\x01ab"):
            with self.assertRaises(ParseError, msg=repr(data)):
                pascal.parse(data)


class TestBitmap(unittest.TestCase):
    def test_full(self):
        self.assertEqual(
            bitmap.parse(b"\x00\x03\x00\x02" + bytes(range(1, 7))),
            {"width": 3, "height": 2, "pixels": bytes(range(1, 7))},
        )

    def test_short_block_is_zero_padded(self):
        self.assertEqual(
            bitmap.parse(b"\x00\x02\x00\x02\x09\x08"),
            {"width": 2, "height": 2, "pixels": b"\x09\x08\x00\x00"},
        )
        self.assertEqual(bitmap.parse(b"\x00\x02\x00\x02")["pixels"], bytes(4))

    def test_extra_ignored(self):
        self.assertEqual(bitmap.parse(b"\x00\x01\x00\x01\x05\x06\x07")["pixels"], b"\x05")

    def test_header_errors(self):
        for data in (b"", b"\x00\x02", b"\x00\x02\x00"):
            with self.assertRaises(ParseError, msg=repr(data)):
                bitmap.parse(data)
        with self.assertRaises(ParseError):
            bitmap.parse(b"\xff\xff\xff\xff")


class TestTables(unittest.TestCase):
    def test_parse(self):
        data = (2).to_bytes(4, "big") + row(258, 1, b"caf\xe9") + row(3, 0, b"")
        self.assertEqual(
            tables.parse(data),
            [{"id": 258, "flag": 1, "name": "caf\u00e9"}, {"id": 3, "flag": 0, "name": ""}],
        )

    def test_last_row_reserved_bytes_optional(self):
        base = (1).to_bytes(4, "big")
        want = [{"id": 1, "flag": 0, "name": "ab"}]
        self.assertEqual(tables.parse(base + row(1, 0, b"ab", b"")), want)
        self.assertEqual(tables.parse(base + row(1, 0, b"ab", b"\x00")), want)

    def test_errors(self):
        base = (2).to_bytes(4, "big")
        for data in (b"", b"\x00\x00", base, base + row(1, 0, b"a"), base + row(1, 0, b"a")[:3],
                     (1).to_bytes(4, "big") + b"\x00\x01\x00\x05ab"):
            with self.assertRaises(ParseError, msg=repr(data)):
                tables.parse(data)

    def test_zero_rows(self):
        self.assertEqual(tables.parse(bytes(4)), [])


class TestChunks(unittest.TestCase):
    def test_parse_and_ignore_after_end(self):
        data = chunks.chunk(b"DATA", b"xyz") + chunks.chunk(b"END ") + b"garbage"
        self.assertEqual(chunks.parse(data), [(b"DATA", b"xyz"), (b"END ", b"")])

    def test_only_end(self):
        self.assertEqual(chunks.parse(chunks.chunk(b"END ", b"zz")), [(b"END ", b"zz")])

    def test_errors(self):
        good = chunks.chunk(b"DATA", b"xyz") + chunks.chunk(b"END ")
        flipped = bytearray(good)
        flipped[8] ^= 0xFF
        cases = [b"", chunks.chunk(b"DATA", b"xyz"), good[:5], good[:10], good[:15], good[:-1], bytes(flipped)]
        for data in cases:
            with self.assertRaises(ParseError, msg=repr(data)):
                chunks.parse(data)


if __name__ == "__main__":
    unittest.main()
