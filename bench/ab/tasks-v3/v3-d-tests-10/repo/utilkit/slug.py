"""slug: URL-safe slugs from free text."""
import re

SEPARATOR = "-"


def is_slug(text):
    """True when ``text`` is already a clean slug."""
    return bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", text))


# TODO(fix): slugify must
#   * fold accents to ASCII first ("Cafe" with an acute e becomes "cafe"),
#   * collapse every run of non-alphanumeric characters into one "-",
#   * never start or end with "-",
#   * honour max_len (None means unlimited): keep the longest prefix made of
#     whole words (split at "-") that fits in max_len; if even the first word is
#     longer than max_len, cut that word at max_len. The result never ends in "-".


def slugify(text, max_len=None):
    """Return a slug for ``text``."""
    return re.sub(r"[^a-z0-9]+", SEPARATOR, text.lower())


def unique_slug(base, taken):
    """``base`` or ``base-2``, ``base-3`` ... whichever is not in ``taken``."""
    if base not in taken:
        return base
    n = 2
    while "%s-%d" % (base, n) in taken:
        n += 1
    return "%s-%d" % (base, n)


def slugs(titles):
    """Slugify many titles, making each result unique."""
    taken = set()
    out = []
    for title in titles:
        slug = unique_slug(slugify(title), taken)
        taken.add(slug)
        out.append(slug)
    return out


def common_prefix(slugs_):
    """Longest shared run of whole words among several slugs."""
    if not slugs_:
        return ""
    split = [s.split(SEPARATOR) for s in slugs_]
    out = []
    for parts in zip(*split):
        if len(set(parts)) != 1:
            break
        out.append(parts[0])
    return SEPARATOR.join(out)


def words(slug_):
    """Words of a slug; empty slug has none."""
    return slug_.split(SEPARATOR) if slug_ else []


def join_words(parts):
    """Build a slug from already clean words, skipping empty ones."""
    return SEPARATOR.join(p for p in parts if p)


def with_suffix(slug_, suffix):
    return join_words([slug_, suffix])
