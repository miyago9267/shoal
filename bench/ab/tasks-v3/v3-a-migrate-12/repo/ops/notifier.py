"""Notifier: fan a message out over several channels."""
from .legacy import legacy_log


def notify(user, text, channels):
    """``channels``: name -> callable(user, text). Returns deliveries."""
    delivered = 0
    for cname, send in channels.items():
        try:
            send(user, text)
        except Exception as exc:
            legacy_log("channel %s failed: %s" % (cname, exc), 40)
            continue
        delivered += 1
        legacy_log("sent to %r via %s" % (user, cname), 20)
    if not delivered:
        legacy_log(
            "dropped notification for %r (%d channels)" % (user, len(channels)),
            level=30,
        )
    return delivered


def broadcast(users, text, channels):
    return {u: notify(u, text, channels) for u in users}


def undelivered(result):
    return sorted(u for u, n in result.items() if n == 0)
