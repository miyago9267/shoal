"""Claude plugin (generic-shoal K1, K2, K4, K5, K6): render, golden, quoting, guard `--plugin` deferral.

tests/golden/claude-plugin is a copy of the render output (repo-relative paths); refresh it by
copying `claude-plugin/` and `.claude-plugin/marketplace.json` after `render.py --host claude-plugin --write`.
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
PLUGIN = ROOT / "claude-plugin"
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
        self.assertEqual(len(golden), 17)
        rendered = render.render_claude_plugin(ROOT)
        self.assertEqual(sorted(rendered), sorted(golden))
        for rel, data in golden.items():
            self.assertEqual(rendered[rel], data, rel)

    def test_committed_files_match_render(self) -> None:
        for rel, data in render.render_claude_plugin(ROOT).items():
            self.assertEqual((ROOT / rel).read_bytes(), data, rel)

    def test_claude_dist_is_not_changed_by_the_plugin_target(self) -> None:
        self.assertEqual(len(render.RENDERERS["claude"](ROOT)), 13)
        self.assertNotIn("claude-plugin", render.RENDERERS)


class ContentTests(unittest.TestCase):
    def test_guard_copy_is_byte_identical_to_the_single_source(self) -> None:
        self.assertEqual(
            (PLUGIN / "hooks" / "shoal_guard.py").read_bytes(), GUARD.read_bytes()
        )

    def test_agents_skills_and_policy_come_from_the_claude_dist(self) -> None:
        dist = render.RENDERERS["claude"](ROOT)
        rendered = render.render_claude_plugin(ROOT)
        for rel, data in dist.items():
            if rel.startswith(("agents/", "skills/")):
                self.assertEqual(rendered[f"claude-plugin/{rel}"], data, rel)
        self.assertEqual(
            rendered["claude-plugin/policy/claude-md.bootstrap.md"],
            dist["claude-md.bootstrap.md"],
        )
        self.assertNotIn("claude-plugin/settings.snippet.json", rendered)

    def test_versions_equal_the_product_version(self) -> None:
        plugin = json.loads(
            (PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        market = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plugin["version"], VERSION)
        self.assertEqual(plugin["name"], "shoal")
        self.assertEqual(market["name"], "shoal")
        (entry,) = market["plugins"]
        self.assertEqual((entry["name"], entry["version"]), ("shoal", VERSION))

    def test_marketplace_source_is_the_plugin_dir_and_not_the_codex_one(self) -> None:
        market = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        source = market["plugins"][0]["source"]
        self.assertEqual(source, "./claude-plugin")
        self.assertTrue((ROOT / source / ".claude-plugin" / "plugin.json").is_file())
        self.assertNotEqual((ROOT / source).resolve(), (ROOT / "plugin").resolve())


class HooksJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hooks = json.loads(
            (PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )["hooks"]

    def test_events_and_matchers(self) -> None:
        self.assertEqual(
            sorted(self.hooks), ["PreToolUse", "SessionStart", "UserPromptSubmit"]
        )
        (pre,) = self.hooks["PreToolUse"]
        self.assertEqual(pre["matcher"], install_hooks.CLAUDE_MATCHER)
        self.assertNotIn("matcher", self.hooks["UserPromptSubmit"][0])

    def test_every_command_quotes_the_plugin_root(self) -> None:
        guard_cmd = 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/shoal_guard.py" --host claude --plugin'
        for event in ("UserPromptSubmit", "PreToolUse"):
            (handler,) = self.hooks[event][0]["hooks"]
            self.assertEqual(handler["command"], guard_cmd, event)
        (start,) = self.hooks["SessionStart"][0]["hooks"]
        self.assertEqual(
            start["command"],
            '/bin/sh "${CLAUDE_PLUGIN_ROOT}/hooks/emit-sessionstart.sh"',
        )

    def test_no_command_uses_an_unquoted_plugin_root(self) -> None:
        text = (PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8")
        for match in re.finditer(r"\$\{CLAUDE_PLUGIN_ROOT\}", text):
            self.assertEqual(text[match.start() - 2 : match.start()], '\\"')

    @unittest.skipIf(os.name == "nt", "POSIX shell")
    def test_commands_run_from_a_plugin_root_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="shoal plugin ") as tmp:
            root = Path(tmp, "my plugin")
            shutil.copytree(PLUGIN, root)
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
            (start,) = self.hooks["SessionStart"][0]["hooks"]
            proc = subprocess.run(
                start["command"], shell=True, capture_output=True, env=env, timeout=30
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
        for rel in ("claude-plugin/hooks/shoal_guard.py", "claude-plugin/hooks/hooks.json",
                    ".claude-plugin/marketplace.json", "claude-plugin/agents/scout.md"):
            target = self.root / rel
            original = target.read_bytes()
            target.write_bytes(original + b" ")
            result = run_render(self.root, "--check")
            self.assertEqual(result.returncode, 1, rel)
            self.assertIn(f"內容不同: {rel}", result.stderr)
            target.write_bytes(original)

    def test_check_fails_on_extra_or_missing_file(self) -> None:
        (self.root / "claude-plugin" / "agents" / "extra.md").write_text("x", encoding="utf-8")
        (self.root / "claude-plugin" / "hooks" / "hooks.json").unlink()
        result = run_render(self.root, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("多出: claude-plugin/agents/extra.md", result.stderr)
        self.assertIn("缺少: claude-plugin/hooks/hooks.json", result.stderr)

    def test_changing_the_guard_source_requires_rewriting_the_copy(self) -> None:
        guard_src = self.root / "hooks" / "shoal_guard.py"
        guard_src.write_bytes(guard_src.read_bytes() + b"# changed\n")
        self.assertEqual(run_render(self.root, "--check").returncode, 1)
        self.assertEqual(run_render(self.root, "--write").returncode, 0)
        self.assertEqual((self.root / "claude-plugin" / "hooks" / "shoal_guard.py").read_bytes(), guard_src.read_bytes())
        self.assertEqual(run_render(self.root, "--check").returncode, 0)

    def test_changing_the_version_requires_rewriting_the_manifests(self) -> None:
        (self.root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        self.assertEqual(run_render(self.root, "--check").returncode, 1)
        run_render(self.root, "--write")
        manifest = json.loads((self.root / "claude-plugin" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "9.9.9")

    def test_bad_version_is_rejected(self) -> None:
        (self.root / "VERSION").write_text("one\n", encoding="utf-8")
        result = run_render(self.root, "--check")
        self.assertEqual(result.returncode, 2)
        self.assertIn("版本格式不合法", result.stderr)

    def test_write_repairs_and_removes_stale_files(self) -> None:
        (self.root / "claude-plugin" / "agents" / "stale.md").write_text("x", encoding="utf-8")
        (self.root / "claude-plugin" / "hooks" / "shoal_guard.py").write_bytes(b"broken")
        self.assertEqual(run_render(self.root, "--write").returncode, 0)
        self.assertFalse((self.root / "claude-plugin" / "agents" / "stale.md").exists())
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
            "<!-- pilotfish v1.4.2-claude.4 -->\n## Orchestration\n", encoding="utf-8"
        )
        out = self.run_script()
        self.assertIn("already carries the pilotfish bootstrap", out)
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
        self.assertTrue(covers("PreToolUse", "Edit"))
        self.assertTrue(covers("PreToolUse", "Workflow"))
        self.assertFalse(covers("PreToolUse", "Bash"))
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
