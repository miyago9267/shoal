"""repo-layout P1：可移植入口（G1、G2、G3、G5、G6）。home、XDG、PATH 一律是 temp 目錄，installer 由假 runner 取代。"""

from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import opencode_global  # noqa: E402
import shoal_install  # noqa: E402
import sync_global  # noqa: E402
from test_sync_global import FAKE_BUN, POSIX  # noqa: E402


class P1Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="shoal-p1-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.env = {
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "XDG_DATA_HOME": str(self.tmp / "data"),
            "XDG_STATE_HOME": str(self.tmp / "state"),
            "CODEX_HOME": str(self.tmp / "codex"),
            "GROK_HOME": str(self.tmp / "grok"),
            "OPENCODE_CONFIG_DIR": str(self.tmp / "oc"),
            "CLAUDE_CONFIG_DIR": str(self.tmp / "claude"),
            "PATH": str(self.bin),  # 只有 fake CLI；沒有的就是「不存在」
        }
        self.calls: list[list[str]] = []
        self.previews: list[list[str]] = []

    def fake_cli(self, name: str) -> str:
        path = self.bin / (name + (".cmd" if sys.platform == "win32" else ""))
        path.write_text(
            "@exit /b 0\n" if sys.platform == "win32" else "#!/bin/sh\nexit 0\n"
        )
        path.chmod(0o755)
        return str(path)

    def runner(self, cmd: list[str], env) -> int:
        self.calls.append(cmd)
        return 0

    def previewer(self, cmd: list[str], env) -> tuple[int, str]:
        self.previews.append(cmd)
        return 0, f"PREVIEW-OF {Path(cmd[1]).name}\n"

    def run_cli(self, *argv: str, runner=None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = shoal_install.main(
                    list(argv), self.env, runner or self.runner, self.previewer
                )
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()


class PortableCoreTests(P1Base):
    def test_no_host_runs_a_shell_or_tar(self) -> None:  # G5、R11
        reg = shoal_install.load_registry()
        for host in reg["hosts"]:
            for cmd in shoal_install.wrapped_commands(
                host, ["core", f"host-{host}", "dispatch-guard"], self.env
            ):
                self.assertNotIn(
                    Path(cmd[0]).name.lower(), ("sh", "bash", "zsh", "tar"), cmd
                )
        cmd = shoal_install.wrapped_commands(
            "opencode", ["core", "host-opencode"], self.env
        )[0]
        self.assertEqual(cmd[0], sys.executable)
        self.assertTrue(cmd[1].endswith("opencode_global.py"))

    def test_core_sources_have_no_sh_bash_tar_literals(self) -> None:
        for name in ("shoal_install.py", "opencode_global.py"):
            text = (ROOT / "tools" / name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"""["'](sh|bash|zsh|tar)["']""", text), name)
        text = (ROOT / "tools" / "sync_global.py").read_text(encoding="utf-8")
        self.assertNotIn('"tar"', text)
        self.assertNotIn('["sh"', text)


