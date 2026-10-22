import unittest

from fmtkit import checksum, frame, sample
from fmtkit.errors import ParseError


class FrameTest(unittest.TestCase):
    def test_roundtrip(self):
        parts = [b"abc", b"", b"\x00" * 300]
        self.assertEqual(frame.unpack(frame.pack(parts)), parts)
        self.assertEqual(frame.sizes(frame.pack(parts)), [3, 0, 300])

    def test_errors(self):
        good = frame.pack([b"abc", b"de"])
        for blob in (b"", b"\x00", good[:-1], good[:4], good + b"x"):
            with self.assertRaises(ParseError, msg=repr(blob)):
                frame.unpack(blob)

    def test_parse_all(self):
        blob = frame.pack([sample.kv_sample(), sample.pascal_sample()])
        kv_part, pascal_part = frame.parse_all(blob, ["kv", "pascal"])
        self.assertEqual(kv_part["mode"], "fast")
        self.assertEqual(pascal_part[-1], "blue")

    def test_parse_all_count_mismatch(self):
        with self.assertRaises(ParseError):
            frame.parse_all(frame.pack([b"a"]), ["kv", "kv"])


class ChecksumTest(unittest.TestCase):
    def test_xor8(self):
        self.assertEqual(checksum.xor8(b"\x01\x02\x03"), 0)
        self.assertEqual(checksum.xor8(b"\xff"), 0xFF)

    def test_crc_adler_known_values(self):
        self.assertEqual(checksum.crc(b"123456789"), 0xCBF43926)
        self.assertEqual(checksum.adler(b"Wikipedia"), 0x11E60398)

    def test_fingerprint(self):
        fp = checksum.fingerprint(b"123456789")
        self.assertEqual(fp, "cbf43926-31-9")
        self.assertTrue(checksum.verify(b"123456789", fp))
        self.assertFalse(checksum.verify(b"123456780", fp))

    def test_same(self):
        self.assertTrue(checksum.same(b"ab", b"ab"))
        self.assertFalse(checksum.same(b"ab", b"ac"))
