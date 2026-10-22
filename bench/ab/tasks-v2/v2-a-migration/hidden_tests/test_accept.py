import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from shelf.cli import main
from shelf.errors import ShelfError, StorageError
from shelf.library import Library
from shelf.model import Book
from shelf.storage import load, save

V1 = {
    "schema": 1,
    "books": [
        {"id": 1, "title": "Dune", "author": "Frank Herbert", "year": 1965},
        {"id": 2, "title": "Beowulf", "author": "Unknown", "year": None},
        {"id": 5, "title": "Emma", "author": "Jane Austen"},
    ],
}


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "lib.json")

    def tearDown(self):
        self.dir.cleanup()

    def write(self, payload):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--db", self.path, *args])
        return code, out.getvalue(), err.getvalue()

    def test_v1_file_migrates_on_load(self):
        self.write(V1)
        lib = load(self.path)
        dune = lib.get(1)
        self.assertEqual(dune.published, 1965)
        self.assertEqual(dune.format, "print")
        self.assertIsNone(lib.get(2).published)
        self.assertIsNone(lib.get(5).published)
        self.assertEqual([b.title for b in lib.in_year(1965)], ["Dune"])

    def test_load_does_not_modify_file(self):
        self.write(V1)
        with open(self.path, "rb") as fh:
            before = fh.read()
        load(self.path)
        for args in (("list",), ("show", "1"), ("search", "dune")):
            code, _, _ = self.run_cli(*args)
            self.assertEqual(code, 0, args)
        with open(self.path, "rb") as fh:
            self.assertEqual(fh.read(), before)

    def test_save_writes_v2(self):
        self.write(V1)
        save(load(self.path), self.path)
        data = self.read()
        self.assertEqual(data["schema"], 2)
        first = data["books"][0]
        self.assertEqual(first["published"], 1965)
        self.assertEqual(first["format"], "print")
        self.assertNotIn("year", first)

    def test_v2_round_trip(self):
        lib = Library([Book(id=1, title="Dune", author="Frank Herbert",
                            published=1965, format="audio")])
        save(lib, self.path)
        again = load(self.path).get(1)
        self.assertEqual((again.published, again.format), (1965, "audio"))

    def test_book_defaults(self):
        book = Book(id=1, title="t", author="a")
        self.assertIsNone(book.published)
        self.assertEqual(book.format, "print")
        with self.assertRaises(ShelfError):
            Book(id=1, title="t", author="a", format="vinyl").validate()

    def test_v2_requires_valid_format(self):
        self.write({"schema": 2, "books": [
            {"id": 1, "title": "Dune", "author": "F", "published": 1965}]})
        with self.assertRaises(StorageError):
            load(self.path)
        self.write({"schema": 2, "books": [
            {"id": 1, "title": "Dune", "author": "F", "published": 1965, "format": "vinyl"}]})
        with self.assertRaises(StorageError):
            load(self.path)

    def test_unknown_schema(self):
        self.write({"schema": 3, "books": []})
        with self.assertRaises(StorageError):
            load(self.path)

    def test_cli_add_on_v1_file(self):
        self.write(V1)
        code, _, err = self.run_cli("add", "Neuromancer", "--author", "William Gibson",
                                    "--published", "1984", "--format", "ebook")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.run_cli("add", "Ulysses", "--author", "James Joyce",
                                      "--year", "1922")[0], 0)
        data = self.read()
        self.assertEqual(data["schema"], 2)
        by_title = {b["title"]: b for b in data["books"]}
        self.assertEqual(by_title["Neuromancer"]["format"], "ebook")
        self.assertEqual(by_title["Neuromancer"]["published"], 1984)
        self.assertEqual(by_title["Ulysses"]["published"], 1922)
        self.assertEqual(by_title["Ulysses"]["format"], "print")
        self.assertEqual(by_title["Dune"]["format"], "print")

    def test_cli_list_format(self):
        self.write(V1)
        self.run_cli("add", "Neuromancer", "--author", "William Gibson", "--format", "ebook")
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("ebook", out)
        self.assertIn("print", out)
        code, out, _ = self.run_cli("list", "--format", "ebook")
        self.assertEqual(code, 0)
        self.assertIn("Neuromancer", out)
        self.assertNotIn("Dune", out)
        code, out, _ = self.run_cli("show", "1")
        self.assertIn("print", out)

    def test_cli_rejects_bad_format(self):
        with redirect_stderr(io.StringIO()):
            try:
                code = main(["--db", self.path, "add", "X", "--author", "Y",
                             "--format", "vinyl"])
            except SystemExit as exc:
                code = exc.code
        self.assertNotEqual(code, 0)
