from datetime import datetime, timedelta, timezone

from notes.app import build_service

T0 = datetime(2024, 5, 1, 9, 0, tzinfo=timezone.utc)


class StepClock:
    """Each call returns the next minute."""

    def __init__(self, start=T0):
        self.now = start

    def __call__(self):
        self.now += timedelta(minutes=1)
        return self.now


def seeded(n, tags_every=0):
    svc = build_service(clock=StepClock())
    for i in range(1, n + 1):
        tags = ["work"] if tags_every and i % tags_every == 0 else []
        svc.create_note(f"note {i}", tags=tags)
    return svc
