import json
import os
import tempfile
import unittest

from appcfg import ConfigError, load_config


class LoadConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        path = os.path.join(self.tmp.name, "config.json")
        with open(path, "w") as fh:
            json.dump(data, fh)
        return path

    def test_defaults(self):
        config = load_config(environ={})
        self.assertEqual(config["server"]["port"], 8080)
        self.assertEqual(config["database"]["url"], "sqlite:///app.db")

    def test_file_merges_nested(self):
        path = self.write({"server": {"port": 9000}, "database": {"url": "postgres://db/x"}})
        config = load_config(path, environ={})
        self.assertEqual(config["server"], {"host": "127.0.0.1", "port": 9000})
        self.assertEqual(config["database"]["pool_size"], 5)

    def test_config_path_from_env(self):
        path = self.write({"debug": True})
        self.assertTrue(load_config(environ={"APP_CONFIG": path})["debug"])

    def test_env_beats_file(self):
        path = self.write({"server": {"port": 9000}})
        config = load_config(path, environ={"APP_PORT": "9100", "APP_DEBUG": "yes"})
        self.assertEqual(config["server"]["port"], 9100)
        self.assertTrue(config["debug"])

    def test_invalid_values(self):
        with self.assertRaises(ConfigError):
            load_config(environ={"APP_PORT": "http"})
        with self.assertRaises(ConfigError):
            load_config(environ={"APP_LOG_LEVEL": "loud"})
        with self.assertRaises(ConfigError):
            load_config(os.path.join(self.tmp.name, "missing.json"), environ={})


if __name__ == "__main__":
    unittest.main()
