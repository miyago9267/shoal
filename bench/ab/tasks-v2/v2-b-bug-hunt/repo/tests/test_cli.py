import re

from tests.helpers import CliCase


class CliTest(CliCase):
    def ids(self, text):
        return [int(n) for n in re.findall(r"^#(\d+)", text, re.M)]

    def test_priority_order(self):
        self.tick("add", "low one", "--priority", "low")
        self.tick("add", "high one", "--priority", "high")
        self.tick("add", "medium one")
        self.assertEqual(self.ids(self.tick("list")), [2, 3, 1])

    def test_done_hidden(self):
        self.tick("add", "a")
        self.tick("add", "b")
        self.tick("done", "1")
        self.assertEqual(self.ids(self.tick("list")), [2])
        self.assertEqual(sorted(self.ids(self.tick("list", "--all"))), [1, 2])

    def test_due_shown_utc(self):
        self.tick("add", "rent", "--due", "2026-03-01")
        self.assertIn("2026-03-01", self.tick("list"))

    def test_tag_filter(self):
        self.tick("add", "a", "--tag", "home")
        self.tick("add", "b", "--tag", "work")
        self.assertEqual(self.ids(self.tick("list", "--tag", "work")), [2])

    def test_export_header(self):
        self.tick("add", "plain title", "--priority", "high", "--tag", "x", "--tag", "y")
        lines = self.tick("export").splitlines()
        self.assertEqual(lines[0], "id,title,priority,due,done,tags")
        self.assertEqual(lines[1], "1,plain title,high,,no,x;y")
