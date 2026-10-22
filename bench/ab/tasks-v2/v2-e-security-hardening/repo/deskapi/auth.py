"""Authentication helpers shared by the handlers."""
from functools import wraps

from .http import error


def authenticate(request, context):
    """Attach ``request.user`` from the bearer token. Returns the user or None."""
    header = request.header("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    user_id = context.tokens.resolve(token.strip())
    if user_id is None:
        return None
    user = context.store.get_user(user_id)
    if user is None or not user["active"]:
        return None
    request.user = user
    return user


def require_user(handler):
    @wraps(handler)
    def wrapper(request, context):
        if authenticate(request, context) is None:
            return error(401, "authentication required")
        return handler(request, context)
    return wrapper


def require_admin(handler):
    @wraps(handler)
    def wrapper(request, context):
        user = authenticate(request, context)
        if user is None:
            return error(401, "authentication required")
        if user["role"] != "admin":
            return error(403, "admin only")
        return handler(request, context)
    return wrapper
