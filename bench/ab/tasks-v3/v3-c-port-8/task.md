# Task: port the `fmtkit` parsers to the new reader

`fmtkit.reader_v2.Cursor` is the replacement for the old
`fmtkit.reader.Reader`; `docs/reader-v2.md` explains the differences. Port all
eight parsers (`bitmap`, `chunks`, `cstrings`, `header`, `kv`, `pascal`,
`tables`, `tlv`) so that none of them imports `fmtkit.reader`. Every parser must
keep returning exactly what it returned before for the same input, including
the cases it tolerated (short or unterminated data) and the cases where it
raised `ParseError`. Do not modify `fmtkit/reader.py`, `fmtkit/reader_v2.py`
or `fmtkit/errors.py`.
