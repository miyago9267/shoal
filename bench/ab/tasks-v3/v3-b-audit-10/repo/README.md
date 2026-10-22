# hq

Request handlers for a small back office. Each handler validates a JSON-like
payload and returns a normalised dict, or raises `hq.errors.ValidationError`
whose `field` names the offending field.

* `hq/router.py` - `dispatch(name, payload)`
* `hq/validate.py` - shared validation helpers (newer handlers use them)
* `hq/handlers/` - one module per handler, each exposing `handle(payload)`
* `docs/handlers.md` - the contract every handler must meet

Some handlers predate `validate.py` and do their own checks.

Other modules:

* `hq/batch.py` - run many requests and collect per-request outcomes
* `hq/normalize.py` - display-only text helpers (not used for validation)
* `docs/validation-notes.md` - pitfalls seen in earlier reviews

## Conventions

* Handlers never mutate the payload they receive.
* Handlers do not catch `ValidationError`; the caller decides what to do.
* New code should prefer the helpers in `hq/validate.py` over hand-rolled checks.
* Tests live in `tests/`, one file per handler plus one per support module.

Run the tests with `python3 -m unittest discover -s tests -t .`.
