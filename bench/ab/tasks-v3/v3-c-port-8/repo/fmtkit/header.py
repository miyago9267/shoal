"""header: magic, version, flags, payload length, payload."""
from .errors import ParseError
from .reader import Reader, ReaderError

MAGIC = b"FMT1"


def parse(data):
    r = Reader(data)
    try:
        magic = r.read(4)
        if magic != MAGIC:
            raise ParseError("bad magic %r" % magic)
        version = r.u8()
        flags = r.u16()
        length = r.u32()
    except ReaderError as exc:
        raise ParseError(str(exc)) from None
    payload = r.read(length)
    if len(payload) != length:
        raise ParseError("payload is %d bytes short" % (length - len(payload)))
    return {"version": version, "flags": flags, "payload": payload}


def build(version, flags, payload):
    return (
        MAGIC
        + bytes([version])
        + flags.to_bytes(2, "big")
        + len(payload).to_bytes(4, "big")
        + payload
    )


def has_flag(parsed, bit):
    return bool(parsed["flags"] & (1 << bit))
