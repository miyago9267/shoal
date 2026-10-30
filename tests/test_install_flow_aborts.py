"""P0 characterization (docs/specs/code-restructure T4.1 precondition): every InstallAbort raised directly in
install.install() and in the helpers it drives, with exact message, abort type and the state of the home afterwards.

Cases are (name, setup, expected message) tables. Aborts raised after the pending sidecar is written leave the
``.pending`` file with status "aborted" and the home bytes restored; earlier aborts leave nothing at all.

Sites that need a TOCTOU race are reproduced by wrapping the one primitive that observes the race. Not covered
(unreachable or needs a second racing writer), by install.py line at this commit:
  "legacy V2 migration requires a committed install state" (raise removed in P4): merge_config_text(migration_proven=False) always raises first
  2244 legacy V2 unapproved primary target, 2247 planned native config invalid, 2277 inventory target missing,
  2319 reconciliation target outside inventory, 2333/2336 reconciliation preimage/identity unavailable
       (state validation or earlier gates reject every input that could reach them)
  2435 reconciliation backup source unavailable, 2510 reconciliation target changed (needs a concurrent writer
       between pre_targets and the backup loop; no single primitive to wrap)
  2630 published state changed before verification (needs a writer after the atomic state write)
"""

from __future__ import annotations

import errno
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import install as installer  # noqa: E402
from install import InstallAbort  # noqa: E402

STAMP = "20260101T000000Z"


def snapshot(home: Path) -> dict[str, bytes]:
    return {
        p.relative_to(home).as_posix(): p.read_bytes()
        for p in sorted(home.rglob("*")) if p.is_file() and not p.is_symlink()
    }


def pending_of(home: Path) -> Path:
    return installer._state_path(home).with_suffix(".json.pending")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()

    def run_install(self, **kwargs: object) -> int:
        kwargs.setdefault("check_codex", False)
        return installer.install(source_root=ROOT, codex_home=self.home, dry_run=False, **kwargs)

    def installed(self) -> None:
        self.assertEqual(self.run_install(), 0)

    def assertAborts(self, message: str, fn, *args, prefix: bool = False, **kwargs) -> InstallAbort:
        with self.assertRaises(InstallAbort) as ctx:
            fn(*args, **kwargs)
        if prefix:
            self.assertTrue(str(ctx.exception).startswith(message), str(ctx.exception))
        else:
            self.assertEqual(str(ctx.exception), message)
        return ctx.exception


