"""Mailer: deliver messages through a flaky transport."""
from .legacy import legacy_log

MAX_ATTEMPTS = 3


def render(template, **ctx):
    out = template
    for key, value in ctx.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def send(transport, message):
    """``transport(message)`` may raise OSError. True when delivered."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        level = 20 if attempt == 1 else 30
        legacy_log("sending to %s (attempt %d)" % (message["to"], attempt), level)
        try:
            transport(message)
            return True
        except OSError:
            continue
    legacy_log(
        "giving up on %s after %d attempts" % (message["to"], MAX_ATTEMPTS), 40
    )
    return False


def send_batch(transport, messages):
    """Send each message; returns how many were delivered."""
    return sum(1 for m in messages if send(transport, m))


def addresses(messages):
    return sorted({m["to"] for m in messages})
