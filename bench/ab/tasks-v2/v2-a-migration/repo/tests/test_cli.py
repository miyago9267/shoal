import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from shelf.cli import main


class CliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.dir.name, "lib.json")

    def tearDown(self):
        self.dir.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--db", self.db, *args])
        return code, out.getvalue(), err.getvalue()

    def test_add_and_list(self):
        self.assertEqual(self.run_cli("add", "Dune", "--author", "Frank Herbert",
                                      "--year", "1965")[0], 0)
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("Dune", out)
        self.assertIn("1965", out)

    def test_show_missing(self):
        code, _, err = self.run_cli("show", "4")
        self.assertEqual(code, 1)
        self.assertIn("no book", err)
