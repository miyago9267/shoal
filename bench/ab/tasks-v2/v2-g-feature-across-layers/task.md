Listing notes uses `limit`/`offset`, so clients that page through the list while other people add
notes see duplicates or miss notes. Please replace offset pagination with cursor pagination in
every layer (repository, service, HTTP handler and CLI). The order stays the same as today:
newest first by `created_at`, ties broken by the higher id first. Remember that imported notes
can carry an older `created_at` than notes created before them.

- `NoteService.list_notes(tag=None, limit=20, cursor=None)` returns `(notes, next_cursor)`.
  `next_cursor` is an opaque string (not a raw id) to pass back for the following page, and
  `None` exactly when there are no more notes. An invalid cursor raises `ValueError`.
- `GET /notes?limit=N&cursor=C&tag=T` returns `{"items": [...], "next_cursor": "..." | null}`;
  an invalid cursor is a 400 with an `error` message.
- `python3 -m notes --db FILE list --limit N [--cursor C] [--tag T]` prints the notes as today
  and, when there are more, a last line `next cursor: <cursor>`. A bad cursor exits with code 2.

Walking all pages must return every note that existed when the walk started exactly once and
in order, and never repeat a note, even if notes are created, or the last note of a page is
deleted, between page requests. `limit` keeps its 1-100 validation, and the tag filter must keep
working with cursors.
