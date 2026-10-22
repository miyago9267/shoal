"""Ticket endpoints for regular agents."""
from ..auth import require_user
from ..http import created, error, no_content, ok
from ..store import STATUSES


def _parse_id(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@require_user
def list_tickets(request, context):
    return ok({"tickets": context.store.tickets_for(request.user["id"])})


@require_user
def create_ticket(request, context):
    title = (request.body.get("title") or "").strip()
    if not title:
        return error(400, "title is required")
    ticket = context.store.add_ticket(request.user["id"], title, request.body.get("body", ""))
    context.store.log(request.user["id"], "ticket.create", ticket["id"])
    return created(ticket)


@require_user
def get_ticket(request, context):
    ticket = context.store.get_ticket(_parse_id(request.params["id"]))
    if ticket is None:
        return error(404, "no such ticket")
    if ticket["owner_id"] != request.user["id"] and request.user["role"] != "admin":
        return error(404, "no such ticket")
    return ok(ticket)


@require_user
def update_status(request, context):
    ticket = context.store.get_ticket(_parse_id(request.params["id"]))
    if ticket is None or ticket["owner_id"] != request.user["id"]:
        return error(404, "no such ticket")
    status = request.body.get("status")
    if status not in STATUSES:
        return error(400, f"status must be one of {', '.join(STATUSES)}")
    ticket["status"] = status
    context.store.log(request.user["id"], "ticket.status", ticket["id"])
    return ok(ticket)


@require_user
def whoami(request, context):
    return ok({"id": request.user["id"], "name": request.user["name"],
               "role": request.user["role"]})


@require_user
def logout(request, context):
    key_id = request.header("Authorization", "").partition(" ")[2].partition(".")[0]
    context.tokens.revoke(key_id)
    return no_content()


def register(router):
    router.add("GET", "/me", whoami)
    router.add("POST", "/logout", logout)
    router.add("GET", "/tickets", list_tickets)
    router.add("POST", "/tickets", create_ticket)
    router.add("GET", "/tickets/{id}", get_ticket)
    router.add("POST", "/tickets/{id}/status", update_status)
