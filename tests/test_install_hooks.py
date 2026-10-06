"""tools/install_hooks.py 的測試（docs/specs/dispatch-enforcement，R7）。

來源是 temp 目錄裡的 git repo（commit 了本 repo 的 hooks/shoal_guard.py）；設定檔、腳本與備份
一律在 temp 目錄，測試不讀寫真實的 ~/.claude、~/.gemini 或 ~/.local。
"""

from __future__ import annotations

import contextlib
import io
import json
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
sys.path.insert(0, str(ROOT / "tests"))
import guard_vectors_helper as helper  # noqa: E402
import install_hooks  # noqa: E402

sys.path.insert(0, str(ROOT / "install"))
import install as installer  # noqa: E402
from hook_registration import GUARD_PROJECTION_ID, TRUSTED_PROJECTIONS  # noqa: E402

FOREIGN_TOOL = {
    "matcher": "Bash",
    "hooks": [{"type": "command", "command": "/opt/audit.sh", "timeout": 5}],
}
FOREIGN_PROMPT = {"hooks": [{"type": "command", "command": "~/bin/jev-route.sh"}]}


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(repo),
            *args,
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


class Case(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.repo = self.base / "repo"
        (self.repo / "hooks").mkdir(parents=True)
        shutil.copy(
            ROOT / "hooks" / "shoal_guard.py", self.repo / "hooks" / "shoal_guard.py"
        )
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "add", "-A")
        run_git(self.repo, "commit", "-q", "-m", "guard")
        self.claude = self.base / "claude-home"
        self.gemini = self.base / "gemini-home"
        self.claude.mkdir()
        self.gemini.mkdir()
        self.codex = self.base / "codex-home"
        self.codex.mkdir()
        self.env = {
            "XDG_DATA_HOME": str(self.base / "data"),
            "XDG_STATE_HOME": str(self.base / "state"),
            "HOME": str(self.base / "no-home"),
        }
        self.script = self.base / "data" / "shoal" / "guard" / "shoal_guard.py"
        self.backups = self.base / "state" / "shoal" / "install-hooks" / "backups"

    def cli(
        self, host: str, *args: str, home: Path | None = None
    ) -> tuple[int, str, str]:
        home = home or {"claude": self.claude, "agy": self.gemini, "codex": self.codex}[host]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = install_hooks.main(
                ["--host", host, "--home", str(home), "--repo", str(self.repo), *args],
                env=self.env,
            )
        return code, out.getvalue(), err.getvalue()

    def settings(self, document: object, home: Path | None = None) -> Path:
        path = (home or self.claude) / "settings.json"
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return path

    def hooks_json(self, document: object) -> Path:
        path = self.gemini / "config" / "hooks.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))


UNRELATED = {
    "model": "opus",
    "permissions": {"allow": ["Bash(ls:*)"]},
    "hooks": {
        "UserPromptSubmit": [FOREIGN_PROMPT],
        "PreToolUse": [FOREIGN_TOOL],
        "Stop": [{"hooks": [{"type": "command", "command": "/opt/stop.sh"}]}],
    },
    "env": {"A": "1"},
}


