"""Errors raised by the handlers."""


class ValidationError(ValueError):
    """Bad input. ``field`` names the offending field."""

    def __init__(self, field, message):
        super().__init__("%s: %s" % (field, message))
        self.field = field
        self.message = message


class UnknownHandler(KeyError):
    pass
