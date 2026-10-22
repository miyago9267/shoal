"""Retry policy for failing handler calls."""
import time


class RetryPolicy:
    def __init__(self, attempts=1, backoff=0.0, retry_on=(Exception,)):
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        self.attempts = attempts
        self.backoff = backoff
        self.retry_on = tuple(retry_on)

    def should_retry(self, error, attempt):
        return attempt < self.attempts and isinstance(error, self.retry_on)

    def delay(self, attempt):
        return self.backoff * (2 ** (attempt - 1))

    def sleep(self, attempt):
        pause = self.delay(attempt)
        if pause > 0:
            time.sleep(pause)


NO_RETRY = RetryPolicy(attempts=1)
