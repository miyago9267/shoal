"""shelf: a tiny JSON-backed personal library tracker."""
from .errors import ShelfError, StorageError, ValidationError
from .library import Library
from .model import Book

__all__ = ["Book", "Library", "ShelfError", "StorageError", "ValidationError"]
__version__ = "0.4.2"
