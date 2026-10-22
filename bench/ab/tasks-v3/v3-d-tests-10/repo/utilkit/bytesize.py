"""bytesize: human readable byte counts."""

UNITS = ["B", "KiB", "MiB", "GiB", "TiB"]


def parse_size(text):
    """Inverse for the common cases: "1.5 KiB" -> 1536."""
    number, _, unit = text.strip().partition(" ")
    factor = 1024 ** UNITS.index(unit or "B")
    return int(round(float(number) * factor))


# TODO(fix): human_size(n) must
#   * use the binary units B, KiB, MiB, GiB, TiB (nothing above TiB),
#   * show at most one decimal and drop a trailing ".0" ("1 KiB", "1.5 KiB"),
#   * carry on rounding: 1048575 bytes is "1 MiB", never "1024 KiB",
#   * print plain integers below 1024 ("1023 B"),
#   * keep the sign for negative sizes ("-1.5 KiB"),
#   * raise TypeError for bool or non-numbers.


def human_size(n):
    """Render ``n`` bytes."""
    value = n
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024:
            return "%.1f %s" % (value, unit)
        value /= 1024
    return "%.1f PB" % value


def total(sizes):
    return sum(sizes)


def biggest(sizes):
    return max(sizes) if sizes else 0


def percent(part, whole):
    """Integer percentage of ``part`` in ``whole`` (0 when whole is 0)."""
    return 0 if whole == 0 else int(part * 100 // whole)


def fits(size, capacity):
    return size <= capacity


def split_evenly(total_bytes, parts):
    """Sizes of ``parts`` chunks that add up to ``total_bytes``."""
    if parts <= 0:
        raise ValueError("parts must be positive")
    base, extra = divmod(total_bytes, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def units_for(n):
    """Index into UNITS that human_size would pick for ``n`` (before rounding)."""
    index = 0
    value = abs(n)
    while value >= 1024 and index < len(UNITS) - 1:
        value /= 1024
        index += 1
    return index
