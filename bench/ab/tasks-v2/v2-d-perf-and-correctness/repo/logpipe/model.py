"""Records passed between pipeline stages."""
from dataclasses import dataclass


@dataclass
class User:
    id: int
    name: str
    plan: str


UNKNOWN_USER = User(id=-1, name="unknown", plan="none")


@dataclass
class Event:
    ts: int            # epoch seconds, UTC
    request_id: str
    user_id: int
    status: int
    bytes: int
    path: str
    ms: int
    user: "User | None" = None
    session: int = -1
