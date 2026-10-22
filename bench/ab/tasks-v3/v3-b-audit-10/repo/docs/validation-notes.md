# Validation notes

Background for people touching the handlers.

## Why the handlers are not all alike

`signup`, `transfer`, `schedule`, `upload`, `search` and `coupon` were written
before `hq/validate.py` existed. They validate by hand, each with a few private
helpers. `profile`, `address`, `rating` and `invite` were written afterwards and
lean on the shared helpers. Both styles have to obey `docs/handlers.md`; do not
rewrite a handler only to change its style.

## Things that have bitten us before

* `bool` is a subclass of `int`. `isinstance(True, int)` is true, so an integer
  check needs an explicit bool test.
* `re.match` anchors only at the start. `$` matches before a trailing newline,
  so `^abc$` accepts `"abc\n"`. Use `fullmatch`.
* Range checks written as `a <= x <= b` are easy to get off by one at the top
  end; check the contract table, not the neighbouring handler.
* `if not value` treats whitespace-only strings as present. Strip first, then
  test for emptiness.
* "Contains an @ and a dot" is not an email check.
* Blacklisting `../` at the front of a filename lets `a/../b` and `a\b`
  through. The contract forbids separators outright.

## Error shape

Every failure is a `ValidationError(field, message)`. Callers group errors by
`field`, so a wrong field name is a bug even when the input was rejected. When
two fields are wrong, the first one in the handler's own check order is
reported; the order is part of the contract documented per handler.

## Adding a handler

1. Add the contract to `docs/handlers.md`.
2. Write `hq/handlers/<name>.py` exposing `handle(payload)`.
3. Register it in `hq/handlers/__init__.py`.
4. Add `tests/test_<name>.py` with one valid case and one rejection per field.
