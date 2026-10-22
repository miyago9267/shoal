import unittest

from ops import authn


class AuthnTest(unittest.TestCase):
    users = {"ann": "pw", "root": "pw"}

    def test_ok(self):
        self.assertTrue(authn.login("ann", "pw", self.users))

    def test_bad_password(self):
        self.assertFalse(authn.login("ann", "no", self.users))

    def test_unknown(self):
        self.assertFalse(authn.login("zed", "pw", self.users))

    def test_locked(self):
        self.assertFalse(authn.login("root", "pw", self.users))
