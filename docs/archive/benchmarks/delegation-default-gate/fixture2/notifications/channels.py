"""Channel registry: per-channel limits and quiet hours."""

from collections import namedtuple

Channel = namedtuple("Channel", "name per_minute quiet_start quiet_end")

CHANNELS = {
    "email": Channel("email", 120, None, None),
    "sms": Channel("sms", 30, 22, 7),
    "push": Channel("push", 600, 23, 6),
}

FALLBACK = Channel("plain", 60, None, None)


def get(name):
    """Channel settings for a name; unknown names get the fallback."""
    return CHANNELS.get(name, FALLBACK)


def in_quiet_hours(name, hour):
    """True when a non-urgent message should wait for the morning."""
    channel = get(name)
    if channel.quiet_start is None:
        return False
    if channel.quiet_start > channel.quiet_end:  # window wraps midnight
        return hour >= channel.quiet_start or hour < channel.quiet_end
    return channel.quiet_start <= hour < channel.quiet_end


def names():
    """Registered channel names, sorted."""
    return sorted(CHANNELS)
