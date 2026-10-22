"""Page-number strip for rendering pagination controls."""


def page_links(page, window=1):
    """Return page numbers to render around ``page``.

    Always includes the first and last page; ``None`` marks a gap.
    """
    last = page.total_pages
    if last == 0:
        return []
    current = page.page
    wanted = {1, last}
    for n in range(current - window, current + window + 1):
        if 1 <= n <= last:
            wanted.add(n)
    out = []
    prev = 0
    for n in sorted(wanted):
        if n - prev > 1:
            out.append(None)
        out.append(n)
        prev = n
    return out
