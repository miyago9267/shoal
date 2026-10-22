"""Human-readable listing."""
from . import dates


def line(task, tz):
    box = "[x]" if task.done else "[ ]"
    tags = " " + " ".join(f"+{tag}" for tag in task.tags) if task.tags else ""
    return (f"#{task.id:<3} {box} {task.priority_name:<6} "
            f"{dates.format_due(task.due, tz):<10}  {task.title}{tags}")


def listing(tasks, tz):
    if not tasks:
        return "(no tasks)"
    return "\n".join(line(task, tz) for task in tasks)