@unittest.skipIf(sys.platform == "win32", "POSIX shell, symlinks and file modes")
class ClaudeTests(Case):
    def test_dry_run_writes_nothing(self) -> None:
        path = self.settings(UNRELATED)
        before = path.read_bytes()
        code, out, _ = self.cli("claude")
        self.assertEqual(code, 0)
        self.assertIn("dry-run", out)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.script.exists())
        self.assertFalse(self.backups.exists())

    def test_apply_merges_next_to_unrelated_hooks_and_is_idempotent(self) -> None:
        path = self.settings(UNRELATED)
        original = path.read_bytes()
        code, out, err = self.cli("claude", "--apply")
        self.assertEqual(code, 0, err)
        data = self.load(path)
        # key order and every unrelated value survive
        self.assertEqual(list(data), list(UNRELATED))
        self.assertEqual(list(data["hooks"]), list(UNRELATED["hooks"]))
        self.assertEqual(data["permissions"], UNRELATED["permissions"])
        self.assertEqual(data["hooks"]["Stop"], UNRELATED["hooks"]["Stop"])
        prompt, tool = data["hooks"]["UserPromptSubmit"], data["hooks"]["PreToolUse"]
        self.assertEqual(prompt[0], FOREIGN_PROMPT)
        self.assertEqual(tool[0], FOREIGN_TOOL)
        self.assertEqual(len(prompt), 2)
        self.assertEqual(len(tool), 2)
        self.assertEqual(
            tool[1]["matcher"], "Edit|Write|NotebookEdit|MultiEdit|Agent|Workflow"
        )
        for group in (prompt[1], tool[1]):
            (handler,) = group["hooks"]
            self.assertIn("shoal_guard.py --host claude", handler["command"])
            self.assertIn(str(self.script), handler["command"])
        # 2-space JSON with a final newline, like the original
        self.assertEqual(
            path.read_text(encoding="utf-8"), json.dumps(data, indent=2) + "\n"
        )
        # script comes from committed HEAD, 0755
        self.assertEqual(
            self.script.read_bytes(),
            (self.repo / "hooks" / "shoal_guard.py").read_bytes(),
        )
        self.assertEqual(stat.S_IMODE(self.script.stat().st_mode), 0o755)
        # backup: original bytes, 0600 file in a 0700 directory
        (backup,) = self.backups.iterdir()
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
        self.assertEqual((backup / "settings.json").read_bytes(), original)
        self.assertEqual(stat.S_IMODE((backup / "settings.json").stat().st_mode), 0o600)

        # second run: no change, no second backup
        after = path.read_bytes()
        code, out, _ = self.cli("claude", "--apply")
        self.assertEqual(code, 0)
        self.assertIn("不建立備份", out)
        self.assertEqual(path.read_bytes(), after)
        self.assertEqual(len(list(self.backups.iterdir())), 1)

    def test_creates_settings_when_missing(self) -> None:
        code, _, err = self.cli("claude", "--apply")
        self.assertEqual(code, 0, err)
        data = self.load(self.claude / "settings.json")
        self.assertEqual(sorted(data["hooks"]), ["PreToolUse", "UserPromptSubmit"])
        self.assertFalse(self.backups.exists())  # nothing existed to back up

    def test_symlinked_settings_are_written_through(self) -> None:
        target_dir = self.base / "dotfile"
        target_dir.mkdir()
        target = target_dir / "settings.json"
        target.write_text(json.dumps(UNRELATED, indent=2) + "\n", encoding="utf-8")
        os.chmod(target, 0o600)
        link = self.claude / "settings.json"
        os.symlink(target, link)
        code, _, err = self.cli("claude", "--apply")
        self.assertEqual(code, 0, err)
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), str(target))
        self.assertEqual(len(self.load(target)["hooks"]["PreToolUse"]), 2)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(self.load(target)["permissions"], UNRELATED["permissions"])

    def test_uninstall_removes_only_owned_entries(self) -> None:
        path = self.settings(UNRELATED)
        self.assertEqual(self.cli("claude", "--apply")[0], 0)
        code, _, err = self.cli("claude", "--uninstall", "--apply")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load(path), UNRELATED)
        self.assertTrue(
            self.script.exists()
        )  # shared by claude and agy; uninstall keeps it

    def test_uninstall_drops_hooks_it_created_and_ignores_missing_file(self) -> None:
        self.assertEqual(self.cli("claude", "--apply")[0], 0)
        self.assertEqual(self.cli("claude", "--uninstall", "--apply")[0], 0)
        self.assertEqual(self.load(self.claude / "settings.json"), {})
        shutil.rmtree(self.claude)
        self.claude.mkdir()
        self.assertEqual(self.cli("claude", "--uninstall", "--apply")[0], 0)
        self.assertFalse((self.claude / "settings.json").exists())

    def test_stale_entry_is_replaced_in_place_without_touching_neighbours(self) -> None:
        stale = {
            "matcher": "Edit|Write",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 /old/place/shoal_guard.py --host claude",
                    "timeout": 3,
                },
                {"type": "command", "command": "/opt/neighbour.sh"},
            ],
        }
        path = self.settings({"hooks": {"PreToolUse": [FOREIGN_TOOL, stale]}})
        self.assertEqual(self.cli("claude", "--apply")[0], 0)
        groups = self.load(path)["hooks"]["PreToolUse"]
        self.assertEqual(groups[0], FOREIGN_TOOL)
        self.assertEqual(
            groups[1]["matcher"], "Edit|Write|NotebookEdit|MultiEdit|Agent|Workflow"
        )
        self.assertIn(str(self.script), groups[1]["hooks"][0]["command"])
        # the neighbour that shared the stale group stays, as its own group
        self.assertEqual(
            groups[2],
            {
                "matcher": "Edit|Write",
                "hooks": [{"type": "command", "command": "/opt/neighbour.sh"}],
            },
        )
        self.assertEqual(
            sum("shoal_guard.py" in h["command"] for g in groups for h in g["hooks"]), 1
        )

    def test_path_with_spaces_is_quoted_and_still_owned(self) -> None:
        self.env["XDG_DATA_HOME"] = str(self.base / "data dir")
        path = self.settings({})
        self.assertEqual(self.cli("claude", "--apply")[0], 0)
        command = self.load(path)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn("'", command)
        self.assertTrue(install_hooks.is_owned({"command": command}))
        self.assertEqual(self.cli("claude", "--apply")[0], 0)
        self.assertEqual(len(self.load(path)["hooks"]["PreToolUse"]), 1)

    def test_refuses_when_head_has_no_guard_and_ignores_the_working_tree(self) -> None:
        run_git(self.repo, "rm", "-q", "hooks/shoal_guard.py")
        run_git(self.repo, "commit", "-q", "-m", "remove")
        (self.repo / "hooks").mkdir(exist_ok=True)
        (self.repo / "hooks" / "shoal_guard.py").write_text(
            "# working tree only\n", encoding="utf-8"
        )
        path = self.settings(UNRELATED)
        before = path.read_bytes()
        code, _, err = self.cli("claude", "--apply")
        self.assertEqual(code, 2)
        self.assertIn("shoal_guard.py", err)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.script.exists())

    def test_installs_head_not_a_dirty_working_tree(self) -> None:
        committed = (self.repo / "hooks" / "shoal_guard.py").read_bytes()
        (self.repo / "hooks" / "shoal_guard.py").write_bytes(committed + b"# dirty\n")
        self.assertEqual(self.cli("claude", "--apply")[0], 0)
        self.assertEqual(self.script.read_bytes(), committed)

    def test_invalid_or_unexpected_settings_abort_without_writing(self) -> None:
        for text in (
            "{not json",
            "[]",
            json.dumps({"hooks": []}),
            json.dumps({"hooks": {"PreToolUse": {}}}),
        ):
            with self.subTest(text=text):
                (self.claude / "settings.json").write_text(text, encoding="utf-8")
                code, _, err = self.cli("claude", "--apply")
                self.assertEqual(code, 2)
                self.assertIn("不處理", err)
                self.assertEqual(
                    (self.claude / "settings.json").read_text(encoding="utf-8"), text
                )
                self.assertFalse(self.script.exists())

    def test_claude_config_dir_is_the_default_home(self) -> None:
        self.env["CLAUDE_CONFIG_DIR"] = str(self.claude)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = install_hooks.main(
                ["--host", "claude", "--apply", "--repo", str(self.repo)], env=self.env
            )
        self.assertEqual(code, 0, err.getvalue())
        self.assertTrue((self.claude / "settings.json").is_file())

    def test_installed_command_denies_through_a_shell(self) -> None:
        # settings.json commands are run by a shell; replay one with an E0-shaped payload
        path = self.settings({})
        self.assertEqual(self.cli("claude", "--apply")[0], 0)
        command = self.load(path)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        payload = {
            "session_id": "s-1",
            "prompt_id": "p-1",
            "cwd": str(self.base),
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "scout"},
            "agent_id": "a-1",
            "agent_type": "executor",
        }  # a subagent dispatching: leaf violation
        env = {**os.environ, **self.env, "SHOAL_GUARD": "enforce"}
        done = subprocess.run(
            command,
            shell=True,
            input=json.dumps(payload).encode(),
            capture_output=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(
            json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"], "deny"
        )


@unittest.skipIf(sys.platform == "win32", "POSIX shell, symlinks and file modes")
class AgyTests(Case):
    FOREIGN = {
        "orca-status": {
            "PreInvocation": [
                {"type": "command", "command": "bash /x/orca.sh", "timeout": 10}
            ],
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "/x/ask.sh"}]}
            ],
        },
        "herdr": {
            "PreInvocation": [
                {"type": "command", "command": "bash /x/herdr.sh session"}
            ]
        },
    }

    def test_apply_adds_named_group_and_keeps_other_groups(self) -> None:
        path = self.hooks_json(self.FOREIGN)
        original = path.read_bytes()
        code, _, err = self.cli("agy", "--apply")
        self.assertEqual(code, 0, err)
        data = self.load(path)
        self.assertEqual(list(data), ["orca-status", "herdr", "shoal-guard"])
        self.assertEqual({k: data[k] for k in self.FOREIGN}, self.FOREIGN)
        group = data["shoal-guard"]
        (tool,) = group["PreToolUse"]
        self.assertEqual(tool["matcher"], "*")
        self.assertIn("shoal_guard.py --host agy", tool["hooks"][0]["command"])
        (invocation,) = group["PreInvocation"]
        self.assertIn("shoal_guard.py --host agy", invocation["command"])
        self.assertEqual(stat.S_IMODE(self.script.stat().st_mode), 0o755)
        (backup,) = self.backups.iterdir()
        self.assertEqual((backup / "hooks.json").read_bytes(), original)

        after = path.read_bytes()
        code, out, _ = self.cli("agy", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(path.read_bytes(), after)
        self.assertIn("不建立備份", out)

    def test_uninstall_removes_the_group_only(self) -> None:
        path = self.hooks_json(self.FOREIGN)
        self.assertEqual(self.cli("agy", "--apply")[0], 0)
        self.assertEqual(self.cli("agy", "--uninstall", "--apply")[0], 0)
        self.assertEqual(self.load(path), self.FOREIGN)

    def test_symlinked_hooks_json_is_written_through(self) -> None:
        target = self.base / "dotfile-hooks.json"
        target.write_text(json.dumps(self.FOREIGN, indent=2) + "\n", encoding="utf-8")
        link = self.gemini / "config" / "hooks.json"
        link.parent.mkdir(parents=True)
        os.symlink(target, link)
        self.assertEqual(self.cli("agy", "--apply")[0], 0)
        self.assertTrue(link.is_symlink())
        self.assertIn("shoal-guard", self.load(target))

    def test_foreign_handler_inside_the_named_group_survives(self) -> None:
        mixed = {
            "shoal-guard": {
                "PreInvocation": [{"type": "command", "command": "/mine.sh"}]
            }
        }
        path = self.hooks_json(mixed)
        self.assertEqual(self.cli("agy", "--apply")[0], 0)
        flat = self.load(path)["shoal-guard"]["PreInvocation"]
        self.assertEqual(flat[0], {"type": "command", "command": "/mine.sh"})
        self.assertEqual(len(flat), 2)
        self.assertEqual(self.cli("agy", "--uninstall", "--apply")[0], 0)
        self.assertEqual(self.load(path), mixed)

    def test_installed_command_logs_advise_in_shadow(self) -> None:
        path = self.hooks_json({})
        self.assertEqual(self.cli("agy", "--apply")[0], 0)
        command = self.load(path)["shoal-guard"]["PreToolUse"][0]["hooks"][0]["command"]
        sandbox = helper.Sandbox()  # a work dir that is not exempt as a temp path
        self.addCleanup(sandbox.close)
        payload = {"conversationId": "conv-1", "cwd": sandbox.work,
                   "toolCall": {"name": "write_to_file", "args": {"TargetFile": os.path.join(sandbox.work, "a.py")}}}
        env = {**os.environ, **self.env, "HOME": sandbox.home, "TMPDIR": sandbox.tmpdir,
               "XDG_STATE_HOME": os.path.join(sandbox.home, "xdg-state"), "SHOAL_GUARD_MAX_FILES": "0"}
        done = subprocess.run(command, shell=True, input=json.dumps(payload).encode(), capture_output=True,
                              env=env, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        # agy is forced to shadow: nothing on stdout, an advise record in the guard log
        self.assertEqual(done.stdout, b"")
        log = Path(sandbox.home, "xdg-state", "shoal", "guard", "guard.jsonl").read_text(encoding="utf-8")
        self.assertIn('"decision":"advise"', log)


GATE = {
    "hooks": [
        {
            "type": "command",
            "command": '/usr/bin/env python3 "${CODEX_HOME:-$HOME/.codex}/hooks/pilotfish_autoroute_gate.py"',
            "timeout": 10,
        }
    ]
}
THREE_FILE_PATCH = (
    "*** Begin Patch\n*** Add File: a.py\n+1\n*** Add File: b.py\n+2\n"
    "*** Update File: c.py\n@@\n-x\n+y\n*** End Patch\n"
)


@unittest.skipIf(sys.platform == "win32", "POSIX shell, symlinks and file modes")
class CodexTests(Case):
    def hooks_path(self) -> Path:
        return self.codex / "hooks.json"

    def write_hooks(self, document: object) -> Path:
        self.hooks_path().write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return self.hooks_path()

    @property
    def codex_script(self) -> Path:
        return self.codex / "hooks" / "shoal_guard.py"

    def test_apply_writes_the_canonical_projection_next_to_other_hooks(self) -> None:
        mixed = {"hooks": {"UserPromptSubmit": [GATE, FOREIGN_PROMPT], "Stop": [GATE]}}
        path = self.write_hooks(mixed)
        code, out, err = self.cli("codex")
        self.assertEqual(code, 0, err)
        self.assertIn("dry-run", out)
        self.assertEqual(self.load(path), mixed)
        self.assertFalse(self.codex_script.exists())
        code, out, err = self.cli("codex", "--apply")
        self.assertEqual(code, 0, err)
        self.assertIn("提醒", out)  # trust reminder; hooks.state is never written
        hooks = self.load(path)["hooks"]
        projection = TRUSTED_PROJECTIONS[GUARD_PROJECTION_ID]
        self.assertEqual(hooks["UserPromptSubmit"], [GATE, FOREIGN_PROMPT, projection["UserPromptSubmit"]])
        self.assertEqual(hooks["PreToolUse"], [projection["PreToolUse"]])
        self.assertEqual(hooks["Stop"], [GATE])
        self.assertIn("commandWindows", hooks["PreToolUse"][0]["hooks"][0])
        self.assertEqual(self.codex_script.read_bytes(), (ROOT / "hooks" / "shoal_guard.py").read_bytes())
        self.assertFalse((self.codex / "hooks.state").exists())
        self.assertFalse((self.codex / "config.toml").exists())
        # idempotent: bytes unchanged, no second backup
        before, backups = path.read_bytes(), sorted(p.name for p in self.backups.iterdir())
        code, out, _ = self.cli("codex", "--apply")
        self.assertEqual(code, 0)
        self.assertNotIn("提醒", out)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.backups.iterdir()), backups)

    def test_uninstall_restores_hooks_bytes_and_removes_only_the_script(self) -> None:
        path = self.write_hooks({"hooks": {"UserPromptSubmit": [GATE, FOREIGN_PROMPT], "Stop": [GATE]}})
        original = path.read_bytes()
        gate_script = self.codex / "hooks" / "pilotfish_autoroute_gate.py"
        gate_script.parent.mkdir()
        gate_script.write_text("# my experiment\n", encoding="utf-8")
        self.assertEqual(self.cli("codex", "--apply")[0], 0)
        self.assertNotEqual(path.read_bytes(), original)
        code, _, err = self.cli("codex", "--uninstall", "--apply")
        self.assertEqual(code, 0, err)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(self.codex_script.exists())
        self.assertEqual(gate_script.read_text(encoding="utf-8"), "# my experiment\n")
        self.assertEqual(self.cli("codex", "--uninstall", "--apply")[0], 0)  # no-op

    def test_uninstall_keeps_foreign_handler_sharing_a_group(self) -> None:
        mixed = {"hooks": {"PreToolUse": [{"matcher": "x", "hooks": [
            {"type": "command", "command": "/mine.sh"}]}]}}
        path = self.write_hooks(mixed)
        self.assertEqual(self.cli("codex", "--apply")[0], 0)
        document = self.load(path)
        document["hooks"]["PreToolUse"][-1]["hooks"].insert(0, {"type": "command", "command": "/pre.sh"})
        self.write_hooks(document)
        self.assertEqual(self.cli("codex", "--uninstall", "--apply")[0], 0)
        survivors = self.load(path)["hooks"]["PreToolUse"]
        self.assertEqual(survivors[0], mixed["hooks"]["PreToolUse"][0])
        self.assertEqual(survivors[1]["hooks"], [{"type": "command", "command": "/pre.sh"}])
        self.assertEqual(len(survivors), 2)

    def test_creates_hooks_json_and_home_comes_from_codex_home(self) -> None:
        self.env["CODEX_HOME"] = str(self.codex)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = install_hooks.main(["--host", "codex", "--apply", "--repo", str(self.repo)], env=self.env)
        self.assertEqual(code, 0, err.getvalue())
        self.assertTrue(self.hooks_path().is_file())
        self.assertNotIn("注意", out.getvalue())
        self.assertEqual(self.cli("codex", "--uninstall", "--apply")[0], 0)
        self.assertEqual(self.load(self.hooks_path()), {"hooks": {}})  # install.py needs a hooks object

    def test_symlinked_hooks_json_is_written_through(self) -> None:
        real = self.base / "dotfiles" / "hooks.json"
        real.parent.mkdir()
        real.write_text(json.dumps({"hooks": {}}) + "\n", encoding="utf-8")
        self.hooks_path().symlink_to(real)
        self.assertEqual(self.cli("codex", "--apply")[0], 0)
        self.assertTrue(self.hooks_path().is_symlink())
        self.assertIn("PreToolUse", self.load(real)["hooks"])
        self.assertEqual(self.codex_script.parent, self.codex / "hooks")

    def test_malformed_hooks_json_aborts_without_writing(self) -> None:
        path = self.write_hooks({"hooks": {"PreToolUse": "nope"}})
        before = path.read_bytes()
        code, _, err = self.cli("codex", "--apply")
        self.assertEqual(code, 2)
        self.assertIn("中止", err)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.codex_script.exists())

    def test_installed_command_advises_a_three_file_apply_patch(self) -> None:
        self.assertEqual(self.cli("codex", "--apply")[0], 0)
        command = self.load(self.hooks_path())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        sandbox = helper.Sandbox()
        self.addCleanup(sandbox.close)
        payload = {
            "session_id": "s-1", "turn_id": "t-1", "cwd": sandbox.work,
            "hook_event_name": "PreToolUse", "tool_name": "apply_patch",
            "tool_input": {"command": THREE_FILE_PATCH},
        }

        def run(extra: dict) -> subprocess.CompletedProcess:
            env = {**os.environ, **self.env, "HOME": sandbox.home, "TMPDIR": sandbox.tmpdir,
                   "XDG_STATE_HOME": os.path.join(sandbox.home, "xdg-state"),
                   "CODEX_HOME": str(self.codex), **extra}
            env.pop("SHOAL_GUARD", None) if "SHOAL_GUARD" not in extra else None
            return subprocess.run(command, shell=True, input=json.dumps(payload).encode(),
                                  capture_output=True, env=env, timeout=30)

        enforced = run({})
        self.assertEqual(enforced.returncode, 0, enforced.stderr)
        body = json.loads(enforced.stdout)["hookSpecificOutput"]
        self.assertEqual(set(body), {"hookEventName", "additionalContext"})
        shadow = run({"SHOAL_GUARD": "shadow"})
        self.assertEqual(shadow.returncode, 0, shadow.stderr)
        self.assertEqual(shadow.stdout, b"")
        log = Path(sandbox.home, "xdg-state", "shoal", "guard", "guard.jsonl").read_text(encoding="utf-8")
        self.assertIn('"decision":"advise"', log)