class InstallPlanningAborts(Base):
    """Aborts before anything is written: the home and the sidecar stay exactly as they were."""

    def check(self, name: str, message: str, kwargs: dict, *, prefix: bool = False, sidecar: bool = False) -> None:
        before = snapshot(self.home)
        with self.subTest(name):
            self.assertAborts(message, self.run_install, prefix=prefix, **kwargs)
            self.assertEqual(snapshot(self.home), before)
            if not sidecar:
                self.assertFalse(pending_of(self.home).exists())

    def test_unknown_drifted_role_and_reconcile_without_state(self) -> None:
        self.check("unknown role", "unknown drifted role: nope, zzz",
                   {"replace_drifted_role": ("zzz", "nope")})
        self.check("reconcile w/o state", "reconcile-current requires committed install state",
                   {"reconcile_current": True})
        self.assertFalse(installer._state_path(self.home).exists())

    def test_hard_linked_policy(self) -> None:
        other = self.root / "other.md"
        other.write_text("# policy\n", encoding="utf-8")
        os.link(other, self.home / "AGENTS.md")
        self.check("hard link",
                   "active policy path is hard-linked; explicit policy integration is required", {})
        self.assertEqual(other.read_text(encoding="utf-8"), "# policy\n")

    def test_role_and_hook_drift(self) -> None:
        agents = self.home / "agents"
        agents.mkdir()
        (agents / "executor.toml").write_bytes(
            (ROOT / "templates" / "agents" / "executor.toml").read_bytes() + b"\n# custom\n")
        self.check("role drift",
                   "installed_role_drift: agents/executor.toml requires explicit replacement approval", {})
        (agents / "executor.toml").unlink()
        hooks = self.home / "hooks"
        hooks.mkdir()
        (hooks / "shoal_autoroute_gate.py").write_bytes(b"custom\n")
        self.check("hook drift", "installed_hook_drift: hook script requires explicit replacement approval", {})
        (hooks / "shoal_autoroute_gate.py").unlink()
        (hooks / "shoal_guard.py").write_bytes(b"custom\n")
        self.check("guard drift", "installed_hook_drift: guard script requires explicit replacement approval", {})

    def test_hook_registration_rejected(self) -> None:
        (self.home / "hooks.json").write_text('{"hooks":[]}', encoding="utf-8")
        before = snapshot(self.home)
        err = self.assertAborts("hook registration rejected: ", self.run_install, prefix=True)
        self.assertIsInstance(err.__cause__, installer.HookRegistrationError)
        self.assertEqual(snapshot(self.home), before)

    def test_pending_and_invalid_state_gate_install(self) -> None:
        pending_of(self.home).write_text("{}", encoding="utf-8")
        self.check("pending", "pending install state exists; resolve the aborted transaction before writing", {},
                   sidecar=True)
        pending_of(self.home).unlink()
        installer._state_path(self.home).write_text("{not json", encoding="utf-8")
        self.check("invalid state", "install state is invalid; resolve it before writing", {})
        installer._state_path(self.home).write_text('{"status":"pending"}', encoding="utf-8")
        self.check("uncommitted state", "install state is not a committed transaction", {})

    def test_policy_identity_changed_during_plan(self) -> None:
        target = self.root / "real.md"
        target.write_text("# policy\n", encoding="utf-8")
        (self.home / "AGENTS.md").symlink_to(target)
        real = installer._capture_policy_identity
        calls = {"n": 0}

        def swap(*args, **kwargs):
            result = real(*args, **kwargs)
            calls["n"] += 1
            if calls["n"] == 1:
                target.write_text("# edited\n", encoding="utf-8")
            return result

        with mock.patch.object(installer, "_capture_policy_identity", swap):
            self.assertAborts("policy target changed while install was planned",
                              self.run_install, follow_policy_symlink=True, policy_root=self.root)
        self.assertEqual(target.read_text(encoding="utf-8"), "# edited\n")
        self.assertFalse((self.home / "config.toml").exists())


