"""Dispatch protocol requests to a KVStore."""
from . import protocol
from .errors import BadRequest, KVError, NoSnapshotPath
from .snapshot import save_snapshot


class Handler:
    def __init__(self, store, snapshot_path=None):
        self.store = store
        self.snapshot_path = snapshot_path
        self._ops = {
            "ping": self.op_ping,
            "get": self.op_get,
            "set": self.op_set,
            "delete": self.op_delete,
            "exists": self.op_exists,
            "incr": self.op_incr,
            "mget": self.op_mget,
            "keys": self.op_keys,
            "snapshot": self.op_snapshot,
        }

    def handle(self, request):
        """Turn one request dict into one response dict; never raises."""
        if not isinstance(request, dict):
            return protocol.error("bad_request", "request must be an object")
        op = self._ops.get(request.get("op"))
        if op is None:
            return protocol.error("bad_request", f"unknown op {request.get('op')!r}")
        try:
            return op(request)
        except KVError as exc:
            return protocol.error(exc.code, str(exc))

    def op_ping(self, request):
        return protocol.ok(pong=True)

    def op_get(self, request):
        return protocol.ok(value=self.store.get(protocol.require_key(request)))

    def op_set(self, request):
        key = protocol.require_key(request)
        self.store.set(key, protocol.require_value(request))
        return protocol.ok()

    def op_delete(self, request):
        self.store.delete(protocol.require_key(request))
        return protocol.ok()

    def op_exists(self, request):
        return protocol.ok(exists=protocol.require_key(request) in self.store)

    def op_incr(self, request):
        key = protocol.require_key(request)
        by = protocol.optional_int(request, "by", 1)
        return protocol.ok(value=self.store.incr(key, by))

    def op_mget(self, request):
        keys = protocol.require_keys(request)
        return protocol.ok(values={key: self.store.get(key, None) for key in keys})

    def op_keys(self, request):
        prefix = request.get("prefix", "")
        if not isinstance(prefix, str):
            raise BadRequest("'prefix' must be a string")
        return protocol.ok(keys=self.store.keys(prefix))

    def op_snapshot(self, request):
        if not self.snapshot_path:
            raise NoSnapshotPath("handler has no snapshot path")
        return protocol.ok(count=save_snapshot(self.store, self.snapshot_path))
