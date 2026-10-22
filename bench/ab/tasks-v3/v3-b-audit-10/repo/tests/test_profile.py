import unittest

from hq import router
from hq.errors import ValidationError


class ProfileTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(router.dispatch("profile", {"name": "Ann", "bio": "hi", "tags": ["Go", "py"]}), {"name": "Ann", "bio": "hi", "tags": ["go", "py"]})

    def test_rejects_0(self):
        with self.assertRaises(ValidationError):
            router.dispatch("profile", {"name": ""})

    def test_rejects_1(self):
        with self.assertRaises(ValidationError):
            router.dispatch("profile", {"name": "A", "tags": ["a", "A"]})

    def test_rejects_2(self):
        with self.assertRaises(ValidationError):
            router.dispatch("profile", {"name": "A", "tags": "x"})

    def test_rejects_3(self):
        with self.assertRaises(ValidationError):
            router.dispatch("profile", {"name": "A", "bio": "x" * 300})


    def test_not_a_dict(self):
        with self.assertRaises(ValidationError):
            router.dispatch("profile", [])
