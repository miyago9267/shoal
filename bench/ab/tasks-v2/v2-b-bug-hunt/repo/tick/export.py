"""CSV export."""
from . import dates

HEADER = ("id", "title", "priority", "due", "done", "tags")


def _row(task, tz):
    return [
        str(task.id),
        task.title,
        task.priority_name,
        "" if task.due is None else dates.format_due(task.due, tz),
        "yes" if task.done else "no",
        ";".join(task.tags),
    ]


def to_csv(tasks, tz):
    """Render ``tasks`` as CSV text with a header row."""
    lines = [",".join(HEADER)]
    for task in tasks:
        lines.append(",".join(_row(task, tz)))
    return "\n".join(lines) + "\n"
