import unittest

from shelf.errors import NotFoundError, ValidationError
from shelf.library import Library
from shelf.model import Book


def sample():
    lib = Library()
    lib.add(Book(id=0, title="Dune", author="Frank Herbert", year=1965))
    lib.add(Book(id=0, title="Emma", author="Jane Austen", year=1815))
    lib.add(Book(id=0, title="Persuasion", author="Jane Austen", year=1817))
    return lib


class LibraryTest(unittest.TestCase):
    def test_assigns_ids(self):
        self.assertEqual([b.id for b in sample()], [1, 2, 3])

    def test_duplicate_id(self):
        lib = sample()
        with self.assertRaises(ValidationError):
            lib.add(Book(id=2, title="x", author="y"))

    def test_filters(self):
        lib = sample()
        self.assertEqual([b.title for b in lib.by_author("austen")], ["Emma", "Persuasion"])
        self.assertEqual([b.title for b in lib.in_year(1965)], ["Dune"])
        self.assertEqual([b.title for b in lib.search("dun")], ["Dune"])

    def test_remove_missing(self):
        with self.assertRaises(NotFoundError):
            sample().remove(99)
