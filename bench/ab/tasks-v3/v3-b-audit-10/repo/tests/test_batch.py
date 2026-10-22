import unittest

from hq import batch


class BatchTest(unittest.TestCase):
    def test_outcomes(self):
        out = batch.run_all(
            [
                {"handler": "rating", "payload": {"item_id": 1, "stars": 4}},
                {"handler": "rating", "payload": {"item_id": 1, "stars": 9}},
                {"handler": "nope", "payload": {}},
                {"handler": "rating", "payload": "x"},
            ]
        )
        self.assertTrue(out[0]["ok"])
        self.assertEqual(out[1]["field"], "stars")
        self.assertIn("unknown handler", out[2]["error"])
        self.assertEqual(out[3]["field"], "payload")

    def test_summary(self):
        out = batch.run_all(
            [
                {"handler": "rating", "payload": {"item_id": 1, "stars": 4}},
                {"handler": "rating", "payload": {"item_id": 1, "stars": 9}},
                {"handler": "rating", "payload": {"item_id": 1, "stars": 0}},
            ]
        )
        self.assertEqual(
            batch.summary(out), {"total": 3, "ok": 1, "failed": 2, "fields": {"stars": 2}}
        )
        self.assertEqual(batch.first_failure(out)[0], 1)
        self.assertIsNone(batch.first_failure(out[:1]))
