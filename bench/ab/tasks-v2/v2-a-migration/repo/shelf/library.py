"""In-memory collection of books."""
from .errors import NotFoundError, ValidationError


class Library:
    def __init__(self, books=None):
        self._books = {}
        for book in books or []:
            self.add(book)

    def __len__(self):
        return len(self._books)

    def __iter__(self):
        return iter(self.all())

    def next_id(self):
        return max(self._books, default=0) + 1

    def add(self, book):
        """Insert ``book``; id 0 means "assign the next free id"."""
        if book.id == 0:
            book.id = self.next_id()
        book.validate()
        if book.id in self._books:
            raise ValidationError(f"duplicate id: {book.id}")
        self._books[book.id] = book
        return book

    def get(self, book_id):
        try:
            return self._books[book_id]
        except KeyError:
            raise NotFoundError(f"no book with id {book_id}") from None

    def remove(self, book_id):
        return self._books.pop(self.get(book_id).id)

    def all(self):
        return [self._books[key] for key in sorted(self._books)]

    def by_author(self, text):
        """Books whose author contains ``text`` (case-insensitive)."""
        needle = text.casefold()
        return [book for book in self.all() if needle in book.author.casefold()]

    def in_year(self, year):
        return [book for book in self.all() if book.year == year]

    def search(self, text):
        needle = text.casefold()
        return [book for book in self.all()
                if needle in book.title.casefold() or needle in book.author.casefold()]
