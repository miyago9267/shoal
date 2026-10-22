# Task: audit the `hq` handlers

Audit every handler in `hq/handlers/` against `docs/handlers.md` and fix the
validation bugs you find. Some handlers are correct; leave their behaviour
alone. Do not change `hq/errors.py` or `hq/router.py`. Bad input must always
raise `ValidationError` with the offending field name, and valid input must keep
producing the same normalised result as before.
