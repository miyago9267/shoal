import unittest

from logpipe.pipeline import run

USERS = "id,name,plan\n1,ana,pro\n2,bo,free\n"
LOG = """\
2026-10-01T09:00:00Z req=r1 user=1 status=200 bytes=100 path=/a ms=5
2026-10-01T09:10:00Z req=r2 user=1 status=500 bytes=50 path=/b ms=9
2026-10-01T11:00:00Z req=r3 user=1 status=200 bytes=10 path=/a ms=2
2026-10-01T09:05:00Z req=r4 user=2 status=200 bytes=- path=/a ms=1
2026-10-01T09:06:00Z req=r5 user=9 status=404 bytes=7 path=/z ms=1
not a log line
"""


class PipelineTest(unittest.TestCase):
    def test_summary(self):
        out = run(LOG.splitlines(), USERS)
        self.assertEqual(out["total_requests"], 5)
        self.assertEqual(out["total_bytes"], 167)
        self.assertEqual(out["skipped"], 1)
        self.assertEqual(out["users"]["ana"],
                         {"requests": 3, "bytes": 160, "errors": 1, "sessions": 2})
        self.assertEqual(out["users"]["unknown"]["requests"], 1)
        self.assertEqual(out["plans"]["pro"], {"requests": 3, "bytes": 160})
        self.assertEqual(out["plans"]["none"], {"requests": 1, "bytes": 7})
