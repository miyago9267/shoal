"""Error types; each maps to a protocol error code."""


class KVError(Exception):
    code = "internal"


class BadRequest(KVError):
    code = "bad_request"


class NotFound(KVError):
    code = "not_found"


class WrongType(KVError):
    code = "wrong_type"


class NoSnapshotPath(KVError):
    code = "no_snapshot_path"
