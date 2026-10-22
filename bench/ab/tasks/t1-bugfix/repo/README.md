# pager

Small offset-pagination helpers used by our list endpoints.

- `pager.paginate.paginate(items, page, page_size)` returns a `Page`
  with `items`, `total_pages`, `has_next`, `has_prev`.
- `pager.links.page_links(page)` builds the page-number strip shown under
  tables (`[1, None, 4, 5, 6, None, 12]`, `None` = ellipsis).

Run tests: `python3 -m unittest discover -s tests -t .`
