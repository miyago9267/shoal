# Module notes

What each module is for, and which function is waiting on its `TODO(fix)`.

## slug

`slugify(text, max_len=None)` turns titles into URL slugs. `is_slug` validates
one, `unique_slug`/`slugs` de-duplicate a list of titles by appending `-2`,
`-3`. Pending: accent folding, trimming, `max_len`.

## durations

`parse_duration` reads strings like `1h30m`; `format_duration` writes whole
seconds back. `total` and `longest` build on `parse_duration`. Pending: more
units, decimals, strict errors.

## wrap

`wrap(text, width)` is a greedy text wrapper used for terminal output.
`indent`, `fill`, `center`, `dedent_lines` and `truncate` are small
companions. Pending: paragraph handling and long words.

## bytesize

`human_size(n)` renders byte counts for people; `parse_size` is the common-case
inverse. Pending: unit names, rounding carry, negative numbers, type errors.

## csvline

`join_csv_line` quotes fields correctly. `split_csv_line` is the reading half
and does not understand quotes yet.

## versions

`compare_versions` is a three-way comparison used by `sort_versions`, `newest`
and `satisfies`. It currently compares the raw strings.

## retry

`backoff_delays` produces the wait before each retry. `schedule`,
`describe`, `attempts_within` and `constant` are conveniences. Pending: cap and
jitter.

## paths

POSIX path helpers without touching the filesystem. `join`, `is_inside`,
`split`, `basename`, `extension` and `parents` all go through `normalize`, so
fixing `normalize` fixes them.

## ranges

Inclusive integer ranges. `total_length` and `gaps` go through `merge_ranges`.
Pending: adjacency, reversed pairs, immutability.

## template

`render(template, ctx)` fills `{{ name }}` placeholders. `variables`,
`missing`, `safe_render` and `render_many` sit on top. Pending: dotted names,
default filter, strict missing variables, escaping.

## pipeline and cli

`pipeline` runs a function over many inputs and reports failures per index.
`cli` exposes five of the utilities on the command line.

## Working agreement

* Fix one module at a time and keep its helpers green.
* Remove the `TODO(fix)` comment when the behaviour is in.
* Do not widen a function's signature beyond what its comment asks for.
* When behaviour is ambiguous, the comment wins over the docstring.
