"""Run many requests and collect per-request outcomes."""
from .errors import UnknownHandler, ValidationError
from .router import dispatch


def run_one(request):
    """``request`` is ``{"handler": name, "payload": {...}}``."""
    try:
        result = dispatch(request.get("handler"), request.get("payload"))
    except ValidationError as exc:
        return {"ok": False, "field": exc.field, "error": exc.message}
    except UnknownHandler as exc:
        return {"ok": False, "field": None, "error": "unknown handler %s" % exc}
    return {"ok": True, "result": result}


def run_all(requests):
    """Outcomes in request order; one bad request never stops the rest."""
    return [run_one(r) for r in requests]


def summary(outcomes):
    good = sum(1 for o in outcomes if o["ok"])
    fields = {}
    for outcome in outcomes:
        if not outcome["ok"] and outcome["field"]:
            fields[outcome["field"]] = fields.get(outcome["field"], 0) + 1
    return {"total": len(outcomes), "ok": good, "failed": len(outcomes) - good, "fields": fields}


def first_failure(outcomes):
    for index, outcome in enumerate(outcomes):
        if not outcome["ok"]:
            return index, outcome
    return None
