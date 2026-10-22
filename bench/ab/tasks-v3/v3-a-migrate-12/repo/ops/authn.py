"""Authn: password login with a static lock list."""
from .legacy import legacy_log

LOCKED = {"root", "guest"}


class BadPassword(Exception):
    pass


def check(user, password, users):
    if user not in users:
        raise KeyError(user)
    if users[user] != password:
        raise BadPassword("bad password")


def login(user, password, users):
    """True when ``user`` may log in. Never raises for bad credentials."""
    if user in LOCKED:
        legacy_log("login blocked: %s is locked" % user, 30)
        return False
    try:
        check(user, password, users)
    except (KeyError, BadPassword) as exc:
        legacy_log("login failed for %s: %s" % (user, exc), 40)
        return False
    legacy_log("login ok: %s" % user, 20)
    return True


def lock(user):
    LOCKED.add(user)


def unlock(user):
    LOCKED.discard(user)


def is_locked(user):
    return user in LOCKED
