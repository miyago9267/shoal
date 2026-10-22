import unittest

from hq import router
from hq.errors import ValidationError


class RatingTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(router.dispatch("rating", {"item_id": 7, "stars": 5, "comment": " great "}), {"item_id": 7, "stars": 5, "comment": "great"})

    def test_rejects_0(self):
        with self.assertRaises(ValidationError):
            router.dispatch("rating", {"item_id": 0, "stars": 5})

    def test_rejects_1(self):
        with self.assertRaises(ValidationError):
            router.dispatch("rating", {"item_id": 1, "stars": 6})

    def test_rejects_2(self):
        with self.assertRaises(ValidationError):
            router.dispatch("rating", {"item_id": 1, "stars": 3, "comment": 5})

    def test_rejects_3(self):
        with self.assertRaises(ValidationError):
            router.dispatch("rating", {"stars": 3})


    def test_not_a_dict(self):
        with self.assertRaises(ValidationError):
            router.dispatch("rating", [])
