import unittest

from hq import router
from hq.errors import ValidationError


class ScheduleTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(router.dispatch("schedule", {"date": "2026-02-28", "hour": 9, "duration_min": 30}), {"date": "2026-02-28", "hour": 9, "duration_min": 30, "end_minute": 570})

    def test_rejects_0(self):
        with self.assertRaises(ValidationError):
            router.dispatch("schedule", {"date": "2026-02-30", "hour": 9, "duration_min": 30})

    def test_rejects_1(self):
        with self.assertRaises(ValidationError):
            router.dispatch("schedule", {"date": "2026-2-3", "hour": 9, "duration_min": 30})

    def test_rejects_2(self):
        with self.assertRaises(ValidationError):
            router.dispatch("schedule", {"date": "2026-02-28", "hour": 30, "duration_min": 30})

    def test_rejects_3(self):
        with self.assertRaises(ValidationError):
            router.dispatch("schedule", {"date": "2026-02-28", "hour": 9, "duration_min": 0})


    def test_not_a_dict(self):
        with self.assertRaises(ValidationError):
            router.dispatch("schedule", [])
