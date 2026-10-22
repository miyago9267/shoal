import unittest

from hq import router
from hq.errors import ValidationError


class TransferTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(router.dispatch("transfer", {"src": "a", "dst": "b", "amount_cents": 1250}), {"src": "a", "dst": "b", "amount_cents": 1250, "fee_cents": 12})

    def test_rejects_0(self):
        with self.assertRaises(ValidationError):
            router.dispatch("transfer", {"src": "a", "dst": "a", "amount_cents": 5})

    def test_rejects_1(self):
        with self.assertRaises(ValidationError):
            router.dispatch("transfer", {"src": "a", "dst": "b", "amount_cents": 0})

    def test_rejects_2(self):
        with self.assertRaises(ValidationError):
            router.dispatch("transfer", {"src": "a", "dst": "b", "amount_cents": "5"})

    def test_rejects_3(self):
        with self.assertRaises(ValidationError):
            router.dispatch("transfer", {"src": "", "dst": "b", "amount_cents": 5})


    def test_not_a_dict(self):
        with self.assertRaises(ValidationError):
            router.dispatch("transfer", [])
