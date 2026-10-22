# Handler contracts

General rules, true for every handler:

* The payload is a dict; anything else is a `ValidationError` on field
  `payload`.
* A required field that is missing or `None` is a `ValidationError` on that
  field. Wrong types are also `ValidationError`, never `TypeError`/`KeyError`.
* `bool` is not an integer. Integer fields reject `True` and `False`.
* Strings are stripped before they are measured or stored, unless stated.
* On success the handler returns a new dict with normalised values and never
  mutates the payload.

## signup

| field | rule |
|---|---|
| `email` | string, stripped and lowercased. One `@`, non-empty local part, domain made of non-empty dot-separated labels with at least one dot, at most 254 characters |
| `age` | int, 13 to 120 |
| `name` | string, 1 to 50 characters |

Returns `{"email", "age", "name"}`.

## transfer

| field | rule |
|---|---|
| `src`, `dst` | non-empty strings, must differ |
| `amount_cents` | int, 1 to 1,000,000 |

Returns `{"src", "dst", "amount_cents", "fee_cents"}`; the fee is
`amount_cents // 100`.

## schedule

| field | rule |
|---|---|
| `date` | `YYYY-MM-DD`, exactly that shape, and a real calendar date |
| `hour` | int, 0 to 23 |
| `duration_min` | int, 1 to 480 |

Returns `{"date", "hour", "duration_min", "end_minute"}` where `end_minute` is
`hour * 60 + duration_min`.

## upload

| field | rule |
|---|---|
| `filename` | 1 to 100 characters; no `/`, no `\`, no NUL; not `.` or `..` |
| `size` | int, 1 to 10,485,760 |
| `content_type` | one of `image/png`, `image/jpeg`, `text/plain`, `application/pdf` |

Returns `{"filename", "size", "content_type"}`.

## search

| field | rule |
|---|---|
| `query` | string, 1 to 200 characters after stripping (blank is invalid) |
| `limit` | optional int, 1 to 100, default 20 |
| `offset` | optional int, at least 0, default 0 |

Returns `{"query", "limit", "offset"}`.

## coupon

| field | rule |
|---|---|
| `code` | exactly 4 to 12 characters from `A-Z0-9`; no surrounding whitespace is tolerated and nothing may follow the code, not even a newline |
| `percent` | int, 1 to 90 |
| `max_uses` | optional int, at least 1 |

Returns `{"code", "percent", "max_uses"}` (`max_uses` is `None` when absent).

## profile

| field | rule |
|---|---|
| `name` | string, 1 to 50 characters |
| `bio` | optional string, at most 280 characters; empty becomes `None` |
| `tags` | optional list of at most 5 distinct strings (compared case-insensitively), each 1 to 20 characters of `a-z0-9-` after lowercasing |

Returns `{"name", "bio", "tags"}` with tags lowercased in the original order.

## address

| field | rule |
|---|---|
| `line1` | string, 1 to 80 characters |
| `city` | string, 1 to 40 characters |
| `country` | one of `US`, `TW`, `JP`, `GB` |
| `zip` | must match the country: US `12345` or `12345-6789`; TW 3 digits plus optional 2 or 3 digits; JP `123-4567`; GB postcode such as `SW1A 1AA` (uppercase) |

Returns the four fields normalised.

## rating

| field | rule |
|---|---|
| `item_id` | int, at least 1 |
| `stars` | int, 1 to 5 |
| `comment` | optional string, at most 500 characters; empty becomes `None` |

Returns `{"item_id", "stars", "comment"}`.

## invite

| field | rule |
|---|---|
| `emails` | list of 1 to 20 valid emails (same rule as signup), lowercased, duplicates removed keeping the first |
| `role` | optional, one of `viewer`, `editor`, `admin`; default `viewer` |

Returns `{"emails", "role"}`.
