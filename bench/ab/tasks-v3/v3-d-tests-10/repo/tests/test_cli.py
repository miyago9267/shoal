import unittest

from utilkit import cli


class CliSmoke(unittest.TestCase):
    def test_slug_tool(self):
        self.assertEqual(cli.TOOLS["slug"](["Hello", "World"]), "hello-world")

    def test_usage(self):
        self.assertEqual(cli.main([]), 2)
        self.assertEqual(cli.main(["nope"]), 2)

    def test_error_code(self):
        self.assertEqual(cli.main(["size", "abc"]), 1)
