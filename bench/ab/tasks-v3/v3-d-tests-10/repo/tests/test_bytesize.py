import unittest

from utilkit import bytesize


class BytesizeSmoke(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(bytesize.parse_size("2 KiB"), 2048)
        self.assertEqual(bytesize.parse_size("512"), 512)

    def test_total(self):
        self.assertEqual(bytesize.total([1, 2, 3]), 6)
        self.assertEqual(bytesize.biggest([]), 0)
