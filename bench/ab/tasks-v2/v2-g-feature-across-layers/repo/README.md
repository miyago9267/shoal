# notes

A small note-taking service on top of SQLite (stdlib only), in three layers:

- `notes/repository.py` – SQL access (`NoteRepository`)
- `notes/service.py` – validation and business rules (`NoteService`)
- `notes/http.py` – a framework-free JSON handler: `handle(service, method, path, query, body)`
  returns `(status, body_dict)`
- `notes/cli.py` – `python3 -m notes --db notes.sqlite add "Title" --tag work`

`notes.app.build_service(db_path=":memory:", clock=None)` wires the layers;
`clock` is a zero-argument callable returning an aware `datetime`.

Notes are always listed newest first (by `created_at`, ties broken by the
higher id first). Listing currently pages with `limit`/`offset`:

    GET /notes?limit=20&offset=40&tag=work
    -> {"items": [...], "total": 123}

Run tests: `python3 -m unittest discover -s tests -t .`
