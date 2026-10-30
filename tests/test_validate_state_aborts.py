"""P0 characterization (docs/specs/code-restructure T0.4 / T4.2): every InstallAbort raised inside
install._validate_committed_state, reached with the smallest bad state, compared on the full message.

Each case starts from a state/home written by the real installer (valid by construction; the baseline tests prove
it), mutates one thing, and asserts (a) the exact message and (b) that no file next to the home changed.
`site` is the line of the raise in install.py before P4 (documentation only, not asserted).

Raise sites that no state can reach (so they have no case):
  - "install state rollback backup target is unknown" (raise removed in P4): the set(rollback_backups) != required_backups
    gate only admits keys drawn from accepted_targets and recorded, both already proven to be recorded targets.
  - the two "raise HookRegistrationError" sites ("owned hooks.json is missing", "guard projection state is malformed")
    are not InstallAbort; they surface as the wrapped hook-registration message and are covered below.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import install as installer  # noqa: E402

H1, H2 = "1" * 64, "2" * 64
B64_OF_X = base64.b64encode(b"x").decode()
SHA_OF_X = hashlib.sha256(b"x").hexdigest()
NO_SNAPSHOT = object()


class Ctx:
    def __init__(self, home: Path, state: dict) -> None:
        self.home, self.policy, self.state = home, home / "AGENTS.md", state
        self.snapshot: object = NO_SNAPSHOT
        self.allow_drift = False
        self.extra: dict = {}

    @property
    def reco(self) -> dict:
        return self.state["reconciliation"]

    def preimage(self, relative: str = "AGENTS.md") -> dict:
        return self.reco["accepted_preimages"][relative]

    def original(self, relative: str = "AGENTS.md") -> dict:
        return self.state["original_targets"][relative]


def _install(home: Path, **kwargs: object) -> None:
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        installer.install(source_root=ROOT, codex_home=home, dry_run=False, check_codex=False, **kwargs)


def build(root: Path, kind: str) -> Ctx:
    home = root / "home"
    if kind == "v4link":
        canonical = root / "canonical"
        home.mkdir()
        canonical.mkdir()
        (canonical / "AGENTS.md").write_bytes(b"# canonical policy\n")
        (home / "AGENTS.md").symlink_to(canonical / "AGENTS.md")
        _install(home, follow_policy_symlink=True, policy_root=canonical)
    else:
        _install(home)
        if kind == "v4":
            (home / "AGENTS.md").write_bytes((home / "AGENTS.md").read_bytes() + b"\n# current\n")
            _install(home, reconcile_current=True)
    state = json.loads(installer._state_path(home).read_text())
    assert state["state_version"] == (3 if kind == "v3" else 4), kind
    return Ctx(home, state)


def tree(root: Path) -> dict[str, bytes | str]:
    return {
        str(p.relative_to(root)): (p.readlink().as_posix() if p.is_symlink() else p.read_bytes() if p.is_file() else "")
        for p in sorted(root.rglob("*"))
    }


def call(ctx: Ctx) -> object:
    if ctx.snapshot is NO_SNAPSHOT:
        config = ctx.home / "config.toml"
        snapshot = config.read_bytes() if config.is_file() else None
    else:
        snapshot = ctx.snapshot
    return installer._validate_committed_state(
        ctx.state, home=ctx.home, policy_path=ctx.policy, config_snapshot=snapshot,
        allow_policy_drift=ctx.allow_drift,
    )


def _set(key: str, value) -> object:
    return lambda c: c.state.__setitem__(key, value)


def _drop(key: str) -> object:
    return lambda c: c.state.pop(key)


def _file_append(relative: str) -> object:
    return lambda c: (c.home / relative).write_bytes((c.home / relative).read_bytes() + b"\n")


def _unlink(relative: str, drift: bool = False) -> object:
    def mutate(c: Ctx) -> None:
        (c.home / relative).unlink()
        c.allow_drift = drift
    return mutate


def _both(*fns) -> object:
    def mutate(c: Ctx) -> None:
        for fn in fns:
            fn(c)
    return mutate


def _extra_target(c: Ctx) -> None:
    c.state["target_fingerprints"]["extra.toml"] = H1
    c.state["original_targets"]["extra.toml"] = {"present": False, "sha256": None, "bytes_b64": None}


def _guard_ids_wrong(c: Ctx) -> None:
    c.state["guard_registration"] = dict(c.state["hook_registration"])


def _config_text_edit(c: Ctx) -> None:
    config = c.home / "config.toml"
    text = config.read_text()
    assert "max_concurrent_threads_per_session = 3" in text
    config.write_text(text.replace("max_concurrent_threads_per_session = 3", "max_concurrent_threads_per_session = 2"))


def _legacy(**fields) -> object:
    evidence = {"original_present": True, "original_sha256": SHA_OF_X, "original_bytes_b64": B64_OF_X}
    evidence.update(fields)
    return lambda c: c.state.__setitem__("owned_legacy", {"features.multi_agent": evidence})


def _original(**fields) -> object:
    return lambda c: c.original().update(fields)


def _preimage(**fields) -> object:
    return lambda c: c.preimage().update(fields)


def _backup(**fields) -> object:
    return lambda c: c.state["rollback_backups"]["AGENTS.md"].update(fields)


def _reco(**fields) -> object:
    return lambda c: c.reco.update(fields)


def _unlink_state_backup(c: Ctx) -> None:
    (c.home.parent / c.reco["previous_state_backup"]["path"]).unlink()


def _backup_missing_file(c: Ctx) -> None:
    (c.home / c.state["rollback_backups"]["AGENTS.md"]["path"]).unlink()


def _backup_symlink(c: Ctx) -> None:
    path = c.home / c.state["rollback_backups"]["AGENTS.md"]["path"]
    real = c.home / "backup-real"
    real.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(real)


def _preimage_symlink_flag(c: Ctx) -> None:
    c.preimage().update(symlink=True, link_dev=1, link_ino=1)


def _policy_root(value: str) -> object:
    return lambda c: c.preimage().update(policy_root=value)


# (name, base kind, mutate, expected message, site)
CASES = [
    # --- shape gates ---------------------------------------------------------------------------------------------
    ("status not committed", "v3", _set("status", "pending"), "install state is not a committed transaction", 886),
    ("state_version 2", "v3", _set("state_version", 2),
     "install state predates shoal 3.0.0 or is malformed; reinstall", 889),
    ("v3 unknown field", "v3", _set("surprise", 1), "install state has missing or unknown fields", 906),
    ("v3 missing field", "v3", _drop("runtime_status"), "install state has missing or unknown fields", 906),
    ("v4 missing reconciliation", "v4", _drop("reconciliation"), "install state has missing or unknown fields", 906),
    ("v3 carrying reconciliation", "v3", _set("reconciliation", {}), "install state has missing or unknown fields", 906),
    ("v4 plugin not a dict", "v4", _set("plugin", "x"), "install state plugin status is malformed", 912),
    ("v4 plugin extra key", "v4", lambda c: c.state["plugin"].update(extra="x"),
     "install state plugin status is malformed", 912),
    ("v4 plugin non-string value", "v4", lambda c: c.state["plugin"].update(version=3),
     "install state plugin status is malformed", 912),
    ("v4 plugin wrong name", "v4", lambda c: c.state["plugin"].update(name="other"),
     "install state plugin status is malformed", 916),
    ("v4 plugin bad status", "v4", lambda c: c.state["plugin"].update(status="bogus"),
     "install state plugin status is malformed", 916),
    ("v4 plugin bad digest", "v4", lambda c: c.state["plugin"].update(source_sha256="zz"),
     "install state plugin status is malformed", 916),
    ("v4 runtime status", "v4", _set("runtime_status", "bogus"), "install state runtime status is malformed", 918),
    ("v4 rollback backups not a dict", "v4", _set("rollback_backups", []),
     "install state rollback backup manifest is malformed", 931),
    ("v4 rollback backup value is a string", "v4", _set("rollback_backups", {"AGENTS.md": "x"}),
     "install state rollback backup manifest is malformed", 931),
    ("v4 rollback backup absolute path", "v4", _backup(path="/abs.shoal-codex-1"),
     "install state rollback backup manifest is malformed", 931),
    ("v4 rollback backup rooted backslash path", "v4", _backup(path="\\abs.shoal-codex-1"),
     "install state rollback backup manifest is malformed", 931),
    ("v4 rollback backup drive-relative path", "v4", _backup(path="C:abs.shoal-codex-1"),
     "install state rollback backup manifest is malformed", 931),
    ("v4 rollback backup missing marker", "v4", _backup(path="AGENTS.md.bak"),
     "install state rollback backup manifest is malformed", 931),
    ("v3 plugin not a dict", "v3", _set("plugin", None), "install state plugin status is malformed", 937),
    ("v3 plugin bad status", "v3", lambda c: c.state["plugin"].update(status="bogus"),
     "install state plugin status is malformed", 941),
    ("v3 runtime status", "v3", _set("runtime_status", "bogus"), "install state runtime status is malformed", 943),
    ("v3 rollback backup value is a dict", "v3", _set("rollback_backups", {"AGENTS.md": {}}),
     "install state rollback backup manifest is malformed", 953),
    ("v3 rollback backup absolute key", "v3", _set("rollback_backups", {"/abs": "a.shoal-codex-1"}),
     "install state rollback backup manifest is malformed", 953),
    ("v3 rollback backup drive-relative key", "v3", _set("rollback_backups", {"C:abs": "a.shoal-codex-1"}),
     "install state rollback backup manifest is malformed", 953),
    ("v3 rollback backup value with a directory", "v3", _set("rollback_backups", {"a": "d/a.shoal-codex-1"}),
     "install state rollback backup manifest is malformed", 953),
    ("policy ownership not a dict", "v3", _set("policy_ownership", []), "install state policy ownership is malformed", 959),
    ("policy ownership wrong keys", "v3", _set("policy_ownership", {"user_policy": {}}),
     "install state policy ownership is malformed", 959),
    ("policy ownership entry not a dict", "v3",
     lambda c: c.state["policy_ownership"].update(user_policy="x"), "install state policy ownership is malformed", 965),
    ("policy ownership entry wrong keys", "v3",
     lambda c: c.state["policy_ownership"]["shoal_policy"].pop("owner"),
     "install state policy ownership is malformed", 965),
    ("policy ownership entry non-string", "v3",
     lambda c: c.state["policy_ownership"]["shoal_policy"].update(sha256=1),
     "install state policy ownership is malformed", 967),
    # --- target evidence manifest --------------------------------------------------------------------------------
    ("target_fingerprints not a dict", "v3", _set("target_fingerprints", []),
     "install state target evidence is malformed", 971),
    ("original_targets not a dict", "v3", _set("original_targets", None),
     "install state target evidence is malformed", 971),
    ("guard script recorded without guard registration", "v3", _drop("guard_registration"),
     "install state target manifest is stale or incomplete", 982),
    ("guard registration without guard script", "v3",
     lambda c: (c.state["target_fingerprints"].pop("hooks/shoal_guard.py"),
                c.state["original_targets"].pop("hooks/shoal_guard.py")),
     "install state target manifest is stale or incomplete", 982),
    ("autoroute script recorded without hook registration", "v3", _drop("hook_registration"),
     "install state target manifest is stale or incomplete", 984),
    ("unknown recorded target", "v3", _extra_target,
     "install state target manifest is stale or incomplete", 990),
    ("originals differ from recorded targets", "v3", lambda c: c.state["original_targets"].pop("AGENTS.md"),
     "install state target manifest is stale or incomplete", 990),
    ("required role target missing from state while others stay", "v3",
     lambda c: (c.state["target_fingerprints"].pop("config.toml"), c.state["original_targets"].pop("config.toml")),
     "install state target manifest is stale or incomplete", 990),
    # --- hooks / config gates ------------------------------------------------------------------------------------
    ("hooks.json missing", "v3", _unlink("hooks.json"),
     "committed hook registration is invalid: owned hooks.json is missing", 1010),
    ("guard projection id not a guard projection", "v3", _guard_ids_wrong,
     "committed hook registration is invalid: guard projection state is malformed", 1010),
    ("config.toml differs from the snapshot", "v3", lambda c: setattr(c, "snapshot", b"changed"),
     "config.toml changed during state validation", 1014),
    # --- per-target original evidence ----------------------------------------------------------------------------
    ("fingerprint not hex", "v3", lambda c: c.state["target_fingerprints"].update({"AGENTS.md": "zz"}),
     "install state target fingerprint is malformed", 1021),
    ("fingerprint not a string", "v3", lambda c: c.state["target_fingerprints"].update({"AGENTS.md": 5}),
     "install state target fingerprint is malformed", 1021),
    ("original evidence not a dict", "v3", lambda c: c.state["original_targets"].update({"AGENTS.md": "x"}),
     "install state original evidence is malformed", 1023),
    ("original evidence wrong keys", "v3", lambda c: c.original().pop("present"),
     "install state original evidence is malformed", 1023),
    ("original presence not a bool", "v3", _original(present="yes"),
     "install state original presence is malformed", 1026),
    ("original present with bad digest", "v3", _original(present=True, sha256="zz", bytes_b64=B64_OF_X),
     "install state original bytes are malformed", 1029),
    ("original present with non-string bytes", "v3", _original(present=True, sha256=SHA_OF_X, bytes_b64=None),
     "install state original bytes are malformed", 1029),
    ("original bytes not base64", "v3", _original(present=True, sha256=SHA_OF_X, bytes_b64="!!!"),
     "install state original bytes are malformed", 1033),
    ("original bytes digest mismatch", "v3", _original(present=True, sha256=H1, bytes_b64=B64_OF_X),
     "install state original bytes fingerprint mismatch", 1035),
    ("absent original carries a digest", "v3", _original(present=False, sha256=H1, bytes_b64=None),
     "install state absent-original evidence is malformed", 1038),
    ("absent original carries bytes", "v3", _original(present=False, sha256=None, bytes_b64=B64_OF_X),
     "install state absent-original evidence is malformed", 1038),
    # --- target drift --------------------------------------------------------------------------------------------
    ("hook script drifted", "v3", _file_append("hooks/shoal_guard.py"),
     "committed install state is stale; operator resolution required", 1052),
    ("policy drifted without allow_policy_drift", "v3", _file_append("AGENTS.md"),
     "committed install state is stale; operator resolution required", 1052),
    ("role missing under allow_policy_drift", "v3", _unlink("agents/applier.toml", drift=True),
     "committed install state is stale; operator resolution required", 1052),
    ("hook script drifted under allow_policy_drift", "v3",
     lambda c: (_file_append("hooks/shoal_guard.py")(c), setattr(c, "allow_drift", True)),
     "committed install state is stale; operator resolution required", 1052),
    # --- owned_legacy evidence -----------------------------------------------------------------------------------
    ("owned_legacy not a dict", "v3", _set("owned_legacy", []),
     "install state ownership evidence is malformed", 1057),
    ("owned_legacy unknown path", "v3", _set("owned_legacy", {"bogus.path": {}}),
     "install state ownership evidence is malformed", 1061),
    ("owned_legacy evidence not a dict", "v3", _set("owned_legacy", {"features.multi_agent": "x"}),
     "install state ownership evidence is malformed", 1061),
    ("owned_legacy evidence wrong keys", "v3", _set("owned_legacy", {"features.multi_agent": {}}),
     "install state ownership evidence is malformed", 1063),
    ("owned_legacy original not present", "v3", _legacy(original_present=False),
     "install state ownership evidence is malformed", 1068),
    ("owned_legacy bad digest", "v3", _legacy(original_sha256="zz"),
     "install state ownership evidence is malformed", 1068),
    ("owned_legacy bytes not a string", "v3", _legacy(original_bytes_b64=None),
     "install state ownership evidence is malformed", 1068),
    ("owned_legacy bytes not base64", "v3", _legacy(original_bytes_b64="!!!"),
     "install state ownership evidence is malformed", 1072),
    ("owned_legacy digest mismatch", "v3", _legacy(original_sha256=H1),
     "install state ownership fingerprint mismatch", 1074),
    # --- config provenance ---------------------------------------------------------------------------------------
    ("config.toml absent on disk and in snapshot", "v3", _unlink("config.toml"),
     "committed install state is stale; operator resolution required", 1078),
    ("config digest unknown and routing changed", "v3",
     lambda c: (c.state["target_fingerprints"].update({"config.toml": H1}), _config_text_edit(c)),
     "committed config provenance cannot be reconstructed", 1107),
    ("config routing changed after commit", "v3", _config_text_edit,
     "committed config routing projection is stale", 1119),
    # --- v4 reconciliation metadata ------------------------------------------------------------------------------
    ("reconciliation not a dict", "v4", _set("reconciliation", "x"),
     "install state reconciliation metadata is malformed", 1130),
    ("reconciliation wrong keys", "v4", lambda c: c.reco.pop("accepted_targets"),
     "install state reconciliation metadata is malformed", 1130),
    ("accepted_targets not a list", "v4", _reco(accepted_targets="x"),
     "install state reconciliation targets are malformed", 1135),
    ("accepted_targets non-string", "v4", _reco(accepted_targets=[1]),
     "install state reconciliation targets are malformed", 1135),
    ("accepted_targets empty", "v4", _reco(accepted_targets=[]),
     "install state reconciliation targets are malformed", 1142),
    ("accepted_targets unsorted", "v4", _reco(accepted_targets=["config.toml", "AGENTS.md"]),
     "install state reconciliation targets are malformed", 1142),
    ("accepted_targets duplicate", "v4", _reco(accepted_targets=["AGENTS.md", "AGENTS.md"]),
     "install state reconciliation targets are malformed", 1142),
    ("accepted_targets outside policy and config", "v4", _reco(accepted_targets=["agents/applier.toml"]),
     "install state reconciliation targets are malformed", 1142),
    ("previous_state_sha256 not a string", "v4", _reco(previous_state_sha256=1),
     "install state previous state digest is malformed", 1147),
    ("previous_state_sha256 not hex", "v4", _reco(previous_state_sha256="zz"),
     "install state previous state digest is malformed", 1147),
    ("previous_state_backup not a dict", "v4", _reco(previous_state_backup="x"),
     "install state previous state backup is malformed", 1151),
    ("previous_state_backup wrong keys", "v4", lambda c: c.reco["previous_state_backup"].pop("sha256"),
     "install state previous state backup is malformed", 1151),
    ("previous_state_backup absolute path", "v4",
     lambda c: c.reco["previous_state_backup"].update(path="/abs.shoal-codex-1"),
     "install state previous state backup is malformed", 1161),
    ("previous_state_backup drive-relative path", "v4",
     lambda c: c.reco["previous_state_backup"].update(path="C:abs.shoal-codex-1"),
     "install state previous state backup is malformed", 1161),
    ("previous_state_backup missing marker", "v4",
     lambda c: c.reco["previous_state_backup"].update(path="backup.json"),
     "install state previous state backup is malformed", 1161),
    ("previous_state_backup bad digest", "v4", lambda c: c.reco["previous_state_backup"].update(sha256="zz"),
     "install state previous state backup is malformed", 1161),
    ("previous_state_backup digest mismatch", "v4", lambda c: c.reco["previous_state_backup"].update(sha256=H1),
     "install state previous state backup is unavailable", 1172),
    ("previous_state_backup file missing", "v4", _unlink_state_backup,
     "install state previous state backup is unavailable", 1172),
    ("previous digest recorded without backup", "v4", _reco(previous_state_backup=None),
     "install state previous state backup is missing", 1174),
    ("previous_target_fingerprints not a dict", "v4", _reco(previous_target_fingerprints=[]),
     "install state previous target fingerprints are malformed", 1180),
    ("previous_target_fingerprints unknown target", "v4", _reco(previous_target_fingerprints={"zz.toml": H1}),
     "install state previous target fingerprints are malformed", 1180),
    ("previous_target_fingerprints not hex", "v4", _reco(previous_target_fingerprints={"AGENTS.md": "zz"}),
     "install state previous target fingerprints are malformed", 1180),
    ("accepted_preimages not a dict", "v4", _reco(accepted_preimages=[]),
     "install state accepted preimages are malformed", 1183),
    ("accepted_preimages keys differ from accepted_targets", "v4", _reco(accepted_preimages={}),
     "install state accepted preimages are malformed", 1183),
    ("preimage not a dict", "v4", lambda c: c.reco["accepted_preimages"].update({"AGENTS.md": "x"}),
     "install state accepted preimage is malformed", 1190),
    ("preimage wrong keys", "v4", lambda c: c.preimage().pop("link_ino"),
     "install state accepted preimage is malformed", 1190),
    ("preimage sha256 not hex", "v4", _preimage(sha256="zz"), "install state accepted preimage is malformed", 1192),
    ("preimage sha256 not a string", "v4", _preimage(sha256=1), "install state accepted preimage is malformed", 1192),
    ("preimage link_path not a string", "v4", _preimage(link_path=1),
     "install state accepted preimage is malformed", 1211),
    ("preimage symlink not a bool", "v4", _preimage(symlink="no"),
     "install state accepted preimage is malformed", 1211),
    ("preimage target_dev not an int", "v4", _preimage(target_dev="1"),
     "install state accepted preimage is malformed", 1211),
    ("preimage target_dev is a bool", "v4", _preimage(target_dev=True),
     "install state accepted preimage is malformed", 1211),
    ("preimage link_dev not an int", "v4", _preimage(link_dev="1"),
     "install state accepted preimage is malformed", 1211),
    ("preimage target_sha256 not hex", "v4", _preimage(target_sha256="zz"),
     "install state accepted preimage is malformed", 1211),
    ("preimage sha256 differs from target_sha256", "v4", _preimage(sha256=H1),
     "install state accepted preimage is malformed", 1211),
    ("preimage symlink without link identity", "v4", _preimage(symlink=True),
     "install state accepted preimage is malformed", 1211),
    ("preimage regular file with link identity", "v4", _preimage(link_dev=1, link_ino=1),
     "install state accepted preimage is malformed", 1211),
    ("preimage policy missing", "v4", _unlink("AGENTS.md", drift=True),
     "install state accepted preimage is unavailable", 1216),
    ("preimage link_path differs", "v4", _preimage(link_path="/elsewhere/AGENTS.md"),
     "install state accepted preimage path is malformed", 1218),
    ("preimage claims symlink but policy is a file", "v4", _preimage_symlink_flag,
     "install state accepted preimage symlink identity is malformed", 1221),
    ("preimage symlink policy_root unresolvable", "v4link", _policy_root("/nonexistent/shoal-root"),
     "install state accepted preimage root is malformed", 1226),
    ("preimage symlink policy_root not in canonical form", "v4link",
     lambda c: c.preimage().update(policy_root=c.preimage()["policy_root"] + "/../canonical"),
     "install state accepted preimage symlink identity is malformed", 1232),
    ("preimage symlink target_path differs", "v4link", _preimage(target_path="/elsewhere/AGENTS.md"),
     "install state accepted preimage symlink identity is malformed", 1232),
    ("preimage regular file with policy_root", "v4", _policy_root("/some/root"),
     "install state accepted preimage path is malformed", 1240),
    ("preimage regular file target_path differs", "v4", _preimage(target_path="/elsewhere/AGENTS.md"),
     "install state accepted preimage path is malformed", 1240),
    ("post-merge fingerprints missing a target", "v4", lambda c: c.reco["post_merge_target_fingerprints"].pop("AGENTS.md"),
     "install state post-merge fingerprints are malformed", 1245),
    ("post-merge fingerprint differs", "v4",
     lambda c: c.reco["post_merge_target_fingerprints"].update({"AGENTS.md": H1}),
     "install state post-merge fingerprints are malformed", 1245),
    ("rollback backups missing an accepted target", "v4", lambda c: c.state["rollback_backups"].pop("config.toml"),
     "install state rollback backup manifest is incomplete", 1253),
    ("rollback backups carry an extra key", "v4",
     lambda c: c.state["rollback_backups"].update({"zz.toml": dict(c.state["rollback_backups"]["AGENTS.md"])}),
     "install state rollback backup manifest is incomplete", 1253),
    ("accepted target without original evidence", "v4", _original(present=False, sha256=None, bytes_b64=None),
     "install state accepted target has no original evidence", 1255),
    ("rollback backup digest mismatch", "v4", _backup(sha256=H1),
     "install state rollback backup is unavailable", 1272),
    ("rollback backup file missing", "v4", _backup_missing_file,
     "install state rollback backup is unavailable", 1272),
    ("rollback backup is a symlink", "v4", _backup_symlink,
     "install state rollback backup is unavailable", 1272),
    ("rollback backup digest not hex", "v4", _backup(sha256="zz"),
     "install state rollback backup is unavailable", 1272),
    ("rollback backup target digest not hex", "v4", _backup(target_sha256="zz"),
     "install state rollback backup is unavailable", 1272),
    ("rollback backup target digest differs from original", "v4", _backup(target_sha256=H1),
     "install state rollback backup is unavailable", 1272),
]


class ValidateStateAbortTests(unittest.TestCase):
    def test_baselines_validate(self) -> None:
        for kind in ("v3", "v4", "v4link"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                result = call(build(Path(tmp), kind))
                self.assertEqual(len(result), 5)

    def test_every_case_has_a_unique_name(self) -> None:
        names = [case[0] for case in CASES]
        self.assertEqual(len(names), len(set(names)))

    def test_each_bad_state_aborts_with_its_exact_message_and_writes_nothing(self) -> None:
        for name, kind, mutate, message, site in CASES:
            with self.subTest(name=name, site=site), tempfile.TemporaryDirectory() as tmp:
                ctx = build(Path(tmp), kind)
                mutate(ctx)
                before = tree(Path(tmp))
                with self.assertRaises(installer.InstallAbort) as caught:
                    call(ctx)
                self.assertEqual(str(caught.exception), message)
                self.assertEqual(tree(Path(tmp)), before)


if __name__ == "__main__":
    unittest.main()
