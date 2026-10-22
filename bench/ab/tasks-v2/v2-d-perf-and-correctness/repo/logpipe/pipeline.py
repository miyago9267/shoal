"""Wire the five stages together."""
from . import aggregate, enrich, parse, report, sessionize
from .users import load_users


def run(lines, users_csv):
    """Log lines + users CSV text -> report dict (see README)."""
    events, skipped = parse.parse(lines)
    events = enrich.enrich(events, load_users(users_csv))
    events = sessionize.sessionize(events)
    summary = aggregate.aggregate(events)
    return report.build(summary, skipped)


def run_files(log_path, users_path):
    with open(users_path, encoding="utf-8") as fh:
        users_csv = fh.read()
    with open(log_path, encoding="utf-8") as fh:
        return run(fh, users_csv)
