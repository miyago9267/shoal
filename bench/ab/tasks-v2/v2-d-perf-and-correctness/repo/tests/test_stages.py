import unittest

from logpipe.aggregate import aggregate
from logpipe.enrich import enrich
from logpipe.model import Event, User
from logpipe.sessionize import sessionize

USERS = [User(1, "ana", "pro"), User(2, "bo", "free")]


def ev(ts, req, user, status=200, size=10):
    return Event(ts=ts, request_id=req, user_id=user, status=status, bytes=size,
                 path="/", ms=1)


class EnrichTest(unittest.TestCase):
    def test_join(self):
        events = enrich([ev(0, "a", 2), ev(1, "b", 5)], USERS)
        self.assertEqual([e.user.name for e in events], ["bo", "unknown"])


class SessionizeTest(unittest.TestCase):
    def test_gap(self):
        events = sessionize([ev(0, "a", 1), ev(1800, "b", 1), ev(3601, "c", 1),
                             ev(100, "d", 2)])
        by_req = {e.request_id: e.session for e in events}
        self.assertEqual(by_req["a"], by_req["b"])
        self.assertNotEqual(by_req["b"], by_req["c"])
        self.assertNotEqual(by_req["a"], by_req["d"])

    def test_sorted_output(self):
        events = sessionize([ev(5, "x", 1), ev(1, "y", 1)])
        self.assertEqual([e.ts for e in events], [1, 5])


class AggregateTest(unittest.TestCase):
    def test_errors_and_plans(self):
        events = sessionize(enrich([ev(0, "a", 1, 502, 5), ev(9, "b", 2, 200, 7)], USERS))
        out = aggregate(events)
        self.assertEqual(out["users"]["ana"]["errors"], 1)
        self.assertEqual(out["plans"]["free"], {"requests": 1, "bytes": 7})
        self.assertEqual(out["total_bytes"], 12)
