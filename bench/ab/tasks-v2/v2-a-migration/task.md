We need to move `shelf`'s library file to schema version 2. Existing users have schema 1 files on
disk and those must keep working.

Schema 2 changes each book record like this:

- the `year` field is renamed to `published` (same meaning: an integer year, or `null` when unknown);
- a new required field `format`, one of `"print"`, `"ebook"` or `"audio"`.

What we expect:

- `Book` follows the new schema: `Book(id=..., title=..., author=..., published=..., format=...)`,
  where `published` defaults to `None` and `format` defaults to `"print"`. An invalid `format` is a
  `ValidationError`.
- `shelf.storage.load` accepts both schema 1 and schema 2 files. Schema 1 records are migrated on
  load: `year` becomes `published` and `format` becomes `"print"`. A schema 2 record without
  `format`, or with an invalid one, is rejected with `StorageError`, as is any other schema version.
- `shelf.storage.save` always writes schema 2. Loading a file must never modify it; a schema 1 file is
  only upgraded the next time something is saved.
- `Library.in_year(year)` keeps working and matches on the published year.
- CLI: `add` takes `--published YEAR` (keep `--year` working as an alias) and `--format FORMAT`
  (default `print`). `list` gets a `--format FORMAT` filter next to the existing filters, and the
  `list`/`show` output include the format.
- Update the README and `docs/FORMAT.md` to describe schema 2 and the migration.
