"""Task record."""
from dataclasses import dataclass, field

PRIORITIES = {"low": 1, "medium": 2, "high": 3}
PRIORITY_NAMES = {value: name for name, value in PRIORITIES.items()}


class TickError(Exception):
    """User-facing error; the CLI prints it and exits with status 1."""


@dataclass
class Task:
    id: int
    title: str
    priority: int = PRIORITIES["medium"]
    due: "int | None" = None  # UTC epoch seconds of local midnight
    done: bool = False
    tags: list = field(default_factory=list)

    @property
    def priority_name(self):
        return PRIORITY_NAMES[self.priority]

    def to_dict(self):
        return {"id": self.id, "title": self.title, "priority": self.priority,
                "due": self.due, "done": self.done, "tags": list(self.tags)}

    @classmethod
    def from_dict(cls, data):
        return cls(id=data["id"], title=data["title"], priority=data["priority"],
                   due=data.get("due"), done=data.get("done", False),
                   tags=list(data.get("tags", [])))


def parse_priority(text):
    try:
        return PRIORITIES[text.lower()]
    except KeyError:
        raise TickError(f"unknown priority {text!r} (use low, medium or high)") from None
