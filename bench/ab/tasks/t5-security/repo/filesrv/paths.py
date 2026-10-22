"""Map request paths onto the static root directory."""
import os
from urllib.parse import unquote

INDEX_FILES = ("index.html", "index.htm")


def normalize_request_path(raw):
    """Strip the query string / fragment and percent-decode a request path."""
    path = raw.split("?", 1)[0].split("#", 1)[0]
    return unquote(path)


def resolve_path(root, request_path):
    """Return the filesystem path that serves ``request_path`` under ``root``.

    Directories resolve to their index file when one exists.
    """
    rel = normalize_request_path(request_path)
    candidate = os.path.normpath(os.path.join(root, rel.lstrip("/")))
    if os.path.isdir(candidate):
        for name in INDEX_FILES:
            index = os.path.join(candidate, name)
            if os.path.isfile(index):
                return index
    return candidate
