import unittest

from hq import router
from hq.errors import ValidationError


class SearchTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(router.dispatch("search", {"query": " shoes "}), {"query": "shoes", "limit": 20, "offset": 0})

    def test_rejects_0(self):
        with self.assertRaises(ValidationError):
            router.dispatch("search", {"query": ""})

    def test_rejects_1(self):
        with self.assertRaises(ValidationError):
            router.dispatch("search", {"query": "x", "limit": 0})

    def test_rejects_2(self):
        with self.assertRaises(ValidationError):
            router.dispatch("search", {"query": "x", "offset": -1})

    def test_rejects_3(self):
        with self.assertRaises(ValidationError):
            router.dispatch("search", {"query": 5})


    def test_not_a_dict(self):
        with self.assertRaises(ValidationError):
            router.dispatch("search", [])
