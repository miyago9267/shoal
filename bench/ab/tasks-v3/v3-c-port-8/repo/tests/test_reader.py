import unittest

from fmtkit.reader import Reader, ReaderError
from fmtkit.reader_v2 import Cursor, Truncated


class OldReaderTest(unittest.TestCase):
    def test_ints_and_short_reads(self):
        r = Reader(b"\x01\x02\x03\x04\x05")
        self.assertEqual(r.u8(), 1)
        self.assertEqual(r.u16(), 0x0203)
        self.assertEqual(r.read(10), b"\x04\x05")
        self.assertTrue(r.at_end())
        with self.assertRaises(ReaderError):
            r.u8()

    def test_until(self):
        r = Reader(b"ab;cd")
        self.assertEqual(r.until(b";"), b"ab")
        self.assertEqual(r.until(b";"), b"cd")


class CursorTest(unittest.TestCase):
    def test_endian(self):
        self.assertEqual(Cursor(b"\x01\x02").uint(2), 0x0201)
        self.assertEqual(Cursor(b"\x01\x02", endian="big").uint(2), 0x0102)

    def test_exact_vs_upto(self):
        c = Cursor(b"abc")
        self.assertEqual(c.take_upto(5), b"abc")
        with self.assertRaises(Truncated):
            Cursor(b"abc").take(5)
        self.assertEqual(Cursor(b"abc").remaining, 3)

    def test_take_until(self):
        c = Cursor(b"ab;cd")
        self.assertEqual(c.take_until(b";"), b"ab")
        with self.assertRaises(Truncated):
            c.take_until(b";")
        self.assertEqual(c.take_until(b";", require=False), b"cd")
        self.assertTrue(c.done())

    def test_advance_and_peek(self):
        c = Cursor(b"abc")
        self.assertEqual(c.peek(2), b"ab")
        c.advance(3)
        self.assertEqual(c.peek(), b"")
        with self.assertRaises(Truncated):
            c.advance(1)

    def test_text_encoding(self):
        self.assertEqual(Cursor(b"caf\xc3\xa9").text(5), "caf\u00e9")
        self.assertEqual(Cursor(b"caf\xe9").text(4, "latin-1"), "caf\u00e9")
