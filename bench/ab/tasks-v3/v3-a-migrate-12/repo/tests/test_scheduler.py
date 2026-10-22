import unittest

from ops import scheduler


class SchedulerTest(unittest.TestCase):
    def jobs(self):
        return [
            {"name": "a", "at": 1},
            {"name": "b", "at": 1, "after": ["a"]},
            {"name": "c", "at": 1, "paused": True},
            {"name": "d", "at": 99},
        ]

    def test_tick(self):
        ran = []
        jobs = self.jobs()
        n = scheduler.tick(jobs, 5, lambda j: ran.append(j["name"]))
        self.assertEqual(ran, ["a", "b"])
        self.assertEqual(n, 2)

    def test_pending(self):
        jobs = self.jobs()
        scheduler.tick(jobs, 5, lambda j: None)
        self.assertEqual(scheduler.pending(jobs), ["c", "d"])
