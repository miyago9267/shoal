import unittest

from pager.paginate import clamp_page_size, page_bounds, paginate
from pager.links import page_links


class PaginateTest(unittest.TestCase):
    def setUp(self):
        self.items = list(range(45))

    def test_first_page(self):
        p = paginate(self.items, page=1, page_size=20)
        self.assertEqual(p.items, list(range(20)))
        self.assertFalse(p.has_prev)
        self.assertTrue(p.has_next)

    def test_last_partial_page(self):
        p = paginate(self.items, page=3, page_size=20)
        self.assertEqual(p.items, [40, 41, 42, 43, 44])
        self.assertEqual(p.total_pages, 3)
        self.assertFalse(p.has_next)

    def test_bounds(self):
        self.assertEqual(page_bounds(2, 10), (10, 20))

    def test_clamp(self):
        self.assertEqual(clamp_page_size(None), 20)
        self.assertEqual(clamp_page_size(0), 1)
        self.assertEqual(clamp_page_size(500), 100)

    def test_rejects_page_zero(self):
        with self.assertRaises(ValueError):
            paginate(self.items, page=0)

    def test_links(self):
        p = paginate(list(range(115)), page=5, page_size=10)
        self.assertEqual(page_links(p), [1, None, 4, 5, 6, None, 12])


if __name__ == "__main__":
    unittest.main()
