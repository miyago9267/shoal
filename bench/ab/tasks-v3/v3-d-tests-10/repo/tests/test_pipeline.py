import unittest

from utilkit import pipeline


class PipelineSmoke(unittest.TestCase):
    def test_safe(self):
        self.assertEqual(pipeline.safe(int, "5"), 5)
        self.assertEqual(pipeline.safe(int, "x", default=-1), -1)
        self.assertIsNone(pipeline.safe(len, 5))

    def test_batch(self):
        results, errors = pipeline.batch(int, ["1", "x", "3"])
        self.assertEqual(results, {0: 1, 2: 3})
        self.assertEqual(list(errors), [1])
        self.assertTrue(errors[1].startswith("ValueError"))
        self.assertEqual(pipeline.summary(results, errors), "2 ok, 1 failed of 3")
        self.assertEqual(pipeline.first_error(errors)[0], 1)
        self.assertIsNone(pipeline.first_error({}))

    def test_table(self):
        text = pipeline.table([("a", 1), ("bbb", 22)], headers=("k", "v"))
        self.assertEqual(text, "k    v\na    1\nbbb  22")
        self.assertEqual(pipeline.table([]), "")

    def test_partition(self):
        self.assertEqual(pipeline.partition(range(6), lambda n: n % 2), ([1, 3, 5], [0, 2, 4]))
