"""repo-layout P3：shoal_install.py --update（R13、R14）。

HOME、XDG_DATA_HOME、CODEX_HOME、CLAUDE_CONFIG_DIR 一律是 temp 目錄；PATH 只有 temp 的 bin，裡面是
假的 claude、codex（有狀態的 Python stub，可指定第 N 次呼叫失敗）和轉呼叫真 git 的 wrapper，
所以不會碰到真的 ~/.claude、~/.codex、~/.local/share/shoal，也不受本機有沒有 claude、codex、bun 影響。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import shoal_install  # noqa: E402
import shoal_update  # noqa: E402

FAKE_CLI = r"""
import json, sys
from pathlib import Path

state = Path(sys.argv[1])
name, argv = sys.argv[2], sys.argv[3:]
db = state / f"{name}.json"
data = json.loads(db.read_text()) if db.exists() else {"marketplaces": [], "plugins": []}
log = state / f"{name}.log"
with log.open("a") as fh:
    fh.write(" ".join(argv) + "\n")
count = len(log.read_text().splitlines())
fail = state / f"{name}.fail_on"
if fail.exists() and str(count) in fail.read_text().split():
    sys.stderr.write(f"fake {name}: forced failure on call {count}\n")
    sys.exit(1)
rest = [a for a in argv if a != "--json"]
version = (state / "codex.version").read_text().strip() if (state / "codex.version").exists() else ""
out = None
if name == "claude":
    if rest[:3] == ["plugin", "marketplace", "list"]:
        out = [{"name": m} for m in data["marketplaces"]]
    elif rest[:3] == ["plugin", "marketplace", "add"]:
        data["marketplaces"].append("shoal")
    elif rest[:2] == ["plugin", "list"]:
        out = [{"id": p} for p in data["plugins"]]
    elif rest[:2] == ["plugin", "install"]:
        data["plugins"].append(rest[2])
else:
    if rest[:3] == ["plugin", "marketplace", "list"]:
        out = {"marketplaces": [{"name": "shoal-codex", "root": s, "marketplaceSource": {"source": s}} for s in data["marketplaces"]]}
    elif rest[:3] == ["plugin", "marketplace", "add"]:
        data["marketplaces"] = [rest[3]]
    elif rest[:3] == ["plugin", "marketplace", "remove"]:
        data["marketplaces"] = []
    elif rest[:2] == ["plugin", "list"]:
        out = {"installed": [{"name": "shoal-codex", "marketplaceName": "shoal-codex", "version": version, "enabled": True,
                              "marketplaceSource": {"source": s}} for s in data["marketplaces"] if data["plugins"]]}
    elif rest[:2] == ["plugin", "add"]:
        data["plugins"] = ["shoal-codex"]
db.write_text(json.dumps(data))
if out is not None:
    print(json.dumps(out))
