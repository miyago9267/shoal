"""paths: POSIX style path helpers (no filesystem access)."""
import re


def split(path):
    """(directory, name) of a normalised path."""
    path = normalize(path)
    head, _, tail = path.rpartition("/")
    return (head or ("/" if path.startswith("/") else ".")), tail


# TODO(fix): normalize(path) must
#   * collapse repeated slashes and drop "." segments,
#   * resolve ".." against the previous segment,
#   * keep a leading "/" and never climb above the root ("/../a" is "/a"),
#   * keep leading ".." of a relative path ("../a", "a/../../b" is "../b"),
#   * drop a trailing slash (except for the root itself),
#   * return "." for an empty or fully cancelled relative path.


def normalize(path):
    """Return the canonical spelling of ``path``."""
    return re.sub(r"/+", "/", path)


def join(base, *parts):
    """Join and normalise; an absolute later part restarts the path."""
    result = base
    for part in parts:
        result = part if part.startswith("/") else result + "/" + part
    return normalize(result)


def is_inside(root, path):
    root, path = normalize(root), normalize(path)
    return path == root or path.startswith(root.rstrip("/") + "/")


def basename(path):
    return split(path)[1]


def extension(path):
    """File extension without the dot ("" when there is none)."""
    name = basename(path)
    stem, dot, ext = name.rpartition(".")
    return ext if dot and stem else ""


def with_extension(path, ext):
    directory, name = split(path)
    stem = name.rpartition(".")[0] if extension(path) else name
    new = stem + ("." + ext if ext else "")
    return join(directory, new) if directory != "." else new


def parents(path):
    path = normalize(path)
    out = []
    while True:
        head, _ = split(path)
        if head == path or not head:
            return out
        out.append(head)
        path = head
        if head in ("/", "."):
            return out
