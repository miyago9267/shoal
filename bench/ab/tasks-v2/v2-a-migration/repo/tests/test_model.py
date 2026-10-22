import unittest

from shelf.errors import ValidationError
from shelf.model import Book


class BookTest(unittest.TestCase):
    def test_round_trip(self):
        book = Book(id=3, title="Dune", author="Frank Herbert", year=1965)
        self.assertEqual(Book.from_dict(book.to_dict()), book)

    def test_year_optional(self):
        book = Book.from_dict({"id": 1, "title": "Beowulf", "author": "Unknown"})
        self.assertIsNone(book.year)

    def test_rejects_empty_title(self):
        with self.assertRaises(ValidationError):
            Book(id=1, title="  ", author="x").validate()

    def test_rejects_unknown_field(self):
        with self.assertRaises(ValidationError):
            Book.from_dict({"id": 1, "title": "t", "author": "a", "isbn": "1"})
