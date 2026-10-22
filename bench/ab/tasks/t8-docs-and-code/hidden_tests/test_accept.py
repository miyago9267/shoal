import json
import os
import tempfile
import unittest
from pathlib import Path

from appcfg import load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


class DatabaseUrlOverrideAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        path = os.path.join(self.tmp.name, "config.json")
        with open(path, "w") as fh:
            json.dump(data, fh)
        return path

    def test_env_overrides_file(self):
        path = self.write({"database": {"url": "postgres://file/db", "pool_size": 9}})
        config = load_config(path, environ={"APP_DATABASE_URL": "postgres://env/db"})
        self.assertEqual(config["database"]["url"], "postgres://env/db")
        self.assertEqual(config["database"]["pool_size"], 9)

    def test_env_overrides_default(self):
        config = load_config(environ={"APP_DATABASE_URL": "postgres://env/db"})
        self.assertEqual(config["database"]["url"], "postgres://env/db")

    def test_env_overrides_file_named_by_app_config(self):
        path = self.write({"database": {"url": "postgres://file/db"}})
        config = load_config(environ={"APP_CONFIG": path, "APP_DATABASE_URL": "mysql://env/db"})
        self.assertEqual(config["database"]["url"], "mysql://env/db")

    def test_unset_keeps_file_value(self):
        path = self.write({"database": {"url": "postgres://file/db"}})
        self.assertEqual(load_config(path, environ={})["database"]["url"], "postgres://file/db")

    def test_other_overrides_still_work(self):
        config = load_config(environ={"APP_PORT": "9001", "APP_DATABASE_URL": "postgres://env/db"})
        self.assertEqual(config["server"]["port"], 9001)

    def test_readme_documents_variable(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("APP_DATABASE_URL", readme)


if __name__ == "__main__":
    unittest.main()