class InstallTransactionAborts(Base):
    """Aborts after the pending sidecar is written: rolled back, pending marked aborted."""

    def tamper_after(self, nth: int, mutate) -> mock._patch:
        """Run ``mutate`` on the nth _assert_active_instruction_file call made after _commit returns."""
        real_commit, real_assert = installer._commit, installer._assert_active_instruction_file
        state = {"after": False, "n": 0}

        def commit(*a, **k):
            result = real_commit(*a, **k)
            state["after"] = True
            return result

        def assert_active(*a, **k):
            if state["after"]:
                state["n"] += 1
                if state["n"] == nth:
                    mutate()
            return real_assert(*a, **k)

        stack = mock.patch.multiple(installer, _commit=commit, _assert_active_instruction_file=assert_active)
        return stack

    def assertRolledBack(self, before: dict[str, bytes]) -> None:
        self.assertEqual(snapshot(self.home), before)
        pending = pending_of(self.home)
        self.assertEqual(json.loads(pending.read_text())["status"], "aborted")

    def test_post_write_fingerprint_checks(self) -> None:
        cases = [
            ("post-write transaction fingerprint mismatch", 1),
            ("post-write state publication fingerprint mismatch", 2),
            ("post-sidecar transaction fingerprint mismatch", 4),
        ]
        for message, nth in cases:
            with self.subTest(message), tempfile.TemporaryDirectory() as tmp:
                self.home = Path(tmp) / "home"
                self.home.mkdir()
                before = snapshot(self.home)
                target = self.home / "config.toml"

                def corrupt() -> None:
                    target.write_bytes(b"# tampered\n")

                with self.tamper_after(nth, corrupt):
                    self.assertAborts(message, self.run_install)
                self.assertFalse(installer._state_path(self.home).exists())
                self.assertTrue(pending_of(self.home).is_file())
                self.assertEqual(json.loads(pending_of(self.home).read_text())["status"], "aborted")
                # config.toml was created by this install, so rollback removes it unless it was tampered with
                # afterwards; the tamper is the only residue.
                self.assertEqual(
                    {k: v for k, v in snapshot(self.home).items() if k != "config.toml"},
                    {k: v for k, v in before.items() if k != "config.toml"},
                )

    def test_pending_changed_before_removal(self) -> None:
        pending = pending_of(self.home)
        with self.tamper_after(4, lambda: pending.write_text("{}", encoding="utf-8")):
            self.assertAborts("pending install state changed before removal", self.run_install)
        self.assertFalse(installer._state_path(self.home).exists())

    def test_rollback_backup_already_exists_and_state_backup_exists(self) -> None:
        self.installed()
        before = snapshot(self.home)
        state = installer._state_path(self.home)
        state_before = state.read_bytes()
        backup = self.home / f"config.toml.shoal-codex-{STAMP}"
        backup.write_bytes(b"squatter")
        with mock.patch.object(installer, "_stamp", return_value=STAMP):
            self.assertAborts(f"rollback backup already exists: {backup}",
                              self.run_install, reconcile_current=True)
        # the policy backup is made before the config one collides; the abort leaves it behind
        leftover = self.home / f"AGENTS.md.shoal-codex-{STAMP}"
        self.assertTrue(leftover.is_file())
        self.assertEqual(json.loads(pending_of(self.home).read_text())["status"], "aborted")
        pending_of(self.home).unlink()
        leftover.unlink()
        backup.unlink()
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(state.read_bytes(), state_before)
        state_backup = state.parent / f"{state.name}.shoal-codex-{STAMP}"
        state_backup.write_bytes(b"squatter")
        with mock.patch.object(installer, "_stamp", return_value=STAMP):
            self.assertAborts(f"previous install state backup already exists: {state_backup}",
                              self.run_install, reconcile_current=True)
        self.assertFalse(pending_of(self.home).exists())
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(state.read_bytes(), state_before)

    def test_config_disappears_around_plugin_install(self) -> None:
        unavailable = {
            "name": "shoal-codex", "version": installer.SHOAL_PLUGIN_VERSION, "status": "unavailable",
            "source_sha256": installer._plugin_source_digest(ROOT / "plugin"),
        }
        version = mock.Mock(returncode=0, stdout="codex 0.147.0", stderr="")
        config = self.home / "config.toml"

        def gone(**_):
            config.unlink()
            return unavailable

        with mock.patch.object(installer.subprocess, "run", return_value=version), \
                mock.patch.object(installer, "_probe_plugin", return_value=unavailable):
            with mock.patch.object(installer, "_install_plugin", side_effect=gone):
                self.assertAborts("config.toml disappeared during Plugin installation",
                                  self.run_install, check_codex=True)
            self.assertEqual(json.loads(pending_of(self.home).read_text())["status"], "aborted")
            pending_of(self.home).unlink()
            config.unlink(missing_ok=True)
            # check1, check2 and the plugin step each call config.toml.is_file(); the third one loses the race
            real_commit, real_is_file, seen = installer._commit, Path.is_file, {"after": False, "n": 0}

            def commit(*a, **k):
                result = real_commit(*a, **k)
                seen["after"] = True
                return result

            def is_file(path):
                if seen["after"] and path == config:
                    seen["n"] += 1
                    if seen["n"] == 3:
                        return False
                return real_is_file(path)

            with mock.patch.object(installer, "_commit", commit), mock.patch.object(Path, "is_file", is_file):
                self.assertAborts("config.toml disappeared before plugin installation",
                                  self.run_install, check_codex=True)
        self.assertEqual(json.loads(pending_of(self.home).read_text())["status"], "aborted")
        self.assertFalse(installer._state_path(self.home).exists())

    def test_foreign_config_mutation_variants(self) -> None:
        unavailable = {
            "name": "shoal-codex", "version": installer.SHOAL_PLUGIN_VERSION, "status": "unavailable",
            "source_sha256": installer._plugin_source_digest(ROOT / "plugin"),
        }
        version = mock.Mock(returncode=0, stdout="codex 0.147.0", stderr="")
        config = self.home / "config.toml"
        for name, junk in (("invalid toml", b"\nnot = [valid\n"), ("foreign table", b"\n[foreign]\nkeep = true\n")):
            with self.subTest(name):
                pending_of(self.home).unlink(missing_ok=True)
                config.unlink(missing_ok=True)

                def mutate(**_):
                    config.write_bytes(config.read_bytes() + junk)
                    return unavailable

                with mock.patch.object(installer.subprocess, "run", return_value=version), \
                        mock.patch.object(installer, "_probe_plugin", return_value=unavailable), \
                        mock.patch.object(installer, "_install_plugin", side_effect=mutate):
                    err = self.assertAborts("foreign config mutation during plugin installation",
                                            self.run_install, check_codex=True)
                if name == "invalid toml":
                    self.assertIsInstance(err.__cause__, installer.InstallAbort)
                self.assertEqual(json.loads(pending_of(self.home).read_text())["status"], "aborted")
                self.assertFalse(installer._state_path(self.home).exists())


