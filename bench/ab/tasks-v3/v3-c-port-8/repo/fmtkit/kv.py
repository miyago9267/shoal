"""kv: ``key=value`` lines in latin-1; the last line may lack a newline."""
from .errors import ParseError
from .reader import Reader


def parse(data):
    """Return a dict. Blank lines are skipped, a line without = is an error."""
    r = Reader(data)
    out = {}
    lineno = 0
    while not r.at_end():
        lineno += 1
        line = r.until(b"\n").decode("latin-1").rstrip("\r")
        if not line.strip():
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ParseError("line %d: missing '='" % lineno)
        out[key.strip()] = value.strip()
    return out


def render(mapping):
    return "".join("%s=%s\n" % (k, v) for k, v in mapping.items()).encode("latin-1")
