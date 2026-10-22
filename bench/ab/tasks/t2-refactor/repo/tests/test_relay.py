import json
import os
import tempfile
import unittest

from relay.backoff import compute_backoff, schedule
from relay.config import load_config
from relay.worker import drain, worst_case_wait


class BackoffTest(unittest.TestCase):
    def test_doubles_and_caps(self):
        cfg = load_config(overrides={"backoff_base": 2.0, "max_delay": 10.0})
        self.assertEqual([compute_backoff(n, cfg) for n in (1, 2, 3, 4)],
                         [2.0, 4.0, 8.0, 10.0])

    def test_schedule(self):
        cfg = load_config(overrides={"max_attempts": 4})
        self.assertEqual(schedule(cfg), [1.0, 2.0, 4.0])
        self.assertEqual(worst_case_wait(cfg), 7.0)

    def test_config_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "relay.json")
            with open(path, "w") as fh:
                json.dump({"backoff_base": 0.5}, fh)
            self.assertEqual(load_config(path)["backoff_base"], 0.5)


class DrainTest(unittest.TestCase):
    def test_retries_then_dead_letters(self):
        waits = []

        def transport(event):
            if event == "bad":
                raise OSError("refused")

        cfg = load_config(overrides={"max_attempts": 3})
        delivered, dead = drain(["ok", "bad"], transport, cfg, waits.append)
        self.assertEqual((delivered, dead), (["ok"], ["bad"]))
        self.assertEqual(waits, [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
