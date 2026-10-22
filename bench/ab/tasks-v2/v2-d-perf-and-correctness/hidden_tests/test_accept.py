import random
import time
import unittest
from datetime import datetime, timezone

from logpipe.pipeline import run

DAY = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
TIME_LIMIT_S = 4.0


def stamp(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def line(ts, req, user, status=200, size=100):
    return f"{stamp(ts)} req={req} user={user} status={status} bytes={size} path=/p ms=3"


def big_input(n_events=40000, n_users=25000, seed=7):
    rng = random.Random(seed)
    users = ["id,name,plan"] + [f"{i},user{i},{('free', 'pro', 'team')[i % 3]}"
                                for i in range(1, n_users + 1)]
    lines, expected = [], {"requests": 0, "bytes": 0, "users": {}, "plans": {}}
    for i in range(n_events):
        uid = rng.randint(1, n_users + 50)          # a few ids are unknown
        ts = DAY + rng.randint(0, 86399)
        size = rng.randint(0, 50000)
        req = f"r{i:06x}"
        lines.append(line(ts, req, uid, rng.choice((200, 200, 200, 404, 503)), size))
        name = f"user{uid}" if uid <= n_users else "unknown"
        plan = ("free", "pro", "team")[uid % 3] if uid <= n_users else "none"
        expected["requests"] += 1
        expected["bytes"] += size
        row = expected["users"].setdefault(name, [0, 0])
        row[0] += 1
        row[1] += size
        prow = expected["plans"].setdefault(plan, [0, 0])
        prow[0] += 1
        prow[1] += size
        if rng.random() < 0.03:                      # proxy retry: same req logged again
            lines.append(line(ts + rng.randint(1, 2), req, uid, 200, size))
        if rng.random() < 0.03:                      # a distinct request in the same second
            j = f"s{i:06x}"
            lines.append(line(ts, j, uid, 200, 1))
            expected["requests"] += 1
            expected["bytes"] += 1
            row[0] += 1
            row[1] += 1
            prow[0] += 1
            prow[1] += 1
    return lines, "\n".join(users) + "\n", expected


USERS = "id,name,plan\n1,ana,pro\n2,bo,free\n"


class Checks:
    def check(self, out, expected):
        self.assertEqual(out["total_requests"], expected["requests"])
        self.assertEqual(out["total_bytes"], expected["bytes"])
        got_users = {k: [v["requests"], v["bytes"]] for k, v in out["users"].items()}
        self.assertEqual(got_users, expected["users"])
        got_plans = {k: [v["requests"], v["bytes"]] for k, v in out["plans"].items()}
        self.assertEqual(got_plans, expected["plans"])


class CorrectnessTest(Checks, unittest.TestCase):
    def test_same_second_requests_are_distinct(self):
        lines = [line(DAY, "a1", 1, size=10), line(DAY, "a2", 1, size=20),
                 line(DAY, "a3", 1, size=30), line(DAY, "b1", 2, size=5)]
        out = run(lines, USERS)
        self.assertEqual(out["total_requests"], 4)
        self.assertEqual(out["total_bytes"], 65)
        self.assertEqual(out["users"]["ana"]["requests"], 3)
        self.assertEqual(out["users"]["ana"]["bytes"], 60)
        self.assertEqual(out["users"]["ana"]["sessions"], 1)
        self.assertEqual(out["plans"]["pro"], {"requests": 3, "bytes": 60})

    def test_retries_counted_once(self):
        lines = [line(DAY, "a1", 1, status=502, size=10),
                 line(DAY + 2, "a1", 1, status=200, size=10),
                 line(DAY + 1, "a2", 1, size=7),
                 line(DAY + 3, "a2", 1, size=7)]
        out = run(lines, USERS)
        self.assertEqual(out["total_requests"], 2)
        self.assertEqual(out["total_bytes"], 17)
        self.assertEqual(out["users"]["ana"]["errors"], 1)

    def test_large_totals(self):
        lines, users, expected = big_input(n_events=3000, n_users=400, seed=11)
        self.check(run(lines, users), expected)


class PerformanceTest(Checks, unittest.TestCase):
    def test_big_log_is_fast(self):
        lines, users, expected = big_input()
        start = time.perf_counter()
        out = run(lines, users)
        elapsed = time.perf_counter() - start
        self.check(out, expected)
        self.assertLess(elapsed, TIME_LIMIT_S,
                        f"pipeline took {elapsed:.1f}s on {len(lines)} lines")
