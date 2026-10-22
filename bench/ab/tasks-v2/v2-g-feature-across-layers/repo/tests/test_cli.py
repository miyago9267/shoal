import io
import os
import tempfile
import unittest

from notes.cli import main


class CliTest(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)

    def tearDown(self):
        os.unlink(self.db)

    def run_cli(self, *args):
        out = io.StringIO()
        code = main(["--db", self.db, *args], out=out)
        return code, out.getvalue()

    def test_add_and_list(self):
        self.run_cli("add", "first", "--tag", "work")
        self.run_cli("add", "second")
        code, out = self.run_cli("list", "--limit", "1")
        self.assertEqual(code, 0)
        self.assertIn("second", out)
        self.assertNotIn("first", out)
        code, out = self.run_cli("list", "--tag", "work")
        self.assertIn("first  [work]", out)


if __name__ == "__main__":
    unittest.main()
