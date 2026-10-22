# relay

Delivers outbound webhook events with retries.

Configuration is a JSON file merged over `relay.config.DEFAULTS`:

| key            | default | meaning                                  |
|----------------|---------|------------------------------------------|
| `max_attempts` | 5       | attempts before an event is dead-lettered |
| `backoff_base` | 1.0     | seconds to wait after the first failure  |
| `max_delay`    | 60.0    | upper bound for any single wait          |

Waits double on every failed attempt: see `relay.backoff.compute_backoff`.

Run tests: `python3 -m unittest discover -s tests -t .`
