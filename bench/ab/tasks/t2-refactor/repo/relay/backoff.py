"""Retry wait calculation."""


def compute_backoff(attempt, config):
    """Seconds to wait after failed ``attempt`` (1-based).

    Doubles from ``backoff_base`` and is capped at ``max_delay``.
    """
    if attempt < 1:
        raise ValueError("attempt is 1-based")
    delay = config["backoff_base"] * (2 ** (attempt - 1))
    return min(delay, config["max_delay"])


def schedule(config):
    """Full list of waits used between attempts for one event."""
    return [compute_backoff(n, config) for n in range(1, config["max_attempts"])]
