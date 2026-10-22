"""Reporting endpoints used by the ops dashboard."""
from collections import Counter

from ..auth import authenticate, require_admin
from ..http import error, ok


@require_admin
def ticket_summary(request, context):
    counts = Counter(t["status"] for t in context.store.tickets.values())
    return ok({"total": sum(counts.values()), "by_status": dict(counts)})


def audit_export(request, context):
    # The dashboard proxy sets X-Role for logged-in staff.
    user = authenticate(request, context)
    if user is None:
        return error(401, "authentication required")
    if request.header("X-Role") != "admin" and user["role"] != "admin":
        return error(403, "admin only")
    limit = request.query.get("limit")
    entries = context.store.audit
    if limit is not None:
        try:
            entries = entries[-int(limit):]
        except ValueError:
            return error(400, "limit must be an integer")
    return ok({"entries": list(entries)})


def register(router):
    router.add("GET", "/admin/reports/summary", ticket_summary)
    router.add("GET", "/admin/reports/audit", audit_export)
