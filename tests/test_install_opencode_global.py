"""hosts/opencode/plugin/install/install.sh --global 的測試（docs/specs/opencode-global，O2）。

config dir、state dir（XDG_STATE_HOME）與 HOME 一律是 temp 目錄，測試不讀寫真實的
~/.config/opencode 或 ~/.local/state。安裝來源是本 repo 的 committed HEAD；plugin 的
build 預設用 PATH 上的假 bun（不需要網路），另有一個真 bun 的整合測試，沒有 bun 就 skip。
"""

from __future__ import annotations

import hashlib
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
INSTALL_SH = ROOT / "hosts" / "opencode" / "plugin" / "install" / "install.sh"
ROLES = ("scout", "executor", "verifier", "security-reviewer", "security-executor")
FAKE_PLUGIN = "// fake plugin bundle\n"

# 假 bun：install 什麼都不做；build 只把固定內容寫到 --outfile。
FAKE_BUN = """#!/bin/sh
if [ "$1" = "build" ]; then
  out=
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--outfile" ]; then out=$2; fi
    shift
  done
  printf '// fake plugin bundle\\n' > "$out"
fi
exit 0
"""

# 只放 key 名稱，沒有任何值：daily opencode.json 的 provider 與 enabled_providers。
DAILY_PROVIDER_KEYS = ["openai", "chatgpt-proxy", "google", "aluo", "xai", "grok-cli"]
DAILY_ENABLED_PROVIDERS = [
    "openai",
    "chatgpt-proxy",
    "deepseek",
    "google",
    "github-copilot",
    "xai",
    "grok-cli",
    "opencode",
    "aluo",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def head_bytes(path_in_repo: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"HEAD:{path_in_repo}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def installer_available() -> bool:
    if sys.platform == "win32":
        return False
    return all(shutil.which(tool) for tool in ("sh", "git", "tar")) and bool(
        shutil.which("shasum") or shutil.which("sha256sum")
    )


@unittest.skipUnless(
    installer_available(),
    "install.sh --global needs a POSIX shell, git, tar and shasum",
)
class InstallOpenCodeGlobalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="shoal-opencode-global-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.config = self.tmp / "config"
        self.config.mkdir()
        self.state_home = self.tmp / "state"
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.cwd = self.tmp / "cwd"
        self.cwd.mkdir()
        self.fake_bin = self.tmp / "fakebin"
        self.fake_bin.mkdir()
        fake = self.fake_bin / "bun"
        write_text(fake, FAKE_BUN)
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        self.manifest = (
            self.state_home / "shoal" / "opencode-global" / "install.manifest"
        )

    def env(self, *, fake_bun: bool = True) -> dict[str, str]:
        env = dict(os.environ)
        env.pop("OPENCODE_CONFIG_DIR", None)
        env["HOME"] = str(self.home)
        env["XDG_STATE_HOME"] = str(self.state_home)
        if fake_bun:
            env["PATH"] = f"{self.fake_bin}{os.pathsep}{env['PATH']}"
        return env

    def run_installer(
        self,
        *args: str,
        config: Path | None = None,
        fake_bun: bool = True,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = ["sh", str(INSTALL_SH), "--global"]
        command += ["--config-dir", str(config or self.config)]
        command += list(args)
        return subprocess.run(
            command,
            cwd=cwd or self.cwd,
            env=self.env(fake_bun=fake_bun),
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )

    def installed_files(self) -> list[Path]:
        return sorted(
            path.relative_to(self.config)
            for path in self.config.rglob("*")
            if path.is_file()
        )

    def snapshot(self) -> dict[str, str]:
        return {
            str(path.relative_to(self.config)): sha256(path)
            for path in self.config.rglob("*")
            if path.is_file()
        }

    # ---- enable ----

    def test_enable_installs_files_matching_committed_dist(self) -> None:
        result = self.run_installer("--enable")
        self.assertEqual(result.returncode, 0, result.stderr)

        for role in ROLES:
            installed = self.config / "agents" / f"{role}.md"
            self.assertEqual(
                installed.read_bytes(),
                head_bytes(f"hosts/opencode/dist/roles/{role}.md"),
            )
        for name in ("catalog.json", "routing.json"):
            self.assertEqual(
                (self.config / "pilotfish" / name).read_bytes(),
                head_bytes(f"hosts/opencode/dist/{name}"),
            )
        self.assertEqual(
            (self.config / "plugins" / "pilotfish-opencode.js").read_text(
                encoding="utf-8"
            ),
            FAKE_PLUGIN,
        )
        self.assertEqual(len(self.installed_files()), len(ROLES) + 3)

    def test_manifest_records_every_installed_file_with_matching_hash(self) -> None:
        self.assertEqual(self.run_installer("--enable").returncode, 0)

        text = self.manifest.read_text(encoding="utf-8")
        self.assertIn("state|enabled", text)
        self.assertIn(f"config|{self.config.resolve()}", text)
        entries = [
            line.split("|") for line in text.splitlines() if line.startswith("entry|")
        ]
        self.assertEqual(len(entries), len(ROLES) + 3)
        for _, present, digest, relative in entries:
            self.assertEqual(present, "0")
            self.assertEqual(digest, sha256(self.config / relative), relative)
        # manifest 與備份只放在 state dir，不進 config dir。
        self.assertFalse((self.config / "install.manifest").exists())
        self.assertFalse(any("backups" in str(p) for p in self.installed_files()))

    def test_enable_twice_is_a_no_op(self) -> None:
        self.assertEqual(self.run_installer("--enable").returncode, 0)
        before = self.snapshot()
        repeat = self.run_installer("--enable")
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertIn("already enabled", repeat.stdout)
        self.assertEqual(self.snapshot(), before)

    # ---- disable / rollback ----

    def test_disable_removes_installed_files_and_keeps_user_files(self) -> None:
        user_agent = self.config / "agents" / "monika.md"
        write_text(user_agent, "my own agent\n")
        native = self.config / "opencode.json"
        write_text(native, '{"provider":{"x":{}}}\n')
        self.assertEqual(self.run_installer("--enable").returncode, 0)

        result = self.run_installer("--disable")
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertEqual(
            self.installed_files(), [Path("agents/monika.md"), Path("opencode.json")]
        )
        self.assertEqual(user_agent.read_text(encoding="utf-8"), "my own agent\n")
        self.assertIn("state|disabled", self.manifest.read_text(encoding="utf-8"))

    def test_disable_without_manifest_is_a_no_op(self) -> None:
        result = self.run_installer("--disable")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no install manifest", result.stdout)
        self.assertFalse(self.state_home.exists())

    def test_disable_refuses_when_an_installed_file_was_modified(self) -> None:
        self.assertEqual(self.run_installer("--enable").returncode, 0)
        scout = self.config / "agents" / "scout.md"
        write_text(scout, "edited by hand\n")
        before = self.snapshot()

        result = self.run_installer("--disable")

        self.assertEqual(result.returncode, 1)
        self.assertIn("file changed after installation", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_rollback_removes_agents_plugins_and_pilotfish_json(self) -> None:
        self.assertEqual(self.run_installer("--enable").returncode, 0)
        self.assertTrue((self.config / "agents").is_dir())

        result = self.run_installer("--rollback")
        self.assertEqual(result.returncode, 0, result.stderr)

        # 全新的 config dir：檔案與 installer 建立的三個目錄都應該消失。
        self.assertEqual(self.installed_files(), [])
        for name in ("agents", "plugins", "pilotfish"):
            self.assertFalse((self.config / name).exists(), name)
        self.assertIn("state|rolled_back", self.manifest.read_text(encoding="utf-8"))

    def test_rollback_keeps_directories_the_user_already_had(self) -> None:
        write_text(self.config / "agents" / "monika.md", "mine\n")
        write_text(self.config / "plugins" / "mine.js", "// mine\n")
        self.assertEqual(self.run_installer("--enable").returncode, 0)

        self.assertEqual(self.run_installer("--rollback").returncode, 0)

        self.assertEqual(
            self.installed_files(), [Path("agents/monika.md"), Path("plugins/mine.js")]
        )
        self.assertFalse((self.config / "pilotfish").exists())

    def test_rollback_without_manifest_fails(self) -> None:
        result = self.run_installer("--rollback")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no install manifest", result.stderr)

    def test_enable_after_disable_installs_again(self) -> None:
        self.assertEqual(self.run_installer("--enable").returncode, 0)
        self.assertEqual(self.run_installer("--disable").returncode, 0)
        result = self.run_installer("--enable")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.installed_files()), len(ROLES) + 3)
        self.assertIn("state|enabled", self.manifest.read_text(encoding="utf-8"))

    def test_disable_with_a_different_config_dir_is_refused(self) -> None:
        self.assertEqual(self.run_installer("--enable").returncode, 0)
        other = self.tmp / "other"
        other.mkdir()
        before = self.snapshot()

        result = self.run_installer("--disable", config=other)

        self.assertEqual(result.returncode, 1)
        self.assertIn("manifest was installed into", result.stderr)
        self.assertEqual(self.snapshot(), before)

    # ---- R3：不覆寫使用者檔案 ----

    def test_user_file_with_the_same_name_aborts_without_writing(self) -> None:
        user_scout = self.config / "agents" / "scout.md"
        write_text(user_scout, "my own scout\n")
        write_text(self.config / "plugins" / "pilotfish-opencode.js", "// my plugin\n")
        before = self.snapshot()

        result = self.run_installer("--enable")

        self.assertEqual(result.returncode, 1)
        self.assertIn("nothing was written", result.stderr)
        self.assertIn("agents/scout.md", result.stderr)
        self.assertIn("plugins/pilotfish-opencode.js", result.stderr)
        self.assertEqual(self.snapshot(), before)
        # 完全不寫入：沒有新目錄、沒有 manifest、沒有 state dir。
        self.assertFalse((self.config / "pilotfish").exists())
        self.assertEqual(
            sorted(p.name for p in self.config.iterdir()), ["agents", "plugins"]
        )
        self.assertFalse(self.state_home.exists())

    def test_user_file_matching_the_source_is_adopted_and_restored_on_rollback(
        self,
    ) -> None:
        identical = self.config / "agents" / "scout.md"
        identical.parent.mkdir()
        identical.write_bytes(head_bytes("hosts/opencode/dist/roles/scout.md"))

        self.assertEqual(self.run_installer("--enable").returncode, 0)
        self.assertIn("entry|1|", self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(self.run_installer("--rollback").returncode, 0)

        self.assertEqual(self.installed_files(), [Path("agents/scout.md")])

    def test_file_recorded_in_manifest_with_matching_hash_may_be_replaced(self) -> None:
        # 先前由本 installer 安裝（manifest 有記錄且 hash 相符）的舊版內容可以被取代。
        old = self.config / "agents" / "scout.md"
        write_text(old, "older shoal scout\n")
        write_text(
            self.manifest,
            "version|1\nstate|disabled\n"
            f"config|{self.config.resolve()}\nbackup|backups/old|\n"
            f"entry|0|{sha256(old)}|agents/scout.md\n",
        )

        result = self.run_installer("--enable")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            old.read_bytes(), head_bytes("hosts/opencode/dist/roles/scout.md")
        )

    def test_file_recorded_in_manifest_with_a_different_hash_is_a_conflict(
        self,
    ) -> None:
        edited = self.config / "agents" / "scout.md"
        write_text(edited, "edited after install\n")
        write_text(
            self.manifest,
            "version|1\nstate|disabled\n"
            f"config|{self.config.resolve()}\nbackup|backups/old|\n"
            f"entry|0|{'0' * 64}|agents/scout.md\n",
        )
        before = self.snapshot()

        result = self.run_installer("--enable")

        self.assertEqual(result.returncode, 1)
        self.assertIn("agents/scout.md", result.stderr)
        self.assertEqual(self.snapshot(), before)

    # ---- R5：provider 檢查 ----

    def write_daily_like_opencode_json(self, *, with_deepseek: bool = True) -> None:
        enabled = [
            p for p in DAILY_ENABLED_PROVIDERS if with_deepseek or p != "deepseek"
        ]
        document = {
            "provider": {name: {} for name in DAILY_PROVIDER_KEYS},
            "enabled_providers": enabled,
        }
        write_text(self.config / "opencode.json", json.dumps(document, indent=2) + "\n")

    def test_daily_provider_layout_does_not_warn_about_deepseek(self) -> None:
        self.write_daily_like_opencode_json()

        result = self.run_installer("--enable")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("deepseek", result.stderr)
        self.assertNotIn("not in opencode.json", result.stderr)

    def test_undeclared_provider_warns_but_does_not_abort(self) -> None:
        self.write_daily_like_opencode_json(with_deepseek=False)

        result = self.run_installer("--enable")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "warning: routing.json candidate provider 'deepseek'", result.stderr
        )
        self.assertIn("scout", result.stderr)
        self.assertNotIn("'openai'", result.stderr)
        self.assertTrue((self.config / "agents" / "scout.md").is_file())

    def test_missing_or_unparseable_opencode_json_only_warns(self) -> None:
        missing = self.run_installer("--enable")
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertIn("provider check skipped", missing.stderr)
        self.assertEqual(self.run_installer("--disable").returncode, 0)

        write_text(self.config / "opencode.json", '{ // jsonc\n "provider": {} }\n')
        unparseable = self.run_installer("--enable")
        self.assertEqual(unparseable.returncode, 0, unparseable.stderr)
        self.assertIn("cannot parse opencode.json", unparseable.stderr)

    def test_provider_check_never_prints_config_values(self) -> None:
        write_text(
            self.config / "opencode.json",
            json.dumps(
                {"provider": {"aluo": {"options": {"apiKey": "SECRET-VALUE-123"}}}}
            ),
        )

        result = self.run_installer("--enable")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("SECRET-VALUE-123", result.stdout + result.stderr)

    # ---- R2a：專案 plugin 共存警告 ----

    def test_warns_when_cwd_project_already_has_the_plugin(self) -> None:
        write_text(
            self.cwd / ".opencode" / "plugins" / "pilotfish-opencode.js", "// project\n"
        )

        result = self.run_installer("--enable")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("project plugin found at", result.stderr)
        self.assertIn(str(self.cwd), result.stderr)

    def test_no_coexistence_warning_without_a_project_plugin(self) -> None:
        result = self.run_installer("--enable")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("project plugin found", result.stderr)

    # ---- 參數 ----

    def test_missing_config_directory_fails_before_any_write(self) -> None:
        result = self.run_installer("--enable", config=self.tmp / "does-not-exist")
        self.assertEqual(result.returncode, 1)
        self.assertIn("config directory does not exist", result.stderr)
        self.assertFalse(self.state_home.exists())

    def test_config_dir_falls_back_to_opencode_config_dir_env(self) -> None:
        env = self.env()
        env["OPENCODE_CONFIG_DIR"] = str(self.config)
        result = subprocess.run(
            ["sh", str(INSTALL_SH), "--global", "--enable"],
            cwd=self.cwd,
            env=env,
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.config / "agents" / "scout.md").is_file())

    def test_global_without_an_action_is_a_usage_error(self) -> None:
        result = self.run_installer()
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)

    def test_global_and_target_cannot_be_combined(self) -> None:
        result = subprocess.run(
            ["sh", str(INSTALL_SH), "--global", "--target", str(self.cwd), "--enable"],
            cwd=self.cwd,
            env=self.env(),
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.cwd / ".opencode").exists())

    # ---- R6：--target 不變 ----

    def test_target_mode_still_installs_into_the_project(self) -> None:
        project = self.tmp / "project"
        project.mkdir()
        # --target 流程需要 plugin/ 已有 node_modules 才能 build；這裡只驗證不走 --global 分支。
        result = subprocess.run(
            ["sh", str(INSTALL_SH), "--target", str(project), "--disable"],
            cwd=self.cwd,
            env=self.env(),
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "pilotfish-opencode is disabled: no install manifest", result.stdout
        )
        self.assertFalse(self.state_home.exists())

    def test_target_mode_usage_error_is_unchanged_in_exit_code(self) -> None:
        result = subprocess.run(
            ["sh", str(INSTALL_SH), "--enable"],
            cwd=self.cwd,
            env=self.env(),
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)


