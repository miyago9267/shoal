# reports

Builds the daily sales summary from the shop backend's order export.

```python
from reports.loader import load_orders
from reports.report import build_report, render_report

with open("orders.csv", newline="") as fh:
    print(render_report(build_report(load_orders(fh))))
```

The exporter retries on timeouts, so the same order can appear more than once
(sometimes with different casing or stray whitespace). Duplicates are removed
before totals are computed; the first occurrence wins.

`reports/formatting.py` is shared with the invoicing CLI.

Run the tests with `python3 -m unittest discover -s tests -t .`.
