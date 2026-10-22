# Reader v2

`fmtkit.reader_v2.Cursor` replaces `fmtkit.reader.Reader`. The names changed,
and so did three behaviours that parsers silently relied on. Port by reading
what each old call *did*, not just by renaming it.

## Construction and defaults

| | old `Reader(data)` | new `Cursor(data, *, endian="little")` |
|---|---|---|
| integer byte order | always big-endian | `endian` argument, default **little** |
| text encoding | always latin-1 | `encoding` argument per call, default **utf-8** |

Every format in this package is big-endian and latin-1. Say so explicitly.

## Method mapping

| old | new | difference |
|---|---|---|
| `tell()` | `offset` (property) | |
| `at_end()` | `done()` | |
| (none) | `remaining` (property) | bytes left |
| `peek()` -> next byte as int, or `None` | `peek(n=1)` -> up to `n` bytes as `bytes` | empty `b""` at the end instead of `None` |
| `read(n)` -> up to `n` bytes, short read allowed | `take_upto(n)` | same semantics, new name |
| (none) | `take(n)` | exactly `n` bytes or `Truncated` |
| `skip(n)` -> silently stops at the end | `advance(n)` | raises `Truncated` when fewer than `n` bytes remain |
| `u8()`, `u16()`, `u32()` | `uint(1)`, `uint(2)`, `uint(4)` | byte order from the cursor; raises `Truncated` |
| `string(n)` -> up to `n` bytes decoded, short read allowed | `text(n, encoding="utf-8")` | exactly `n` bytes or `Truncated` |
| `until(delim)` -> bytes before `delim`, consumes it; if absent returns the rest | `take_until(delim, *, require=True)` | with `require=True` a missing delimiter raises `Truncated`; pass `require=False` for the old behaviour |

## Errors

The old reader raised `ReaderError` only from `u8`/`u16`/`u32`. The new one
raises `Truncated` from every exact read (`take`, `advance`, `uint`, `text`,
`take_until(require=True)`). Neither is a `ParseError`; parsers translate.

## Porting checklist

1. Construct the cursor with the byte order the format uses.
2. For each `read`/`string`/`skip`/`until`, decide whether the old parser
   *tolerated* the short or missing data. If it did (a trailing unterminated
   string, a pixel block cut short, optional reserved bytes), keep the
   tolerance with `take_upto` / `take_until(require=False)`. If it checked the
   length itself and raised `ParseError`, you can now let `take`/`text`
   raise `Truncated` instead.
3. Catch `Truncated` where the parser caught `ReaderError`, and keep the
   `ParseError` message style.
4. Keep the decoded values identical, including latin-1 text.
