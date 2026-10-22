import time
import unittest

from workpool.pipeline import Pipeline, Stage


class PipelineTest(unittest.TestCase):
    def test_two_stages_with_filter(self):
        pipe = Pipeline([
            Stage("parse", int, workers=2),
            Stage("even", lambda n: n * 10 if n % 2 == 0 else None, workers=2),
        ])
        pipe.feed(["1", "2", "3", "4"])
        time.sleep(0.2)
        self.assertEqual(sorted(pipe.close()), [20, 40])
        self.assertEqual(pipe.stats()["parse"]["processed"], 4)

    def test_errors_per_stage(self):
        pipe = Pipeline([Stage("parse", int, workers=1)])
        pipe.feed(["7", "x"])
        time.sleep(0.2)
        self.assertEqual(pipe.close(), [7])
        self.assertEqual([e.item for e in pipe.errors()["parse"]], ["x"])

    def test_needs_a_stage(self):
        with self.assertRaises(ValueError):
            Pipeline([])


if __name__ == "__main__":
    unittest.main()
