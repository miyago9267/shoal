Users of our `tick` todo CLI reported three problems. Please find and fix them, without changing
the documented behaviour in the README:

1. "When I have several tasks with the same priority, `tick list` shows them in a weird order. The
   one due last is on top, and tasks with no due date come before the ones that have one."
2. "I'm in Taipei and run with `--tz +08:00`. I added a task with `--due 2026-03-10` and `tick list`
   shows 2026-03-09. The CSV export has the wrong date too. My colleague in New York says it's fine
   for her."
3. "`tick export` produces a broken CSV as soon as a task title contains a comma. Spreadsheet apps
   shift the columns over."
