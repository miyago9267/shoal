"""Exception hierarchy shared by every shelf module."""


class ShelfError(Exception):
    """Base class for all errors raised by shelf."""


class ValidationError(ShelfError):
    """A record does not satisfy the model's rules."""


class StorageError(ShelfError):
    """The library file cannot be read or written."""


class NotFoundError(ShelfError):
    """No book has the requested id."""
