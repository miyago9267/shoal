# deskapi

A tiny help-desk API with a hand-rolled router (no web framework). Handlers
receive a `Request` and return a `Response`; `deskapi.app.build_app()` wires
the routes, the in-memory store and the API token registry together.

Authentication uses bearer tokens of the form `<key_id>.<secret>`:

    Authorization: Bearer k1.s3cr3t

Users have a role of `agent` or `admin`. Every route under `/admin/` is meant
for admins only.

    from deskapi.app import build_app
    app = build_app()
    app.tokens.issue("k1", "s3cr3t", user_id=1)
    resp = app.handle("GET", "/tickets", headers={"Authorization": "Bearer k1.s3cr3t"})

`app.router.routes()` lists every registered `(method, pattern)` pair.

Run tests: `python3 -m unittest discover -s tests -t .`
