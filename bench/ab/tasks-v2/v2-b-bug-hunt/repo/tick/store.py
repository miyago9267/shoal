"""JSON persistence for the task list."""
import json
import os

from .model import Task, TickError


class Store:
    def __init__(self, path):
        self.path = path
        self.tasks = []
        if os.path.exists(path):
            self._read()

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError) as exc:
            raise TickError(f"cannot read {self.path}: {exc}") from exc
        self.tasks = [Task.from_dict(item) for item in payload.get("tasks", [])]

    def save(self):
        payload = {"version": 1, "tasks": [task.to_dict() for task in self.tasks]}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def add(self, task):
        task.id = max((t.id for t in self.tasks), default=0) + 1
        self.tasks.append(task)
        return task

    def get(self, task_id):
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise TickError(f"no task #{task_id}")
