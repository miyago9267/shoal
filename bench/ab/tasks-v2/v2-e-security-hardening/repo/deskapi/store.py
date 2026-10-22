"""In-memory persistence for users, tickets and the audit log."""
import itertools

ROLES = ("agent", "admin")
STATUSES = ("open", "pending", "closed")


class Store:
    def __init__(self):
        self.users = {}
        self.tickets = {}
        self.audit = []
        self._user_ids = itertools.count(1)
        self._ticket_ids = itertools.count(1)

    # users ---------------------------------------------------------------
    def add_user(self, name, role="agent"):
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        user_id = next(self._user_ids)
        self.users[user_id] = {"id": user_id, "name": name, "role": role, "active": True}
        return self.users[user_id]

    def get_user(self, user_id):
        return self.users.get(user_id)

    def set_role(self, user_id, role):
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        self.users[user_id]["role"] = role

    def deactivate(self, user_id):
        self.users[user_id]["active"] = False

    # tickets -------------------------------------------------------------
    def add_ticket(self, owner_id, title, body=""):
        ticket_id = next(self._ticket_ids)
        self.tickets[ticket_id] = {
            "id": ticket_id,
            "owner_id": owner_id,
            "title": title,
            "body": body,
            "status": "open",
        }
        return self.tickets[ticket_id]

    def get_ticket(self, ticket_id):
        return self.tickets.get(ticket_id)

    def tickets_for(self, owner_id):
        return [t for t in self.tickets.values() if t["owner_id"] == owner_id]

    def delete_ticket(self, ticket_id):
        return self.tickets.pop(ticket_id, None)

    # audit ---------------------------------------------------------------
    def log(self, actor_id, action, target=None):
        self.audit.append({"actor": actor_id, "action": action, "target": target})
