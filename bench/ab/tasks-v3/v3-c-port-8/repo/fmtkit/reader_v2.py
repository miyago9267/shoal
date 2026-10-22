"""Cursor: the replacement for fmtkit.reader.Reader (docs/reader-v2.md)."""


class Truncated(Exception):
    """An exact read ran past the end of the data."""


class Cursor:
    """Forward-only cursor over bytes.

    ``endian`` is "little" or "big" and applies to ``uint``. Exact reads raise
    ``Truncated``; the ``*_upto`` and ``require=False`` forms tolerate the end.
    """

    def __init__(self, data, *, endian="little"):
        if endian not in ("little", "big"):
            raise ValueError("endian must be 'little' or 'big'")
        self._data = bytes(data)
        self._pos = 0
        self.endian = endian

    @property
    def offset(self):
        return self._pos

    @property
    def remaining(self):
        return len(self._data) - self._pos

    def done(self):
        return self._pos >= len(self._data)

    def peek(self, n=1):
        return self._data[self._pos : self._pos + n]

    def take_upto(self, n):
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def take(self, n):
        if n < 0 or self.remaining < n:
            raise Truncated("need %d bytes at offset %d, have %d" % (n, self._pos, self.remaining))
        return self.take_upto(n)

    def advance(self, n):
        self.take(n)

    def uint(self, size):
        if size not in (1, 2, 4):
            raise ValueError("size must be 1, 2 or 4")
        return int.from_bytes(self.take(size), self.endian)

    def text(self, n, encoding="utf-8"):
        return self.take(n).decode(encoding)

    def take_until(self, delim, *, require=True):
        index = self._data.find(delim, self._pos)
        if index < 0:
            if require:
                raise Truncated("delimiter %r not found after offset %d" % (delim, self._pos))
            return self.take_upto(self.remaining)
        chunk = self._data[self._pos : index]
        self._pos = index + len(delim)
        return chunk