class PluginNotNewer(Base):
    def run_guard(self, rows, version=None) -> None:
        patches = [mock.patch.object(installer, "_installed_plugin_rows", return_value=rows)]
        if version is not None:
            patches.append(mock.patch.object(installer, "SHOAL_PLUGIN_VERSION", version))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        installer._assert_plugin_not_newer(source_root=ROOT, codex_home=self.home, allow_downgrade=False)

    def row(self, version):
        return {"name": "shoal-codex", "marketplaceName": "shoal-codex", "version": version}

    def test_table(self) -> None:
        cases = [
            ("source malformed", [self.row("1.0.0")], "not-a-version", "source plugin version is malformed"),
            ("installed not str", [self.row(5)], None, "installed plugin version is malformed"),
            ("installed unparseable", [self.row("???")], None, "installed plugin version is malformed"),
            ("installed newer", [self.row("99.0.0")], None,
             "installed plugin is newer than source; explicit downgrade approval required"),
        ]
        for name, rows, version, message in cases:
            with self.subTest(name):
                self.assertAborts(message, self.run_guard, rows, version)
                mock.patch.stopall()
        self.assertEqual(snapshot(self.home), {})

    def test_other_plugin_rows_and_downgrade_flag_do_not_abort(self) -> None:
        self.run_guard([{"name": "other", "marketplaceName": "other", "version": "99.0.0"}])
        mock.patch.stopall()
        with mock.patch.object(installer, "_installed_plugin_rows", return_value=[self.row("99.0.0")]):
            installer._assert_plugin_not_newer(source_root=ROOT, codex_home=self.home, allow_downgrade=True)


