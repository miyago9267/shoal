import unittest

from ops import reports


class ReportsTest(unittest.TestCase):
    def test_skips_none(self):
        self.assertEqual(reports.summarize("r", [1, None, 2]), [1, 2])

    def test_head(self):
        self.assertEqual(reports.head("r", [1, 2, 3, 4], 2), [1, 2])

    def test_count_empty(self):
        self.assertEqual(reports.count_empty([None, 1, None]), 2)
