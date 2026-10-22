# fmtkit

Parsers for eight small binary and text formats. Every parser exposes
`parse(data: bytes)` and raises `fmtkit.errors.ParseError` on malformed or
truncated input.

The parsers were written against the original `fmtkit.reader.Reader`. That
class is being retired in favour of `fmtkit.reader_v2.Cursor`; the migration
guide is `docs/reader-v2.md`. `reader_v2` is finished and tested; the parsers
are not ported yet.

Run the tests with `python3 -m unittest discover -s tests -t .`.