class StateAndHookTargets(Base):
    def test_load_state(self) -> None:
        self.assertIsNone(installer._load_state(self.home))
        state = installer._state_path(self.home)
        state.write_bytes(b'{"status": "pending"}')
        self.assertAborts("install state is not a committed transaction", installer._load_state, self.home)
        state.write_bytes(b"[1]")
        self.assertAborts("install state is not a committed transaction", installer._load_state, self.home)
        state.write_bytes(b'{"a":1,"a":2}')
        err = self.assertAborts("install state is invalid; resolve it before writing", installer._load_state, self.home)
        self.assertIsInstance(err.__cause__, installer.HookRegistrationError)
        pending_of(self.home).write_bytes(b"{}")
        self.assertAborts("pending install state exists; resolve the aborted transaction before writing",
                          installer._load_state, self.home)

    def test_hook_targets(self) -> None:
        check = installer._assert_hook_targets
        outside = self.root / "outside"
        outside.mkdir()
        hooks = self.home / "hooks"
        hooks.symlink_to(outside, target_is_directory=True)
        self.assertAborts("hooks root escapes Codex home", check, self.home)
        hooks.unlink()
        hooks.write_text("x", encoding="utf-8")
        self.assertAborts("hooks root must be a non-symlink directory", check, self.home)
        hooks.unlink()
        hooks.mkdir()
        (self.home / "hooks.json").mkdir()
        self.assertAborts("hook target must be a regular non-symlink file", check, self.home)
        (self.home / "hooks.json").rmdir()
        (self.home / "hooks.json").symlink_to(self.root / "missing.json")
        self.assertAborts("hook target must be a regular non-symlink file", check, self.home)
        (self.home / "hooks.json").unlink()
        script = hooks / "shoal_guard.py"
        script.write_text("x", encoding="utf-8")
        real = Path.lstat

        def lstat(path, *a, **k):
            if path == script:
                raise OSError(errno.EIO, "boom")
            return real(path, *a, **k)

        with mock.patch.object(Path, "lstat", lstat):
            self.assertAborts("hook target is unavailable", check, self.home)
        check(self.home)


class PolicyIdentity(Base):
    def identity(self, content=b"# p\n"):
        target = self.root / "real.md"
        target.write_bytes(content)
        link = self.home / "AGENTS.md"
        link.symlink_to(target)
        return target, link, installer._capture_policy_identity(
            link, follow_policy_symlink=True, policy_root=self.root)

    def test_changed_identity_variants(self) -> None:
        message = "policy target changed while install was planned"
        installer._assert_policy_identity(None)
        target, link, identity = self.identity()
        installer._assert_policy_identity(identity)
        # link repointed to another file (path comparison)
        other = self.root / "other.md"
        other.write_bytes(b"# p\n")
        link.unlink()
        link.symlink_to(other)
        self.assertAborts(message, installer._assert_policy_identity, identity)
        # same path, new inode (identity comparison before the digest)
        link.unlink()
        link.symlink_to(target)
        # Replace atomically so the new file is allocated while the old inode
        # is still live; unlink + rewrite lets ext4 hand the same inode back.
        fresh = self.root / "fresh.md"
        fresh.write_bytes(b"# p\n")
        os.replace(fresh, target)
        self.assertAborts(message, installer._assert_policy_identity, identity)
        # same inode, different content (digest comparison)
        identity = installer._capture_policy_identity(link, follow_policy_symlink=True, policy_root=self.root)
        installer._assert_policy_identity(identity)
        target.write_bytes(b"# q\n")
        self.assertAborts(message, installer._assert_policy_identity, identity)
        installer._assert_policy_identity(identity, expected_sha256=installer._sha256_bytes(b"# q\n"))
        self.assertAborts(message, installer._assert_policy_identity, identity,
                          expected_sha256=installer._sha256_bytes(b"# other\n"))
        # link disappears: capture returns None
        link.unlink()
        self.assertAborts(message, installer._assert_policy_identity, identity)


