"""Backup: rate-limited backup runs."""
from .legacy import legacy_log

MIN_INTERVAL = 86400


def run(name, copy, now, last_run=None):
    """``copy(name)`` returns the seconds the copy took and may raise."""
    if last_run is not None and now - last_run < MIN_INTERVAL:
        age_days = (now - last_run) / 86400
        legacy_log(
            level=30,
            msg="backup {} skipped, last run {:.1f}d ago".format(name, age_days),
        )
        return False
    try:
        secs = copy(name)
    finally:
        legacy_log("backup attempt for %s finished" % name, 10)
    legacy_log("backup {name} done in {secs:.1f}s".format(name=name, secs=secs), 20)
    return True


def due(last_runs, now):
    return sorted(n for n, t in last_runs.items() if now - t >= MIN_INTERVAL)


def oldest(last_runs):
    return min(last_runs, key=last_runs.get) if last_runs else None
