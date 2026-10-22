"""chunks: (length u32, tag 4 bytes, payload, crc32 u32) until the END chunk."""
import zlib

from .errors import ParseError
from .reader import Reader, ReaderError


def parse(data):
    """Return [(tag, payload)] including the END chunk; bytes after END are ignored."""
    r = Reader(data)
    out = []
    try:
        while True:
            if r.peek() is None:
                raise ParseError("missing END chunk")
            length = r.u32()
            tag = r.read(4)
            payload = r.read(length)
            crc = r.u32()
            if len(tag) != 4 or len(payload) != length:
                raise ParseError("chunk %d is cut short" % len(out))
            if zlib.crc32(tag + payload) != crc:
                raise ParseError("chunk %d: bad crc" % len(out))
            out.append((tag, payload))
            if tag == b"END ":
                return out
    except ReaderError as exc:
        raise ParseError(str(exc)) from None


def chunk(tag, payload=b""):
    crc = zlib.crc32(tag + payload)
    return len(payload).to_bytes(4, "big") + tag + payload + crc.to_bytes(4, "big")


def tags(chunks):
    return [tag for tag, _ in chunks]
