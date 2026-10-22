"""Plain data objects passed between the layers."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Note:
    id: int
    title: str
    body: str
    created_at: datetime
    tags: list = field(default_factory=list)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "created_at": self.created_at.isoformat(),
            "tags": list(self.tags),
        }
