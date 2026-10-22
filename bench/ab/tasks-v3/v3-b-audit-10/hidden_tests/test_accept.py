import unittest

from hq import router
from hq.errors import ValidationError


class Base(unittest.TestCase):
    def ok(self, name, payload, want=None):
        got = router.dispatch(name, payload)
        if want is not None:
            self.assertEqual(got, want)
        return got

    def bad(self, name, payload, field):
        with self.assertRaises(ValidationError, msg=repr(payload)) as ctx:
            router.dispatch(name, payload)
        self.assertEqual(ctx.exception.field, field, repr(payload))


class TestSignup(Base):  # seeded: weak email check
    def test_good(self):
        self.ok("signup", {"email": "A.b+c@Mail.Example.com", "age": 20, "name": "A"},
                {"email": "a.b+c@mail.example.com", "age": 20, "name": "A"})

    def test_weak_email_shapes(self):
        for email in ["@.", "a@.com", "a@b..c", "@b.com", "a@b.", "a@@b.com", "a b@c.com", "a@b"]:
            self.bad("signup", {"email": email, "age": 20, "name": "A"}, "email")

    def test_other_fields(self):
        self.bad("signup", {"email": "a@b.co", "age": True, "name": "A"}, "age")
        self.bad("signup", {"email": "a@b.co", "age": 12, "name": "A"}, "age")
        self.bad("signup", {"email": "a@b.co", "age": 121, "name": "A"}, "age")
        self.bad("signup", {"email": "a@b.co", "age": 20, "name": " "}, "name")


class TestTransfer(Base):  # seeded: bool accepted as int
    def test_good(self):
        self.ok("transfer", {"src": "a", "dst": "b", "amount_cents": 1_000_000},
                {"src": "a", "dst": "b", "amount_cents": 1_000_000, "fee_cents": 10000})

    def test_bool_amount(self):
        self.bad("transfer", {"src": "a", "dst": "b", "amount_cents": True}, "amount_cents")
        self.bad("transfer", {"src": "a", "dst": "b", "amount_cents": False}, "amount_cents")

    def test_bounds_and_missing(self):
        self.bad("transfer", {"src": "a", "dst": "b", "amount_cents": 1_000_001}, "amount_cents")
        self.bad("transfer", {"src": "a", "dst": "b", "amount_cents": 1.5}, "amount_cents")
        self.bad("transfer", {"src": "a", "dst": "b"}, "amount_cents")
        self.bad("transfer", {"src": "a", "dst": " a ", "amount_cents": 5}, "dst")


class TestSchedule(Base):  # seeded: hour 24 accepted
    def test_good(self):
        self.ok("schedule", {"date": "2028-02-29", "hour": 0, "duration_min": 480},
                {"date": "2028-02-29", "hour": 0, "duration_min": 480, "end_minute": 480})
        self.ok("schedule", {"date": "2026-12-31", "hour": 23, "duration_min": 1},
                {"date": "2026-12-31", "hour": 23, "duration_min": 1, "end_minute": 1381})

    def test_hour_24(self):
        self.bad("schedule", {"date": "2026-01-01", "hour": 24, "duration_min": 5}, "hour")
        self.bad("schedule", {"date": "2026-01-01", "hour": -1, "duration_min": 5}, "hour")

    def test_dates(self):
        self.bad("schedule", {"date": "2027-02-29", "hour": 1, "duration_min": 5}, "date")
        self.bad("schedule", {"date": "20260101", "hour": 1, "duration_min": 5}, "date")
        self.bad("schedule", {"date": "2026-01-01", "hour": 1, "duration_min": 481}, "duration_min")


class TestUpload(Base):  # seeded: path check only catches a leading ../
    def test_good(self):
        self.ok("upload", {"filename": "report.v2.pdf", "size": 10485760, "content_type": "application/pdf"},
                {"filename": "report.v2.pdf", "size": 10485760, "content_type": "application/pdf"})

    def test_paths(self):
        for name in ["a/b.png", "a/../b.png", "..\\x.png", "x\\y.png", "/etc/passwd", ".", "..", "a\0b"]:
            self.bad("upload", {"filename": name, "size": 5, "content_type": "image/png"}, "filename")

    def test_rest(self):
        self.bad("upload", {"filename": "a", "size": 10485761, "content_type": "text/plain"}, "size")
        self.bad("upload", {"filename": "a", "size": 5, "content_type": "text/html"}, "content_type")
        self.bad("upload", {"filename": "x" * 101, "size": 5, "content_type": "text/plain"}, "filename")


class TestSearch(Base):  # seeded: blank query accepted
    def test_good(self):
        self.ok("search", {"query": "  a b ", "limit": 100, "offset": 7},
                {"query": "a b", "limit": 100, "offset": 7})

    def test_blank(self):
        for q in ["   ", "\t\n", " "]:
            self.bad("search", {"query": q}, "query")

    def test_rest(self):
        self.bad("search", {"query": "x" * 201}, "query")
        self.bad("search", {"query": "x", "limit": 101}, "limit")
        self.bad("search", {"query": "x", "limit": True}, "limit")


