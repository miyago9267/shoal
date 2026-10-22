import unittest

from ops import billing


class BillingTest(unittest.TestCase):
    def acct(self):
        return {"id": "a1", "balance": 0, "limit": 5000}

    def test_charge_ok(self):
        a = self.acct()
        self.assertTrue(billing.charge(a, 1250))
        self.assertEqual(a["balance"], 1250)

    def test_charge_over_limit(self):
        a = self.acct()
        self.assertFalse(billing.charge(a, 9000))
        self.assertEqual(a["balance"], 0)

    def test_charge_zero(self):
        self.assertFalse(billing.charge(self.acct(), 0))

    def test_refund_capped(self):
        a = self.acct()
        billing.charge(a, 100)
        self.assertEqual(billing.refund(a, 500), 100)

    def test_statement(self):
        a = self.acct()
        billing.charge(a, 1205)
        self.assertEqual(billing.statement([a]), ["a1 12.05"])
