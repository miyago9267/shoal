import unittest

from ops import cli, config, util


class UtilTest(unittest.TestCase):
    def test_chunks(self):
        self.assertEqual(list(util.chunks([1, 2, 3, 4, 5], 2)), [[1, 2], [3, 4], [5]])
        with self.assertRaises(ValueError):
            list(util.chunks([1], 0))

    def test_clamp(self):
        self.assertEqual(util.clamp(9, 0, 5), 5)
        self.assertEqual(util.clamp(-1, 0, 5), 0)
        self.assertEqual(util.clamp(3, 0, 5), 3)

    def test_human_duration(self):
        self.assertEqual(util.human_duration(5), "5s")
        self.assertEqual(util.human_duration(65), "1m05s")
        self.assertEqual(util.human_duration(3723), "1h02m03s")

    def test_group_flatten_dedupe(self):
        self.assertEqual(util.group_by([1, 2, 3], lambda n: n % 2), {1: [1, 3], 0: [2]})
        self.assertEqual(util.flatten([1, [2, (3, [4])]]), [1, 2, 3, 4])
        self.assertEqual(util.dedupe([3, 1, 3, 2, 1]), [3, 1, 2])
        self.assertEqual(util.first([], "x"), "x")


class ConfigTest(unittest.TestCase):
    def test_get_default_and_override(self):
        self.assertEqual(config.get("cache", "capacity"), 128)
        self.assertEqual(config.get("cache", "capacity", {"cache": {"capacity": 4}}), 4)

    def test_validate(self):
        self.assertEqual(config.validate({"cache": {"capacity": 1}}), [])
        self.assertEqual(
            config.validate({"nope": {}, "cache": {"zzz": 1}}),
            ["unknown section nope", "unknown key cache.zzz"],
        )


class CliTest(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(cli.cmd_money(["1205"]), "12.05")
        self.assertEqual(cli.cmd_low(["a=1", "b=9"]), "a")
        self.assertEqual(cli.cmd_duration(["3723"]), "1h02m03s")
        self.assertEqual(cli.cmd_config(["cache", "capacity"]), "128")

    def test_main_usage(self):
        self.assertEqual(cli.main([]), 2)
