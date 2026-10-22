import unittest

from ops import importer


class ImporterTest(unittest.TestCase):
    def test_good_rows(self):
        rows = importer.parse_rows(["a,1,2.5", "b,2,1.0"])
        self.assertEqual(importer.total_value(rows), 4.5)

    def test_bad_rows_skipped(self):
        rows = importer.parse_rows(["a,1", "b,x,1", "c,1,1"])
        self.assertEqual([r["name"] for r in rows], ["c"])

    def test_split_lines(self):
        self.assertEqual(importer.split_lines("a\n\nb\n"), ["a", "b"])
