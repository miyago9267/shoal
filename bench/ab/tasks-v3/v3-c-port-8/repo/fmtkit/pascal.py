"""pascal: u16 count, then that many u8-length-prefixed latin-1 strings."""
from .errors import ParseError
from .reader import Reader, ReaderError


def parse(data):
    r = Reader(data)
    try:
        count = r.u16()
        out = []
        for index in range(count):
            size = r.u8()
            text = r.string(size)
            if len(text) != size:
                raise ParseError("string %d is cut short" % index)
            out.append(text)
    except ReaderError as exc:
        raise ParseError(str(exc)) from None
    if not r.at_end():
        raise ParseError("%d trailing bytes" % (len(data) - r.tell()))
    return out


def build(strings):
    out = bytearray(len(strings).to_bytes(2, "big"))
    for s in strings:
        raw = s.encode("latin-1")
        out.append(len(raw))
        out += raw
    return bytes(out)
