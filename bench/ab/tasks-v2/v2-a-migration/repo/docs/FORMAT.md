# On-disk format

The library file is a JSON object:

```json
{
  "schema": 1,
  "books": [
    {"id": 1, "title": "Dune", "author": "Frank Herbert", "year": 1965}
  ]
}
```

| field    | type   | notes                                  |
|----------|--------|----------------------------------------|
| `id`     | int    | positive, unique within the file       |
| `title`  | string | non-empty                              |
| `author` | string | non-empty                              |
| `year`   | int    | publication year, `null` when unknown  |

`schema` is the format version. Files with any other `schema` value are
rejected with `StorageError`. Writes go to a temporary file first and are then
renamed over the target, so a crash never leaves a half-written library.
