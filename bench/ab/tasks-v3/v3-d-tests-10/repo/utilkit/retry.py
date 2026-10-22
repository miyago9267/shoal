"""retry: backoff schedules for retried operations."""


def total_delay(delays):
    return sum(delays)


def should_retry(exc, retryable):
    """True when ``exc`` is an instance of one of the ``retryable`` classes."""
    return isinstance(exc, tuple(retryable))


# TODO(fix): backoff_delays(attempts, base, factor, cap, jitter, rng) must
#   * return attempts delays: base, base*factor, base*factor**2 ... ([] for 0),
#   * limit every delay to cap when cap is not None (cap applies before jitter),
#   * when jitter is greater than 0, multiply each delay by 1 - jitter*rng(),
#     calling rng() once per delay in order (rng returns a float in [0, 1)),
#   * raise ValueError when attempts < 0, jitter is outside [0, 1], or jitter > 0
#     and no rng was given.


def backoff_delays(attempts, base=0.5, factor=2.0, cap=None, jitter=0.0, rng=None):
    """Delays (seconds) to wait before each retry."""
    return [base * factor**i for i in range(attempts)]


def schedule(attempts, **kwargs):
    """Cumulative wait before each attempt."""
    out = []
    running = 0.0
    for delay in backoff_delays(attempts, **kwargs):
        running += delay
        out.append(running)
    return out


def describe(delays):
    """Short text such as "3 retries, 7.0s total"."""
    return "%d retries, %.1fs total" % (len(delays), total_delay(delays))


def attempts_within(budget, base=0.5, factor=2.0):
    """How many attempts fit in ``budget`` seconds without a cap or jitter."""
    n = 0
    spent = 0.0
    while True:
        spent += base * factor**n
        if spent > budget:
            return n
        n += 1


def constant(attempts, delay):
    return [delay] * attempts
