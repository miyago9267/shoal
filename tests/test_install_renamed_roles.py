"""Codex installer 對 3.0.0 改名前 role 檔案（mech-executor、plan-verifier）的處理。

規則與 tools/sync_global.py 相同：位元組等於已發行 template 才移除（先備份），其他一律不動並以
note 回報 drift；dry-run 不改任何東西。home 一律是 temp 目錄。
"""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import install as installer  # noqa: E402
from install import InstallAbort, install, install_roles  # noqa: E402

OLD_MECH, OLD_PLAN = "mech-executor", "plan-verifier"
NEW_NAME = {OLD_MECH: "applier", OLD_PLAN: "plan-critic"}


def released(old: str) -> bytes:
    """valid 的舊名 role：現行新名 template 換回舊名，當作「已發行的位元組」。"""
    text = (ROOT / "templates" / "agents" / f"{NEW_NAME[old]}.toml").read_text(encoding="utf-8")
    return text.replace(f'name = "{NEW_NAME[old]}"', f'name = "{old}"', 1).encode()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _snapshot(home: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(home.parent)): p.read_bytes()
        for p in sorted(home.parent.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }


class RenamedRoleInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.agents = self.home / "agents"
        self.agents.mkdir(parents=True)
        patcher = mock.patch.dict(
            installer.RENAMED_ROLE_LEGACY_DIGESTS,
            {old: frozenset({_digest(released(old))}) for old in (OLD_MECH, OLD_PLAN)},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_installer(self, mode: str, dry_run: bool = False) -> str:
        fn = install_roles if mode == "roles-only" else install
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(
                fn(source_root=ROOT, codex_home=self.home, dry_run=dry_run, check_codex=False),
                0,
            )
        return out.getvalue()

    def backups(self, old: str) -> list[Path]:
        return sorted(self.agents.glob(f"{old}.toml.shoal-codex-*"))

    def test_released_old_role_is_backed_up_and_removed(self) -> None:
        for mode in ("roles-only", "full"):
            with self.subTest(mode=mode):
                self.setUp()
                for old in (OLD_MECH, OLD_PLAN):
                    (self.agents / f"{old}.toml").write_bytes(released(old))
                text = self.run_installer(mode)
                self.assertIn("removed renamed role mech-executor.toml", text)
                for old in (OLD_MECH, OLD_PLAN):
                    self.assertFalse((self.agents / f"{old}.toml").exists())
                    backup = self.backups(old)
                    self.assertEqual(len(backup), 1)
                    self.assertEqual(backup[0].read_bytes(), released(old))
                self.assertTrue((self.agents / "applier.toml").is_file())
                self.assertNotIn("renamed role", self.run_installer(mode))  # 第二次沒有東西可動

    def test_dry_run_reports_and_changes_nothing(self) -> None:
        for mode in ("roles-only", "full"):
            with self.subTest(mode=mode):
                self.setUp()
                (self.agents / f"{OLD_MECH}.toml").write_bytes(released(OLD_MECH))
                before = _snapshot(self.home)
                text = self.run_installer(mode, dry_run=True)
                self.assertIn("would remove renamed role mech-executor.toml", text)
                self.assertIn("would remove primary: agents/mech-executor.toml", text)
                self.assertEqual(_snapshot(self.home), before)

    def test_removal_alone_is_not_reported_as_up_to_date(self) -> None:
        self.run_installer("roles-only")
        (self.agents / f"{OLD_PLAN}.toml").write_bytes(released(OLD_PLAN))
        self.assertNotIn("already up to date", self.run_installer("roles-only", dry_run=True))
        self.assertIn("changed native role manifest", self.run_installer("roles-only"))

    def test_modified_old_role_is_drift_and_untouched(self) -> None:
        """symlink 的 role 檔本來就會讓 _assert_agents_root 中止，不到這裡。"""
        for mode in ("roles-only", "full"):
            with self.subTest(mode=mode):
                self.setUp()
                edited = {old: released(old) + b"# mine\n" for old in (OLD_MECH, OLD_PLAN)}
                for old, data in edited.items():
                    (self.agents / f"{old}.toml").write_bytes(data)
                text = self.run_installer(mode)
                self.assertIn("renamed role drift: agents/mech-executor.toml", text)
                self.assertIn("renamed role drift: agents/plan-verifier.toml", text)
                for old, data in edited.items():
                    self.assertEqual((self.agents / f"{old}.toml").read_bytes(), data)
                    self.assertEqual(self.backups(old), [])

    def test_failed_backup_leaves_every_old_role_in_place(self) -> None:
        for old in (OLD_MECH, OLD_PLAN):
            (self.agents / f"{old}.toml").write_bytes(released(old))
        real = installer._copy_backup_no_follow
        calls = []

        def flaky(source: Path, backup: Path, original: bytes) -> None:
            calls.append(source.name)
            if source.name == f"{OLD_PLAN}.toml":
                raise InstallAbort("boom")
            real(source, backup, original)

        with mock.patch.object(installer, "_copy_backup_no_follow", flaky):
            with self.assertRaises(InstallAbort):
                self.run_installer("roles-only")
        for old in (OLD_MECH, OLD_PLAN):
            self.assertEqual((self.agents / f"{old}.toml").read_bytes(), released(old))

    def test_failure_while_removing_restores_removed_roles(self) -> None:
        for old in (OLD_MECH, OLD_PLAN):
            (self.agents / f"{old}.toml").write_bytes(released(old))
        real_unlink = Path.unlink

        def flaky(self_path: Path, *args: object, **kwargs: object) -> None:
            if self_path.name == f"{OLD_PLAN}.toml":
                raise OSError("boom")
            real_unlink(self_path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", flaky):
            with self.assertRaises(OSError):
                self.run_installer("roles-only")
        for old in (OLD_MECH, OLD_PLAN):
            self.assertEqual((self.agents / f"{old}.toml").read_bytes(), released(old))


class RenamedRoleDigestTableTests(unittest.TestCase):
    def test_table_covers_every_released_template_in_git_history(self) -> None:
        """tools/sync_global.py 讀 git 歷史；這張表必須和它看到的位元組一致。"""
        def git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)

        if git("rev-parse", "--git-dir").returncode != 0:
            self.skipTest("not a git checkout")
        if git("rev-parse", "--is-shallow-repository").stdout.strip() == b"true":
            self.skipTest("shallow clone has no template history")
        for old, digests in installer.RENAMED_ROLE_LEGACY_DIGESTS.items():
            path = f"templates/agents/{old}.toml"
            seen = set()
            for rev in git("rev-list", "HEAD", "--", path).stdout.decode().split():
                blob = git("show", f"{rev}:{path}")
                if blob.returncode == 0 and blob.stdout:
                    seen.add(_digest(blob.stdout))
            self.assertEqual(seen, set(digests), old)


if __name__ == "__main__":
    unittest.main()
