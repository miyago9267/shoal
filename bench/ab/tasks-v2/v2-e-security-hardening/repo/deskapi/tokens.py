"""API token registry. Tokens look like ``<key_id>.<secret>``."""


class TokenRegistry:
    def __init__(self):
        self._keys = {}

    def issue(self, key_id, secret, user_id):
        if "." in key_id:
            raise ValueError("key_id must not contain '.'")
        self._keys[key_id] = {"secret": secret, "user_id": user_id, "revoked": False}

    def revoke(self, key_id):
        if key_id in self._keys:
            self._keys[key_id]["revoked"] = True

    def key_ids_for(self, user_id):
        return sorted(k for k, v in self._keys.items() if v["user_id"] == user_id)

    def resolve(self, token):
        """Return the user id the token belongs to, or None."""
        if not token or "." not in token:
            return None
        key_id, _, secret = token.partition(".")
        entry = self._keys.get(key_id)
        if entry is None or entry["revoked"]:
            return None
        if not _secrets_match(secret, entry["secret"]):
            return None
        return entry["user_id"]


def _secrets_match(supplied, expected):
    if len(supplied) != len(expected):
        return False
    for a, b in zip(supplied, expected):
        if a != b:
            return False
    return True
