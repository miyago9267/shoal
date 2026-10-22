"""Exporter: write named documents through a caller-supplied writer."""
from .legacy import legacy_log


def _note(msg, level=20):
    legacy_log("[export] " + msg, level)


def export_all(files, write):
    """``files``: name -> text. ``write(name, text)`` returns bytes written.

    Empty documents are skipped. Returns the number of documents written.
    """
    done = 0
    for name in sorted(files):
        text = files[name]
        if not text:
            _note("empty: " + name, 30)
            continue
        size = write(name, text)
        _note("wrote %s (%d bytes)" % (name, size))
        done += 1
    return done


def manifest(files):
    return [(n, len(t)) for n, t in sorted(files.items())]


def total_bytes(files):
    return sum(len(t.encode()) for t in files.values())
