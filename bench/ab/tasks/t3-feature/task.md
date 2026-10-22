Our `invsum` CLI only prints a text table, but we want to pipe its output into other tools. Please
add a `--format` option that accepts `text` (the current output, still the default) or `json`.
The JSON output should be a list with one object per category row, using the keys `category`,
`items`, `quantity` and `value`, with numbers as JSON numbers; leave out the TOTAL line.
`--sort` and `--min-quantity` should work the same in both formats.
