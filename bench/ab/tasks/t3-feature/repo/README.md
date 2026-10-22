# invsum

Summarizes an inventory CSV (`sku,category,quantity,unit_price`) by category.

    python3 -m invsum stock.csv --sort value --min-quantity 5

Prints a table with one row per category (item count, total units, stock
value) followed by a TOTAL line.

Run tests: `python3 -m unittest discover -s tests -t .`
