import unittest

from utilkit import versions


class VersionsSmoke(unittest.TestCase):
    def test_ordering(self):
        self.assertEqual(versions.compare_versions("1.2.3", "1.2.4"), -1)
        self.assertEqual(versions.compare_versions("2.0.0", "1.9.9"), 1)
        self.assertEqual(versions.compare_versions("1.0.0", "1.0.0"), 0)

    def test_newest(self):
        self.assertEqual(versions.newest(["1.0.0", "2.0.0", "1.5.0"]), "2.0.0")
        self.assertIsNone(versions.newest([]))
