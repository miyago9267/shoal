# utilkit

Small stand-alone utilities: slugs, durations, text wrapping, byte sizes, CSV
lines, version comparison, retry backoff, path normalisation, range merging and
a tiny template engine.

Each module in `utilkit/` carries a `TODO(fix)` comment above the function that
needs work, describing the behaviour it should have. The modules are
independent of each other except where a helper in the same file builds on the
function with the TODO.

Only smoke tests exist so far (`tests/`); see `docs/style.md` for conventions.

Run the tests with `python3 -m unittest discover -s tests -t .`.
