"""Claude plugin (generic-shoal K1, K2, K4, K5, K6): render, golden, quoting, guard `--plugin` deferral.

tests/golden/claude-plugin is a copy of the render output (repo-relative paths); refresh it by
copying `plugins/claude/`, `plugins/claude-guard/` and `.claude-plugin/marketplace.json` after `render.py --host claude-plugin --write`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "tests"))
import guard_vectors_helper as helper  # noqa: E402
import install_hooks  # noqa: E402
import render  # noqa: E402
import shoal_guard as guard  # noqa: E402

GOLDEN = ROOT / "tests" / "golden" / "claude-plugin"
GUARD = ROOT / "hooks" / "shoal_guard.py"
PLUGIN = ROOT / "plugins" / "claude"
GUARD_PLUGIN = ROOT / "plugins" / "claude-guard"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def run_render(root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "render.py"),
            "--host",
            "claude-plugin",
            "--root",
            str(root),
            *flags,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def golden_files() -> dict[str, bytes]:
    return {
        p.relative_to(GOLDEN).as_posix(): p.read_bytes()
        for p in GOLDEN.rglob("*")
        if p.is_file() and p.name != "SOURCE"
    }


class GoldenTests(unittest.TestCase):
    def test_render_is_byte_identical_to_golden(self) -> None:
        golden = golden_files()
        self.assertEqual(len(golden), 22)
        rendered = render.render_claude_plugin(ROOT)
        self.assertEqual(sorted(rendered), sorted(golden))
        for rel, data in golden.items():
            self.assertEqual(rendered[rel], data, rel)

    def test_committed_files_match_render(self) -> None:
        for rel, data in render.render_claude_plugin(ROOT).items():
            self.assertEqual((ROOT / rel).read_bytes(), data, rel)

    def test_claude_dist_is_not_changed_by_the_plugin_target(self) -> None:
        self.assertEqual(len(render.RENDERERS["claude"](ROOT)), 15)
        self.assertNotIn("claude-plugin", render.RENDERERS)


class ContentTests(unittest.TestCase):
    def test_guard_copy_is_byte_identical_to_the_single_source(self) -> None:
        self.assertEqual(
            (GUARD_PLUGIN / "hooks" / "shoal_guard.py").read_bytes(), GUARD.read_bytes()
        )
        # S4: the base plugin carries no guard; 3.8.1 keeps only the compatibility shim (not the guard)
        self.assertNotEqual((PLUGIN / "hooks" / "shoal_guard.py").read_bytes(), GUARD.read_bytes())
        self.assertEqual(
            (PLUGIN / "hooks" / "shoal_guard.py").read_bytes(),
            (ROOT / "hosts" / "claude" / "plugin-src" / "shoal_guard_compat.py").read_bytes(),
        )

    def test_agents_skills_and_policy_come_from_the_claude_dist(self) -> None:
        dist = render.RENDERERS["claude"](ROOT)
        rendered = render.render_claude_plugin(ROOT)
        for rel, data in dist.items():
            if rel.startswith(("agents/", "skills/")):
                self.assertEqual(rendered[f"plugins/claude/{rel}"], data, rel)
        self.assertEqual(
            rendered["plugins/claude/policy/claude-md.bootstrap.md"],
            dist["claude-md.bootstrap.md"],
        )
        self.assertNotIn("plugins/claude/settings.snippet.json", rendered)

    def test_versions_equal_the_product_version(self) -> None:
        plugin = json.loads(
            (PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        market = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        guard_plugin = json.loads(
            (GUARD_PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plugin["version"], VERSION)
        self.assertEqual(plugin["name"], "shoal")
        self.assertEqual((guard_plugin["name"], guard_plugin["version"]), ("shoal-dispatch-guard", VERSION))
        self.assertEqual(market["name"], "shoal")
        self.assertEqual(
            [(e["name"], e["version"]) for e in market["plugins"]],
            [("shoal", VERSION), ("shoal-dispatch-guard", VERSION)],
        )

    def test_marketplace_source_is_the_plugin_dir_and_not_the_codex_one(self) -> None:
        market = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        sources = [e["source"] for e in market["plugins"]]
        self.assertEqual(sources, ["./plugins/claude", "./plugins/claude-guard"])
        for source in sources:
            self.assertTrue((ROOT / source / ".claude-plugin" / "plugin.json").is_file())
            self.assertNotEqual((ROOT / source).resolve(), (ROOT / "plugin").resolve())


class BaseHooksTests(unittest.TestCase):
    def test_base_plugin_registers_only_the_policy_bootstrap(self) -> None:
        # S4: every guard hook lives in the shoal-dispatch-guard plugin; the base plugin only injects the policy.
        hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(list(hooks), ["SessionStart"])
        self.assertNotIn("shoal_guard", (PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))


class CompatShimTests(unittest.TestCase):
    """3.8.1: sessions started before the 3.8.0 split still call the base plugin's hooks/shoal_guard.py."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.market = Path(tmp.name) / "market"
        self.shim = self.market / "plugins" / "claude" / "hooks" / "shoal_guard.py"
        self.shim.parent.mkdir(parents=True)
        shutil.copy(PLUGIN / "hooks" / "shoal_guard.py", self.shim)
        self.home = Path(tmp.name) / "home"
        self.home.mkdir()

    def run_shim(self, *args: str, stdin: str = "{}") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.shim), *args], input=stdin, capture_output=True, text=True,
            env={**os.environ, "HOME": str(self.home), "USERPROFILE": str(self.home),
                 "CLAUDE_CONFIG_DIR": str(self.home / ".claude")},
        )

    def write_target(self, path: Path, exit_code: int = 0) -> None:
        path.parent.mkdir(parents=True)
        path.write_text(
            "import sys\nprint('ARGV=' + ' '.join(sys.argv[1:]) + ' STDIN=' + sys.stdin.read())\n"
            f"sys.exit({exit_code})\n", encoding="utf-8")

    def test_shim_is_not_registered_in_the_base_hooks(self) -> None:
        text = (PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8")
        self.assertNotIn("shoal_guard", text)

    def test_shim_delegates_to_the_sibling_guard_plugin_with_argv_and_stdin(self) -> None:
        self.write_target(self.market / "plugins" / "claude-guard" / "hooks" / "shoal_guard.py")
        result = self.run_shim("--host", "claude", "--plugin", stdin='{"x":1}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'ARGV=--host claude --plugin STDIN={"x":1}')

    def test_shim_still_finds_the_pre_3_11_sibling_guard_plugin(self) -> None:
        legacy = self.market / "plugins" / "claude-guard-plugin" / "hooks" / "shoal_guard.py"
        self.write_target(legacy, exit_code=4)
        self.assertEqual(self.run_shim("--host", "claude").returncode, 4)

    def test_shim_passes_the_target_exit_code_through(self) -> None:
        self.write_target(self.market / "plugins" / "claude-guard" / "hooks" / "shoal_guard.py", exit_code=2)
        self.assertEqual(self.run_shim("--host", "claude").returncode, 2)

    def test_shim_uses_the_newest_cached_guard_plugin_when_there_is_no_sibling(self) -> None:
        cache = self.home / ".claude" / "plugins" / "cache" / "shoal" / "shoal-dispatch-guard"
        self.write_target(cache / "3.8.1" / "hooks" / "shoal_guard.py", exit_code=0)
        self.write_target(cache / "3.10.0" / "hooks" / "shoal_guard.py", exit_code=7)
        self.assertEqual(self.run_shim("--host", "claude").returncode, 7)

    def test_shim_orders_by_version_not_plugin_name_and_ignores_non_version_dirs(self) -> None:
        cache = self.home / ".claude" / "plugins" / "cache" / "shoal" / "shoal-dispatch-guard"
        self.write_target(cache / "3.8.1" / "hooks" / "shoal_guard.py", exit_code=1)
        self.write_target(cache / "3.10.0" / "hooks" / "shoal_guard.py", exit_code=7)
        self.write_target(cache / "latest" / "hooks" / "shoal_guard.py", exit_code=9)
        self.assertEqual(self.run_shim("--host", "claude").returncode, 7)

    def test_shim_honours_claude_config_dir_over_the_home_directory(self) -> None:
        config = self.home / "elsewhere"
        self.write_target(config / "plugins" / "cache" / "shoal" / "shoal-dispatch-guard" / "3.8.1" / "hooks" / "shoal_guard.py", exit_code=5)
        env = {**os.environ, "HOME": str(self.home), "USERPROFILE": str(self.home), "CLAUDE_CONFIG_DIR": str(config)}
        done = subprocess.run([sys.executable, str(self.shim)], input="{}", capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 5)

    def test_shim_exits_zero_silently_when_no_guard_plugin_is_found(self) -> None:
        result = self.run_shim("--host", "claude", "--plugin")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_shim_exits_zero_silently_when_the_target_is_a_directory(self) -> None:
        (self.market / "plugins" / "claude-guard" / "hooks" / "shoal_guard.py").mkdir(parents=True)
        result = self.run_shim("--host", "claude")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_shim_delegates_to_the_real_rendered_guard(self) -> None:
        shutil.copytree(GUARD_PLUGIN, self.market / "plugins" / "claude-guard")
        result = self.run_shim("--host", "claude", "--plugin", stdin="{}")
        self.assertEqual(result.returncode, 0, result.stderr)


class HooksJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hooks = json.loads(
            (GUARD_PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )["hooks"]

    def test_events_and_matchers(self) -> None:
        self.assertEqual(
            sorted(self.hooks), ["PostToolUse", "PostToolUseFailure", "PreToolUse", "SessionEnd", "Stop", "SubagentStart", "UserPromptSubmit"]
        )
        self.assertNotIn("matcher", self.hooks["SubagentStart"][0])
        self.assertNotIn("matcher", self.hooks["Stop"][0])
        (pre,) = self.hooks["PreToolUse"]
        self.assertEqual(pre["matcher"], install_hooks.CLAUDE_MATCHER)
        self.assertNotIn("matcher", self.hooks["UserPromptSubmit"][0])
        # B2: the completion check counts a Bash call at its PostToolUse; guard chain (issue #3) adds the edit tools
        post, post_edit = self.hooks["PostToolUse"]
        self.assertEqual(post["matcher"], "Bash")
        self.assertEqual(post_edit["matcher"], "Edit|Write|MultiEdit|NotebookEdit")
        self.assertNotIn("matcher", self.hooks["SessionEnd"][0])
        (fail,) = self.hooks["PostToolUseFailure"]  # a failed Bash call fires this instead of PostToolUse
        self.assertEqual(fail["matcher"], "Bash")

    def test_start_event_is_registered_whenever_the_guard_unlocks_on_it(self) -> None:
        # M11: the guard (claude) unlocks a write dispatch only on SubagentStart; without this registration the
        # unlock would never come.  The script and the registration ship together.
        self.assertIn("claude", guard.START_UNLOCK_HOSTS)
        (handler,) = self.hooks["SubagentStart"][0]["hooks"]
        self.assertIn("shoal_guard.py", handler["command"])
        self.assertIn("--host claude --plugin", handler["command"])
        self.assertEqual(self.hooks["SubagentStart"][0].get("matcher"), None)  # every agent_type; the guard filters
        self.assertEqual(
            set(self.hooks), {"UserPromptSubmit", "PreToolUse", "SubagentStart", "Stop", "PostToolUse", "PostToolUseFailure", "SessionEnd"}
        )

    def test_stop_event_is_registered_whenever_the_guard_blocks_on_it(self) -> None:
        # B3 (shared-rules): the completion check blocks on Stop; without this registration it never fires.
        self.assertIn("claude", guard.STOP_HOSTS)
        (handler,) = self.hooks["Stop"][0]["hooks"]
        self.assertIn("shoal_guard.py", handler["command"])
        self.assertIn("--host claude --plugin", handler["command"])
        self.assertEqual(self.hooks["Stop"][0].get("matcher"), None)

    def test_every_command_quotes_the_plugin_root(self) -> None:
        guard_cmd = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/shoal_guard.py" --host claude --plugin'
        for event in ("UserPromptSubmit", "PreToolUse", "SubagentStart", "Stop", "PostToolUse", "PostToolUseFailure", "SessionEnd"):
            for group in self.hooks[event]:
                (handler,) = group["hooks"]
                self.assertEqual(handler["command"], guard_cmd, event)
        base = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        (start,) = base["SessionStart"][0]["hooks"]
        self.assertEqual(
            start["command"],
            '/bin/sh "${CLAUDE_PLUGIN_ROOT}/hooks/emit-sessionstart.sh"',
        )

    def test_no_command_uses_an_unquoted_plugin_root(self) -> None:
        for plugin in (PLUGIN, GUARD_PLUGIN):
            text = (plugin / "hooks" / "hooks.json").read_text(encoding="utf-8")
            for match in re.finditer(r"\$\{CLAUDE_PLUGIN_ROOT\}", text):
                self.assertEqual(text[match.start() - 2 : match.start()], '\\"')

    @unittest.skipIf(os.name == "nt", "POSIX shell")
    def test_commands_run_from_a_plugin_root_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shoal plugin ") as tmp:
            root = Path(tmp, "my plugin")
            shutil.copytree(GUARD_PLUGIN, root)
            base_root = Path(tmp, "my base plugin")
            shutil.copytree(PLUGIN, base_root)
            env = {
                **os.environ,
                "CLAUDE_PLUGIN_ROOT": str(root),
                "HOME": tmp,
                "CLAUDE_CONFIG_DIR": str(Path(tmp, "cfg dir")),
                "XDG_STATE_HOME": str(Path(tmp, "state")),
                "XDG_DATA_HOME": str(Path(tmp, "data")),
            }
            (handler,) = self.hooks["UserPromptSubmit"][0]["hooks"]
            proc = subprocess.run(
                handler["command"],
                shell=True,
                input=b"{}",
                capture_output=True,
                env=env,
                timeout=30,
            )
            self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, b"", b""))
            base = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
            (start,) = base["SessionStart"][0]["hooks"]
            proc = subprocess.run(
                start["command"], shell=True, capture_output=True,
                env={**env, "CLAUDE_PLUGIN_ROOT": str(base_root)}, timeout=30
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(
                proc.stdout, (PLUGIN / "policy" / "claude-md.bootstrap.md").read_bytes()
            )


class RenderCommandTests(unittest.TestCase):
    """`--host claude-plugin --check/--write` against a temp copy of the sources and outputs."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
        shutil.copytree(ROOT / "hosts" / "claude", self.root / "hosts" / "claude")
        (self.root / "hooks").mkdir()
        shutil.copy(GUARD, self.root / "hooks" / "shoal_guard.py")
        shutil.copy(ROOT / "VERSION", self.root / "VERSION")
        self.assertEqual(run_render(self.root, "--write").returncode, 0)

    def test_check_passes_after_write(self) -> None:
        result = run_render(self.root, "--check")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_check_fails_when_one_byte_changes(self) -> None:
        for rel in ("plugins/claude-guard/hooks/shoal_guard.py", "plugins/claude/hooks/hooks.json",
                    "plugins/claude/hooks/shoal_guard.py",
                    "plugins/claude-guard/hooks/hooks.json",
                    ".claude-plugin/marketplace.json", "plugins/claude/agents/scout.md"):
            target = self.root / rel
            original = target.read_bytes()
            target.write_bytes(original + b" ")
            result = run_render(self.root, "--check")
            self.assertEqual(result.returncode, 1, rel)
            self.assertIn(f"內容不同: {rel}", result.stderr)
            target.write_bytes(original)

    def test_check_fails_on_extra_or_missing_file(self) -> None:
        (self.root / "plugins" / "claude" / "agents" / "extra.md").write_text("x", encoding="utf-8")
        (self.root / "plugins" / "claude" / "hooks" / "hooks.json").unlink()
        result = run_render(self.root, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("多出: plugins/claude/agents/extra.md", result.stderr)
        self.assertIn("缺少: plugins/claude/hooks/hooks.json", result.stderr)

    def test_changing_the_guard_source_requires_rewriting_the_copy(self) -> None:
        guard_src = self.root / "hooks" / "shoal_guard.py"
        guard_src.write_bytes(guard_src.read_bytes() + b"# changed\n")
        self.assertEqual(run_render(self.root, "--check").returncode, 1)
        self.assertEqual(run_render(self.root, "--write").returncode, 0)
        self.assertEqual((self.root / "plugins" / "claude-guard" / "hooks" / "shoal_guard.py").read_bytes(), guard_src.read_bytes())
        self.assertEqual(run_render(self.root, "--check").returncode, 0)

    def test_changing_the_version_requires_rewriting_the_manifests(self) -> None:
        (self.root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        self.assertEqual(run_render(self.root, "--check").returncode, 1)
        run_render(self.root, "--write")
        manifest = json.loads((self.root / "plugins" / "claude" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "9.9.9")

    def test_bad_version_is_rejected(self) -> None:
        (self.root / "VERSION").write_text("one\n", encoding="utf-8")
        result = run_render(self.root, "--check")
        self.assertEqual(result.returncode, 2)
        self.assertIn("版本格式不合法", result.stderr)

    def test_write_repairs_and_removes_stale_files(self) -> None:
        (self.root / "plugins" / "claude" / "agents" / "stale.md").write_text("x", encoding="utf-8")
        (self.root / "plugins" / "claude-guard" / "hooks" / "shoal_guard.py").write_bytes(b"broken")
        self.assertEqual(run_render(self.root, "--write").returncode, 0)
        self.assertFalse((self.root / "plugins" / "claude" / "agents" / "stale.md").exists())
        self.assertEqual(run_render(self.root, "--check").returncode, 0)


@unittest.skipIf(os.name == "nt", "POSIX shell")
class SessionStartTests(unittest.TestCase):
    SCRIPT = PLUGIN / "hooks" / "emit-sessionstart.sh"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="shoal ss ")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.cfg = self.home / "cfg dir"
        self.cfg.mkdir()

    def run_script(self, **extra: str) -> str:
        env = {
            "HOME": str(self.home),
            "CLAUDE_CONFIG_DIR": str(self.cfg),
            "PATH": "/nonexistent",
            **extra,
        }
        proc = subprocess.run(
            ["/bin/sh", str(self.SCRIPT)], capture_output=True, env=env, timeout=30
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.decode()

    def install_global(self) -> Path:
        script = self.home / ".local" / "share" / "shoal" / "guard" / "shoal_guard.py"
        script.parent.mkdir(parents=True)
        shutil.copy(GUARD, script)
        settings = install_hooks.apply_claude(
            {}, install_hooks.command_for(script, "claude")
        )
        (self.cfg / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        return script

    def test_injects_the_bootstrap_and_fixes_path(self) -> None:
        # PATH=/nonexistent in the env: the script must set its own, or `cat` and `dirname` would fail.
        self.assertEqual(
            self.run_script(),
            (PLUGIN / "policy" / "claude-md.bootstrap.md").read_text(encoding="utf-8"),
        )

    def test_notes_the_global_guard_and_still_injects(self) -> None:
        self.install_global()
        out = self.run_script()
        self.assertTrue(out.startswith("shoal plugin note: a global shoal guard"), out)
        self.assertTrue(
            out.endswith(
                (PLUGIN / "policy" / "claude-md.bootstrap.md").read_text(
                    encoding="utf-8"
                )
            )
        )

    def test_no_note_when_the_global_script_is_missing(self) -> None:
        script = self.install_global()
        script.unlink()
        self.assertNotIn("shoal plugin note", self.run_script())

    def test_skips_injection_when_claude_md_already_has_the_bootstrap(self) -> None:
        (self.cfg / "CLAUDE.md").write_text(
            "<!-- shoal-claude v1.4.2-claude.4 -->\n## Orchestration\n", encoding="utf-8"
        )
        out = self.run_script()
        self.assertIn("already carries the shoal bootstrap", out)
        self.assertNotIn("Named roles", out)


@unittest.skipIf(os.name == "nt", "shoal guard is POSIX-only; it is a no-op on Windows")
class PluginDeferralTests(unittest.TestCase):
    """K4: with `--plugin` the guard runs exactly once per event whether or not the global entry exists."""

    def setUp(self) -> None:
        self.sandbox = helper.Sandbox()
        self.addCleanup(self.sandbox.close)
        self.home = Path(self.sandbox.home)
        self.work = self.sandbox.work
        self.cfg = self.home / "claude config"  # a path with a space
        self.cfg.mkdir()
        self.state = self.home / "xdg-state"
        self.data = self.home / "xdg-data"
        self.script = self.data / "shoal" / "guard" / "shoal_guard.py"
        self.plugin_script = self.home / "plugin root" / "hooks" / "shoal_guard.py"
        self.plugin_script.parent.mkdir(parents=True)
        shutil.copy(GUARD, self.plugin_script)

    def env(self, **extra: str) -> dict:
        env = {
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.state),
            "XDG_DATA_HOME": str(self.data),
            "CLAUDE_CONFIG_DIR": str(self.cfg),
            "TMPDIR": self.sandbox.tmpdir,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            # These tests count R2 reminders to prove each event is judged once; the declare rule has its own tests.
            "SHOAL_GUARD_R1": "classified",
        }
        env.update(extra)
        return env

    def install_global(self, *, script_exists: bool = True) -> None:
        self.script.parent.mkdir(parents=True, exist_ok=True)
        if script_exists:
            shutil.copy(GUARD, self.script)
        settings = install_hooks.apply_claude(
            {"theme": "x"}, install_hooks.command_for(self.script, "claude")
        )
        self.write_settings(settings)

    def write_settings(self, settings) -> None:
        (self.cfg / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    def fire(self, payload: dict, **env_extra: str) -> str:
        """One hook event: the global entry (if registered) and the plugin entry both fire, as Claude Code does."""
        raw = json.dumps(payload).encode()
        outs = []
        if self.script.is_file():
            outs.append(self.call(self.script, ["--host", "claude"], raw, env_extra))
        outs.append(
            self.call(
                self.plugin_script, ["--host", "claude", "--plugin"], raw, env_extra
            )
        )
        return "".join(outs)

    def call(self, script: Path, args: list, raw: bytes, env_extra: dict) -> str:
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            input=raw,
            capture_output=True,
            env=self.env(**env_extra),
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.decode()

    def records(self) -> list:
        path = self.state / "shoal" / "guard" / "guard.jsonl"
        return (
            [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            if path.is_file()
            else []
        )

    def prompt(self) -> dict:
        return {
            "session_id": "sess-1",
            "prompt_id": "p-1",
            "cwd": self.work,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "edit",
        }

    def edit(self, name: str) -> dict:
        return {
            "session_id": "sess-1",
            "prompt_id": "p-1",
            "cwd": self.work,
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": os.path.join(self.work, name)},
            "tool_use_id": "t",
        }

    def run_turn(self) -> list:
        """Prompt, then three edits; returns each event's stdout."""
        return [self.fire(self.prompt())] + [
            self.fire(self.edit(n)) for n in ("a", "b", "c")
        ]

    def assert_one_log_per_event(self, outs: list) -> None:
        records = self.records()
        self.assertEqual(
            [r["decision"] for r in records],
            ["state", "allow", "allow", "advise"],
            records,
        )
        self.assertEqual([bool(o) for o in outs], [False, False, False, True])
        body = json.loads(outs[3])["hookSpecificOutput"]
        self.assertEqual(set(body), {"hookEventName", "additionalContext"})
        self.assertEqual(records[3]["rule"], "R2")

    def test_plugin_only_runs(self) -> None:
        self.assertFalse(self.script.exists())
        self.assert_one_log_per_event(self.run_turn())

    def test_plugin_with_global_entry_defers_to_it(self) -> None:
        self.install_global()
        self.assert_one_log_per_event(self.run_turn())

    def background_bash(self) -> dict:
        return {
            "session_id": "sess-1",
            "prompt_id": "p-1",
            "cwd": self.work,
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "sleep 60", "run_in_background": True},
            "tool_use_id": "t",
        }

    def assert_one_g4_deny(self, out: str) -> None:
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        g4 = [r for r in self.records() if r.get("rule") == "G4"]
        self.assertEqual([(r["decision"], r["tool"]) for r in g4], [("deny", "Bash")], self.records())

    def test_background_bash_plugin_only_is_judged_once(self) -> None:
        self.fire(self.prompt())
        self.assert_one_g4_deny(self.fire(self.background_bash()))

    def test_background_bash_with_current_global_matcher_defers_to_global(self) -> None:
        self.install_global()
        self.fire(self.prompt())
        self.assert_one_g4_deny(self.fire(self.background_bash()))  # global denies, the plugin copy stays silent
        raw = json.dumps(self.background_bash()).encode()
        self.assertEqual(self.call(self.plugin_script, ["--host", "claude", "--plugin"], raw, {}), "")

    def test_background_bash_with_older_global_matcher_is_handled_by_the_plugin(self) -> None:
        """An older install registered a matcher without Bash: Claude Code never calls the global entry for it."""
        self.install_global()
        settings = json.loads((self.cfg / "settings.json").read_text(encoding="utf-8"))
        for group in settings["hooks"]["PreToolUse"]:
            group["matcher"] = "Edit|Write|NotebookEdit|MultiEdit|Agent|Workflow"
        self.write_settings(settings)
        self.assertFalse(guard.global_guard_covers("claude", "PreToolUse", "Bash", self.env(), self.home))
        self.assertTrue(guard.global_guard_covers("claude", "PreToolUse", "Edit", self.env(), self.home))
        self.call(self.plugin_script, ["--host", "claude", "--plugin"], json.dumps(self.prompt()).encode(), {})
        out = self.call(self.plugin_script, ["--host", "claude", "--plugin"], json.dumps(self.background_bash()).encode(), {})
        self.assert_one_g4_deny(out)

    def test_foreground_bash_is_silent_and_leaves_no_trace(self) -> None:
        self.fire(self.prompt())
        before = self.records()
        payload = self.background_bash()
        payload["tool_input"] = {"command": "ls"}
        self.assertEqual(self.fire(payload), "")
        payload["tool_input"] = {"command": "ls", "run_in_background": False}
        self.assertEqual(self.fire(payload), "")
        self.assertEqual(self.records(), before)

    def test_plugin_alone_with_global_entry_is_silent_and_logs_nothing(self) -> None:
        self.install_global()
        raw = json.dumps(self.edit("a")).encode()
        self.assertEqual(
            self.call(self.plugin_script, ["--host", "claude", "--plugin"], raw, {}), ""
        )
        self.assertEqual(self.records(), [])

    def test_global_entry_with_missing_script_does_not_silence_the_plugin(self) -> None:
        self.install_global(script_exists=False)
        self.assertFalse(self.script.exists())
        self.assert_one_log_per_event(self.run_turn())

    def test_global_entry_with_unreadable_settings_does_not_silence_the_plugin(
        self,
    ) -> None:
        self.install_global()
        (self.cfg / "settings.json").write_text("{not json", encoding="utf-8")
        outs = self.run_turn()  # the global script still exists and fires: the broken settings case runs it twice
        # advise records the edit, so the second copy sees the file as already counted and stays quiet
        self.assertEqual(sum(1 for r in self.records() if r["decision"] == "advise"), 1)
        self.assertEqual([bool(o) for o in outs], [False, False, False, True])

    def test_plugin_runs_when_the_global_script_is_a_directory(self) -> None:
        self.install_global(script_exists=False)
        self.script.mkdir()
        raw = json.dumps(self.prompt()).encode()
        self.call(self.plugin_script, ["--host", "claude", "--plugin"], raw, {})
        self.assertEqual([r["decision"] for r in self.records()], ["state"])

    def test_a_plugin_command_in_settings_is_not_a_global_entry(self) -> None:
        # The plugin's own command matches install_hooks.OWNED but is not the install_hooks script.
        command = 'python3 "%s" --host claude --plugin' % self.plugin_script
        self.assertTrue(install_hooks.OWNED.search(command))
        self.install_global()
        settings = install_hooks.apply_claude({}, command)
        self.write_settings(settings)
        self.assertFalse(
            guard.global_guard_covers(
                "claude", "UserPromptSubmit", None, self.env(), self.home
            )
        )
        raw = json.dumps(self.prompt()).encode()
        self.call(self.plugin_script, ["--host", "claude", "--plugin"], raw, {})
        self.assertEqual([r["decision"] for r in self.records()], ["state"])

    def test_script_path_must_be_the_install_hooks_one(self) -> None:
        self.install_global()
        other = self.home / "elsewhere" / "shoal_guard.py"
        other.parent.mkdir()
        shutil.copy(GUARD, other)
        self.write_settings(
            install_hooks.apply_claude({}, install_hooks.command_for(other, "claude"))
        )
        self.assertFalse(
            guard.global_guard_covers(
                "claude", "UserPromptSubmit", None, self.env(), self.home
            )
        )

    def test_event_and_matcher_must_be_covered(self) -> None:
        self.install_global()
        env = self.env()
        covers = lambda name, tool: guard.global_guard_covers(
            "claude", name, tool, env, self.home
        )  # noqa: E731
        self.assertTrue(covers("UserPromptSubmit", None))
        self.assertTrue(covers("SubagentStart", None))  # install_hooks registers it next to the other two
        self.assertTrue(covers("Stop", None))  # 3.4.0: the completion check, same rule
        self.assertTrue(covers("PreToolUse", "Edit"))
        self.assertTrue(covers("PreToolUse", "Workflow"))
        self.assertTrue(covers("PreToolUse", "Bash"))  # G4 needs the shell tool
        self.assertFalse(covers("PreToolUse", "Read"))
        self.assertFalse(covers("PreToolUse", None))
        self.assertFalse(covers("SessionStart", None))
        self.assertFalse(covers(None, None))
        settings = json.loads((self.cfg / "settings.json").read_text(encoding="utf-8"))
        del settings["hooks"]["UserPromptSubmit"]
        self.write_settings(settings)
        self.assertFalse(covers("UserPromptSubmit", None))
        self.assertTrue(covers("PreToolUse", "Agent"))

    def test_other_host_never_defers(self) -> None:
        self.install_global()
        self.assertFalse(
            guard.defer_to_global(
                "codex", json.dumps(self.prompt()).encode(), self.env()
            )
        )

    def test_settings_symlink_is_resolved(self) -> None:
        self.install_global()
        real = self.home / "dotfiles" / "settings.json"
        real.parent.mkdir()
        (self.cfg / "settings.json").replace(real)
        (self.cfg / "settings.json").symlink_to(real)
        self.assertTrue(
            guard.global_guard_covers(
                "claude", "UserPromptSubmit", None, self.env(), self.home
            )
        )

    def test_default_config_dir_and_data_dir(self) -> None:
        env = {"HOME": str(self.home)}
        script = self.home / ".local" / "share" / "shoal" / "guard" / "shoal_guard.py"
        script.parent.mkdir(parents=True)
        shutil.copy(GUARD, script)
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "settings.json").write_text(
            json.dumps(
                install_hooks.apply_claude(
                    {}, install_hooks.command_for(script, "claude")
                )
            ),
            encoding="utf-8",
        )
        self.assertTrue(
            guard.global_guard_covers(
                "claude", "UserPromptSubmit", None, env, self.home
            )
        )
        env["CLAUDE_CONFIG_DIR"] = (
            "relative/dir"  # not absolute: falls back to ~/.claude, as Claude Code does
        )
        self.assertTrue(
            guard.global_guard_covers(
                "claude", "UserPromptSubmit", None, env, self.home
            )
        )
        env["CLAUDE_CONFIG_DIR"] = str(self.cfg)  # empty config dir without the entry
        self.assertFalse(
            guard.global_guard_covers(
                "claude", "UserPromptSubmit", None, env, self.home
            )
        )

    def test_portable_command_from_install_hooks_is_recognised(self) -> None:
        self.install_global()
        self.write_settings(
            install_hooks.apply_claude({}, install_hooks.portable_command_for("claude"))
        )
        # XDG_DATA_HOME set: the command follows it
        self.assertTrue(
            guard.global_guard_covers("claude", "PreToolUse", "Edit", self.env(), self.home)
        )
        # unset or empty: ~/.local/share, which has no script yet
        unset = {k: v for k, v in self.env().items() if k != "XDG_DATA_HOME"}
        for env in (unset, {**unset, "XDG_DATA_HOME": ""}):
            self.assertFalse(
                guard.global_guard_covers("claude", "UserPromptSubmit", None, env, self.home)
            )
        default = self.home / ".local" / "share" / "shoal" / "guard" / "shoal_guard.py"
        default.parent.mkdir(parents=True)
        shutil.copy(GUARD, default)
        for env in (unset, {**unset, "XDG_DATA_HOME": ""}):
            self.assertTrue(
                guard.global_guard_covers("claude", "UserPromptSubmit", None, env, self.home)
            )
        # the unguarded form 300bc1d wrote is recognised too
        self.write_settings(
            install_hooks.apply_claude(
                {},
                'python3 "${XDG_DATA_HOME:-$HOME/.local/share}/shoal/guard/shoal_guard.py" --host claude',
            )
        )
        self.assertTrue(
            guard.global_guard_covers("claude", "PreToolUse", "Edit", self.env(), self.home)
        )
        # the host in the command still has to match
        self.write_settings(
            install_hooks.apply_claude({}, install_hooks.portable_command_for("agy"))
        )
        self.assertFalse(
            guard.global_guard_covers("claude", "UserPromptSubmit", None, unset, self.home)
        )

    def test_home_spelling_in_a_hand_written_command(self) -> None:
        script = self.home / ".local" / "share" / "shoal" / "guard" / "shoal_guard.py"
        script.parent.mkdir(parents=True)
        shutil.copy(GUARD, script)
        env = {"HOME": str(self.home)}
        for spelling in ("$HOME", "${HOME}", "~"):
            command = (
                'python3 "%s/.local/share/shoal/guard/shoal_guard.py" --host claude'
                % spelling
            )
            self.write_settings(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {"hooks": [{"type": "command", "command": command}]}
                        ]
                    }
                }
            )
            env["CLAUDE_CONFIG_DIR"] = str(self.cfg)
            self.assertTrue(
                guard.global_guard_covers(
                    "claude", "UserPromptSubmit", None, env, self.home
                ),
                spelling,
            )


if __name__ == "__main__":
    unittest.main()
