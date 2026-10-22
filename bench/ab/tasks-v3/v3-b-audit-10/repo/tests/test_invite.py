import unittest

from hq import router
from hq.errors import ValidationError


class InviteTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(router.dispatch("invite", {"emails": ["A@x.io", "a@x.io", "b@x.io"], "role": "editor"}), {"emails": ["a@x.io", "b@x.io"], "role": "editor"})

    def test_rejects_0(self):
        with self.assertRaises(ValidationError):
            router.dispatch("invite", {"emails": []})

    def test_rejects_1(self):
        with self.assertRaises(ValidationError):
            router.dispatch("invite", {"emails": ["bad"]})

    def test_rejects_2(self):
        with self.assertRaises(ValidationError):
            router.dispatch("invite", {"emails": ["a@x.io"], "role": "root"})

    def test_rejects_3(self):
        with self.assertRaises(ValidationError):
            router.dispatch("invite", {"emails": "a@x.io"})


    def test_not_a_dict(self):
        with self.assertRaises(ValidationError):
            router.dispatch("invite", [])
