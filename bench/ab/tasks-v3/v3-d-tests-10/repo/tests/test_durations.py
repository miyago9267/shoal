import unittest

from utilkit import durations


class DurationsSmoke(unittest.TestCase):
    def test_parse_basic(self):
        self.assertEqual(durations.parse_duration("1h30m"), 5400)
        self.assertEqual(durations.parse_duration("45s"), 45)

    def test_format(self):
        self.assertEqual(durations.format_duration(5400), "1h30m")
        self.assertEqual(durations.format_duration(0), "0s")
