import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from tick.cli import main


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "tick.json")

    def tearDown(self):
        self.tmp.cleanup()

    def tick(self, *args, tz="+00:00"):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--db", self.db, "--tz", tz, *args])
        self.assertEqual(code, 0, err.getvalue())
        return out.getvalue()
