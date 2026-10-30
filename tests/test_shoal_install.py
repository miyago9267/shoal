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

sys.path.insert(0, str(ROOT / "hooks"))
import shoal_guard  # noqa: E402


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
        # 外部 CLI 一律用假的（CI runner 沒有 claude、codex）；PATH 只含它們
        fake_bin = self.tmp / "fake-cli"
        fake_bin.mkdir()
        for cli in ("claude", "codex"):
            fake = fake_bin / (cli + (".cmd" if sys.platform == "win32" else ""))
            fake.write_text("@exit /b 0\n" if sys.platform == "win32" else "#!/bin/sh\nexit 0\n")
            fake.chmod(0o755)
        self.env["PATH"] = str(fake_bin)
        self.calls: list[list[str]] = []
        self.manifest = self.data / "shoal" / "modules.json"

    def runner(self, cmd: list[str], env) -> int:
        self.calls.append(cmd)
        return 0

    def run_cli(self, *argv: str, runner=None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = shoal_install.main(list(argv), self.env, runner or self.runner, lambda cmd, env: (0, ""))
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def tree(self) -> list[str]:
        return sorted(str(p) for p in self.tmp.rglob("*") if "fake-cli" not in p.parts)


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
            ("codex", "install.py"),
            ("agy", "install_hooks.py"),
            ("grok", "install_grok.py"),
            ("opencode", "opencode_global.py"),
        ):
            code, out, _ = self.run_cli("--host", host)
            self.assertEqual(code, 0, host)
            self.assertIn("would run:", out)
            self.assertIn(needle, out)
            self.assertIn("dry-run", out)
        code, out, _ = self.run_cli("--host", "claude")
        self.assertIn("claude plugin install shoal@shoal", out)
        self.assertIn("claude plugin install shoal-dispatch-guard@shoal", out)  # D5: the guard is on by default
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

    def test_without_modules_pass_real_skip_flags_to_the_wrapped_installers(self) -> None:
        _, out, _ = self.run_cli("--host", "codex", "--without", "dispatch-guard,codex-autoroute")
        self.assertNotIn("dispatch-guard,", out.splitlines()[0])
        cmd = next(line for line in out.splitlines() if "install.py" in line)
        self.assertIn("--no-guard", cmd)
        self.assertIn("--no-autoroute", cmd)
        _, out, _ = self.run_cli("--host", "codex")
        self.assertNotIn("--no-guard", out)
        self.assertNotIn("--no-autoroute", out)
        _, out, _ = self.run_cli("--host", "grok", "--without", "dispatch-guard")
        self.assertIn("install_grok.py", out)
        self.assertIn("--no-guard", out)
        _, out, _ = self.run_cli("--host", "agy", "--without", "dispatch-guard")
        self.assertIn("--uninstall --apply", out)
        _, out, _ = self.run_cli("--host", "agy")
        self.assertNotIn("--uninstall", out)
        _, out, _ = self.run_cli("--host", "opencode", "--without", "dispatch-guard")  # guard inside the plugin
        self.assertIn("off 模式", out)
        self.assertNotIn("--no-guard", out)
        # claude (S4): the guard is its own plugin, so --without means it is not installed at all
        _, out, _ = self.run_cli("--host", "claude", "--without", "dispatch-guard")
        self.assertIn("claude plugin install shoal@shoal", out)
        self.assertNotIn("claude plugin install shoal-dispatch-guard@shoal", out)
        self.assertIn("claude plugin uninstall shoal-dispatch-guard@shoal", out)
        self.assertNotIn("off 模式", out)

    def test_claude_explore_removal_only_when_identical_to_dist(self) -> None:
        agents = Path(self.env["CLAUDE_CONFIG_DIR"]) / "agents"
        agents.mkdir(parents=True)
        explore = agents / "Explore.md"
        explore.write_bytes((ROOT / shoal_install.EXPLORE_DIST).read_bytes())
        _, out, _ = self.run_cli("--host", "claude", "--without", "claude-explore")
        self.assertIn("would remove: " + str(explore), out)
        self.assertTrue(explore.exists())  # dry-run removes nothing
        self.assertEqual(self.run_cli("--host", "claude", "--without", "claude-explore", "--apply")[0], 0)
        self.assertFalse(explore.exists())
        explore.write_text("my own Explore\n")
        self.assertEqual(self.run_cli("--host", "claude", "--without", "claude-explore", "--apply")[0], 0)
        self.assertEqual(explore.read_text(), "my own Explore\n")  # not shoal's bytes: kept

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

    def test_claude_apply_runs_plugin_commands_and_records_manifest(self) -> None:
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        name = "claude.cmd" if sys.platform == "win32" else "claude"
        (bin_dir / name).write_text("@exit /b 0\n" if sys.platform == "win32" else "#!/bin/sh\n")
        (bin_dir / name).chmod(0o755)
        self.env["PATH"] = str(bin_dir)
        self.assertEqual(self.run_cli("--host", "claude", "--apply")[0], 0)
        self.assertEqual(len(self.calls), 3)  # marketplace add、shoal、guard（細節見 test_shoal_install_p1）
        self.assertIn("claude", json.loads(self.manifest.read_text()))

    def test_xdg_default_under_home(self) -> None:
        del self.env["XDG_DATA_HOME"]
        self.assertEqual(
            shoal_install.manifest_path(self.env), self.home / ".local/share/shoal/modules.json"
        )


    def test_non_absolute_xdg_data_home_is_ignored_like_the_guard(self) -> None:
        # XDG Base Directory spec；guard（Python/TS）同一條規則，兩邊才會讀到同一份 manifest
        fallback = self.home / ".local/share/shoal/modules.json"
        for bad in ("relative/dir", "~/xdg", "./x", ""):
            self.env["XDG_DATA_HOME"] = bad
            self.assertEqual(shoal_install.manifest_path(self.env), fallback, bad)
        self.env["XDG_DATA_HOME"] = str(self.data)
        self.assertEqual(shoal_install.manifest_path(self.env), self.manifest)

    def test_relative_xdg_data_home_writes_to_home_fallback(self) -> None:
        self.env["XDG_DATA_HOME"] = "rel"
        self.assertEqual(self.run_cli("--host", "claude", "--apply")[0], 0)
        self.assertTrue((self.home / ".local/share/shoal/modules.json").is_file())
        self.assertFalse(Path("rel").exists())


