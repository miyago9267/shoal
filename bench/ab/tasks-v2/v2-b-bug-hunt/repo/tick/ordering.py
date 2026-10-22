"""Sort orders for task listings."""

_NO_DUE = float("inf")


def _due_key(task):
    return task.due if task.due is not None else _NO_DUE


def by_priority(tasks):
    """High priority first; then soonest due, undated last; then lowest id."""
    return sorted(tasks, key=lambda t: (t.priority, _due_key(t), t.id), reverse=True)


def by_due(tasks):
    """Soonest due first (undated last); then high priority; then lowest id."""
    return sorted(tasks, key=lambda t: (_due_key(t), -t.priority, t.id))


def by_id(tasks):
    return sorted(tasks, key=lambda t: t.id)


SORTS = {"priority": by_priority, "due": by_due, "id": by_id}


def sort_tasks(tasks, how="priority"):
    return SORTS[how](tasks)
