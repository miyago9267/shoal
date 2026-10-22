# shelf

A tiny personal library tracker. Books live in a single JSON file
(`library.json` by default) and are managed with a small CLI.

```sh
python3 -m shelf --db library.json add "Dune" --author "Frank Herbert" --year 1965
python3 -m shelf --db library.json list
python3 -m shelf --db library.json list --author herbert
python3 -m shelf --db library.json show 1
python3 -m shelf --db library.json remove 1
```

## Python API

```python
from shelf.model import Book
from shelf.storage import load, save

lib = load("library.json")          # missing file -> empty Library
lib.add(Book(id=0, title="Dune", author="Frank Herbert", year=1965))
save(lib, "library.json")
```

`Library.add` assigns the next free id when `id` is 0. See
[docs/FORMAT.md](docs/FORMAT.md) for the on-disk format.

## Tests

```sh
python3 -m unittest discover -s tests -t .
```
