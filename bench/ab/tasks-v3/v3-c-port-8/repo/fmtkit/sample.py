"""Deterministic sample inputs for every format, used by docs and tests."""
from . import chunks, cstrings, header, kv, pascal, tlv


def tlv_sample():
    return tlv.dump([(1, b"alpha"), (2, b""), (3, b"\x00\x01\x02")])


def cstrings_sample():
    return cstrings.join(["one", "two", "three"])


def header_sample():
    return header.build(1, 0b101, b"payload")


def kv_sample():
    return kv.render({"host": "example", "port": "8080", "mode": "fast"})


def pascal_sample():
    return pascal.build(["red", "green", "blue"])


def bitmap_sample(width=4, height=3):
    pixels = bytes((x * 16 + y) % 256 for y in range(height) for x in range(width))
    return width.to_bytes(2, "big") + height.to_bytes(2, "big") + pixels


def tables_sample():
    def row(ident, flag, name):
        return ident.to_bytes(2, "big") + bytes([flag, len(name)]) + name + b"\x00\x00"

    return (3).to_bytes(4, "big") + row(1, 0, b"first") + row(2, 1, b"second") + row(3, 0, b"third")


def chunks_sample():
    return chunks.chunk(b"HEAD", b"v1") + chunks.chunk(b"BODY", b"x" * 40) + chunks.chunk(b"END ")


ALL = {
    "bitmap": bitmap_sample,
    "chunks": chunks_sample,
    "cstrings": cstrings_sample,
    "header": header_sample,
    "kv": kv_sample,
    "pascal": pascal_sample,
    "tables": tables_sample,
    "tlv": tlv_sample,
}


def corrupt(data, how):
    """Return a damaged copy: "cut" drops the last byte, "flip" changes the first."""
    if how == "cut":
        return data[:-1]
    if how == "flip":
        return bytes([data[0] ^ 0xFF]) + data[1:]
    raise ValueError(how)
