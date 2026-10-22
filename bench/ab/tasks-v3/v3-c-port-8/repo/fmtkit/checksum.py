"""Cheap integrity helpers for encoded documents."""
import zlib


def xor8(data):
    value = 0
    for byte in data:
        value ^= byte
    return value


def adler(data):
    return zlib.adler32(data) & 0xFFFFFFFF


def crc(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def fingerprint(data):
    """Short, stable, human-comparable id for a blob."""
    return "%08x-%02x-%d" % (crc(data), xor8(data), len(data))


def same(a, b):
    return len(a) == len(b) and crc(a) == crc(b) and a == b


def verify(data, expected):
    return fingerprint(data) == expected
