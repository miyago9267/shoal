import unittest

from fmtkit.reader import Reader, ReaderError
from fmtkit.reader_v2 import Cursor, Truncated


class OldReaderEdges(unittest.TestCase):
    def test_peek_returns_int_or_none(self):
        r = Reader(b"\x07")
        self.assertEqual(r.peek(), 7)
        r.read(1)
        self.assertIsNone(r.peek())

    def test_skip_clamps(self):
        r = Reader(b"abc")
        r.skip(10)
        self.assertTrue(r.at_end())
        self.assertEqual(r.tell(), 3)

    def test_failed_int_does_not_consume(self):
        r = Reader(b"\x01")
        with self.assertRaises(ReaderError):
            r.u16()
        self.assertEqual(r.tell(), 0)
        self.assertEqual(r.u8(), 1)

    def test_string_is_latin1_and_short_ok(self):
        r = Reader(b"caf\xe9")
        self.assertEqual(r.string(9), "caf\u00e9")

    def test_until_missing_returns_rest(self):
        r = Reader(b"abc")
        self.assertEqual(r.until(b"|"), b"abc")
        self.assertTrue(r.at_end())

    def test_until_multibyte_delimiter(self):
        r = Reader(b"a--b--c")
        self.assertEqual(r.until(b"--"), b"a")
        self.assertEqual(r.until(b"--"), b"b")
        self.assertEqual(r.until(b"--"), b"c")


class CursorEdges(unittest.TestCase):
    def test_failed_exact_read_does_not_consume(self):
        c = Cursor(b"\x01")
        with self.assertRaises(Truncated):
            c.uint(2)
        self.assertEqual(c.offset, 0)
        self.assertEqual(c.uint(1), 1)

    def test_bad_arguments(self):
        with self.assertRaises(ValueError):
            Cursor(b"", endian="middle")
        with self.assertRaises(ValueError):
            Cursor(b"abc").uint(3)
        with self.assertRaises(Truncated):
            Cursor(b"abc").take(-1)

    def test_take_until_multibyte(self):
        c = Cursor(b"a--b")
        self.assertEqual(c.take_until(b"--"), b"a")
        self.assertEqual(c.take_until(b"--", require=False), b"b")

    def test_remaining_tracks_offset(self):
        c = Cursor(b"abcdef")
        c.take(2)
        self.assertEqual((c.offset, c.remaining), (2, 4))
        c.take_upto(10)
        self.assertEqual((c.offset, c.remaining), (6, 0))
        self.assertTrue(c.done())