class ChainOnlyTests(Base):
    """--without dispatch-guard 但 chain 在該 host 有成員：shoal hook 仍要註冊（chain-only）。"""

    def add(self, hosts: str, *extra: str) -> tuple[int, str, str]:
        return self.run_cli("--chain-add", "ext", "--chain-command", '["ext"]', "--chain-hosts", hosts, *extra)

    def seed(self, host: str, mods: list[str], chain_hosts: str = "") -> None:
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        chain = [{"name": "ext", "command": ["ext"], "hosts": chain_hosts.split(","), "order": 0}] if chain_hosts else []
        self.manifest.write_text(json.dumps({host: {"modules": mods, "version": "x"}, "chain": chain}))

    def test_install_keeps_guard_hook_when_chain_has_members_for_host(self) -> None:
        self.seed("codex", ["core", "host-codex"], "codex")
        _, out, _ = self.run_cli("--host", "codex", "--without", "dispatch-guard")
        self.assertNotIn("--no-guard", next(l for l in out.splitlines() if "install.py" in l))
        self.assertIn("chain-only", out)
        self.seed("agy", ["core", "host-agy"], "agy")
        _, out, _ = self.run_cli("--host", "agy", "--without", "dispatch-guard")
        self.assertNotIn("--uninstall", out)
        self.seed("grok", ["core", "host-grok"], "grok")
        _, out, _ = self.run_cli("--host", "grok", "--without", "dispatch-guard")
        self.assertNotIn("--no-guard", out)

    def test_installer_and_guard_agree_on_chain_only(self) -> None:
        # installer 保留 guard hook（inst2）與 guard 在同一份 manifest 上只跑 chain（chain2）要同時成立。
        self.seed("codex", ["core", "host-codex"], "codex")
        _, out, _ = self.run_cli("--host", "codex", "--without", "dispatch-guard")
        self.assertNotIn("--no-guard", next(l for l in out.splitlines() if "install.py" in l))
        env = {"XDG_DATA_HOME": str(self.data)}
        self.assertFalse(shoal_guard.dispatch_guard_selected("codex", env, self.home))
        guard = shoal_guard._Guard({"host": "codex"}, env, self.home)
        self.assertTrue(guard.chain_only)
        self.assertNotEqual(guard.mode, "off")
        # 沒有 codex 成員：installer 移除 hook，guard 整個 off。
        self.seed("codex", ["core", "host-codex"], "agy")
        _, out, _ = self.run_cli("--host", "codex", "--without", "dispatch-guard")
        self.assertIn("--no-guard", out)
        guard = shoal_guard._Guard({"host": "codex"}, env, self.home)
        self.assertFalse(guard.chain_only)
        self.assertEqual(guard.mode, "off")

    def members(self) -> list:
        return json.loads(self.manifest.read_text(encoding="utf-8"))["chain"]

    def test_chain_events_are_stored_validated_preserved_and_listed(self) -> None:
        self.assertEqual(self.add("codex", "--chain-events", "PostToolUse,SessionEnd", "--apply")[0], 0)
        self.assertEqual(self.members()[0]["events"], ["PostToolUse", "SessionEnd"])
        _, out, _ = self.run_cli("--list")
        self.assertIn("events=PostToolUse,SessionEnd", out)
        # re-registering without --chain-events keeps the events
        self.assertEqual(self.add("codex", "--apply")[0], 0)
        self.assertEqual(self.members()[0]["events"], ["PostToolUse", "SessionEnd"])
        # a bad event is refused and nothing changes
        code, _, err = self.add("codex", "--chain-events", "PostToolUse,Bogus", "--apply")
        self.assertNotEqual(code, 0)
        self.assertIn("Bogus", err)
        self.assertEqual(self.members()[0]["events"], ["PostToolUse", "SessionEnd"])

    def test_chain_events_omitted_means_no_events_field(self) -> None:
        self.assertEqual(self.add("codex", "--apply")[0], 0)
        self.assertNotIn("events", self.members()[0])

    def test_chain_event_names_match_the_guard(self) -> None:
        self.assertEqual(tuple(shoal_install.CHAIN_EVENTS), tuple(shoal_guard.CHAIN_EVENTS))

    def test_chain_for_another_host_does_not_keep_the_hook(self) -> None:
        self.seed("codex", ["core", "host-codex"], "agy")
        _, out, _ = self.run_cli("--host", "codex", "--without", "dispatch-guard")
        self.assertIn("--no-guard", out)
        self.assertNotIn("chain-only", out)

    def test_claude_prints_guard_plugin_when_chain_has_claude_members(self) -> None:
        self.seed("claude", ["core", "host-claude"], "claude")
        _, out, _ = self.run_cli("--host", "claude", "--without", "dispatch-guard")
        self.assertIn("claude plugin install shoal-dispatch-guard@shoal", out)
        self.assertNotIn("uninstall", out)
        self.seed("claude", ["core", "host-claude"], "codex")
        _, out, _ = self.run_cli("--host", "claude", "--without", "dispatch-guard")
        self.assertNotIn("claude plugin install shoal-dispatch-guard@shoal", out)

    def test_chain_add_apply_reinstalls_guard_step_for_codex_agy_grok(self) -> None:
        for host, needle in (("codex", "install.py"), ("agy", "install_hooks.py"), ("grok", "install_grok.py")):
            self.calls.clear()
            self.seed(host, ["core", f"host-{host}"])
            code, out, _ = self.add(host)  # dry-run: 只印
            self.assertEqual((code, self.calls), (0, []))
            self.assertIn("would run", out)
            self.assertEqual(self.add(host, "--apply")[0], 0)
            self.assertEqual(len(self.calls), 1, host)
            self.assertIn(needle, " ".join(self.calls[0]))
            self.assertNotIn("--no-guard", self.calls[0])
            self.assertNotIn("--uninstall", self.calls[0])
            self.calls.clear()
            self.assertEqual(self.run_cli("--chain-remove", "ext", "--apply")[0], 0)
            self.assertEqual(len(self.calls), 1, host)
            cmd = self.calls[0]
            self.assertTrue("--no-guard" in cmd or "--uninstall" in cmd, host)

    def test_chain_add_does_not_rerun_when_dispatch_guard_selected_or_no_manifest(self) -> None:
        self.seed("codex", ["core", "host-codex", "dispatch-guard"])
        self.assertEqual(self.add("codex", "--apply")[0], 0)
        self.assertEqual(self.calls, [])
        self.manifest.unlink()
        self.assertEqual(self.add("agy", "--apply")[0], 0)
        self.assertEqual(self.calls, [])

    def test_chain_add_failure_of_follow_up_is_reported(self) -> None:
        self.seed("agy", ["core", "host-agy"])
        code, _, err = self.run_cli("--chain-add", "ext", "--chain-command", '["ext"]', "--chain-hosts", "agy", "--apply", runner=lambda c, e: 3)
        self.assertEqual(code, 1)
        self.assertIn("exit 3", err)

    def test_chain_add_for_claude_prints_plugin_command(self) -> None:
        self.seed("claude", ["core", "host-claude"])
        _, out, _ = self.add("claude", "--apply")
        self.assertIn("run manually: claude plugin install shoal-dispatch-guard@shoal", out)
        self.assertEqual(self.calls, [])
        _, out, _ = self.run_cli("--chain-remove", "ext", "--apply")
        self.assertIn("claude plugin uninstall shoal-dispatch-guard@shoal", out)


