import unittest

from fmtkit import describe, registry


class RegistryTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(len(registry.names()), 8)

    def test_parse_by_name(self):
        self.assertEqual(registry.parse("cstrings", b"a\0b\0"), ["a", "b"])

    def test_summarize(self):
        self.assertEqual(describe.summarize("cstrings", b"a\0"), "cstrings: 1 items")
        self.assertTrue(describe.summarize("tlv", b"\x01").startswith("tlv: error"))

    def test_hexdump(self):
        self.assertIn("61 62", describe.hexdump(b"ab"))
