"""Text normalisation helpers for display, not for validation."""
import unicodedata


def squash_spaces(text):
    """Collapse any run of whitespace into one space and strip the ends."""
    return " ".join(text.split())


def title_case(text):
    small = {"a", "an", "and", "of", "the", "in", "on"}
    words = squash_spaces(text).lower().split(" ")
    out = []
    for i, word in enumerate(words):
        out.append(word if i and word in small else word.capitalize())
    return " ".join(out)


def ascii_fold(text):
    """Drop accents: cafe for the accented spelling."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def initials(name, limit=2):
    parts = [p for p in squash_spaces(name).split(" ") if p]
    return "".join(p[0].upper() for p in parts[:limit])


def truncate(text, width, marker="..."):
    if width < len(marker):
        raise ValueError("width too small")
    if len(text) <= width:
        return text
    return text[: width - len(marker)] + marker


def mask_email(email):
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return "*" * len(local) + "@" + domain
    return local[0] + "*" * (len(local) - 2) + local[-1] + "@" + domain


def slug(text):
    folded = ascii_fold(text).lower()
    out = []
    for ch in folded:
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")
