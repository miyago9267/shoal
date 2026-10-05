"""tools/install_grok.py 的測試（docs/specs/grok-workflow，AC-GW-030 至 AC-GW-040）。

來源是 temp 目錄裡的 git repo（由本 repo 的 hosts/grok/dist 與 VERSION 建立並 commit），
grok home 一律是 temp 目錄；測試不讀寫真實的 ~/.grok。
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import install_grok  # noqa: E402

ROLES = (
    "scout",
    "plan-verifier",
    "security-reviewer",
    "mech-executor",
    "executor",
    "verifier",
    "security-executor",
)
SECRETS = {
    "auth.json": b'{"token": "SECRET-1"}\n',
    "sessions/s1/messages.jsonl": b"{}\n",
    "history.jsonl": b"hello\n",
    "trusted_folders.toml": b"[x]\n",
    ".env": b"KEY=VALUE\n",
    "credentials/token": b"SECRET-2",
}

CONFIG = """# user config
[models]
default = "grok-build"   # keep

[subagents]
enabled = true

[subagents.toggle]
Explore = false
security-reviewer = false
"scout" = false   # old workaround
executor = true
codex = false
plan-verifier = false

[compat.claude]
skills = false
"""

_opened: list[str] = []
_watching = False


def _audit(event: str, args: tuple) -> None:
    if _watching and event == "open" and args and isinstance(args[0], (str, bytes)):
        _opened.append(os.fsdecode(args[0]))


sys.addaudithook(_audit)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(home: Path) -> dict[str, str]:
    return {
        p.relative_to(home).as_posix(): sha(p)
        for p in sorted(home.rglob("*"))
        if p.is_file()
    }


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


class InstallGrokCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.repo, self.home = base / "repo", base / "grok-home"
        (self.repo / "hosts" / "grok").mkdir(parents=True)
        shutil.copytree(
            ROOT / "hosts" / "grok" / "dist", self.repo / "hosts" / "grok" / "dist"
        )
        shutil.copy(
            ROOT / "hosts" / "grok" / "VERSION",
            self.repo / "hosts" / "grok" / "VERSION",
        )
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "add", "-A")
        run_git(self.repo, "commit", "-q", "-m", "dist")
        self.home.mkdir()
        self.dist = self.repo / "hosts" / "grok" / "dist"
        self.version = (
            (self.repo / "hosts" / "grok" / "VERSION")
            .read_text(encoding="utf-8")
            .strip()
        )

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = install_grok.main(
                    ["--grok-home", str(self.home), "--repo", str(self.repo), *args]
                )
            except SystemExit as exc:  # argparse 的錯誤
                code = int(exc.code)
        return code, out.getvalue(), err.getvalue()

    def installable(self) -> dict[str, str]:
        return {
            p.relative_to(self.dist).as_posix(): sha(p)
            for p in sorted(self.dist.rglob("*"))
            if p.is_file()
            and p.relative_to(self.dist).parts[0]
            in ("agents", "roles", "rules", "hooks")
        }

    def installed(self) -> dict[str, str]:
        return {
            k: v for k, v in tree(self.home).items() if not k.startswith("backups/")
        }

    def write_config(self, text: str = CONFIG) -> bytes:
        data = text.encode("utf-8")
        (self.home / "config.toml").write_bytes(data)
        return data

    def backups(self) -> list[Path]:
        root = self.home / "backups"
        return sorted(root.iterdir()) if root.is_dir() else []


class DryRunTests(InstallGrokCase):
    def test_dry_run_writes_nothing(self) -> None:  # AC-GW-030
        self.write_config()
        (self.home / "agents").mkdir()
        (self.home / "agents" / "scout.md").write_text(
            "old", encoding="utf-8", newline="\n"
        )
        before = tree(self.home)
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(tree(self.home), before)
        self.assertFalse((self.home / "backups").exists())
        self.assertIn("[取代] agents/scout.md", out)
        self.assertIn("[新增] rules/pilotfish-grok.md", out)
        self.assertIn("dry-run", out)

    def test_dry_run_on_missing_home_creates_nothing(self) -> None:  # AC-GW-030
        shutil.rmtree(self.home)
        self.assertEqual(self.run_cli()[0], 0)
        self.assertFalse(self.home.exists())

    def test_dry_run_flags_disabled_shoal_roles(self) -> None:  # AC-GW-033
        self.write_config()
        _, out, _ = self.run_cli()
        self.assertIn("設成 false: plan-verifier, scout, security-reviewer", out)
        self.assertIn("加 --fix-toggles 才會移除", out)
        self.assertNotIn("Explore", out.split("設成 false:")[1].splitlines()[0])

    def test_cli_runs_under_cp1252_stdout(
        self,
    ) -> None:  # 輸出中文不可在 Windows 預設編碼下失敗
        done = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "install_grok.py"),
                "--grok-home",
                str(self.home),
                "--repo",
                str(self.repo),
            ],
            capture_output=True,
            timeout=60,
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("dry-run", done.stdout.decode("utf-8"))


class ApplyTests(InstallGrokCase):
    def test_apply_installs_files_matching_committed_dist(self) -> None:  # AC-GW-031
        code, out, err = self.run_cli("--apply")
        self.assertEqual(code, 0, err)
        self.assertIn("驗證通過", out)
        expected = self.installable()
        self.assertEqual(self.installed(), expected)
        self.assertEqual(len([k for k in expected if k.startswith("agents/")]), 7)
        self.assertEqual(len([k for k in expected if k.startswith("roles/")]), 7)
        rules = (self.home / "rules" / "pilotfish-grok.md").read_text(encoding="utf-8")
        self.assertIn(f"<!-- pilotfish-grok v{self.version} -->", rules)
        for script in (self.home / "hooks" / "pilotfish-grok").glob("*.py"):
            self.assertTrue(os.access(script, os.X_OK), script.name)
        self.assertFalse((self.home / "config.snippet.toml").exists())

    def test_installed_hooks_are_runnable_from_the_grok_home(self) -> None:  # AC-GW-031
        self.run_cli("--apply")
        config = json.loads(
            (self.home / "hooks" / "pilotfish-grok.json").read_text(encoding="utf-8")
        )
        command = config["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        script = self.home / "hooks" / command  # 相對於 JSON 檔
        payload = json.dumps(
            {"permissionMode": "plan", "toolInput": {"subagent_type": "executor"}}
        )
        # 以 sys.executable 執行：Windows 不看 shebang 與執行權限
        done = subprocess.run(
            [sys.executable, str(script), "--grok-home", str(self.home)],
            input=payload.encode(),
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(json.loads(done.stdout)["decision"], "deny")

    def test_installs_the_dispatch_guard_with_hash_and_exec_bit(self) -> None:  # dispatch-enforcement R7
        self.assertEqual(self.run_cli("--apply")[0], 0)
        rel = "hooks/pilotfish-grok/shoal_guard.py"
        script = self.home / rel
        self.assertEqual(sha(script), sha(self.dist / rel))
        self.assertTrue(os.access(script, os.X_OK))
        config = json.loads(
            (self.home / "hooks" / "pilotfish-grok.json").read_text(encoding="utf-8")
        )["hooks"]
        # the existing plan-mode guard stays first; the dispatch guard is added next to it
        self.assertEqual(
            config["PreToolUse"][0]["hooks"][0]["command"], "pilotfish-grok/plan_mode_guard.py"
        )
        self.assertEqual(config["PreToolUse"][1]["matcher"], "^(search_replace|spawn_subagent)$")
        self.assertEqual(len(config["UserPromptSubmit"]), 1)
        # tampering after install is caught by the same hash verification as any other file
        script.write_bytes(script.read_bytes() + b"# tampered\n")
        self.assertEqual(self.run_cli("--apply")[0], 0)  # re-install restores it
        self.assertEqual(sha(script), sha(self.dist / rel))

    @unittest.skipIf(os.name == "nt", "shoal guard is POSIX-only; it is a no-op on Windows")
    def test_installed_dispatch_guard_runs_from_the_grok_home(self) -> None:  # dispatch-enforcement R7
        self.run_cli("--apply")
        config = json.loads(
            (self.home / "hooks" / "pilotfish-grok.json").read_text(encoding="utf-8")
        )["hooks"]["PreToolUse"][1]["hooks"][0]
        script = self.home / "hooks" / config["command"]  # relative to the JSON file
        payload = {
            "hookEventName": "pre_tool_use", "sessionId": "gs-1", "promptId": "gp-1",
            "cwd": str(self.home), "toolName": "spawn_subagent",
            "toolInput": {"subagent_type": "scout"}, "subagentType": "executor",
        }
        done = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=30,
            env={**os.environ, **config["env"], "SHOAL_GUARD": "enforce",
                 "HOME": str(self.home), "XDG_STATE_HOME": str(self.home / "state")},
        )
        self.assertEqual(json.loads(done.stdout)["decision"], "deny")

    def test_uninstall_removes_the_dispatch_guard_too(self) -> None:  # dispatch-enforcement R7
        self.run_cli("--apply")
        self.assertEqual(self.run_cli("--uninstall", "--apply")[0], 0)
        self.assertFalse((self.home / "hooks" / "pilotfish-grok" / "shoal_guard.py").exists())
        self.assertFalse((self.home / "hooks" / "pilotfish-grok.json").exists())

    def test_aborts_when_dist_guard_differs_from_committed_source(self) -> None:  # R1 single source
        (self.repo / "hooks").mkdir()
        shutil.copy(ROOT / "hooks" / "shoal_guard.py", self.repo / "hooks" / "shoal_guard.py")
        run_git(self.repo, "add", "-A")
        run_git(self.repo, "commit", "-q", "-m", "guard source")
        self.assertEqual(self.run_cli("--apply")[0], 0)  # identical copy: fine
        (self.repo / "hooks" / "shoal_guard.py").write_bytes(
            (self.repo / "hooks" / "shoal_guard.py").read_bytes() + b"# newer\n"
        )
        run_git(self.repo, "commit", "-q", "-am", "guard source changed, dist not rendered")
        before = tree(self.home)
        code, _, err = self.run_cli("--apply")
        self.assertEqual(code, 2)
        self.assertIn("render.py --host grok --write", err)
        self.assertEqual(tree(self.home), before)

    def test_apply_backs_up_replaced_files_and_config(self) -> None:  # AC-GW-032
        config = self.write_config()
        (self.home / "agents").mkdir()
        (self.home / "agents" / "scout.md").write_bytes(b"old scout")
        (self.home / "rules").mkdir()
        old_rules = f"{install_grok.BEGIN}\n<!-- pilotfish-grok v1.0.4 -->\nold\n{install_grok.END}\n".encode()
        (self.home / "rules" / "pilotfish-grok.md").write_bytes(old_rules)
        self.assertEqual(self.run_cli("--apply")[0], 0)
        (backup,) = self.backups()
        self.assertRegex(backup.name, r"^shoal-\d{8}-\d{6}$")
        self.assertEqual((backup / "files" / "config.toml").read_bytes(), config)
        self.assertEqual(
            (backup / "files" / "agents" / "scout.md").read_bytes(), b"old scout"
        )
        self.assertEqual(
            (backup / "files" / "rules" / "pilotfish-grok.md").read_bytes(), old_rules
        )
        self.assertFalse(
            (backup / "files" / "agents" / "executor.md").exists()
        )  # 新增的檔案沒有舊版可備份
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("agents/executor.md", manifest["created"])
        self.assertNotIn("agents/scout.md", manifest["created"])

    def test_apply_without_fix_toggles_keeps_config_byte_identical(
        self,
    ) -> None:  # AC-GW-033
        config = self.write_config()
        self.assertEqual(self.run_cli("--apply")[0], 0)
        self.assertEqual((self.home / "config.toml").read_bytes(), config)

    def test_apply_twice_skips_everything_without_a_second_backup(
        self,
    ) -> None:  # AC-GW-040
        self.run_cli("--apply")
        self.assertEqual(len(self.backups()), 1)
        before = tree(self.home)
        code, out, _ = self.run_cli("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(tree(self.home), before)
        self.assertNotIn("[取代]", out)
        self.assertNotIn("[新增]", out)
        self.assertIn("不建立備份", out)

    def test_installs_committed_head_not_the_working_tree(self) -> None:  # AC-GW-038
        committed = self.installable()
        (self.dist / "agents" / "scout.md").write_text(
            "dirty working tree", encoding="utf-8", newline="\n"
        )
        (self.dist / "rules" / "extra.md").write_text(
            "untracked", encoding="utf-8", newline="\n"
        )
        code, out, _ = self.run_cli("--apply")
        self.assertEqual(code, 0)
        self.assertIn("未 commit", out)
        self.assertEqual(self.installed(), committed)

    def test_aborts_before_writing_on_unbalanced_rules_markers(
        self,
    ) -> None:  # AC-GW-039
        (self.home / "rules").mkdir()
        rules = self.home / "rules" / "pilotfish-grok.md"
        for text in (
            f"{install_grok.BEGIN}\na\n{install_grok.END}\n{install_grok.BEGIN}\nb\n{install_grok.END}\n",
            f"{install_grok.BEGIN}\nno end\n",
        ):
            rules.write_text(text, encoding="utf-8", newline="\n")
            code, _, err = self.run_cli("--apply")
            self.assertEqual(code, 2)
            self.assertIn("marker", err)
            self.assertEqual(
                tree(self.home),
                {"rules/pilotfish-grok.md": hashlib.sha256(text.encode()).hexdigest()},
            )

    def test_aborts_on_invalid_config_toml(self) -> None:
        self.write_config("[subagents\n")
        code, _, err = self.run_cli("--apply")
        self.assertEqual(code, 2)
        self.assertIn("TOML", err)
        self.assertEqual(sorted(tree(self.home)), ["config.toml"])

    def test_verification_failure_is_reported(self) -> None:  # R9
        self.run_cli("--apply")
        files, version, commit = install_grok.load_source(self.repo, "HEAD")
        plan = install_grok.Plan(self.home, files, version, commit, False)
        (self.home / "agents" / "scout.md").write_text(
            "tampered", encoding="utf-8", newline="\n"
        )
        (self.home / "rules" / "pilotfish-grok.md").write_text(
            "<!-- pilotfish-grok v9.9.9 -->\n", encoding="utf-8", newline="\n"
        )
        problems = install_grok.verify(plan)
        self.assertIn("hash 不符: agents/scout.md", problems)
        self.assertTrue(any("marker" in p for p in problems))


class FixTogglesTests(InstallGrokCase):
    EXPECTED = (
        CONFIG.replace("security-reviewer = false\n", "")
        .replace('"scout" = false   # old workaround\n', "")
        .replace("plan-verifier = false\n", "")
    )

    def test_removes_only_shoal_role_false_keys(self) -> None:  # AC-GW-034
        self.write_config()
        code, out, _ = self.run_cli("--apply", "--fix-toggles")
        self.assertEqual(code, 0, out)
        self.assertEqual(
            (self.home / "config.toml").read_text(encoding="utf-8"), self.EXPECTED
        )
        self.assertIn(
            "Explore = false", self.EXPECTED
        )  # 非 shoal 的 key 與 true 的 key 留著
        self.assertIn("executor = true", self.EXPECTED)
        self.assertIn("codex = false", self.EXPECTED)

    def test_preserves_crlf_and_missing_trailing_newline(self) -> None:  # AC-GW-034
        crlf = CONFIG.replace("\n", "\r\n").rstrip("\r\n")
        self.write_config(crlf)
        self.assertEqual(self.run_cli("--apply", "--fix-toggles")[0], 0)
        self.assertEqual(
            (self.home / "config.toml").read_bytes(),
            self.EXPECTED.replace("\n", "\r\n").rstrip("\r\n").encode(),
        )

    def test_dry_run_with_fix_toggles_does_not_edit(self) -> None:  # AC-GW-034
        config = self.write_config()
        code, out, _ = self.run_cli("--fix-toggles")
        self.assertEqual(code, 0)
        self.assertIn("將刪除這些 key", out)
        self.assertEqual((self.home / "config.toml").read_bytes(), config)

    def test_aborts_when_minimal_edit_is_impossible(self) -> None:  # AC-GW-034
        for text in (
            "[subagents]\ntoggle = { scout = false }\n",
            "[subagents]\ntoggle.scout = false\n",
        ):
            with self.subTest(text):
                data = self.write_config(text)
                before = tree(self.home)
                code, _, err = self.run_cli("--apply", "--fix-toggles")
                self.assertEqual(code, 2)
                self.assertIn("無法用最小文字編輯", err)
                self.assertEqual(tree(self.home), before)  # 連其他檔案都沒有寫
                self.assertEqual((self.home / "config.toml").read_bytes(), data)

    def test_no_flagged_toggles_leaves_config_alone(self) -> None:
        data = self.write_config("[subagents.toggle]\nExplore = false\nscout = true\n")
        self.assertEqual(self.run_cli("--apply", "--fix-toggles")[0], 0)
        self.assertEqual((self.home / "config.toml").read_bytes(), data)

    def test_missing_config_is_not_created(self) -> None:
        self.assertEqual(self.run_cli("--apply", "--fix-toggles")[0], 0)
        self.assertFalse((self.home / "config.toml").exists())

    def test_fix_toggles_is_rejected_with_restore_or_uninstall(self) -> None:
        self.assertEqual(self.run_cli("--uninstall", "--fix-toggles")[0], 2)


class PermissionTests(InstallGrokCase):
    @unittest.skipIf(os.name == "nt", "POSIX 權限位元")
    def test_config_mode_is_preserved_and_backups_are_private(self) -> None:
        # config.toml 可能放 api_key：安裝、改 toggle、還原都不能把 0600 放寬
        self.write_config()
        os.chmod(self.home / "config.toml", 0o600)
        self.assertEqual(self.run_cli("--apply", "--fix-toggles")[0], 0)
        self.assertEqual(os.stat(self.home / "config.toml").st_mode & 0o777, 0o600)
        (backup,) = self.backups()
        self.assertEqual(os.stat(backup).st_mode & 0o777, 0o700)
        self.assertEqual(
            os.stat(backup / "files" / "config.toml").st_mode & 0o777, 0o600
        )
        self.assertEqual(self.run_cli("--restore", str(backup), "--apply")[0], 0)
        self.assertEqual(os.stat(self.home / "config.toml").st_mode & 0o777, 0o600)


class RestoreTests(InstallGrokCase):
    def test_restore_brings_back_config_and_files_byte_for_byte(
        self,
    ) -> None:  # AC-GW-035
        config = self.write_config()
        (self.home / "agents").mkdir()
        (self.home / "agents" / "scout.md").write_bytes(b"old scout \xe4\xb8\xad")
        (self.home / "agents" / "mine.md").write_bytes(b"user's own agent")
        before = tree(self.home)
        self.assertEqual(self.run_cli("--apply", "--fix-toggles")[0], 0)
        self.assertNotEqual((self.home / "config.toml").read_bytes(), config)
        (backup,) = self.backups()
        code, out, _ = self.run_cli("--restore", str(backup), "--apply")
        self.assertEqual(code, 0, out)
        after = {
            k: v for k, v in tree(self.home).items() if not k.startswith("backups/")
        }
        self.assertEqual(after, before)
        self.assertEqual((self.home / "config.toml").read_bytes(), config)
        self.assertFalse(
            (self.home / "hooks").exists() and any((self.home / "hooks").rglob("*"))
        )

    def test_restore_is_dry_run_without_apply(self) -> None:  # AC-GW-030
        self.write_config()
        self.run_cli("--apply", "--fix-toggles")
        (backup,) = self.backups()
        before = tree(self.home)
        code, out, _ = self.run_cli("--restore", str(backup))
        self.assertEqual((code, tree(self.home)), (0, before))
        self.assertIn("[還原] config.toml", out)

    def test_restore_rejects_a_directory_that_is_not_a_backup(self) -> None:
        (self.home / "x").mkdir()
        self.assertEqual(
            self.run_cli("--restore", str(self.home / "x"), "--apply")[0], 2
        )

    def test_restore_rejects_manifest_paths_outside_shoal_files(self) -> None:  # R6
        self.run_cli("--apply")
        (backup,) = self.backups()
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        for bad in ("../outside.txt", "auth.json", "/etc/passwd", "sessions/a.jsonl"):
            manifest["created"] = [bad]
            (backup / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8", newline="\n"
            )
            with self.subTest(bad):
                self.assertEqual(
                    self.run_cli("--restore", str(backup), "--apply")[0], 2
                )


class UninstallTests(InstallGrokCase):
    def test_uninstall_removes_only_shoal_files(self) -> None:  # AC-GW-036
        config = self.write_config()
        self.run_cli("--apply")
        for rel in (
            "agents/mine.md",
            "roles/mine.toml",
            "rules/other.md",
            "hooks/other.json",
            "hooks/pilotfish-grok/notes.txt",
        ):
            (self.home / rel).write_bytes(b"user file")
        user_files = {
            rel: sha(self.home / rel)
            for rel in (
                "agents/mine.md",
                "roles/mine.toml",
                "rules/other.md",
                "hooks/other.json",
                "hooks/pilotfish-grok/notes.txt",
            )
        }
        code, _, _ = self.run_cli("--uninstall", "--apply")
        self.assertEqual(code, 0)
        remaining = {
            k: v for k, v in tree(self.home).items() if not k.startswith("backups/")
        }
        self.assertEqual(
            remaining, {**user_files, "config.toml": hashlib.sha256(config).hexdigest()}
        )
        self.assertEqual((self.home / "config.toml").read_bytes(), config)

    def test_uninstall_removes_empty_hook_directory_and_can_be_restored(
        self,
    ) -> None:  # AC-GW-036
        self.write_config()
        self.run_cli("--apply")
        installed = {
            k: v for k, v in tree(self.home).items() if not k.startswith("backups/")
        }
        self.run_cli("--uninstall", "--apply")
        self.assertFalse((self.home / "hooks" / "pilotfish-grok").exists())
        backup = self.backups()[-1]
        self.assertEqual(self.run_cli("--restore", str(backup), "--apply")[0], 0)
        self.assertEqual(
            {k: v for k, v in tree(self.home).items() if not k.startswith("backups/")},
            installed,
        )

    def test_uninstall_is_dry_run_without_apply(self) -> None:  # AC-GW-030
        self.run_cli("--apply")
        before = tree(self.home)
        code, out, _ = self.run_cli("--uninstall")
        self.assertEqual((code, tree(self.home)), (0, before))
        self.assertIn("[移除] rules/pilotfish-grok.md", out)


class CredentialIsolationTests(InstallGrokCase):
    def test_never_touches_credential_session_or_history_files(
        self,
    ) -> None:  # AC-GW-037
        global _watching
        self.write_config()
        for rel, data in SECRETS.items():
            (self.home / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.home / rel).write_bytes(data)
        secrets = {
            self.home / rel: (
                sha(self.home / rel),
                (self.home / rel).stat().st_mtime_ns,
            )
            for rel in SECRETS
        }
        _opened.clear()
        _watching = True
        try:
            self.assertEqual(self.run_cli("--apply", "--fix-toggles")[0], 0)
            (backup,) = self.backups()
            self.assertEqual(self.run_cli("--restore", str(backup), "--apply")[0], 0)
            self.assertEqual(self.run_cli("--apply")[0], 0)
            self.assertEqual(self.run_cli("--uninstall", "--apply")[0], 0)
        finally:
            _watching = False
        opened_under_home = [
            p
            for p in _opened
            if p.startswith(str(self.home.resolve())) or p.startswith(str(self.home))
        ]
        self.assertTrue(opened_under_home)  # 監看機制有效：安裝本身有開啟檔案
        for rel in SECRETS:
            self.assertFalse(
                [p for p in opened_under_home if Path(p) == self.home / rel], rel
            )
        for path, (digest, mtime) in secrets.items():
            self.assertEqual(
                (sha(path), path.stat().st_mtime_ns), (digest, mtime), path.name
            )
        self.assertFalse([p for p in _opened if "/.claude" in p])


if __name__ == "__main__":
    unittest.main()
