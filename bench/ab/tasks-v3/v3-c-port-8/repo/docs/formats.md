# Formats

All integers are big-endian. All text is latin-1. Every parser returns plain
Python values and raises `ParseError` for input it cannot accept.

## tlv

Repeated records: type (u8), length (u16), value (`length` bytes). Zero
records is valid. A record whose value or header is cut off is an error.
Result: list of `(type, value)`.

## cstrings

NUL-terminated strings back to back. The last string may be missing its
terminator and is still returned. Empty input gives an empty list; consecutive
NULs give empty strings. Result: list of `str`.

## header

Magic `FMT1`, version (u8), flags (u16), payload length (u32), payload. The
payload must be complete; bytes after it are ignored. Result: dict with
`version`, `flags`, `payload`.

## kv

Lines of `key=value`, newline separated (a carriage return before the newline
is dropped). Keys and values are stripped. The final line needs no newline.
Blank lines are skipped. A non-blank line without `=` is an error. Result:
dict, later keys overwrite earlier ones.

## pascal

Count (u16) followed by that many strings, each with a one-byte length prefix.
Every string must be complete and nothing may follow the last one. Result:
list of `str`.

## bitmap

Width (u16), height (u16), then `width * height` pixel bytes. A pixel block
that is too short is padded with zero bytes; extra bytes are ignored. More
than 2**20 pixels is an error. Result: dict with `width`, `height`, `pixels`.

## tables

Row count (u32) followed by rows: id (u16), flag (u8), name (u8 length +
latin-1 bytes), two reserved bytes. The reserved bytes of the very last row may
be missing. Fewer rows than announced is an error. Result: list of dicts with
`id`, `flag`, `name`.

## chunks

Sequence of chunks: length (u32), tag (4 bytes), payload, CRC-32 (u32) over tag
plus payload. Parsing stops at the chunk tagged `END `; anything after it is
ignored. Running out of data before `END` is an error, as is a CRC mismatch.
Result: list of `(tag, payload)` including the `END ` chunk.