class CopyBackup(Base):
    def setUp(self) -> None:
        super().setUp()
        self.src = self.root / "src"
        self.src.write_bytes(b"orig")
        self.bak = self.root / "bak"

    def copy(self) -> None:
        installer._copy_backup_no_follow(self.src, self.bak, b"orig")

    def test_source_gates(self) -> None:
        self.src.unlink()
        self.assertAborts(f"rollback source changed: {self.src}", self.copy)
        self.src.mkdir()
        self.assertAborts(f"rollback source is not a regular file: {self.src}", self.copy)
        self.src.rmdir()
        self.src.write_bytes(b"changed")
        self.assertAborts(f"rollback source changed while copying: {self.src}", self.copy)
        self.assertFalse(self.bak.exists())

    def test_source_symlink_is_refused(self) -> None:
        real = self.root / "real"
        real.write_bytes(b"orig")
        self.src.unlink()
        self.src.symlink_to(real)
        self.assertAborts(f"rollback source changed: {self.src}", self.copy)

    def test_source_swapped_after_lstat_is_refused(self) -> None:
        # Windows 沒有 O_NOFOLLOW：open 到的 handle 必須與 lstat 看到的是同一個檔
        other = self.root / "other"
        other.write_bytes(b"orig")
        real_lstat = Path.lstat
        swapped = lambda path: real_lstat(other if path == self.src else path)  # noqa: E731
        with mock.patch.object(Path, "lstat", swapped):
            self.assertAborts(f"rollback source changed: {self.src}", self.copy)
        self.assertFalse(self.bak.exists())

    def test_backup_open_gates(self) -> None:
        self.bak.write_bytes(b"squatter")
        self.assertAborts(f"rollback backup path raced: {self.bak}", self.copy)
        self.assertEqual(self.bak.read_bytes(), b"squatter")
        self.bak.unlink()
        self.bak = self.root / "no-dir" / "bak"
        self.assertAborts(f"rollback backup is unavailable: {self.bak}", self.copy)
        self.assertFalse(self.bak.parent.exists())

    def test_backup_symlink_is_not_followed(self) -> None:
        victim = self.root / "victim"
        victim.write_bytes(b"keep")
        self.bak.symlink_to(victim)
        self.assertAborts(f"rollback backup path raced: {self.bak}", self.copy)
        self.assertEqual(victim.read_bytes(), b"keep")

    def test_write_failure(self) -> None:
        with mock.patch.object(installer.os, "write", return_value=0):
            self.assertAborts(f"rollback backup write failed: {self.bak}", self.copy)

    def test_backup_not_regular(self) -> None:
        real = os.fstat
        calls = {"n": 0}

        def fstat(fd):
            calls["n"] += 1
            result = real(fd)
            if calls["n"] == 2:
                values = list(result)
                values[0] = stat.S_IFDIR | 0o700
                return os.stat_result(values)
            return result

        with mock.patch.object(installer.os, "fstat", fstat):
            self.assertAborts(f"rollback backup is not a regular file: {self.bak}", self.copy)

    def test_backup_swapped_while_copying(self) -> None:
        real = Path.lstat

        def gone(path, *a, **k):
            if path == self.bak:
                raise OSError(errno.ENOENT, "gone")
            return real(path, *a, **k)

        with mock.patch.object(Path, "lstat", gone):
            self.assertAborts(f"rollback backup changed while copying: {self.bak}", self.copy)
        self.bak.unlink()

        def swapped(path, *a, **k):
            result = real(path, *a, **k)
            if path == self.bak:
                values = list(result)
                values[1] += 1  # st_ino
                return os.stat_result(values)
            return result

        with mock.patch.object(Path, "lstat", swapped):
            self.assertAborts(f"rollback backup changed while copying: {self.bak}", self.copy)