class ClaudeTests(P1Base):
    def test_apply_runs_claude_plugin_commands(self) -> None:  # G1
        claude = self.fake_cli("claude")
        code, out, err = self.run_cli("--host", "claude", "--apply")
        self.assertEqual(code, 0, err)
        self.assertEqual(
            [c[1:] for c in self.calls],
            [
                ["plugin", "marketplace", "add", "miyago9267/shoal"],
                ["plugin", "install", "shoal@shoal"],
                ["plugin", "install", "shoal-dispatch-guard@shoal"],
            ],
        )
        self.assertEqual({c[0] for c in self.calls}, {claude})

    def test_existing_marketplace_and_plugin_fall_back_to_update(self) -> None:
        self.fake_cli("claude")

        def runner(cmd, env):
            self.calls.append(cmd)
            return 1 if cmd[2] == "install" or cmd[2:4] == ["marketplace", "add"] else 0

        code, _, err = self.run_cli("--host", "claude", "--apply", runner=runner)
        self.assertEqual(code, 0, err)
        tails = [c[1:] for c in self.calls]
        self.assertIn(["plugin", "marketplace", "update", "shoal"], tails)
        self.assertIn(["plugin", "update", "shoal@shoal"], tails)

    def test_missing_cli_is_skipped_in_dry_run_and_error_on_apply(self) -> None:  # G6
        code, out, _ = self.run_cli("--host", "claude")
        self.assertEqual(code, 0)
        self.assertIn("skipped", out)
        self.assertIn("claude", out)
        code, _, err = self.run_cli("--host", "claude", "--apply")
        self.assertEqual(code, 2)
        self.assertIn("claude", err)
        self.assertEqual(self.calls, [])

    def test_explore_is_installed_from_dist_and_never_overwrites_foreign_file(
        self,
    ) -> None:
        self.fake_cli("claude")
        target = Path(self.env["CLAUDE_CONFIG_DIR"]) / "agents" / "Explore.md"
        dist = (ROOT / shoal_install.EXPLORE_DIST).read_bytes()
        code, _, err = self.run_cli(
            "--host", "claude", "--apply", "--with", "claude-explore"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(target.read_bytes(), dist)
        target.write_bytes(b"mine")
        code, out, _ = self.run_cli(
            "--host", "claude", "--apply", "--with", "claude-explore"
        )
        self.assertEqual(code, 0)
        self.assertEqual(target.read_bytes(), b"mine")
        self.assertIn("kept", out)

    def test_dry_run_does_not_write_explore(self) -> None:
        self.fake_cli("claude")
        self.run_cli("--host", "claude", "--with", "claude-explore")
        self.assertFalse(
            (Path(self.env["CLAUDE_CONFIG_DIR"]) / "agents" / "Explore.md").exists()
        )


class DryRunPreviewTests(P1Base):
    def setUp(self) -> None:
        super().setUp()
        self.fake_cli("codex")

    def test_dry_run_calls_underlying_dry_run_and_shows_output(self) -> None:  # G3
        for host, needle in (
            ("codex", "install.py"),
            ("agy", "install_hooks.py"),
            ("grok", "install_grok.py"),
            ("opencode", "opencode_global.py"),
        ):
            self.previews.clear()
            code, out, err = self.run_cli("--host", host)
            self.assertEqual(code, 0, err)
            self.assertEqual(len(self.previews), 1, host)
            self.assertIn(needle, self.previews[0][1])
            self.assertNotIn("--apply", self.previews[0])
            self.assertIn(f"PREVIEW-OF {needle}", out)
        self.assertEqual(self.calls, [])

    def test_preview_commands_are_dry(self) -> None:
        self.run_cli("--host", "codex")
        self.assertIn("--dry-run", self.previews[0])
        self.previews.clear()
        self.run_cli("--host", "opencode")
        self.assertIn("--dry-run", self.previews[0])
        self.assertIn("--enable", self.previews[0])

    def test_failed_preview_fails_dry_run(self) -> None:
        self.previewer = lambda cmd, env: (3, "boom\n")  # type: ignore[method-assign]
        code, out, err = self.run_cli("--host", "grok")
        self.assertEqual(code, 1)
        self.assertIn("preview", out + err)

    def test_missing_codex_cli_is_skipped_not_failed(self) -> None:  # G6
        (self.bin / ("codex.cmd" if sys.platform == "win32" else "codex")).unlink()
        code, out, _ = self.run_cli("--host", "codex", "--with", "jev-router")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"skipped.*codex")
        self.assertEqual(self.previews, [])  # install.py 需要 codex --version，沒有 CLI 就不預覽