class TestCoupon(Base):  # seeded: regex allows a trailing newline
    def test_good(self):
        self.ok("coupon", {"code": "AB12", "percent": 90, "max_uses": 3},
                {"code": "AB12", "percent": 90, "max_uses": 3})

    def test_trailing_newline(self):
        self.bad("coupon", {"code": "SAVE10\n", "percent": 10}, "code")
        self.bad("coupon", {"code": "SAVE10 ", "percent": 10}, "code")

    def test_rest(self):
        self.bad("coupon", {"code": "ABCDEFGHIJKLM", "percent": 10}, "code")
        self.bad("coupon", {"code": "ABCD", "percent": 0}, "percent")
        self.bad("coupon", {"code": "ABCD", "percent": True}, "percent")


class TestProfile(Base):  # correct
    def test_good(self):
        self.ok("profile", {"name": " Ann ", "bio": "", "tags": [" Go ", "a-b"]},
                {"name": "Ann", "bio": None, "tags": ["go", "a-b"]})
        self.ok("profile", {"name": "A"}, {"name": "A", "bio": None, "tags": []})

    def test_bad(self):
        self.bad("profile", {}, "name")
        self.bad("profile", {"name": "A", "tags": ["a", "b", "c", "d", "e", "f"]}, "tags")
        self.bad("profile", {"name": "A", "tags": ["a", "A"]}, "tags")
        self.bad("profile", {"name": "A", "tags": ["a b"]}, "tags")
        self.bad("profile", {"name": "A", "tags": [3]}, "tags")
        self.bad("profile", {"name": "A", "bio": "x" * 281}, "bio")
        self.bad("profile", {"name": "A", "bio": 4}, "bio")


class TestAddress(Base):  # correct
    base = {"line1": "1 Main", "city": "X"}

    def test_good(self):
        for country, z in [("US", "12345-6789"), ("TW", "100"), ("TW", "10001"), ("TW", "100001"),
                           ("JP", "123-4567"), ("GB", "SW1A 1AA"), ("GB", "M1 1AE")]:
            self.ok("address", dict(self.base, country=country, zip=z),
                    dict(self.base, country=country, zip=z))

    def test_bad(self):
        for country, z in [("US", "1234"), ("US", "12345-67"), ("TW", "10"), ("JP", "1234567"),
                           ("GB", "sw1a 1aa"), ("GB", "SW1A1AA")]:
            self.bad("address", dict(self.base, country=country, zip=z), "zip")
        self.bad("address", dict(self.base, country="FR", zip="75001"), "country")
        self.bad("address", {"city": "X", "country": "US", "zip": "12345"}, "line1")


class TestRating(Base):  # correct
    def test_good(self):
        self.ok("rating", {"item_id": 1, "stars": 1}, {"item_id": 1, "stars": 1, "comment": None})
        self.ok("rating", {"item_id": 9, "stars": 5, "comment": " "}, {"item_id": 9, "stars": 5, "comment": None})

    def test_bad(self):
        self.bad("rating", {"item_id": True, "stars": 3}, "item_id")
        self.bad("rating", {"item_id": 1, "stars": True}, "stars")
        self.bad("rating", {"item_id": 1, "stars": 0}, "stars")
        self.bad("rating", {"item_id": 1, "stars": "3"}, "stars")
        self.bad("rating", {"item_id": 1, "stars": 3, "comment": "x" * 501}, "comment")


class TestInvite(Base):  # correct
    def test_good(self):
        self.ok("invite", {"emails": [" A@x.io", "a@X.io", "b@y.org"]},
                {"emails": ["a@x.io", "b@y.org"], "role": "viewer"})
        self.ok("invite", {"emails": ["a@x.io"], "role": "admin"}, {"emails": ["a@x.io"], "role": "admin"})

    def test_bad(self):
        self.bad("invite", {"emails": []}, "emails")
        self.bad("invite", {"emails": ["a@x.io"] * 21}, "emails")
        self.bad("invite", {"emails": ["a@.io"]}, "emails")
        self.bad("invite", {"emails": [5]}, "emails")
        self.bad("invite", {"emails": ["a@x.io"], "role": "owner"}, "role")
        self.bad("invite", {}, "emails")


class TestGeneral(Base):
    def test_payload_not_dict(self):
        for name in ["signup", "profile", "invite"]:
            self.bad(name, "oops", "payload")
            self.bad(name, None, "payload")

    def test_not_mutated(self):
        payload = {"emails": ["A@x.io"]}
        router.dispatch("invite", payload)
        self.assertEqual(payload, {"emails": ["A@x.io"]})


if __name__ == "__main__":
    unittest.main()