class CommitAborts(Base):
    def setUp(self) -> None:
        super().setUp()
        self.agents = self.home / "agents"
        self.hooks = self.home / "hooks"
        self.agents.mkdir()
        self.target = self.agents / "executor.toml"
        self.old = (ROOT / "templates" / "agents" / "executor.toml").read_bytes() + b"\n# old\n"
        self.target.write_bytes(self.old)
        self.policy = self.home / "AGENTS.md"

    def commit(self, writes=None, **kwargs):
        writes = writes if writes is not None else [(self.target, self.old + b"new", 0o600, self.old)]
        return installer._commit(
            writes, STAMP, agents_root=self.agents, hooks_root=self.hooks,
            codex_home=self.home, policy_path=self.policy, **kwargs)

    def assertUntouched(self) -> None:
        self.assertEqual(self.target.read_bytes(), self.old)
        self.assertEqual([p.name for p in self.agents.iterdir()], ["executor.toml"])
        self.assertEqual(sorted(p.name for p in self.home.iterdir() if p.name.startswith(".")), [])

    def test_gates(self) -> None:
        self.assertAborts(f"{self.target} changed while install was planned", self.commit,
                          [(self.target, self.old + b"new", 0o600, b"other")])
        self.assertUntouched()
        self.assertAborts("rollback backup path is missing", self.commit,
                          backup_paths={self.home / "x": self.home / "y"})
        self.assertUntouched()
        backup = self.agents / f"executor.toml.shoal-codex-{STAMP}"
        backup.write_bytes(b"squatter")
        self.assertAborts(f"rollback backup already exists: {backup}", self.commit)
        self.assertEqual(backup.read_bytes(), b"squatter")
        backup.unlink()
        self.assertUntouched()

    def test_post_write_fingerprint_mismatch_rolls_back(self) -> None:
        real = installer._replace_staged

        def replace_then_corrupt(temp, destination, original, *, role_directory_fd):
            real(temp, destination, original, role_directory_fd=role_directory_fd)
            destination.write_bytes(b"corrupt")

        with mock.patch.object(installer, "_replace_staged", replace_then_corrupt):
            self.assertAborts("post-write target fingerprint mismatch", self.commit)
        # the target no longer equals the applied payload, so rollback leaves it alone; only the backup remains
        self.assertEqual(self.target.read_bytes(), b"corrupt")
        backup = self.agents / f"executor.toml.shoal-codex-{STAMP}"
        self.assertEqual(backup.read_bytes(), self.old)

    def test_race_before_replacement(self) -> None:
        def racing(temp, destination, original, *, role_directory_fd):
            destination.write_bytes(b"racer")
            return real(temp, destination, original, role_directory_fd=role_directory_fd)

        real = installer._replace_staged
        with mock.patch.object(installer, "_replace_staged", racing):
            self.assertAborts(f"{self.target} changed immediately before replacement", self.commit)
        self.assertEqual(self.target.read_bytes(), b"racer")