@unittest.skipUnless(
    installer_available() and shutil.which("bun"),
    "real-bun integration needs bun and a POSIX shell",
)
class InstallOpenCodeGlobalRealBunTests(unittest.TestCase):
    """用真的 bun build 一次，確認裝出來的 bundle 能在 config dir 的全域層讀到 catalog。"""

    def test_installed_bundle_loads_and_resolves_from_the_global_layer(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shoal-opencode-global-real-") as raw:
            tmp = Path(raw)
            config = tmp / "config"
            config.mkdir()
            project = tmp / "project"
            project.mkdir()
            env = dict(os.environ)
            env.pop("OPENCODE_CONFIG_DIR", None)
            env["HOME"] = str(tmp / "home")
            env["XDG_STATE_HOME"] = str(tmp / "state")

            install = subprocess.run(
                [
                    "sh",
                    str(INSTALL_SH),
                    "--global",
                    "--config-dir",
                    str(config),
                    "--enable",
                ],
                cwd=project,
                env=env,
                capture_output=True,
                encoding="utf-8",
                check=False,
                timeout=170,
            )
            self.assertEqual(install.returncode, 0, install.stderr)
            plugin = config / "plugins" / "pilotfish-opencode.js"
            self.assertGreater(plugin.stat().st_size, 1000)

            script = (
                "const m = await import(process.argv[1]);"
                "const hooks = await m.default({ directory: process.argv[2] });"
                "const ctx = { directory: process.argv[2], worktree: process.argv[2],"
                " sessionID: 's', messageID: 'm', agent: 'scout',"
                " abort: new AbortController().signal, metadata() {}, ask: async () => {} };"
                "const out = await hooks.tool.pilotfish_route.execute({ role: 'scout' }, ctx);"
                "console.log(JSON.stringify({ title: out.title, output: out.output }));"
            )
            env["OPENCODE_CONFIG_DIR"] = str(config)
            run = subprocess.run(
                ["bun", "-e", script, str(plugin), str(project)],
                cwd=tmp,
                env=env,
                capture_output=True,
                encoding="utf-8",
                check=False,
                timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            payload = json.loads(run.stdout.strip().splitlines()[-1])
            self.assertNotIn("catalog.missing", payload["output"])
            self.assertNotIn("plugin.path", payload["output"])


if __name__ == "__main__":
    unittest.main()
