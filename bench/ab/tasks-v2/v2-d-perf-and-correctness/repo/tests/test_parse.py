import unittest

from logpipe.parse import parse, parse_line


class ParseTest(unittest.TestCase):
    def test_line(self):
        e = parse_line("2026-10-01T00:00:10Z req=a1 user=7 status=503 bytes=- path=/x ms=3")
        self.assertEqual((e.ts, e.request_id, e.user_id, e.status, e.bytes),
                         (1790812810, "a1", 7, 503, 0))

    def test_skips_garbage(self):
        events, skipped = parse(["garbage", "", "2026-10-01T00:00:10Z req=a user=x status=1 "
                                 "bytes=1 path=/ ms=1"])
        self.assertEqual((events, skipped), ([], 2))
