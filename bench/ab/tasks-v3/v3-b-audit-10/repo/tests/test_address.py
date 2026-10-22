import unittest

from hq import router
from hq.errors import ValidationError


class AddressTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(router.dispatch("address", {"line1": "1 Main", "city": "NYC", "country": "US", "zip": "10001"}), {"line1": "1 Main", "city": "NYC", "country": "US", "zip": "10001"})

    def test_rejects_0(self):
        with self.assertRaises(ValidationError):
            router.dispatch("address", {"line1": "1 Main", "city": "NYC", "country": "US", "zip": "1000"})

    def test_rejects_1(self):
        with self.assertRaises(ValidationError):
            router.dispatch("address", {"line1": "1 Main", "city": "NYC", "country": "FR", "zip": "10001"})

    def test_rejects_2(self):
        with self.assertRaises(ValidationError):
            router.dispatch("address", {"line1": "", "city": "NYC", "country": "US", "zip": "10001"})

    def test_rejects_3(self):
        with self.assertRaises(ValidationError):
            router.dispatch("address", {"line1": "1", "city": "NYC", "country": "JP", "zip": "1234567"})


    def test_not_a_dict(self):
        with self.assertRaises(ValidationError):
            router.dispatch("address", [])
