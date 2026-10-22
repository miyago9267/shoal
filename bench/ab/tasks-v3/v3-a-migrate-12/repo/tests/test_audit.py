import unittest

from ops import audit
from ops.cache import Cache


class AuditTest(unittest.TestCase):
    def test_accounts(self):
        accts = [
            {"id": "a", "balance": -1, "limit": 5},
            {"id": "a", "balance": 9, "limit": 5},
            {"balance": 0, "limit": 5},
        ]
        self.assertEqual(
            audit.check_accounts(accts),
            [
                "negative balance on a",
                "duplicate account a",
                "a is over its limit",
                "account without id",
            ],
        )

    def test_stock(self):
        self.assertEqual(
            audit.check_stock({"a": -1, "b": 1.5, "c": 3}),
            ["a: negative quantity", "b: quantity is not an int"],
        )

    def test_jobs_unknown_and_cycle(self):
        jobs = [
            {"name": "a", "after": ["b"]},
            {"name": "b", "after": ["a"]},
            {"name": "c", "after": ["zzz"]},
        ]
        problems = audit.check_jobs(jobs)
        self.assertIn("c depends on unknown job zzz", problems)
        self.assertIn("cycle: a -> b -> a", problems)

    def test_cache(self):
        c = Cache(1)
        self.assertEqual(audit.check_cache(c), [])
        c.capacity = 0
        c._data["x"] = 1
        self.assertEqual(audit.check_cache(c), ["cache over capacity"])

    def test_report(self):
        text = audit.report(("accounts", ["x"]), ("stock", []))
        self.assertEqual(text, "accounts\n  - x")
