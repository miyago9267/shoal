import unittest

from utilkit import ranges


class RangesSmoke(unittest.TestCase):
    def test_overlap_merges(self):
        self.assertEqual([tuple(r) for r in ranges.merge_ranges([(1, 5), (3, 9)])], [(1, 9)])

    def test_disjoint_stay(self):
        self.assertEqual([tuple(r) for r in ranges.merge_ranges([(1, 2), (10, 12)])], [(1, 2), (10, 12)])

    def test_contains(self):
        self.assertTrue(ranges.contains([(1, 2), (5, 6)], 5))
        self.assertFalse(ranges.contains([(1, 2)], 3))
