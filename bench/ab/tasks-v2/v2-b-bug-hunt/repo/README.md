# tick

A small command-line todo list. Tasks are stored in a JSON file
(`tick.json` by default, override with `--db`).

```sh
python3 -m tick add "Pay rent" --priority high --due 2026-03-01 --tag home
python3 -m tick list                 # open tasks, most important first
python3 -m tick list --all --sort due
python3 -m tick done 3
python3 -m tick due --days 7         # open tasks due within a week
python3 -m tick export --out tasks.csv
```

## Ordering

`list` sorts by priority by default: `high` before `medium` before `low`.
Within the same priority, the task due soonest comes first, tasks without a
due date come after dated ones, and remaining ties keep creation order
(lowest id first). `--sort due` orders by due date first, then priority, then id.

## Time zones

Due dates are entered and shown as calendar dates (`YYYY-MM-DD`) in your time
zone, given as a UTC offset with `--tz +08:00` or the `TICK_TZ` environment
variable (default `+00:00`). Internally a due date is stored as the UTC
timestamp of local midnight on that day.

## Export

`export` writes CSV with a header row:
`id,title,priority,due,done,tags` (`tags` joined with `;`).

## Tests

```sh
python3 -m unittest discover -s tests -t .
```
