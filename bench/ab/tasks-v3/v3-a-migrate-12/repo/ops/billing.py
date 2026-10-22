"""Billing: charge accounts against a per-account limit."""
from .legacy import legacy_log

MAX_CENTS = 1_000_000


def format_money(cents):
    return "%d.%02d" % (cents // 100, cents % 100)


def charge(account, cents):
    """Charge ``cents`` to ``account`` (dict with id, balance, limit)."""
    if cents <= 0:
        legacy_log("charge rejected: %d cents" % cents, 30)
        return False
    if cents > account["limit"]:
        legacy_log(
            "charge declined for %s: %d over limit %d"
            % (account["id"], cents, account["limit"]),
            40,
        )
        return False
    account["balance"] += cents
    legacy_log("charged %s %s" % (account["id"], format_money(cents)), 20)
    return True


def refund(account, cents):
    """Give ``cents`` back; never more than what was charged so far."""
    cents = min(cents, account["balance"])
    account["balance"] -= cents
    legacy_log("refund %s %d" % (account["id"], cents), 20)
    return cents


def statement(accounts):
    """One line per account, sorted by id."""
    return [
        "%s %s" % (a["id"], format_money(a["balance"]))
        for a in sorted(accounts, key=lambda a: a["id"])
    ]


def total(accounts):
    return sum(a["balance"] for a in accounts)


def over_limit(accounts):
    return [a["id"] for a in accounts if a["balance"] > a["limit"]]
