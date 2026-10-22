class PoolClosed(RuntimeError):
    """Raised when submitting to a pool that is shutting down."""


class HandlerFailed(Exception):
    def __init__(self, item, error, attempts):
        super().__init__(f"{item!r} failed after {attempts} attempt(s): {error!r}")
        self.item = item
        self.error = error
        self.attempts = attempts
