"""Small helpers used by several modules and by the command line."""


def chunks(items, size):
    """Yield consecutive lists of at most ``size`` items."""
    if size <= 0:
        raise ValueError("size must be positive")
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def clamp(value, low, high):
    if low > high:
        raise ValueError("low > high")
    return max(low, min(high, value))


def human_duration(seconds):
    """Render seconds as 1h02m03s style text, dropping empty leading units."""
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "%dh%02dm%02ds" % (hours, minutes, secs)
    if minutes:
        return "%dm%02ds" % (minutes, secs)
    return "%ds" % secs


def group_by(items, key):
    out = {}
    for item in items:
        out.setdefault(key(item), []).append(item)
    return out


def first(items, default=None):
    for item in items:
        return item
    return default


def flatten(nested):
    out = []
    for item in nested:
        if isinstance(item, (list, tuple)):
            out.extend(flatten(item))
        else:
            out.append(item)
    return out


def dedupe(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
