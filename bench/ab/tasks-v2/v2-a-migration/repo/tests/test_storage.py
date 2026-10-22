import json
import os
import tempfile
import unittest

from shelf.errors import StorageError
from shelf.model import Book
from shelf.storage import load, save
from shelf.library import Library


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "lib.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_missing_file_is_empty(self):
        self.assertEqual(len(load(self.path)), 0)

    def test_save_then_load(self):
        lib = Library([Book(id=1, title="Dune", author="Frank Herbert", year=1965)])
        save(lib, self.path)
        again = load(self.path)
        self.assertEqual(again.get(1).title, "Dune")

    def test_rejects_unknown_schema(self):
        with open(self.path, "w") as fh:
            json.dump({"schema": 99, "books": []}, fh)
        with self.assertRaises(StorageError):
            load(self.path)

    def test_rejects_bad_record(self):
        with open(self.path, "w") as fh:
            json.dump({"schema": 1, "books": [{"id": 1, "title": ""}]}, fh)
        with self.assertRaises(StorageError):
            load(self.path)
