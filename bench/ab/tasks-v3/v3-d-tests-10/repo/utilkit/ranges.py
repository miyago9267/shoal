"""ranges: inclusive integer ranges."""


def contains(ranges, value):
    return any(a <= value <= b for a, b in ranges)


# TODO(fix): merge_ranges(ranges) takes (start, end) pairs of ints, both ends
# inclusive, and must
#   * accept them in any order and swap a pair whose start > end,
#   * merge overlapping AND adjacent pairs ((1, 3) and (4, 6) become (1, 6)),
#   * return a new sorted list of tuples and never modify the input,
#   * return [] for empty input.


def merge_ranges(ranges):
    """Merge ``ranges`` into disjoint ones."""
    out = []
    for start, end in sorted(ranges):
        if out and start < out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out


def total_length(ranges):
    """Number of integers covered."""
    return sum(b - a + 1 for a, b in merge_ranges(ranges))


def gaps(ranges, low, high):
    """Integer ranges inside [low, high] not covered by ``ranges``."""
    out = []
    cursor = low
    for a, b in merge_ranges(ranges):
        if a > cursor:
            out.append((cursor, min(a - 1, high)))
        cursor = max(cursor, b + 1)
        if cursor > high:
            break
    if cursor <= high:
        out.append((cursor, high))
    return [g for g in out if g[0] <= g[1]]


def overlaps(a, b):
    """True when two (start, end) pairs share at least one integer."""
    a0, a1 = min(a), max(a)
    b0, b1 = min(b), max(b)
    return a0 <= b1 and b0 <= a1


def span(ranges):
    """(lowest, highest) covered integer; raises ValueError when empty."""
    if not ranges:
        raise ValueError("no ranges")
    flat = [x for pair in ranges for x in pair]
    return min(flat), max(flat)


def clip(ranges, low, high):
    out = []
    for a, b in ranges:
        a, b = min(a, b), max(a, b)
        a, b = max(a, low), min(b, high)
        if a <= b:
            out.append((a, b))
    return out
