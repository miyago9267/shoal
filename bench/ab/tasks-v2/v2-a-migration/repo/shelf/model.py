"""The Book record and its (de)serialisation."""
from dataclasses import dataclass

from .errors import ValidationError

FIELDS = ("id", "title", "author", "year")


@dataclass
class Book:
    id: int
    title: str
    author: str
    year: "int | None" = None

    def validate(self):
        """Raise ValidationError when the record breaks a model rule."""
        if not isinstance(self.id, int) or isinstance(self.id, bool) or self.id < 0:
            raise ValidationError(f"invalid id: {self.id!r}")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValidationError("title must be a non-empty string")
        if not isinstance(self.author, str) or not self.author.strip():
            raise ValidationError("author must be a non-empty string")
        if self.year is not None:
            if not isinstance(self.year, int) or isinstance(self.year, bool):
                raise ValidationError(f"year must be an integer: {self.year!r}")
            if not 0 < self.year < 3000:
                raise ValidationError(f"year out of range: {self.year}")
        return self

    def to_dict(self):
        return {"id": self.id, "title": self.title, "author": self.author,
                "year": self.year}

    @classmethod
    def from_dict(cls, data):
        """Build a Book from one record of the on-disk format."""
        if not isinstance(data, dict):
            raise ValidationError(f"record must be an object, got {type(data).__name__}")
        missing = [name for name in ("id", "title", "author") if name not in data]
        if missing:
            raise ValidationError(f"record is missing {', '.join(missing)}")
        unknown = sorted(set(data) - set(FIELDS))
        if unknown:
            raise ValidationError(f"unknown field(s): {', '.join(unknown)}")
        book = cls(id=data["id"], title=data["title"], author=data["author"],
                   year=data.get("year"))
        return book.validate()