@unittest.skipIf(sys.platform == "win32", "POSIX shell, symlinks and file modes")
class CodexInstallPyInteropTests(Case):
    """install.py and install_hooks --host codex must agree on the guard entries."""

    def install_py(self) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return installer.install(
                source_root=ROOT, codex_home=self.codex, dry_run=False, check_codex=False
            )

    def guard_commands(self) -> list[str]:
        hooks = json.loads((self.codex / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        return [
            h["command"]
            for groups in hooks.values()
            for g in groups
            for h in g["hooks"]
            if "shoal_guard.py" in h["command"]
        ]

    def test_install_hooks_then_install_py_adopts_without_duplicates_or_drift(self) -> None:
        self.assertEqual(self.cli("codex", "--apply")[0], 0)
        self.assertEqual(self.install_py(), 0)
        self.assertEqual(len(self.guard_commands()), 2)  # UserPromptSubmit + PreToolUse
        state = self.load(self.codex.with_name("codex-home.pilotfish-install-state.json"))
        self.assertEqual(state["guard_registration"]["projection_id"], GUARD_PROJECTION_ID)
        self.assertIn("hooks/shoal_guard.py", state["target_fingerprints"])
        before = (self.codex / "hooks.json").read_bytes()
        self.assertEqual(self.install_py(), 0)  # idempotent
        self.assertEqual(self.cli("codex", "--apply")[0], 0)  # install_hooks is a no-op now
        self.assertEqual((self.codex / "hooks.json").read_bytes(), before)
        self.assertEqual(len(self.guard_commands()), 2)
        # install.py owns the guard now: bypassing its state is refused
        code, _, err = self.cli("codex", "--uninstall", "--apply")
        self.assertEqual(code, 2)
        self.assertIn("install.py", err)
        self.assertEqual((self.codex / "hooks.json").read_bytes(), before)

    def test_install_py_then_install_hooks_is_a_no_op(self) -> None:
        self.assertEqual(self.install_py(), 0)
        hooks, script = (self.codex / "hooks.json").read_bytes(), self.codex_script_bytes()
        code, out, err = self.cli("codex", "--apply")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.codex / "hooks.json").read_bytes(), hooks)
        self.assertEqual(self.codex_script_bytes(), script)
        self.assertEqual(len(self.guard_commands()), 2)
        self.assertEqual(self.install_py(), 0)

    def test_install_hooks_on_a_pre_guard_installed_home_then_install_py(self) -> None:
        self.assertEqual(self.install_py(), 0)
        import test_install

        test_install._make_pre_guard(self.codex)
        self.assertEqual(self.cli("codex", "--apply")[0], 0)
        self.assertEqual(self.install_py(), 0)  # no installed_hook_drift, no duplicates
        self.assertEqual(len(self.guard_commands()), 2)

    def codex_script_bytes(self) -> bytes:
        return (self.codex / "hooks" / "shoal_guard.py").read_bytes()


if __name__ == "__main__":
    unittest.main()
