"""Length-framed containers that wrap several encoded documents in one blob.

Frame layout: count (u16), then for each part a u32 length and the bytes.
These helpers use plain slicing, not a reader, because they sit below the
parsers.
"""
from .errors import ParseError


def pack(parts):
    out = bytearray(len(parts).to_bytes(2, "big"))
    for part in parts:
        out += len(part).to_bytes(4, "big") + part
    return bytes(out)


def unpack(blob):
    if len(blob) < 2:
        raise ParseError("frame is missing its count")
    count = int.from_bytes(blob[:2], "big")
    pos = 2
    parts = []
    for index in range(count):
        if pos + 4 > len(blob):
            raise ParseError("part %d: missing length" % index)
        size = int.from_bytes(blob[pos : pos + 4], "big")
        pos += 4
        if pos + size > len(blob):
            raise ParseError("part %d: cut short" % index)
        parts.append(blob[pos : pos + size])
        pos += size
    if pos != len(blob):
        raise ParseError("%d trailing bytes" % (len(blob) - pos))
    return parts


def parse_all(blob, names):
    """Unpack ``blob`` and parse part i with the parser called names[i]."""
    from .registry import parse

    parts = unpack(blob)
    if len(parts) != len(names):
        raise ParseError("expected %d parts, got %d" % (len(names), len(parts)))
    return [parse(name, part) for name, part in zip(names, parts)]


def sizes(blob):
    return [len(p) for p in unpack(blob)]
