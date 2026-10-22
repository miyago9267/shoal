import unittest

from ops import exporter


class ExporterTest(unittest.TestCase):
    def test_skips_empty(self):
        out = {}
        n = exporter.export_all(
            {"a": "xx", "b": "", "c": "y"}, lambda name, text: out.setdefault(name, len(text))
        )
        self.assertEqual(n, 2)
        self.assertEqual(out, {"a": 2, "c": 1})

    def test_manifest(self):
        self.assertEqual(exporter.manifest({"b": "1", "a": "22"}), [("a", 2), ("b", 1)])
