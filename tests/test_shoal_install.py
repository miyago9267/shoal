"""tools/shoal_install.py 的測試：home、XDG 一律是 temp 目錄，installer 由假 runner 取代。"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import shoal_install  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="shoal-install-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.data = self.tmp / "data"
        self.env = {
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.data),
            "CODEX_HOME": str(self.tmp / "codex"),
            "GROK_HOME": str(self.tmp / "grok"),
            "OPENCODE_CONFIG_DIR": str(self.tmp / "oc"),
            "CLAUDE_CONFIG_DIR": str(self.tmp / "claude"),
        }
        self.calls: list[list[str]] = []
        self.manifest = self.data / "shoal" / "modules.json"

    def runner(self, cmd: list[str], env) -> int:
        self.calls.append(cmd)
        return 0

    def run_cli(self, *argv: str, runner=None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = shoal_install.main(list(argv), self.env, runner or self.runner)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def tree(self) -> list[str]:
        return sorted(str(p) for p in self.tmp.rglob("*"))


class RegistryTests(Base):
    def test_registry_matches_spec_module_map(self) -> None:
        reg = shoal_install.load_registry()
        mods = reg["modules"]
        for name in ("core", "dispatch-guard", "codex-autoroute", "jev-router", "claude-explore", "external"):
            self.assertIn(name, mods)
        for h in reg["hosts"]:
            self.assertEqual(mods[f"host-{h}"]["kind"], "host")
        self.assertTrue(mods["dispatch-guard"]["default_new"])
        self.assertFalse(mods["jev-router"]["default_new"])

    def test_list_without_host(self) -> None:
        code, out, _ = self.run_cli("--list")
        self.assertEqual(code, 0)
        for name in ("core", "host-codex", "dispatch-guard", "jev-router", "external"):
            self.assertIn(name, out)

    def test_list_with_host_filters_and_shows_state(self) -> None:
        code, out, _ = self.run_cli("--list", "--host", "grok")
        self.assertEqual(code, 0)
        self.assertIn("host-grok", out)
        self.assertNotIn("host-codex", out)
        self.assertNotIn("jev-router", out)
        self.assertIn("not installed", out)
        self.assertEqual(self.tree(), [str(self.home)])  # 只有 setUp 建的 home，沒有寫入

    def test_cli_rejects_bad_input(self) -> None:
        self.assertEqual(self.run_cli("--host", "nope")[0], 2)
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.run_cli("--host", "codex", "--dry-run", "--apply")[0], 2)
        code, _, err = self.run_cli("--host", "grok", "--with", "jev-router")
        self.assertEqual(code, 2)
        self.assertIn("不適用", err)
        code, _, err = self.run_cli("--host", "codex", "--with", "bogus")
        self.assertEqual(code, 2)
        self.assertIn("未知模組", err)
        code, _, err = self.run_cli("--host", "codex", "--only", "core,codex-autoroute")
        self.assertEqual(code, 0)  # host 模組自動補上

    def test_core_and_host_module_always_included(self) -> None:
        reg = shoal_install.load_registry()
        mods, _ = shoal_install.resolve("codex", reg, self.env, [], ["host-codex"], ["codex-autoroute"])
        self.assertEqual(mods, ["core", "host-codex", "codex-autoroute"])


class DryRunTests(Base):
    def test_dry_run_prints_commands_and_writes_nothing(self) -> None:
        for host, needle in (
            ("codex", "install/install.py"),
            ("agy", "install_hooks.py"),
            ("grok", "install_grok.py"),
            ("opencode", "install.sh"),
        ):
            code, out, _ = self.run_cli("--host", host)
            self.assertEqual(code, 0, host)
            self.assertIn("would run:", out)
            self.assertIn(needle, out)
            self.assertIn("dry-run", out)
        code, out, _ = self.run_cli("--host", "claude")
        self.assertIn("claude plugin install shoal@shoal", out)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.tree(), [str(self.home)])

    def test_new_install_defaults(self) -> None:
        _, out, _ = self.run_cli("--host", "codex")
        self.assertIn("dispatch-guard", out)
        self.assertIn("codex-autoroute", out)
        self.assertNotIn("jev-router", out.splitlines()[0])
        self.assertIn("new-install defaults", out)

    def test_with_jev_router_adds_plugin_command(self) -> None:
        _, out, _ = self.run_cli("--host", "codex", "--with", "jev-router")
        self.assertIn("plugin add shoal-jev-router@shoal-codex", out)

    def test_without_guard_is_recorded_only_with_note(self) -> None:
        _, out, _ = self.run_cli("--host", "codex", "--without", "dispatch-guard")
        self.assertIn("S3", out)
        self.assertNotIn("dispatch-guard,", out.splitlines()[0])

    def test_only_keeps_core_and_host(self) -> None:
        _, out, _ = self.run_cli("--host", "claude", "--only", "core,host-claude")
        self.assertEqual(out.splitlines()[0].split("modules: ")[1].split("  ")[0], "core, host-claude")


class ApplyTests(Base):
    def test_apply_runs_installers_and_writes_manifest(self) -> None:
        code, out, _ = self.run_cli("--host", "grok", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.calls), 1)
        self.assertIn("install_grok.py", self.calls[0][1])
        self.assertIn("--apply", self.calls[0])
        data = json.loads(self.manifest.read_text())
        self.assertEqual(data["grok"]["modules"], ["core", "host-grok", "dispatch-guard"])
        self.assertEqual(data["chain"], [])
        self.assertEqual(data["grok"]["version"], (ROOT / "VERSION").read_text().strip())

    def test_apply_preserves_other_hosts_and_chain(self) -> None:
        self.manifest.parent.mkdir(parents=True)
        chain = [{"name": "x", "command": ["x"], "hosts": ["codex"], "order": 1}]
        self.manifest.write_text(json.dumps({"agy": {"modules": ["core", "host-agy"], "version": "1"}, "chain": chain}))
        self.assertEqual(self.run_cli("--host", "grok", "--apply")[0], 0)
        data = json.loads(self.manifest.read_text())
        self.assertEqual(data["chain"], chain)
        self.assertEqual(data["agy"]["modules"], ["core", "host-agy"])
        self.assertIn("grok", data)

    def test_manifest_selection_is_the_base_of_next_run(self) -> None:
        self.run_cli("--host", "codex", "--without", "dispatch-guard", "--apply")
        self.assertNotIn("dispatch-guard", json.loads(self.manifest.read_text())["codex"]["modules"])
        _, out, _ = self.run_cli("--host", "codex")
        self.assertIn("(base: manifest)", out)

    def test_failed_installer_leaves_no_manifest(self) -> None:
        code, _, err = self.run_cli("--host", "grok", "--apply", runner=lambda c, e: 3)
        self.assertEqual(code, 1)
        self.assertFalse(self.manifest.exists())

    def test_claude_apply_records_manifest_without_running_anything(self) -> None:
        self.assertEqual(self.run_cli("--host", "claude", "--apply")[0], 0)
        self.assertEqual(self.calls, [])
        self.assertIn("claude", json.loads(self.manifest.read_text()))

    def test_xdg_default_under_home(self) -> None:
        del self.env["XDG_DATA_HOME"]
        self.assertEqual(
            shoal_install.manifest_path(self.env), self.home / ".local/share/shoal/modules.json"
        )


class InferenceTests(Base):
    def test_nothing_installed_infers_none(self) -> None:
        for host in ("codex", "claude", "agy", "grok", "opencode"):
            self.assertIsNone(shoal_install.infer(host, self.env), host)

    def test_codex_inferred_from_files(self) -> None:
        codex = Path(self.env["CODEX_HOME"])
        (codex / "agents").mkdir(parents=True)
        role = next((ROOT / "templates/agents").glob("*.toml")).name
        (codex / "agents" / role).write_text("x")
        self.assertEqual(shoal_install.infer("codex", self.env), ["core", "host-codex"])
        (codex / "hooks.json").write_text('{"a": "shoal_guard.py", "b": "shoal_autoroute_gate.py"}')
        (codex / "config.toml").write_text('[plugins."shoal-jev-router@shoal-codex"]\nenabled = true\n')
        self.assertEqual(
            shoal_install.infer("codex", self.env),
            ["core", "host-codex", "dispatch-guard", "codex-autoroute", "jev-router"],
        )

    def test_existing_machine_without_manifest_is_not_changed_by_list(self) -> None:
        codex = Path(self.env["CODEX_HOME"])
        (codex / "agents").mkdir(parents=True)
        role = next((ROOT / "templates/agents").glob("*.toml")).name
        (codex / "agents" / role).write_text("x")
        before = self.tree()
        _, out, _ = self.run_cli("--list", "--host", "codex")
        self.assertIn("inferred", out)
        self.assertEqual(self.tree(), before)
        _, out, _ = self.run_cli("--host", "codex")  # 推導的基底：既有機器沒有 guard 就不新增
        self.assertIn("(base: inferred)", out)
        self.assertNotIn("dispatch-guard", out.splitlines()[0])

    def test_claude_and_opencode_inferred(self) -> None:
        claude = Path(self.env["CLAUDE_CONFIG_DIR"])
        (claude / "plugins").mkdir(parents=True)
        (claude / "plugins" / "installed_plugins.json").write_text('{"shoal@shoal": []}')
        self.assertEqual(shoal_install.infer("claude", self.env), ["core", "host-claude", "dispatch-guard"])
        oc = Path(self.env["OPENCODE_CONFIG_DIR"])
        (oc / "plugins").mkdir(parents=True)
        (oc / "plugins" / "shoal-opencode.js").write_text("x")
        self.assertEqual(shoal_install.infer("opencode", self.env), ["core", "host-opencode", "dispatch-guard"])


if __name__ == "__main__":
    unittest.main()
