import unittest

from fmtkit import describe, sample


class DescribeTest(unittest.TestCase):
    def test_object_summary(self):
        self.assertEqual(
            describe.summarize("header", sample.header_sample()),
            "header: object with flags,payload,version",
        )

    def test_list_summary(self):
        self.assertEqual(describe.summarize("tlv", sample.tlv_sample()), "tlv: 3 items")
        self.assertEqual(describe.summarize("chunks", sample.chunks_sample()), "chunks: 3 items")

    def test_error_summary(self):
        text = describe.summarize("pascal", b"\x00\x01")
        self.assertTrue(text.startswith("pascal: error: "), text)

    def test_hexdump_layout(self):
        dump = describe.hexdump(bytes(range(32, 52)), width=16)
        lines = dump.split("\n")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("00000000  20 21 22"))
        self.assertTrue(lines[0].endswith(' !"#$%&\'()*+,-./'))
        self.assertTrue(lines[1].startswith("00000010  30 31 32 33"))

    def test_hexdump_empty(self):
        self.assertEqual(describe.hexdump(b""), "")
