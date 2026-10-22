# Porting notes

A worked example, then a list of traps. The example is `kv`, which is not one
of the tricky ones.

## Example

Before:

    r = Reader(data)
    while not r.at_end():
        line = r.until(b"\n").decode("latin-1")

After:

    r = Cursor(data)
    while not r.done():
        line = r.take_until(b"\n", require=False).decode("latin-1")

Three things happened. `at_end` became `done`. `until` kept its "return the
rest when the delimiter is missing" behaviour only because `require=False` was
added. The decode stayed latin-1 because `take_until` returns bytes; had the
parser used `text(n)`, the default encoding would have changed to utf-8.

## Traps

* **Byte order.** `Cursor` defaults to little-endian. The formats here are all
  big-endian. A parser that forgets `endian="big"` still runs and returns wrong
  numbers for any value above 255.
* **Short reads.** `Reader.read(n)` and `Reader.string(n)` returned fewer
  bytes at the end of the data without complaint. Some parsers compare the
  length afterwards and raise `ParseError`, some rely on the short result. The
  exact reads `take` and `text` raise `Truncated`; make sure it is caught
  where the old `ReaderError` was.
* **`skip`.** The old `skip` clamped to the end. `advance` raises. A parser
  that skipped optional trailing bytes needs `take_upto` instead.
* **`peek`.** The old `peek` returned an `int` or `None`. The new one returns
  `bytes`, which is empty (and falsy) at the end. `peek() == 0` and
  `peek() is None` checks must be rewritten, not just renamed.
* **Error type.** `Truncated` is not a `ParseError`. Callers of `parse` only
  know about `ParseError`.
* **Offsets in messages.** `tell()` is now the `offset` property; `remaining`
  is new and saves a subtraction.

## Order of work

1. Port one parser, run `tests/` for it, then the next.
2. Keep each parser's public functions (`parse`, helpers) unchanged.
3. Do not touch `reader.py` or `reader_v2.py`; they have their own tests.
4. When all eight are done, nothing in `fmtkit/` except `reader.py` itself
   should mention `Reader` or `ReaderError`.