class ChainTests(Base):
    CMD = '["python3","/opt/member.py","--flag"]'

    def chain(self) -> list:
        return json.loads(self.manifest.read_text())["chain"]

    def test_add_is_dry_run_by_default_and_never_executes_the_member(self) -> None:
        code, out, _ = self.run_cli("--chain-add", "ext", "--chain-command", self.CMD, "--chain-hosts", "claude,codex")
        self.assertEqual(code, 0)
        self.assertIn("dry-run", out)
        self.assertFalse(self.manifest.exists())
        marker = self.tmp / "ran"
        argv = json.dumps([sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"])
        self.assertEqual(self.run_cli("--chain-add", "ext", "--chain-command", argv, "--chain-hosts", "claude", "--apply")[0], 0)
        self.assertFalse(marker.exists())
        self.assertEqual(self.calls, [])

    def test_add_apply_replace_order_and_remove(self) -> None:
        self.assertEqual(self.run_cli("--chain-add", "a", "--chain-command", self.CMD, "--chain-hosts", "claude,codex", "--apply")[0], 0)
        self.assertEqual(self.chain(), [{"name": "a", "command": ["python3", "/opt/member.py", "--flag"], "hosts": ["claude", "codex"], "order": 0}])
        self.assertEqual(self.run_cli("--chain-add", "b", "--chain-command", '["b"]', "--chain-hosts", "opencode", "--chain-order", "5", "--apply")[0], 0)
        self.assertEqual(self.run_cli("--chain-add", "c", "--chain-command", '["c"]', "--chain-hosts", "agy", "--apply")[0], 0)
        self.assertEqual([(m["name"], m["order"]) for m in self.chain()], [("a", 0), ("b", 5), ("c", 6)])
        self.assertEqual(self.run_cli("--chain-add", "a", "--chain-command", '["a2"]', "--chain-hosts", "claude", "--apply")[0], 0)
        self.assertEqual([m["command"] for m in self.chain() if m["name"] == "a"], [["a2"]])
        self.assertEqual(len(self.chain()), 3)
        self.assertEqual(self.run_cli("--chain-remove", "b", "--apply")[0], 0)
        self.assertEqual([m["name"] for m in self.chain()], ["a", "c"])
        self.assertEqual(self.run_cli("--chain-remove", "nope", "--apply")[0], 0)  # idempotent
        self.assertEqual([m["name"] for m in self.chain()], ["a", "c"])

    def test_chain_keeps_host_records_and_list_shows_it(self) -> None:
        self.assertEqual(self.run_cli("--host", "grok", "--apply")[0], 0)
        self.assertEqual(self.run_cli("--chain-add", "ext", "--chain-command", '["x"]', "--chain-hosts", "grok", "--chain-order", "2", "--apply")[0], 0)
        self.assertIn("grok", json.loads(self.manifest.read_text()))
        _, out, _ = self.run_cli("--list")
        self.assertIn("guard chain:", out)
        self.assertIn("[2] ext  hosts=grok", out)
        _, out, _ = self.run_cli("--list", "--host", "grok")
        self.assertIn("[2] ext", out)
        self.manifest.unlink()
        self.assertIn("(none)", self.run_cli("--list")[1])

    def test_validation_rejects_bad_input_without_writing(self) -> None:
        bad = (
            ("--chain-command", "not json"),
            ("--chain-command", '"python3 member.py"'),
            ("--chain-command", "[]"),
            ("--chain-command", '["a", 1]'),
            ("--chain-command", '["a", ""]'),
            ("--chain-command", '{"a": 1}'),
        )
        for flag, value in bad:
            code, _, err = self.run_cli("--chain-add", "x", flag, value, "--chain-hosts", "claude", "--apply")
            self.assertEqual(code, 2, value)
            self.assertIn("error:", err)
        self.assertEqual(self.run_cli("--chain-add", "x", "--chain-hosts", "claude", "--apply")[0], 2)  # no command
        self.assertEqual(self.run_cli("--chain-add", "x", "--chain-command", '["a"]', "--apply")[0], 2)  # no hosts
        self.assertEqual(self.run_cli("--chain-add", "x", "--chain-command", '["a"]', "--chain-hosts", "vim", "--apply")[0], 2)
        self.assertEqual(self.run_cli("--chain-add", " ", "--chain-command", '["a"]', "--chain-hosts", "claude", "--apply")[0], 2)
        self.assertEqual(self.run_cli("--chain-add", "x", "--chain-command", '["a"]', "--chain-hosts", "claude", "--host", "claude")[0], 2)
        self.assertFalse(self.manifest.exists())


class InferenceTests(Base):
    def test_nothing_installed_infers_none(self) -> None:
        for host in ("codex", "claude", "agy", "grok", "opencode"):
            self.assertIsNone(shoal_install.infer(host, self.env), host)

    GUARD_CMD = 'python3 "$HOME/.local/share/shoal/guard/shoal_guard.py" --host %s --event X'

    def codex_with_role(self) -> Path:
        codex = Path(self.env["CODEX_HOME"])
        (codex / "agents").mkdir(parents=True)
        role = next((ROOT / "templates/agents").glob("*.toml")).name
        (codex / "agents" / role).write_text("x")
        return codex

    def test_codex_inferred_from_files(self) -> None:
        codex = self.codex_with_role()
        (codex / "hooks.json").write_text('{"hooks": {}}')
        (codex / "config.toml").write_text("[other]\nx = 1\n")
        self.assertEqual(shoal_install.infer("codex", self.env), ["core", "host-codex"])
        hooks = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": self.GUARD_CMD % "codex"}]},
                                    {"hooks": [{"type": "command", "command": "python3 shoal_autoroute_gate.py"}]}]}}
        (codex / "hooks.json").write_text(json.dumps(hooks))
        (codex / "config.toml").write_text('[plugins."shoal-jev-router@shoal-codex"]\nenabled = true\n')
        self.assertEqual(
            shoal_install.infer("codex", self.env),
            ["core", "host-codex", "dispatch-guard", "codex-autoroute", "jev-router"],
        )

    def test_codex_undeterminable_is_treated_as_installed(self) -> None:
        codex = self.codex_with_role()  # 沒有 hooks.json、config.toml
        full = ["core", "host-codex", "dispatch-guard", "codex-autoroute", "jev-router"]
        self.assertEqual(shoal_install.infer("codex", self.env), full)
        (codex / "hooks.json").write_text("{not json")
        self.assertEqual(shoal_install.infer("codex", self.env), full)

    def agy_with_links(self) -> Path:
        gem = Path(self.env["HOME"]) / ".gemini"
        (gem / "config" / "agents").mkdir(parents=True)
        src = next((ROOT / "hosts/agy/dist/agents").iterdir())
        (gem / "config" / "agents" / src.name).symlink_to(src)
        return gem

    def test_agy_guard_group_in_hooks_file_is_installed(self) -> None:
        gem = self.agy_with_links()
        group = {"shoal-dispatch-guard": {"PreToolUse": [{"type": "command", "command": self.GUARD_CMD % "agy"}]}}
        (gem / "config" / "hooks.json").write_text(json.dumps(group))
        self.assertEqual(shoal_install.infer("agy", self.env), ["core", "host-agy", "dispatch-guard"])

    def test_agy_guard_group_via_symlink_is_installed(self) -> None:
        gem = self.agy_with_links()
        real = self.tmp / "dotfile" / "hooks.json"
        real.parent.mkdir()
        group = {"shoal-dispatch-guard": {"PreToolUse": [{"type": "command", "command": self.GUARD_CMD % "agy"}]}}
        real.write_text(json.dumps(group))
        (gem / "config" / "hooks.json").symlink_to(real)
        self.assertIn("dispatch-guard", shoal_install.infer("agy", self.env))

    def test_agy_readable_hooks_without_guard_is_not_installed(self) -> None:
        gem = self.agy_with_links()
        (gem / "config" / "hooks.json").write_text('{"other": {"PreToolUse": []}}')
        self.assertEqual(shoal_install.infer("agy", self.env), ["core", "host-agy"])

    def test_agy_undeterminable_is_treated_as_installed(self) -> None:
        gem = self.agy_with_links()
        self.assertIn("dispatch-guard", shoal_install.infer("agy", self.env))  # 沒有 hooks 檔
        (gem / "config" / "hooks.json").write_text("{broken")
        self.assertIn("dispatch-guard", shoal_install.infer("agy", self.env))  # 壞掉的 JSON
        (gem / "config" / "hooks.json").unlink()
        (gem / "config" / "hooks.json").symlink_to(self.tmp / "missing.json")  # 斷掉的 symlink
        self.assertIn("dispatch-guard", shoal_install.infer("agy", self.env))

    def test_grok_guard_is_assumed_installed(self) -> None:
        agents = Path(self.env["GROK_HOME"]) / "agents"
        agents.mkdir(parents=True)
        (agents / next((ROOT / "hosts/grok/dist/agents").iterdir()).name).write_text("x")
        self.assertEqual(shoal_install.infer("grok", self.env), ["core", "host-grok", "dispatch-guard"])

    def test_existing_machine_without_manifest_is_not_changed_by_list(self) -> None:
        codex = self.codex_with_role()
        (codex / "hooks.json").write_text('{"hooks": {}}')
        (codex / "config.toml").write_text("[other]\nx = 1\n")
        before = self.tree()
        _, out, _ = self.run_cli("--list", "--host", "codex")
        self.assertIn("inferred", out)
        self.assertEqual(self.tree(), before)
        _, out, _ = self.run_cli("--host", "codex")  # 推導的基底：確定沒有 guard 就不新增
        self.assertIn("(base: inferred)", out)
        self.assertNotIn("dispatch-guard", out.splitlines()[0])

    def test_claude_and_opencode_inferred(self) -> None:
        claude = Path(self.env["CLAUDE_CONFIG_DIR"])
        (claude / "plugins").mkdir(parents=True)
        (claude / "plugins" / "installed_plugins.json").write_text('{"shoal@shoal": []}')
        self.assertEqual(shoal_install.infer("claude", self.env), ["core", "host-claude"])  # base only: no guard plugin
        (claude / "plugins" / "installed_plugins.json").write_text('{"shoal@shoal": [], "shoal-dispatch-guard@shoal": []}')
        self.assertEqual(shoal_install.infer("claude", self.env), ["core", "host-claude", "dispatch-guard"])
        oc = Path(self.env["OPENCODE_CONFIG_DIR"])
        (oc / "plugins").mkdir(parents=True)
        (oc / "plugins" / "shoal-opencode.js").write_text("x")
        self.assertEqual(shoal_install.infer("opencode", self.env), ["core", "host-opencode", "dispatch-guard"])


if __name__ == "__main__":
    unittest.main()
