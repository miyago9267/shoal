"""One-line summaries of parsed results, used by the command line."""
from .errors import ParseError
from .registry import parse


def summarize(name, data):
    try:
        result = parse(name, data)
    except ParseError as exc:
        return "%s: error: %s" % (name, exc)
    if isinstance(result, dict):
        keys = ",".join(sorted(result))
        return "%s: object with %s" % (name, keys)
    return "%s: %d items" % (name, len(result))


def hexdump(data, width=16):
    lines = []
    for offset in range(0, len(data), width):
        chunk = data[offset : offset + width]
        hexes = " ".join("%02x" % b for b in chunk)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append("%08x  %-*s  %s" % (offset, width * 3 - 1, hexes, text))
    return "\n".join(lines)
