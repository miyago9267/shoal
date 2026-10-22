"""Name -> parser lookup."""
from . import bitmap, chunks, cstrings, header, kv, pascal, tables, tlv

PARSERS = {
    "bitmap": bitmap.parse,
    "chunks": chunks.parse,
    "cstrings": cstrings.parse,
    "header": header.parse,
    "kv": kv.parse,
    "pascal": pascal.parse,
    "tables": tables.parse,
    "tlv": tlv.parse,
}


def parse(name, data):
    """Run the named parser; unknown names raise KeyError."""
    return PARSERS[name](data)


def names():
    return sorted(PARSERS)
