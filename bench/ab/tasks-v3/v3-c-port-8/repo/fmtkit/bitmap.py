"""bitmap: u16 width, u16 height, then width*height pixel bytes.

A short pixel block is tolerated and zero padded; extra bytes are ignored.
"""
from .errors import ParseError
from .reader import Reader, ReaderError

MAX_PIXELS = 1 << 20


def parse(data):
    r = Reader(data)
    try:
        width = r.u16()
        height = r.u16()
    except ReaderError as exc:
        raise ParseError(str(exc)) from None
    need = width * height
    if need > MAX_PIXELS:
        raise ParseError("bitmap too large")
    pixels = r.read(need)
    if len(pixels) < need:
        pixels = pixels + bytes(need - len(pixels))
    return {"width": width, "height": height, "pixels": pixels}


def row(bitmap, y):
    w = bitmap["width"]
    return bitmap["pixels"][y * w : (y + 1) * w]


def histogram(bitmap):
    counts = {}
    for value in bitmap["pixels"]:
        counts[value] = counts.get(value, 0) + 1
    return counts
