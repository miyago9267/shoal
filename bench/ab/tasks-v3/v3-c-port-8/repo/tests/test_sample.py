import unittest

from fmtkit import registry, sample
from fmtkit.errors import ParseError


class SampleTest(unittest.TestCase):
    def test_every_sample_parses(self):
        for name, make in sample.ALL.items():
            with self.subTest(name):
                registry.parse(name, make())

    def test_expected_shapes(self):
        self.assertEqual(registry.parse("kv", sample.kv_sample())["port"], "8080")
        self.assertEqual(registry.parse("pascal", sample.pascal_sample()), ["red", "green", "blue"])
        self.assertEqual(len(registry.parse("tables", sample.tables_sample())), 3)
        self.assertEqual(len(registry.parse("chunks", sample.chunks_sample())), 3)
        self.assertEqual(registry.parse("tlv", sample.tlv_sample())[0], (1, b"alpha"))
        self.assertEqual(registry.parse("header", sample.header_sample())["flags"], 5)
        bm = registry.parse("bitmap", sample.bitmap_sample(2, 2))
        self.assertEqual(bm["pixels"], bytes([0, 16, 1, 17]))

    def test_cut_strict_formats_fail(self):
        for name in ("chunks", "header", "pascal", "tlv"):
            with self.subTest(name):
                with self.assertRaises(ParseError):
                    registry.parse(name, sample.corrupt(sample.ALL[name](), "cut"))

    def test_cut_tolerant_formats_survive(self):
        for name in ("bitmap", "cstrings", "kv"):
            with self.subTest(name):
                registry.parse(name, sample.corrupt(sample.ALL[name](), "cut"))

    def test_bad_corruption_mode(self):
        with self.assertRaises(ValueError):
            sample.corrupt(b"abc", "melt")