class RoleHelpers(Base):
    def setUp(self) -> None:
        super().setUp()
        self.agents = self.home / "agents"
        self.agents.mkdir()
        self.a = self.agents / "executor.toml"
        self.b = self.agents / "scout.toml"
        tpl = ROOT / "templates" / "agents"
        self.A = (tpl / "executor.toml").read_bytes() + b"\n# A\n"
        self.B = (tpl / "scout.toml").read_bytes() + b"\n# B\n"
        self.a.write_bytes(self.A)
        self.b.write_bytes(self.B)

    def writes(self, commit, writes):
        return commit(writes, agents_root=self.agents, codex_home=self.home, stamp=STAMP)

    def backup(self, target):
        return target.with_name(f"{target.name}.shoal-codex-{STAMP}")

    def counted_read(self, schedule):
        """_read_role_target wrapper: schedule maps (path, call number) -> bytes to return instead."""
        real, calls = installer._read_role_target, {}

        def read(path):
            calls[path] = calls.get(path, 0) + 1
            return schedule.get((path, calls[path]), real(path))
        return read

    def test_role_writes_planning(self) -> None:
        src = self.root / "src"
        shutil_copy = __import__("shutil").copytree
        shutil_copy(ROOT / "templates", src / "templates")
        plan = lambda **k: installer._role_writes(source_root=src, codex_home=self.home,
                                                 approved_drift_roles=k.get("approved", set()))
        self.assertAborts("installed_role_drift: agents/executor.toml requires explicit replacement approval", plan)
        agents, writes, notes = plan(approved={"executor", "scout"})
        self.assertEqual(agents, self.agents)
        self.assertIn("replaced drifted role executor with upstream canonical bytes", notes)
        (src / "templates" / "agents" / "scout.toml").write_text("not = [valid", encoding="utf-8")
        self.assertAborts("source role manifest invalid: ", plan, prefix=True, approved={"executor"})
        __import__("shutil").rmtree(src / "templates" / "agents")
        self.assertAborts("source role manifest is unavailable", plan)
        (src / "templates" / "agents").symlink_to(ROOT / "templates" / "agents", target_is_directory=True)
        self.assertAborts("source role manifest is unavailable", plan)
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), (self.A, self.B))

    def test_commit_role_writes_gates(self) -> None:
        elsewhere = self.home / "other" / "scout.toml"
        self.assertAborts("role target escapes agents root", self.writes, installer._commit_role_writes,
                          [(elsewhere, b"n", 0o600, None)])
        self.assertAborts(f"{self.a} changed while install was planned", self.writes,
                          installer._commit_role_writes, [(self.a, b"n", 0o600, b"stale")])
        self.backup(self.a).write_bytes(b"squatter")
        self.assertAborts(f"rollback backup already exists: {self.backup(self.a)}", self.writes,
                          installer._commit_role_writes, [(self.a, b"n", 0o600, self.A)])
        self.backup(self.a).unlink()
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), (self.A, self.B))
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["agents"])

    def test_commit_role_writes_races_roll_back(self) -> None:
        writes = [(self.a, self.A + b"2", 0o600, self.A), (self.b, self.B + b"2", 0o600, self.B)]
        # second planning check (after staging both files) sees b change
        read = self.counted_read({(self.b, 2): b"racer"})
        with mock.patch.object(installer, "_read_role_target", read):
            self.assertAborts(f"{self.b} changed while install was planned", self.writes,
                              installer._commit_role_writes, writes)
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), (self.A, self.B))
        for t in (self.a, self.b):
            self.backup(t).unlink()
        # replacement loop: a replaced, then b changes immediately before its own replacement -> a restored
        read = self.counted_read({(self.b, 3): b"racer"})
        with mock.patch.object(installer, "_read_role_target", read):
            self.assertAborts(f"{self.b} changed immediately before replacement", self.writes,
                              installer._commit_role_writes, writes)
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), (self.A, self.B))
        for t in (self.a, self.b):
            self.backup(t).unlink()
        # post-write verification sees a corrupted target -> a restored, b untouched by rollback (changed)
        real_replace = os.replace
        replaced = {"n": 0}

        def replace(src, dst, **kw):
            real_replace(src, dst, **kw)
            replaced["n"] += 1
            if replaced["n"] == 2:
                self.b.write_bytes(b"corrupt")

        with mock.patch.object(installer.os, "replace", replace):
            self.assertAborts("post-write role fingerprint mismatch", self.writes,
                              installer._commit_role_writes, writes)
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), (self.A, b"corrupt"))

    def test_commit_role_removals(self) -> None:
        removals = [(self.a, self.A), (self.b, self.B)]
        run = lambda rem: installer._commit_role_removals(
            rem, agents_root=self.agents, codex_home=self.home, stamp=STAMP)
        installer._commit_role_removals([], agents_root=self.agents, codex_home=self.home, stamp=STAMP)
        elsewhere = self.home / "other" / "scout.toml"
        self.assertAborts("role target escapes agents root", run, [(elsewhere, b"x")])
        self.assertAborts(f"{self.a} changed while install was planned", run, [(self.a, b"stale")])
        self.backup(self.b).write_bytes(b"squatter")
        self.assertAborts(f"rollback backup already exists: {self.backup(self.b)}", run, removals)
        self.backup(self.b).unlink()
        self.backup(self.a).unlink()  # created for a before b was rejected
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), (self.A, self.B))
        # b changes between the backup pass and its own removal -> a is restored
        read = self.counted_read({(self.b, 2): b"racer"})
        with mock.patch.object(installer, "_read_role_target", read):
            self.assertAborts(f"{self.b} changed immediately before removal", run, removals)
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), (self.A, self.B))


if __name__ == "__main__":
    unittest.main()
