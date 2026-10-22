"""User management endpoints. Admins only."""
from ..auth import require_admin, require_user
from ..http import error, no_content, ok
from ..store import ROLES


def _target_user(request, context):
    try:
        user_id = int(request.params["id"])
    except (TypeError, ValueError):
        return None
    return context.store.get_user(user_id)


@require_admin
def list_users(request, context):
    users = sorted(context.store.users.values(), key=lambda u: u["id"])
    return ok({"users": users})


@require_admin
def deactivate_user(request, context):
    user = _target_user(request, context)
    if user is None:
        return error(404, "no such user")
    context.store.deactivate(user["id"])
    for key_id in context.tokens.key_ids_for(user["id"]):
        context.tokens.revoke(key_id)
    context.store.log(request.user["id"], "user.deactivate", user["id"])
    return no_content()


@require_user
def change_role(request, context):
    user = _target_user(request, context)
    if user is None:
        return error(404, "no such user")
    role = request.body.get("role")
    if role not in ROLES:
        return error(400, f"role must be one of {', '.join(ROLES)}")
    context.store.set_role(user["id"], role)
    context.store.log(request.user["id"], "user.role", user["id"])
    return ok(context.store.get_user(user["id"]))


@require_admin
def delete_ticket(request, context):
    try:
        ticket_id = int(request.params["id"])
    except (TypeError, ValueError):
        return error(404, "no such ticket")
    if context.store.delete_ticket(ticket_id) is None:
        return error(404, "no such ticket")
    context.store.log(request.user["id"], "ticket.delete", ticket_id)
    return no_content()


def register(router):
    router.add("GET", "/admin/users", list_users)
    router.add("POST", "/admin/users/{id}/deactivate", deactivate_user)
    router.add("POST", "/admin/users/{id}/role", change_role)
    router.add("DELETE", "/admin/tickets/{id}", delete_ticket)
