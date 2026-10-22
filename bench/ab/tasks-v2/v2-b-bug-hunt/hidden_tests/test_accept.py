import csv
import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from tick.cli import main


class Base(unittest.TestCase):
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

    @staticmethod
    def ids(text):
        return [int(n) for n in re.findall(r"^#(\d+)", text, re.M)]


class TieOrderTest(Base):
    def test_same_priority_orders_by_due_then_id(self):
        self.tick("add", "undated A", "--priority", "high")             # 1
        self.tick("add", "late", "--priority", "high", "--due", "2026-05-20")   # 2
        self.tick("add", "low", "--priority", "low", "--due", "2026-01-01")     # 3
        self.tick("add", "early", "--priority", "high", "--due", "2026-05-01")  # 4
        self.tick("add", "undated B", "--priority", "high")             # 5
        self.tick("add", "late twin", "--priority", "high", "--due", "2026-05-20")  # 6
        self.tick("add", "medium", "--due", "2026-02-01")               # 7
        self.assertEqual(self.ids(self.tick("list")), [4, 2, 6, 1, 5, 7, 3])


class TimezoneTest(Base):
    def test_east_of_utc_keeps_date(self):
        for tz in ("+08:00", "+13:00", "+05:30", "-05:00", "+00:00"):
            with self.subTest(tz=tz):
                if os.path.exists(self.db):
                    os.unlink(self.db)
                self.tick("add", "rent", "--due", "2026-03-10", tz=tz)
                listing = self.tick("list", tz=tz)
                self.assertIn("2026-03-10", listing)
                rows = list(csv.reader(io.StringIO(self.tick("export", tz=tz))))
                self.assertEqual(rows[1][3], "2026-03-10")

    def test_due_window_matches_display(self):
        self.tick("add", "far", "--due", "2099-01-02", tz="+08:00")
        out = self.tick("list", "--sort", "due", tz="+08:00")
        self.assertIn("2099-01-02", out)


class CsvTest(Base):
    def test_titles_with_commas_and_quotes(self):
        titles = ['Buy milk, eggs, bread', 'Say "hi" to Ana', 'plain', 'line one,\nline two']
        for title in titles:
            self.tick("add", title, "--tag", "a", "--tag", "b,c")
        text = self.tick("export")
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0], ["id", "title", "priority", "due", "done", "tags"])
        self.assertEqual(len(rows), 1 + len(titles))
        for row, title in zip(rows[1:], titles):
            self.assertEqual(len(row), 6, row)
            self.assertEqual(row[1], title)
            self.assertEqual(row[2], "medium")
            self.assertEqual(row[5], "a;b,c")

    def test_export_to_file(self):
        self.tick("add", "x, y")
        path = os.path.join(self.tmp.name, "out.csv")
        self.tick("export", "--out", path)
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[1][:2], ["1", "x, y"])
