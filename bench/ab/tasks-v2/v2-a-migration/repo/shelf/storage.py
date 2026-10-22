"""Load and save a Library as a JSON file."""
import json
import os
import tempfile

from .errors import StorageError, ValidationError
from .library import Library
from .model import Book

SCHEMA_VERSION = 1


def load(path):
    """Read ``path``; a missing file is an empty library."""
    if not os.path.exists(path):
        return Library()
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise StorageError(f"{path}: top level must be an object")
    version = payload.get("schema")
    if version != SCHEMA_VERSION:
        raise StorageError(f"{path}: unsupported schema {version!r}")
    records = payload.get("books", [])
    if not isinstance(records, list):
        raise StorageError(f"{path}: 'books' must be a list")
    try:
        return Library(Book.from_dict(record) for record in records)
    except ValidationError as exc:
        raise StorageError(f"{path}: {exc}") from exc


def save(library, path):
    """Atomically write ``library`` to ``path``."""
    payload = {
        "schema": SCHEMA_VERSION,
        "books": [book.to_dict() for book in library.all()],
    }
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".shelf-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise StorageError(f"cannot write {path}: {exc}") from exc
