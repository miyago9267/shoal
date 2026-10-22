import unittest

from hq import router
from hq.errors import ValidationError


class SignupTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(router.dispatch("signup", {"email": "Ann@Example.com ", "age": 30, "name": " Ann "}), {"email": "ann@example.com", "age": 30, "name": "Ann"})

    def test_rejects_0(self):
        with self.assertRaises(ValidationError):
            router.dispatch("signup", {"email": "nope", "age": 30, "name": "A"})

    def test_rejects_1(self):
        with self.assertRaises(ValidationError):
            router.dispatch("signup", {"email": "a@b.co", "age": 5, "name": "A"})

    def test_rejects_2(self):
        with self.assertRaises(ValidationError):
            router.dispatch("signup", {"email": "a@b.co", "age": 30, "name": ""})

    def test_rejects_3(self):
        with self.assertRaises(ValidationError):
            router.dispatch("signup", {"age": 30, "name": "A"})


    def test_not_a_dict(self):
        with self.assertRaises(ValidationError):
            router.dispatch("signup", [])
