"""The original reader (deprecated, see docs/reader-v2.md)."""


class ReaderError(Exception):
    """Not enough bytes for a fixed-size read."""


class Reader:
    """Big-endian, latin-1 reader over a bytes object."""

    def __init__(self, data):
        self._data = bytes(data)
        self._pos = 0

    def tell(self):
        return self._pos

    def at_end(self):
        return self._pos >= len(self._data)

    def peek(self):
        """Next byte as an int, or None at the end."""
        if self.at_end():
            return None
        return self._data[self._pos]

    def read(self, n):
        """Up to ``n`` bytes; a short read is not an error."""
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def skip(self, n):
        """Skip up to ``n`` bytes, stopping silently at the end."""
        self._pos = min(len(self._data), self._pos + n)

    def _int(self, size):
        chunk = self.read(size)
        if len(chunk) != size:
            self._pos -= len(chunk)
            raise ReaderError("need %d bytes at offset %d" % (size, self._pos))
        return int.from_bytes(chunk, "big")

    def u8(self):
        return self._int(1)

    def u16(self):
        return self._int(2)

    def u32(self):
        return self._int(4)

    def string(self, n):
        """Up to ``n`` bytes decoded as latin-1."""
        return self.read(n).decode("latin-1")

    def until(self, delim):
        """Bytes before ``delim``; the delimiter is consumed.

        If ``delim`` never appears the rest of the data is returned.
        """
        index = self._data.find(delim, self._pos)
        if index < 0:
            return self.read(len(self._data))
        chunk = self._data[self._pos : index]
        self._pos = index + len(delim)
        return chunk
