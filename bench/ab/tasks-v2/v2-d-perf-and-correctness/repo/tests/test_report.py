import unittest

from logpipe.report import human_bytes, to_text


class ReportTest(unittest.TestCase):
    def test_human_bytes(self):
        self.assertEqual(human_bytes(12), "12 B")
        self.assertEqual(human_bytes(2048), "2.0 KiB")

    def test_text(self):
        text = to_text({"total_requests": 1, "total_bytes": 5, "skipped": 0,
                        "users": {"ana": {"requests": 1, "bytes": 5, "errors": 0,
                                          "sessions": 1}},
                        "plans": {"pro": {"requests": 1, "bytes": 5}}})
        self.assertIn("ana", text)
        self.assertIn("pro", text)
