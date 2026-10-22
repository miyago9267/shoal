"""Drain a queue of events through a Sender."""
from .backoff import schedule
from .sender import DeliveryFailed, Sender


def drain(queue, transport, config, sleep):
    """Send every event; return (delivered, dead_lettered) lists."""
    sender = Sender(transport, config, sleep=sleep)
    delivered, dead = [], []
    while queue:
        event = queue.pop(0)
        try:
            sender.send(event)
            delivered.append(event)
        except DeliveryFailed:
            dead.append(event)
    return delivered, dead


def worst_case_wait(config):
    """Longest total time one event can spend waiting between retries."""
    return sum(schedule(config))
