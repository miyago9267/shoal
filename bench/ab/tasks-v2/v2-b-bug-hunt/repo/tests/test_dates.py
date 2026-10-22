import unittest
from datetime import datetime, timezone

from tick import dates


class DatesTest(unittest.TestCase):
    def test_parse_tz(self):
        self.assertEqual(dates.parse_tz("+08:00").utcoffset(None).total_seconds(), 8 * 3600)
        self.assertEqual(dates.parse_tz("-0530").utcoffset(None).total_seconds(), -19800)
        with self.assertRaises(ValueError):
            dates.parse_tz("8")

    def test_parse_due_utc(self):
        epoch = dates.parse_due("2026-03-01", timezone.utc)
        self.assertEqual(datetime.fromtimestamp(epoch, timezone.utc).hour, 0)
        self.assertEqual(dates.format_due(epoch, timezone.utc), "2026-03-01")

    def test_days_until(self):
        tz = timezone.utc
        now = datetime(2026, 3, 1, 15, 0, tzinfo=tz)
        self.assertEqual(dates.days_until(dates.parse_due("2026-03-04", tz), tz, now), 3)
        self.assertEqual(dates.days_until(dates.parse_due("2026-02-27", tz), tz, now), -2)
