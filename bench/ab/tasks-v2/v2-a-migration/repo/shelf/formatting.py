"""Plain-text rendering for the CLI."""

COLUMNS = (("id", "ID"), ("title", "TITLE"), ("author", "AUTHOR"), ("year", "YEAR"))


def _cell(value):
    return "-" if value is None else str(value)


def table(books, columns=COLUMNS):
    """Render ``books`` as a left-aligned text table."""
    rows = [[_cell(getattr(book, attr)) for attr, _ in columns] for book in books]
    headers = [title for _, title in columns]
    widths = [max([len(h)] + [len(r[i]) for r in rows]) for i, h in enumerate(headers)]
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip()]
    for row in rows:
        lines.append("  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())
    return "\n".join(lines)


def detail(book):
    lines = []
    for attr, title in COLUMNS:
        lines.append(f"{title.lower():>7}: {_cell(getattr(book, attr))}")
    return "\n".join(lines)
