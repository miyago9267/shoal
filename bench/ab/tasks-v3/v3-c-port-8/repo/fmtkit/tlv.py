"""tlv: repeated (type u8, length u16, value) records."""
from .errors import ParseError
from .reader import Reader, ReaderError


def parse(data):
    """Return a list of (type, value-bytes)."""
    r = Reader(data)
    items = []
    try:
        while not r.at_end():
            kind = r.u8()
            size = r.u16()
            value = r.read(size)
            if len(value) != size:
                raise ParseError("record %d: value is cut short" % len(items))
            items.append((kind, value))
    except ReaderError as exc:
        raise ParseError(str(exc)) from None
    return items


def find(items, kind):
    return [value for k, value in items if k == kind]


def dump(items):
    out = bytearray()
    for kind, value in items:
        out += bytes([kind]) + len(value).to_bytes(2, "big") + value
    return bytes(out)
