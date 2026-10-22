"""Selection helpers used by the CLI."""
from . import dates


def open_tasks(tasks):
    return [task for task in tasks if not task.done]


def with_tag(tasks, tag):
    return [task for task in tasks if tag in task.tags]


def due_within(tasks, days, tz, now=None):
    """Open tasks with a due date no more than ``days`` days from today."""
    hits = []
    for task in open_tasks(tasks):
        if task.due is None:
            continue
        if dates.days_until(task.due, tz, now) <= days:
            hits.append(task)
    return hits


def overdue(tasks, tz, now=None):
    return [task for task in open_tasks(tasks)
            if task.due is not None and dates.days_until(task.due, tz, now) < 0]
