"""Deliver one event, retrying failed sends."""
import time

from .backoff import compute_backoff


class DeliveryFailed(Exception):
    pass


class Sender:
    def __init__(self, transport, config, sleep=time.sleep):
        self.transport = transport
        self.config = config
        self.sleep = sleep

    def send(self, event):
        """Send ``event``; return the attempt number that succeeded."""
        last_error = None
        for attempt in range(1, self.config["max_attempts"] + 1):
            try:
                self.transport(event)
                return attempt
            except OSError as exc:
                last_error = exc
                if attempt < self.config["max_attempts"]:
                    self.sleep(compute_backoff(attempt, self.config))
        raise DeliveryFailed(str(last_error))
