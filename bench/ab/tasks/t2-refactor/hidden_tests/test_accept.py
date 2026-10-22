import json
import os
import pathlib
import tempfile
import unittest

import relay
from relay import backoff, config, sender
from relay.config import DEFAULTS, load_config
from relay.worker import drain, worst_case_wait

PKG = pathlib.Path(relay.__file__).resolve().parent


class AcceptTest(unittest.TestCase):
    def test_new_function_name(self):
        cfg = load_config(overrides={"retry_base_delay": 2.0, "max_delay": 10.0})
        self.assertEqual([backoff.retry_delay(n, cfg) for n in (1, 2, 3, 4)],
                         [2.0, 4.0, 8.0, 10.0])
        self.assertIs(relay.retry_delay, backoff.retry_delay)
        with self.assertRaises(ValueError):
            backoff.retry_delay(0, cfg)

    def test_old_function_name_gone(self):
        self.assertFalse(hasattr(backoff, "compute_backoff"))
        self.assertFalse(hasattr(relay, "compute_backoff"))
        self.assertFalse(hasattr(sender, "compute_backoff"))

    def test_config_key_renamed(self):
        self.assertEqual(DEFAULTS["retry_base_delay"], 1.0)
        self.assertNotIn("backoff_base", DEFAULTS)
        with self.assertRaises(ValueError):
            load_config(overrides={"retry_base_delay": -1})

    def test_config_file_new_and_old_key(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "relay.json")
            with open(path, "w") as fh:
                json.dump({"retry_base_delay": 0.5}, fh)
            self.assertEqual(load_config(path)["retry_base_delay"], 0.5)
            with open(path, "w") as fh:
                json.dump({"backoff_base": 0.5}, fh)
            with self.assertRaises(KeyError):
                load_config(path)

    def test_behavior_unchanged(self):
        cfg = load_config(overrides={"max_attempts": 4, "retry_base_delay": 0.5})
        self.assertEqual(worst_case_wait(cfg), 3.5)
        waits = []

        def transport(event):
            raise OSError("down")

        delivered, dead = drain(["e"], transport, cfg, waits.append)
        self.assertEqual((delivered, dead), ([], ["e"]))
        self.assertEqual(waits, [0.5, 1.0, 2.0])

    def test_no_stale_references_in_source(self):
        for path in PKG.rglob("*.py"):
            text = path.read_text()
            self.assertNotIn("compute_backoff", text, str(path))
            self.assertNotIn("backoff_base", text, str(path))


if __name__ == "__main__":
    unittest.main()
