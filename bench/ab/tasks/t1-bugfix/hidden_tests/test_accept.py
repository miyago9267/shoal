import unittest

from pager.paginate import page_count, paginate
from pager.links import page_links


class AcceptTest(unittest.TestCase):
    def test_exact_multiple_page_count(self):
        self.assertEqual(page_count(40, 20), 2)
        self.assertEqual(page_count(100, 10), 10)
        self.assertEqual(page_count(20, 20), 1)

    def test_partial_and_small_counts(self):
        self.assertEqual(page_count(41, 20), 3)
        self.assertEqual(page_count(1, 20), 1)
        self.assertEqual(page_count(0, 20), 0)

    def test_last_full_page_has_no_next(self):
        p = paginate(list(range(40)), page=2, page_size=20)
        self.assertEqual(p.items, list(range(20, 40)))
        self.assertEqual(p.total_pages, 2)
        self.assertFalse(p.has_next)
        self.assertTrue(p.has_prev)

    def test_single_full_page(self):
        p = paginate(list(range(20)), page=1, page_size=20)
        self.assertEqual(p.total_pages, 1)
        self.assertFalse(p.has_next)

    def test_links_exact_multiple(self):
        p = paginate(list(range(120)), page=12, page_size=10)
        self.assertEqual(page_links(p), [1, None, 11, 12])

    def test_partial_page_unchanged(self):
        p = paginate(list(range(45)), page=3, page_size=20)
        self.assertEqual(p.total_pages, 3)
        self.assertEqual(p.items, [40, 41, 42, 43, 44])


if __name__ == "__main__":
    unittest.main()
