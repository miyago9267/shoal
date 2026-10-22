import unittest

from deskapi.tokens import TokenRegistry


class TokenTest(unittest.TestCase):
    def setUp(self):
        self.reg = TokenRegistry()
        self.reg.issue("k1", "secret", 7)

    def test_resolve(self):
        self.assertEqual(self.reg.resolve("k1.secret"), 7)
        self.assertIsNone(self.reg.resolve("k1.wrong!"))
        self.assertIsNone(self.reg.resolve("k2.secret"))
        self.assertIsNone(self.reg.resolve("garbage"))
        self.assertIsNone(self.reg.resolve(""))

    def test_revoke(self):
        self.reg.revoke("k1")
        self.assertIsNone(self.reg.resolve("k1.secret"))

    def test_bad_key_id(self):
        with self.assertRaises(ValueError):
            self.reg.issue("a.b", "x", 1)


if __name__ == "__main__":
    unittest.main()
