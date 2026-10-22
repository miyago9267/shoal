"""durations: parse human duration strings into seconds."""
import re

_UNITS = {"s": 1, "m": 60, "h": 3600}


def format_duration(seconds):
    """Inverse of parse_duration for whole seconds: 5400 -> "1h30m"."""
    seconds = int(seconds)
    if seconds <= 0:
        return "0s"
    out = []
    for unit, size in (("h", 3600), ("m", 60), ("s", 1)):
        count, seconds = divmod(seconds, size)
        if count:
            out.append("%d%s" % (count, unit))
    return "".join(out)


# TODO(fix): parse_duration must
#   * support the units s, m, h, d (86400) and w (604800),
#   * accept decimals ("1.5h" is 5400) and whitespace between parts ("1h 30m"),
#   * return an int when the total is a whole number of seconds, else a float,
#   * raise ValueError for an empty string, a number without unit, an unknown
#     unit ("5x") or any other garbage. Today garbage is silently ignored.


def parse_duration(text):
    """Seconds in ``text`` such as "1h30m"."""
    total = 0
    for number, unit in re.findall(r"(\d+)([smh])", text):
        total += int(number) * _UNITS[unit]
    return total


def total(parts):
    """Sum several duration strings."""
    return sum(parse_duration(p) for p in parts)


def longest(parts):
    """The duration string that denotes the most time."""
    return max(parts, key=parse_duration)


def clamp(seconds, low, high):
    """Clamp a number of seconds into [low, high]."""
    if low > high:
        raise ValueError("low > high")
    return max(low, min(high, seconds))


def split_parts(seconds):
    """(hours, minutes, seconds) of a whole number of seconds."""
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return hours, minutes, secs


def clock(seconds):
    """H:MM:SS text for a whole number of seconds."""
    return "%d:%02d:%02d" % split_parts(seconds)


def ratio(part, whole):
    """How much of ``whole`` the ``part`` is, as a float in [0, inf)."""
    if whole == 0:
        raise ValueError("whole is zero")
    return part / whole
