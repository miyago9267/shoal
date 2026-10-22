"""Offset pagination for list endpoints."""
from dataclasses import dataclass, field

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def clamp_page_size(size):
    """Coerce a requested page size into the allowed range."""
    if size is None:
        return DEFAULT_PAGE_SIZE
    size = int(size)
    if size < 1:
        return 1
    return min(size, MAX_PAGE_SIZE)


def page_count(total_items, page_size):
    """Number of pages needed to show ``total_items`` items."""
    if total_items <= 0:
        return 0
    return (total_items + page_size) // page_size


def page_bounds(page, page_size):
    """Return the half-open slice ``(start, end)`` for a 1-based page."""
    start = (page - 1) * page_size
    return start, start + page_size


@dataclass(frozen=True)
class Page:
    items: list
    page: int
    page_size: int
    total_items: int
    meta: dict = field(default_factory=dict)

    @property
    def total_pages(self):
        return page_count(self.total_items, self.page_size)

    @property
    def has_next(self):
        return self.page < self.total_pages

    @property
    def has_prev(self):
        return self.page > 1


def paginate(items, page=1, page_size=None):
    """Slice ``items`` into a :class:`Page`. ``page`` is 1-based."""
    size = clamp_page_size(page_size)
    page = int(page)
    if page < 1:
        raise ValueError("page must be >= 1")
    start, end = page_bounds(page, size)
    items = list(items)
    return Page(items=items[start:end], page=page, page_size=size,
                total_items=len(items))