class AgyLinkTests(P1Base):
    def config(self) -> Path:
        return self.home / ".gemini" / "config"

    def names(self, kind: str) -> list[str]:
        return sorted(p.name for p in (ROOT / "hosts/agy/dist" / kind).iterdir())

    def test_apply_links_agents_skills_rules(self) -> None:  # G2
        code, _, err = self.run_cli("--host", "agy", "--apply")
        self.assertEqual(code, 0, err)
        for kind in ("agents", "skills", "rules"):
            for name in self.names(kind):
                link = self.config() / kind / name
                self.assertTrue(link.is_symlink(), link)
                self.assertEqual(
                    os.path.realpath(link),
                    os.path.realpath(ROOT / "hosts/agy/dist" / kind / name),
                )
        self.assertIsNone(
            (shoal_install.load_manifest(self.env) or {})["agy"].get("agy_mode")
        )

    def test_dry_run_links_nothing(self) -> None:
        code, out, _ = self.run_cli("--host", "agy")
        self.assertEqual(code, 0)
        self.assertIn("would link", out)
        self.assertFalse(self.config().exists())

    def test_existing_regular_file_is_not_overwritten(self) -> None:
        name = self.names("agents")[0]
        target = self.config() / "agents" / name
        target.parent.mkdir(parents=True)
        target.write_text("mine")
        code, out, err = self.run_cli("--host", "agy", "--apply")
        self.assertEqual(code, 0, err)
        self.assertEqual(target.read_text(), "mine")
        self.assertFalse(target.is_symlink())
        self.assertIn("kept", out + err)

    def test_symlink_failure_falls_back_to_copy(
        self,
    ) -> None:  # G2、Windows 無 symlink 權限
        with mock.patch("os.symlink", side_effect=OSError("privilege not held")):
            code, _, err = self.run_cli("--host", "agy", "--apply")
        self.assertEqual(code, 0, err)
        for kind in ("agents", "skills", "rules"):
            for name in self.names(kind):
                copy, src = (
                    self.config() / kind / name,
                    ROOT / "hosts/agy/dist" / kind / name,
                )
                self.assertFalse(copy.is_symlink())
                self.assertEqual(
                    shoal_install.tree_digest(copy),
                    shoal_install.tree_digest(src),
                    copy,
                )
        self.assertEqual(
            shoal_install.load_manifest(self.env)["agy"]["agy_mode"], "copy"
        )
        # 再跑一次：copy 模式下更新過期的檔案
        stale = self.config() / "agents" / self.names("agents")[0]
        victim = next(
            p for p in (stale.rglob("*") if stale.is_dir() else [stale]) if p.is_file()
        )
        victim.write_text("stale")
        with mock.patch("os.symlink", side_effect=OSError("privilege not held")):
            self.run_cli("--host", "agy", "--apply")
        self.assertEqual(
            shoal_install.tree_digest(stale),
            shoal_install.tree_digest(ROOT / "hosts/agy/dist/agents" / stale.name),
        )

    def test_sync_global_compares_content_in_copy_mode(self) -> None:
        with mock.patch("os.symlink", side_effect=OSError("privilege not held")):
            self.run_cli("--host", "agy", "--apply")
        ctx = sync_global.Ctx(ROOT, "HEAD", False, {**self.env, "PATH": os.environ["PATH"]})
        self.assertEqual(sync_global.agy_link_problems(ctx), [])
        victim = next(p for p in (self.config() / "skills").rglob("*") if p.is_file())
        victim.write_text("drift")
        self.assertTrue(any("內容" in p for p in sync_global.agy_link_problems(ctx)))


@unittest.skipUnless(POSIX, "needs sh-based fake bun")
class OpenCodePortTests(P1Base):
    def setUp(self) -> None:
        super().setUp()
        (self.bin / "bun").write_text(FAKE_BUN)
        (self.bin / "bun").chmod(0o755)
        for tool in ("git",):
            self.env["PATH"] += os.pathsep + os.path.dirname(
                shutil.which(tool) or "/usr/bin/git"
            )
        self.env["FAKE_BUNDLE"] = "// bundle"
        self.config = Path(self.env["OPENCODE_CONFIG_DIR"])
        self.config.mkdir()

    def run_oc(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = opencode_global.main([*args, "--repo", str(ROOT)], self.env)
        return code, out.getvalue(), err.getvalue()

    def test_enable_disable_rollback_cycle(self) -> None:
        code, out, err = self.run_oc("--enable")
        self.assertEqual(code, 0, err)
        plugin = self.config / "plugins" / "shoal-opencode.js"
        self.assertEqual(plugin.read_text().strip(), "// bundle")
        self.assertTrue((self.config / "agents" / "scout.md").is_file())
        self.assertTrue((self.config / "shoal" / "routing.json").is_file())
        self.assertIn("already enabled", self.run_oc("--enable")[1])
        self.assertEqual(self.run_oc("--disable")[0], 0)
        self.assertFalse(plugin.exists())
        self.assertEqual(self.run_oc("--enable")[0], 0)
        plugin.write_text("edited")
        code, _, err = self.run_oc("--disable")
        self.assertEqual(code, 1)
        self.assertIn("changed after installation", err)

    def test_refuses_to_overwrite_foreign_file(self) -> None:
        (self.config / "plugins").mkdir()
        (self.config / "plugins" / "shoal-opencode.js").write_text("foreign")
        code, _, err = self.run_oc("--enable")
        self.assertEqual(code, 1)
        self.assertIn("refusing to overwrite", err)
        self.assertEqual(
            (self.config / "plugins" / "shoal-opencode.js").read_text(), "foreign"
        )

    def test_dry_run_needs_no_bun_and_writes_nothing(self) -> None:  # G4
        (self.bin / "bun").unlink()
        code, out, _ = self.run_oc("--enable", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("would install", out)
        self.assertIn("bun not found", out)
        self.assertEqual(list(self.config.iterdir()), [])

    def test_apply_without_bun_fails_clearly(self) -> None:  # G4
        (self.bin / "bun").unlink()
        code, _, err = self.run_oc("--enable")
        self.assertEqual(code, 1)
        self.assertIn("bun is required", err)


if __name__ == "__main__":
    unittest.main()