"""


def sh_wrapper(path: Path, argv: list[str]) -> None:
    if sys.platform == "win32":
        path = path.with_suffix(".cmd")
        path.write_text("@" + " ".join(f'"{a}"' for a in argv) + " %*\n")
    else:
        path.write_text(
            "#!/bin/sh\nexec " + " ".join(f"'{a}'" for a in argv) + ' "$@"\n'
        )
        path.chmod(0o755)


class UpdateBase(unittest.TestCase):
    with_codex = False

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="shoal-p3-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bin = self.tmp / "bin"
        self.state = self.tmp / "state-cli"
        self.bin.mkdir()
        self.state.mkdir()
        home = self.tmp / "home"
        home.mkdir()
        self.env = {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "XDG_DATA_HOME": str(self.tmp / "data"),
            "XDG_STATE_HOME": str(self.tmp / "state"),
            "CODEX_HOME": str(self.tmp / "codex"),
            "GROK_HOME": str(self.tmp / "grok"),
            "OPENCODE_CONFIG_DIR": str(self.tmp / "oc"),
            "CLAUDE_CONFIG_DIR": str(self.tmp / "claude"),
            "PATH": str(self.bin),
        }
        script = self.tmp / "fake_cli.py"
        script.write_text(FAKE_CLI)
        real_git = shutil.which("git")
        assert real_git, "git is required"
        sh_wrapper(self.bin / "git", [real_git])
        self.install_cli("claude", script)
        if self.with_codex:
            mod = shoal_update._load_codex_install()
            (self.state / "codex.version").write_text(mod.SHOAL_PLUGIN_VERSION)
            Path(self.env["CODEX_HOME"]).mkdir()
            self.install_cli("codex", script)
        self.data = Path(self.env["XDG_DATA_HOME"]) / "shoal"
        self.mp = self.data / "claude-marketplace"

    def install_cli(self, name: str, script: Path) -> None:
        sh_wrapper(
            self.bin / name, [sys.executable, str(script), str(self.state), name]
        )

    def fail_on(self, name: str, *calls: int) -> None:
        (self.state / f"{name}.fail_on").write_text(" ".join(map(str, calls)))
        (self.state / f"{name}.log").unlink(missing_ok=True)  # 重新計數

    def calls(self, name: str = "claude") -> list[str]:
        log = self.state / f"{name}.log"
        return log.read_text().splitlines() if log.exists() else []

    def update(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = shoal_install.main(["--update", *argv], self.env)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def statuses(self, out: str) -> dict[str, str]:
        rows = {}
        for line in out.splitlines():
            step, sep, rest = line.partition(": ")
            if sep:
                rows[step] = rest.split(" ", 1)[0]
        return rows

    def leftovers(self) -> list[str]:
        return (
            sorted(
                p.name
                for p in self.data.iterdir()
                if p.name.endswith(".old")
                or p.name.startswith(".claude-marketplace.")
                or p.name.startswith(".codex-marketplace-")
            )
            if self.data.is_dir()
            else []
        )


class UpdateFlowTests(UpdateBase):
    def test_dry_run_reports_and_writes_nothing(self) -> None:
        code, out, err = self.update()
        self.assertEqual(code, 0, out + err)
        self.assertIn("marketplace: updated", out)
        self.assertIn("[dry-run]", out)
        self.assertFalse(self.data.exists())
        self.assertFalse(Path(self.env["CLAUDE_CONFIG_DIR"]).exists())
        # 只有唯讀的 list，沒有 add、install、update
        self.assertTrue(all(" list" in c for c in self.calls()), self.calls())

    def test_apply_installs_then_rerun_is_all_up_to_date(self) -> None:
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("failed", out)
        self.assertEqual(self.statuses(out)["marketplace"], "updated")
        self.assertIn("plugin marketplace add", "\n".join(self.calls()))
        self.assertIn("plugin install shoal@shoal", self.calls())
        self.assertIn("plugin install shoal-dispatch-guard@shoal", self.calls())
        explore = Path(self.env["CLAUDE_CONFIG_DIR"]) / "agents" / "Explore.md"
        self.assertEqual(
            explore.read_bytes(),
            subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(ROOT),
                    "show",
                    "HEAD:hosts/claude/dist/agents/Explore.md",
                ]
            ),
        )
        self.assertEqual(self.leftovers(), [])
        self.assertIn("verify guard: up-to-date", out)

        before = len(self.calls())
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        for step, status in self.statuses(out).items():
            self.assertIn(status, ("up-to-date", "skipped"), f"{step}: {out}")
        self.assertEqual(self.statuses(out)["marketplace"], "up-to-date")
        self.assertTrue(
            all(" list" in c for c in self.calls()[before:]), self.calls()[before:]
        )

    def test_marketplace_matches_head_export_byte_for_byte(self) -> None:
        self.update("--apply")
        listing = subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT),
                "ls-tree",
                "-r",
                "--name-only",
                "HEAD",
                "--",
                ".claude-plugin",
                "plugins/claude",
                "plugins/claude-guard",
            ],
            text=True,
        ).split()
        self.assertTrue(listing)
        for rel in listing:
            want = subprocess.check_output(
                ["git", "-C", str(ROOT), "show", f"HEAD:{rel}"]
            )
            self.assertEqual((self.mp / rel).read_bytes(), want, rel)
        self.assertFalse((self.mp / "hosts").exists())

    def test_modules_disabled_skip_explore_and_guard(self) -> None:
        shoal_install.write_manifest(self.env, "claude", ["core", "host-claude"])
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        rows = self.statuses(out)
        self.assertEqual(rows["explore"], "skipped")
        self.assertEqual(rows["claude plugin shoal-dispatch-guard@shoal"], "skipped")
        self.assertNotIn("plugin install shoal-dispatch-guard@shoal", self.calls())
        self.assertFalse(
            (Path(self.env["CLAUDE_CONFIG_DIR"]) / "agents" / "Explore.md").exists()
        )

    def test_chain_member_keeps_guard_plugin(self) -> None:
        data = {
            "claude": {"modules": ["core", "host-claude"], "version": ""},
            "chain": [{"name": "x", "command": ["x"], "hosts": ["claude"], "order": 0}],
        }
        shoal_install._save_manifest(self.env, data)
        self.update("--apply")
        self.assertIn("plugin install shoal-dispatch-guard@shoal", self.calls())

    def test_missing_claude_is_skipped_not_failed(self) -> None:
        (self.bin / ("claude.cmd" if sys.platform == "win32" else "claude")).unlink()
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.statuses(out)["marketplace"], "skipped")
        self.assertIn("claude not on PATH", out)
        self.assertFalse(self.mp.exists())

    def test_installed_guard_hash_mismatch_is_failed(self) -> None:
        self.update("--apply")
        # base plugin 也有同名的 shim；rglob 順序依平台而異，直接指定 guard plugin 的那份
        guard = self.mp / "plugins" / "claude-guard" / "hooks" / "shoal_guard.py"
        guard.write_text("tampered")
        up = shoal_update.Updater(self.env, True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            up.verify()
        self.assertIn("verify marketplace: failed", out.getvalue())
        self.assertTrue(up.failed)
        # 只有 marketplace 逐檔比對通過、但 guard 副本被換掉的情形
        up = shoal_update.Updater(self.env, True)
        with (
            mock.patch.object(shoal_install, "tree_digest", return_value="same"),
            contextlib.redirect_stdout(out),
        ):
            up.verify()
        self.assertIn("verify guard: failed", out.getvalue())

    def test_update_rejects_other_modes(self) -> None:
        for extra in (
            ["--host", "claude"],
            ["--list"],
            ["--without", "dispatch-guard"],
        ):
            code, _, _ = self.update(*extra)
            self.assertEqual(code, 2, extra)


class SwapContractTests(UpdateBase):
    """R13 的交換契約：兩次 rename、失敗還原、成功才刪 `.old`、啟動時清殘留。"""

    def stale_marketplace(self) -> str:
        self.update("--apply")
        (self.mp / "stale.txt").write_text(
            "old version"
        )  # 讓內容與 HEAD 不同，下一輪會交換
        return shoal_install.tree_digest(self.mp)

    def test_a_claude_failure_on_second_call_rolls_back(self) -> None:
        before = self.stale_marketplace()
        self.fail_on(
            "claude", 2
        )  # 第 1 次是 marketplace list，第 2 次是 marketplace update
        code, out, err = self.update("--apply")
        self.assertEqual(code, 1)
        self.assertIn("failed", out)
        self.assertEqual(shoal_install.tree_digest(self.mp), before)
        self.assertTrue((self.mp / "stale.txt").exists())
        self.assertEqual(self.leftovers(), [])

    def test_a_failure_on_a_fresh_install_leaves_no_marketplace(self) -> None:
        self.fail_on("claude", 2)  # marketplace add 失敗
        code, out, err = self.update("--apply")
        self.assertEqual(code, 1)
        self.assertIn("failed", out)
        self.assertFalse(self.mp.exists())
        self.assertEqual(self.leftovers(), [])

    def test_a_plugin_step_failure_also_rolls_back(self) -> None:
        before = self.stale_marketplace()
        self.fail_on(
            "claude", 4
        )  # list、marketplace update、plugin list、第一個 plugin update
        code, out, err = self.update("--apply")
        self.assertEqual(code, 1)
        self.assertIn("failed", out)
        self.assertEqual(shoal_install.tree_digest(self.mp), before)
        self.assertEqual(self.leftovers(), [])

    def test_b_leftover_old_and_stage_are_cleaned_and_rerun_succeeds(self) -> None:
        self.stale_marketplace()
        old = self.mp.with_name("claude-marketplace.old")
        (old / "sub").mkdir(parents=True)
        (old / "sub" / "junk").write_text("x")
        stage = self.data / ".claude-marketplace.AbC123"
        stage.mkdir()
        (stage / "junk").write_text("x")
        codex_stage = self.data / ".codex-marketplace-zzz"
        codex_stage.mkdir()
        (self.state / "claude.log").unlink()
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("failed", out)
        self.assertIn("cleanup: updated", out)
        self.assertEqual(self.leftovers(), [])
        self.assertFalse((self.mp / "stale.txt").exists())
        code, out, _ = self.update("--apply")
        self.assertEqual(self.statuses(out)["marketplace"], "up-to-date")

    def test_b_interrupted_between_renames_restores_old(self) -> None:
        self.update("--apply")
        os.rename(
            self.mp, self.mp.with_name("claude-marketplace.old")
        )  # 第一次 rename 後被中斷
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertIn("restore claude-marketplace.old", out)
        self.assertTrue(self.mp.is_dir())
        self.assertEqual(self.statuses(out)["marketplace"], "up-to-date")
        self.assertEqual(self.leftovers(), [])

    def test_dry_run_does_not_clean(self) -> None:
        self.stale_marketplace()
        old = self.mp.with_name("claude-marketplace.old")
        old.mkdir()
        code, out, _ = self.update()
        self.assertEqual(code, 0)
        self.assertIn("cleanup: updated", out)
        self.assertTrue(old.exists())

    def test_swap_uses_renames_not_rmtree_copy(self) -> None:
        self.stale_marketplace()
        with mock.patch.object(
            shoal_update.shutil, "copytree", side_effect=AssertionError("copytree")
        ):
            code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)


class CodexStepTests(UpdateBase):
    with_codex = True

    def test_registers_export_dir_then_rerun_is_up_to_date(self) -> None:
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        export = self.data / "codex-marketplace"
        self.assertEqual(self.statuses(out)["codex marketplace"], "updated")
        self.assertTrue((export / ".agents" / "plugins" / "marketplace.json").is_file())
        self.assertIn(f"plugin marketplace add {export} --json", self.calls("codex"))
        self.assertNotIn(str(ROOT), "\n".join(self.calls("codex")))
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.statuses(out)["codex marketplace"], "up-to-date")
        for step, status in self.statuses(out).items():
            self.assertIn(status, ("up-to-date", "skipped"), f"{step}: {out}")

    def test_stale_export_is_refreshed(self) -> None:
        self.update("--apply")
        (self.data / "codex-marketplace" / "junk.txt").write_text("x")
        code, out, _ = self.update("--apply")
        self.assertEqual(self.statuses(out)["codex marketplace"], "updated")
        self.assertFalse((self.data / "codex-marketplace" / "junk.txt").exists())

    def test_dry_run_leaves_codex_untouched(self) -> None:
        code, out, _ = self.update()
        self.assertEqual(self.statuses(out)["codex marketplace"], "updated")
        self.assertFalse((self.data / "codex-marketplace").exists())
        self.assertEqual(
            self.calls("codex"), [c for c in self.calls("codex") if " list" in c]
        )


class AgyCopyModeTests(UpdateBase):
    def test_copy_mode_reports_up_to_date(self) -> None:  # G2
        with (
            mock.patch("os.symlink", side_effect=OSError("privilege not held")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = shoal_install.main(["--host", "agy", "--apply"], self.env)
        self.assertEqual(code, 0)
        self.assertEqual(
            shoal_install.load_manifest(self.env)["agy"]["agy_mode"], "copy"
        )
        code, out, err = self.update()
        self.assertEqual(code, 0, out + err)
        self.assertRegex(out, r"sync agy: up-to-date")
        self.assertNotIn("sync agy: failed", out)
        victim = next(
            p
            for p in (Path(self.env["HOME"]) / ".gemini" / "config" / "skills").rglob(
                "*"
            )
            if p.is_file()
        )
        victim.write_text("drift")
        _, out, _ = self.update()
        self.assertRegex(out, r"sync agy: up-to-date \(.*內容與 hosts/agy/dist 不同")


class NoHeadTests(unittest.TestCase):
    def test_repo_without_head_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            out = io.StringIO()
            env = {
                "HOME": tmp,
                "USERPROFILE": tmp,
                "XDG_DATA_HOME": str(Path(tmp) / "d"),
                "PATH": os.environ["PATH"],
            }
            with (
                mock.patch.object(shoal_update, "REPO", Path(tmp)),
                contextlib.redirect_stdout(out),
            ):
                up = shoal_update.Updater(env, False, Path(tmp))
                try:
                    up.git("rev-parse", "--verify", "HEAD^{commit}")
                except shoal_update.UpdateError:
                    up.emit("head", "failed", "no HEAD")
            self.assertIn("head: failed", out.getvalue())


if __name__ == "__main__":
    unittest.main()
