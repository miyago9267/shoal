"""cstrings: NUL-terminated latin-1 strings, last one may be unterminated."""
from .errors import ParseError
from .reader import Reader


def parse(data):
    """Return the list of strings. Empty input gives an empty list."""
    r = Reader(data)
    out = []
    while not r.at_end():
        raw = r.until(b"\0")
        out.append(raw.decode("latin-1"))
        if len(out) > 10_000:
            raise ParseError("too many strings")
    return out


def join(strings):
    return b"".join(s.encode("latin-1") + b"\0" for s in strings)
