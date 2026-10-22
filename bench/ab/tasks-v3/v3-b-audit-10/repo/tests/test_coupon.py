import unittest

from hq import router
from hq.errors import ValidationError


class CouponTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(router.dispatch("coupon", {"code": "SAVE10", "percent": 10}), {"code": "SAVE10", "percent": 10, "max_uses": None})

    def test_rejects_0(self):
        with self.assertRaises(ValidationError):
            router.dispatch("coupon", {"code": "save10", "percent": 10})

    def test_rejects_1(self):
        with self.assertRaises(ValidationError):
            router.dispatch("coupon", {"code": "AB", "percent": 10})

    def test_rejects_2(self):
        with self.assertRaises(ValidationError):
            router.dispatch("coupon", {"code": "SAVE10", "percent": 95})

    def test_rejects_3(self):
        with self.assertRaises(ValidationError):
            router.dispatch("coupon", {"code": "SAVE10", "percent": 10, "max_uses": 0})


    def test_not_a_dict(self):
        with self.assertRaises(ValidationError):
            router.dispatch("coupon", [])
