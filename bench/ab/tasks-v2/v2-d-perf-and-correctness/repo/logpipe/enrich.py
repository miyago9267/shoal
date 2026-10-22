"""Stage 2: attach the User record to every event."""
from .model import UNKNOWN_USER


def find_user(users, user_id):
    for user in users:
        if user.id == user_id:
            return user
    return UNKNOWN_USER


def enrich(events, users):
    for event in events:
        event.user = find_user(users, event.user_id)
    return events
