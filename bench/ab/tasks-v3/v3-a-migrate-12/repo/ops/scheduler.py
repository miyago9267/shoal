"""Scheduler: run due jobs once, honouring pauses and dependencies."""
from .legacy import legacy_log as _log

SKIP_LEVEL = 10
RUN_LEVEL = 20


def due(jobs, now):
    return [j for j in jobs if j["at"] <= now and not j.get("done")]


def _waiting_on(job, by_name):
    for dep in job.get("after", ()):
        if not by_name[dep].get("done"):
            return dep
    return None


def tick(jobs, now, runner):
    """Run every due job; returns the number executed."""
    by_name = {j["name"]: j for j in jobs}
    ran = 0
    for job in due(jobs, now):
        if job.get("paused"):
            msg = "skip %s: paused" % job["name"]
            _log(msg, SKIP_LEVEL)
            continue
        dep = _waiting_on(job, by_name)
        if dep is not None:
            msg = "skip %s: waiting on %s" % (job["name"], dep)
            _log(msg, SKIP_LEVEL)
            continue
        runner(job)
        job["done"] = True
        ran += 1
        msg = "ran %s" % job["name"]
        _log(msg, RUN_LEVEL)
    return ran


def pending(jobs):
    return [j["name"] for j in jobs if not j.get("done")]


def reset(jobs):
    for job in jobs:
        job.pop("done", None)
