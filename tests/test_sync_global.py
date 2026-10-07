"""tools/sync_global.py 的測試。

home、CODEX_HOME、GROK_HOME、XDG_*、OpenCode config dir 一律是 temp 目錄，測試不讀寫真實的
~/.codex、~/.grok、~/.gemini、~/.config/opencode 或 ~/.local。codex 的 role 測試用 temp git repo
（有多個 commit 的 template 歷史）；grok、agy、opencode 用本 repo 的 committed HEAD。
opencode 的 bun 是 PATH 上的假 bun（不需要網路）。
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import sync_global  # noqa: E402

FAKE_BUN = """#!/bin/sh
if [ "$1" = "build" ]; then
  out=
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--outfile" ]; then out=$2; fi
    shift
  done
  printf '%s\\n' "$FAKE_BUNDLE" > "$out"
fi
exit 0
"""
POSIX = sys.platform != "win32" and all(shutil.which(t) for t in ("sh", "git", "tar"))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def snapshot(*roots: Path) -> dict[str, tuple]:
    out = {}
    for root in roots:
        for path in sorted(root.rglob("*")) if root.exists() else []:
            if path.is_file() and not path.is_symlink():
                st = path.stat()
                out[str(path)] = (
                    path.read_bytes(),
                    stat.S_IMODE(st.st_mode),
                    st.st_mtime_ns,
                )
    return out


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="shoal-sync-global-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.codex = self.tmp / "codex"
        self.codex.mkdir()
        self.grok = self.tmp / "grok"
        self.grok.mkdir()
        self.data = self.tmp / "data"
        self.state = self.tmp / "state"

    def env(self, **extra: str) -> dict[str, str]:
        env = dict(os.environ)
        for key in ("OPENCODE_CONFIG_DIR", "OPENCODE_HARNESS_PLUGIN"):
            env.pop(key, None)
        env.update(
            HOME=str(self.home),
            CODEX_HOME=str(self.codex),
            GROK_HOME=str(self.grok),
            XDG_DATA_HOME=str(self.data),
            XDG_STATE_HOME=str(self.state),
        )
        env.update(extra)
        return env

    def sync(
        self, *args: str, env: dict[str, str] | None = None
    ) -> tuple[int, list[str]]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sync_global.main(list(args), env or self.env())
        return code, buf.getvalue().splitlines()


@unittest.skipUnless(POSIX, "needs git")
class CodexTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.repo = self.tmp / "repo"
        (self.repo / "hooks").mkdir(parents=True)
        (self.repo / "templates" / "agents").mkdir(parents=True)
        git(self.repo, "init", "-q")
        (self.repo / "hooks" / "shoal_guard.py").write_text("# guard v1\n")
        self.template("a.toml", "v1\n")
        self.commit("v1")
        self.agents = self.codex / "agents"
        self.agents.mkdir()

    def template(self, name: str, text: str) -> None:
        (self.repo / "templates" / "agents" / name).write_text(text)

    def commit(self, msg: str) -> None:
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", msg)

    def codex_sync(self, *extra: str) -> list[str]:
        code, lines = self.sync("--host", "codex", "--repo", str(self.repo), *extra)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        return lines

    def test_up_to_date_is_a_no_op(self) -> None:
        (self.agents / "a.toml").write_text("v1\n")
        self.assertTrue(
            self.codex_sync("--apply")[0].startswith("codex: updated (guard hooks")
        )
        before = snapshot(self.codex, self.state, self.data)
        self.assertEqual(self.codex_sync("--apply"), ["codex: up-to-date"])
        self.assertEqual(snapshot(self.codex, self.state, self.data), before)

    def test_dry_run_reports_without_writing(self) -> None:
        (self.agents / "a.toml").write_text("v1\n")
        self.template("a.toml", "v2\n")
        self.commit("v2")
        before = snapshot(self.codex, self.state, self.data)
        line = self.codex_sync()[0]
        self.assertIn("updated (guard hooks; roles: a.toml)", line)
        self.assertTrue(line.endswith("[dry-run]"))
        self.assertEqual(snapshot(self.codex, self.state, self.data), before)

    def test_update_replaces_known_older_version_and_keeps_mode(self) -> None:
        target = self.agents / "a.toml"
        target.write_text("v1\n")
        target.chmod(0o600)
        self.template("a.toml", "v2\n")
        self.commit("v2")
        self.assertIn("roles: a.toml", self.codex_sync("--apply")[0])
        self.assertEqual(target.read_text(), "v2\n")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual([p.name for p in self.agents.iterdir()], ["a.toml"])
        self.assertEqual(self.codex_sync("--apply"), ["codex: up-to-date"])

    def test_user_modified_role_is_left_as_drift(self) -> None:
        target = self.agents / "a.toml"
        self.codex_sync("--apply")
        target.write_text("my own edits\n")
        self.template("a.toml", "v2\n")
        self.commit("v2")
        self.assertEqual(
            self.codex_sync("--apply"), ["codex: up-to-date (drift: a.toml)"]
        )
        self.assertEqual(target.read_text(), "my own edits\n")

    def test_symlinked_role_is_drift_and_untouched(self) -> None:
        elsewhere = self.tmp / "elsewhere.toml"
        elsewhere.write_text("v1\n")
        (self.agents / "a.toml").symlink_to(elsewhere)
        self.codex_sync("--apply")
        self.assertTrue((self.agents / "a.toml").is_symlink())
        self.assertEqual(elsewhere.read_text(), "v1\n")

    def test_missing_codex_home_is_skipped(self) -> None:
        shutil.rmtree(self.codex)
        self.assertEqual(self.codex_sync(), [f"codex: skipped ({self.codex} 不存在)"])


@unittest.skipUnless(POSIX, "needs git")
class GrokTests(Base):
    def install(self) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "install_grok.py"), "--apply"],
            env=self.env(),
            check=True,
            capture_output=True,
        )

    def test_no_change_is_skipped_without_backup(self) -> None:
        self.install()
        before = snapshot(self.grok)
        code, lines = self.sync("--host", "grok", "--apply")
        self.assertEqual((code, lines), (0, ["grok: up-to-date"]))
        self.assertEqual(snapshot(self.grok), before)

    def test_changed_dist_file_is_restored_only_with_apply(self) -> None:
        self.install()
        victim = next(self.grok.glob("roles/*"))
        victim.write_text("stale\n")
        code, lines = self.sync("--host", "grok")
        self.assertEqual(lines, ["grok: updated (dist files) [dry-run]"])
        self.assertEqual(victim.read_text(), "stale\n")
        code, lines = self.sync("--host", "grok", "--apply")
        self.assertEqual(lines, ["grok: updated (dist files)"])
        self.assertNotEqual(victim.read_text(), "stale\n")
        self.assertEqual(
            self.sync("--host", "grok", "--apply")[1], ["grok: up-to-date"]
        )


@unittest.skipUnless(POSIX, "needs git")
class AgyTests(Base):
    def links(self, skip: str | None = None) -> None:
        config = self.home / ".gemini" / "config"
        for kind in ("agents", "skills"):
            (config / kind).mkdir(parents=True, exist_ok=True)
            for src in (ROOT / "hosts" / "agy" / "dist" / kind).iterdir():
                if f"{kind}/{src.name}" != skip:
                    (config / kind / src.name).symlink_to(src)

    def test_symlinks_ok_then_drift(self) -> None:
        self.links()
        code, lines = self.sync("--host", "agy")
        self.assertEqual(code, 0)
        self.assertRegex(
            lines[0],
            r"^agy: (up-to-date|updated \(guard hooks; symlinks ok\) \[dry-run\])",
        )
        self.assertIn("symlinks ok", lines[0])
        shutil.rmtree(self.home / ".gemini")
        self.links(skip="agents/scout")
        self.assertIn(
            "symlink drift: agents/scout 不是 symlink", self.sync("--host", "agy")[1][0]
        )

    def test_dry_run_does_not_write(self) -> None:
        self.links()
        before = snapshot(self.home, self.data, self.state)
        self.sync("--host", "agy")
        self.assertEqual(snapshot(self.home, self.data, self.state), before)


@unittest.skipUnless(POSIX, "needs git")
class OpenCodeTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.config = self.tmp / "opencode"
        self.config.mkdir()
        self.fake_bin = self.tmp / "fakebin"
        self.fake_bin.mkdir()
        fake = self.fake_bin / "bun"
        fake.write_text(FAKE_BUN)
        fake.chmod(0o755)

    def env(self, bundle: str = "// bundle A", **extra: str) -> dict[str, str]:
        env = super().env(
            OPENCODE_CONFIG_DIR=str(self.config), FAKE_BUNDLE=bundle, **extra
        )
        env["PATH"] = f"{self.fake_bin}{os.pathsep}{env['PATH']}"
        return env

    def install(self, bundle: str = "// bundle A") -> None:
        subprocess.run(
            [
                "sh",
                str(ROOT / sync_global.OPENCODE_INSTALL),
                "--global",
                "--config-dir",
                str(self.config),
                "--enable",
            ],
            env=self.env(bundle),
            check=True,
            capture_output=True,
        )

    def plugin(self) -> str:
        return (self.config / "plugins" / "pilotfish-opencode.js").read_text()

    def test_missing_bun_is_skipped(self) -> None:
        empty = self.tmp / "empty"
        empty.mkdir()
        env = self.env()
        env["PATH"] = str(empty)
        code, lines = self.sync("--host", "opencode", env=env)
        self.assertEqual((code, lines), (0, ["opencode: skipped (bun not found)"]))

    def test_not_installed_is_skipped(self) -> None:
        self.assertEqual(
            self.sync("--host", "opencode")[1], ["opencode: skipped (尚未全域安裝)"]
        )

    def test_up_to_date_then_update(self) -> None:
        self.install()
        harness = self.tmp / "harness.js"
        harness.write_text("// bundle A\n")
        env = self.env(OPENCODE_HARNESS_PLUGIN=str(harness))
        before = snapshot(self.config, self.state)
        self.assertEqual(
            self.sync("--host", "opencode", "--apply", env=env)[1],
            ["opencode: up-to-date (harness copy matches)"],
        )
        self.assertEqual(snapshot(self.config, self.state), before)

        env = self.env("// bundle B", OPENCODE_HARNESS_PLUGIN=str(harness))
        line = self.sync("--host", "opencode", env=env)[1][0]
        self.assertEqual(
            line,
            "opencode: updated (plugins/pilotfish-opencode.js; harness copy differs) [dry-run]",
        )
        self.assertEqual(snapshot(self.config, self.state), before)

        line = self.sync("--host", "opencode", "--apply", env=env)[1][0]
        self.assertTrue(
            line.startswith("opencode: updated (plugins/pilotfish-opencode.js")
        )
        self.assertEqual(self.plugin(), "// bundle B\n")
        after = snapshot(self.config)
        self.assertEqual(
            self.sync("--host", "opencode", "--apply", env=env)[1][0],
            "opencode: up-to-date (harness copy differs)",
        )
        self.assertEqual(snapshot(self.config), after)

    def test_modified_installed_file_fails_without_writing(self) -> None:
        self.install()
        plugin = self.config / "plugins" / "pilotfish-opencode.js"
        plugin.write_text("// user edit\n")
        code, lines = self.sync("--host", "opencode", "--apply", "--strict")
        self.assertEqual(code, 1)
        self.assertTrue(lines[0].startswith("opencode: failed (install.sh --disable"))
        self.assertEqual(plugin.read_text(), "// user edit\n")


class CliTests(Base):
    def test_unknown_host_rejected(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            sync_global.main(["--host", "claude"], self.env())

    def test_failure_is_isolated_and_strict_sets_exit(self) -> None:
        def boom(ctx: sync_global.Ctx) -> sync_global.Result:
            raise sync_global.SyncError("boom")

        original = dict(sync_global.RUNNERS)
        self.addCleanup(sync_global.RUNNERS.update, original)
        sync_global.RUNNERS["codex"] = boom
        sync_global.RUNNERS["grok"] = lambda ctx: ("up-to-date", "")
        self.assertEqual(
            self.sync("--host", "codex", "grok"),
            (0, ["codex: failed (boom)", "grok: up-to-date"]),
        )
        self.assertEqual(self.sync("--host", "codex", "grok", "--strict")[0], 1)


if __name__ == "__main__":
    unittest.main()
