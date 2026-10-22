# Changelog

## Unreleased

* Add `fmtkit.reader_v2.Cursor` with exact and tolerant read forms.
* Add `docs/reader-v2.md` describing how old `Reader` calls map to `Cursor`.
* Add `fmtkit.frame` and `fmtkit.checksum` helpers.
* Parsers still use `fmtkit.reader.Reader`; porting is tracked separately.

## 0.3

* Add the `chunks` and `tables` parsers.
* `bitmap` zero-pads short pixel blocks instead of failing.
* `cstrings` accepts an unterminated final string.

## 0.2

* Add `registry` and `describe` for the command line.
* `kv` strips carriage returns before newlines.

## 0.1

* First release: `tlv`, `header`, `pascal`, `cstrings`, `kv`, `bitmap`.
