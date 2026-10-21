"""cross-vendor-relay render（T1.3）：S0.3、S1.8、S1.9、S1.10。

relay 用 tests/fixtures/relay/relay.binding.toml 附加在 hosts/claude/binding.toml 之後開啟；repo 的 binding 不開。
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
import render  # noqa: E402
import shoal_relay  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "relay" / "relay.binding.toml"
POLICY_DOC = "skills/shoal-orchestration/references/orchestration-policy.md"
RELAY_FILES = (
    "tools/shoal_relay.py",
    "core/vendors.toml",
    "core/contracts/handback.schema.json",
)
HOSTS = ("claude", "codex", "agy", "grok", "opencode")


def make_root(
    parent: Path,
    relay: str | None = FIXTURE.read_text(encoding="utf-8"),
    host: str = "claude",
) -> Path:
    """core、hosts/<host>、guard、VERSION、runner 的最小副本；relay 是附加在 binding 後面的 toml（None 為不開）。"""
    root = parent / "root"
    shutil.copytree(ROOT / "core", root / "core")
    shutil.copytree(ROOT / "hosts" / host, root / "hosts" / host)
    (root / "hooks").mkdir(parents=True)
    (root / "tools").mkdir()
    shutil.copy(ROOT / "hooks" / "shoal_guard.py", root / "hooks" / "shoal_guard.py")
    shutil.copy(ROOT / "VERSION", root / "VERSION")
    shutil.copy(ROOT / "tools" / "shoal_relay.py", root / "tools" / "shoal_relay.py")
    if relay:
        binding = root / "hosts" / host / "binding.toml"
        binding.write_text(
            binding.read_text(encoding="utf-8") + relay, encoding="utf-8"
        )
    return root


def run_render(root: Path, host: str, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "render.py"),
            "--host",
            host,
            "--root",
            str(root),
            *flags,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def frontmatter(data: bytes) -> dict[str, str]:
    head = data.decode("utf-8").split("---\n")[1]
    return dict(line.split(": ", 1) for line in head.splitlines())


class TempCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def relay_root(self, extra: str = "", base: str | None = None) -> Path:
        shutil.rmtree(self.tmp / "root", ignore_errors=True)
        relay = FIXTURE.read_text(encoding="utf-8") if base is None else base
        return make_root(self.tmp, relay + extra)


class RelayOffTests(unittest.TestCase):
    """S0.3：沒有 [relay.roles] 時所有 host 與 claude-plugin 的輸出與變更前位元組相同。"""

    def test_every_host_matches_its_committed_dist(self) -> None:
        for host in HOSTS:
            files = render.render_host(ROOT, host)
            self.assertEqual(
                render.diff_dist(ROOT / render.dist_dir(host), files), [], host
            )

    def test_claude_plugin_matches_committed_files_and_has_no_runner(self) -> None:
        files = render.render_claude_plugin(ROOT)
        self.assertEqual(render.diff_owned(ROOT, files, render.CLAUDE_PLUGIN_OWNED), [])
        self.assertFalse(
            [
                rel
                for rel in files
                if "shoal_relay" in rel or rel.endswith("vendors.toml")
            ]
        )
        self.assertFalse((ROOT / render.CLAUDE_PLUGIN / "tools").exists())

    def test_repo_binding_does_not_enable_relay(self) -> None:
        binding = render.load_toml(ROOT / "hosts" / "claude" / "binding.toml")
        self.assertEqual(render.relay_roles(binding), {})
        self.assertNotIn(
            "Relayed roles",
            render.render_host(ROOT, "claude")[POLICY_DOC].decode("utf-8"),
        )

    def test_empty_relay_tables_change_nothing(self) -> None:
        baseline = render.render_host(ROOT, "claude")
        for extra in ('\n[relay]\nshell_model = "haiku"\n', "\n[relay.roles]\n"):
            with tempfile.TemporaryDirectory() as tmp:
                root = make_root(Path(tmp), extra)
                self.assertEqual(render.RENDERERS["claude"](root), baseline, extra)
                self.assertEqual(
                    render.render_claude_plugin(root),
                    render.render_claude_plugin(ROOT),
                    extra,
                )


class RelayShellTests(TempCase):
    """S1.8：同名 subagent、模型 = shell_model、tools = Bash、以 CLAUDE_PLUGIN_ROOT 呼叫 runner。"""

    def setUp(self) -> None:
        super().setUp()
        self.root = self.relay_root()
        self.dist = render.RENDERERS["claude"](self.root)

    def test_relayed_roles_are_shells(self) -> None:
        for name in ("executor", "applier"):
            data = self.dist[f"agents/{name}.md"]
            fields = frontmatter(data)
            self.assertEqual(fields["name"], name)
            self.assertEqual(fields["model"], "haiku")
            self.assertEqual(fields["tools"], "Bash")
            self.assertNotIn("disallowedTools", fields)
            text = data.decode("utf-8")
            self.assertIn('python3 "${CLAUDE_PLUGIN_ROOT}/tools/shoal_relay.py"', text)
            self.assertIn(f"--vendor codex --role {name} ", text)
            self.assertNotIn("{{", text)

    def test_description_keeps_the_routing_text(self) -> None:
        binding = render.load_toml(self.root / "hosts" / "claude" / "binding.toml")
        for name in ("executor", "applier"):
            self.assertTrue(
                frontmatter(self.dist[f"agents/{name}.md"])["description"].startswith(
                    binding["roles"][name]["description"]
                )
            )

    def test_shell_model_comes_from_the_binding(self) -> None:
        root = self.relay_root(
            base=FIXTURE.read_text(encoding="utf-8").replace('"haiku"', '"sonnet"')
        )
        dist = render.RENDERERS["claude"](root)
        self.assertEqual(frontmatter(dist["agents/executor.md"])["model"], "sonnet")

    def test_only_relayed_roles_and_the_policy_doc_change(self) -> None:
        baseline = render.render_host(ROOT, "claude")
        changed = {rel for rel in self.dist if self.dist[rel] != baseline.get(rel)}
        self.assertEqual(set(self.dist), set(baseline))
        self.assertEqual(
            changed, {"agents/executor.md", "agents/applier.md", POLICY_DOC}
        )

    def test_only_one_role_relayed(self) -> None:
        root = self.relay_root(
            base='\n[relay]\nshell_model = "haiku"\n\n[relay.roles]\nexecutor = "codex"\n'
        )
        dist = render.RENDERERS["claude"](root)
        self.assertEqual(frontmatter(dist["agents/executor.md"])["tools"], "Bash")
        self.assertEqual(
            dist["agents/applier.md"],
            render.render_host(ROOT, "claude")["agents/applier.md"],
        )

    def test_long_runs_go_to_the_background(self) -> None:
        executor = self.dist["agents/executor.md"].decode("utf-8")
        self.assertIn("--timeout 1500", executor)
        self.assertIn("run_in_background: true", executor)
        self.assertNotIn("`timeout: ", executor)

    def test_short_runs_get_a_bash_timeout_above_the_runner_limit(self) -> None:
        root = self.relay_root(extra="\n[relay.timeouts]\napplier = 300\n")
        applier = render.RENDERERS["claude"](root)["agents/applier.md"].decode("utf-8")
        self.assertIn("--timeout 300", applier)
        self.assertIn("`timeout: 360000`", applier)
        self.assertNotIn("run_in_background", applier)

    def test_timeout_constants_match_the_runner(self) -> None:
        self.assertEqual(render.RELAY_DEFAULT_TIMEOUT, shoal_relay.DEFAULT_TIMEOUT)
        self.assertEqual(render.RELAY_MAX_TIMEOUT, shoal_relay.MAX_TIMEOUT)
        self.assertEqual(set(render.RELAY_P1_ROLES), set(shoal_relay.RELAY_ROLES))
        for name, seconds in render.RELAY_DEFAULT_TIMEOUT.items():
            if seconds + render.BASH_MARGIN_SECONDS > render.BASH_LIMIT_SECONDS:
                self.assertIn("run_in_background", render._relay_run_step(seconds))


class RelayPackagingTests(TempCase):
    """D3、S1.8：runner 只在 relay 開啟時打包進 plugin，缺少時 --check 失敗。"""

    def setUp(self) -> None:
        super().setUp()
        self.root = self.relay_root()
        self.assertEqual(run_render(self.root, "claude", "--write").returncode, 0)
        self.assertEqual(
            run_render(self.root, "claude-plugin", "--write").returncode, 0
        )
        self.plugin = self.root / render.CLAUDE_PLUGIN

    def test_runner_and_its_data_files_are_packaged(self) -> None:
        for rel in RELAY_FILES:
            self.assertEqual(
                (self.plugin / rel).read_bytes(), (ROOT / rel).read_bytes(), rel
            )
        self.assertEqual(
            run_render(self.root, "claude-plugin", "--check").returncode, 0
        )
        self.assertEqual(run_render(self.root, "claude", "--check").returncode, 0)

    def test_check_fails_when_the_runner_file_is_missing(self) -> None:
        (self.plugin / "tools" / "shoal_relay.py").unlink()
        result = run_render(self.root, "claude-plugin", "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("缺少: plugins/claude/tools/shoal_relay.py", result.stderr)
        host = run_render(self.root, "claude", "--check")
        self.assertEqual(host.returncode, 1)
        self.assertIn("plugins/claude/tools/shoal_relay.py", host.stderr)

    def test_check_fails_when_a_packaged_data_file_changes(self) -> None:
        for rel in RELAY_FILES:
            target = self.plugin / rel
            original = target.read_bytes()
            target.write_bytes(original + b"\n")
            self.assertEqual(
                run_render(self.root, "claude-plugin", "--check").returncode, 1, rel
            )
            target.write_bytes(original)

    def test_packaged_runner_finds_its_files_from_the_plugin_root(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(self.plugin / "tools" / "shoal_relay.py"),
                "--vendor",
                "codex",
                "--role",
                "security-reviewer",
                "--cwd",
                str(self.tmp),
                "--brief",
                str(self.tmp / "none"),
            ],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=60,
        )
        hand_back = json.loads(result.stdout)
        self.assertEqual(hand_back["status"], "blocked")
        self.assertNotIn(
            "schema", hand_back["reason"]
        )  # schema 與 vendors.toml 都從 plugin 內讀到

    def test_relay_files_are_removed_by_write_when_relay_is_off(self) -> None:
        other = self.tmp / "off"
        other.mkdir()
        off = make_root(other, None)
        shutil.copytree(self.plugin, off / render.CLAUDE_PLUGIN)
        self.assertEqual(run_render(off, "claude-plugin", "--check").returncode, 1)
        self.assertEqual(run_render(off, "claude-plugin", "--write").returncode, 0)
        self.assertFalse((off / render.CLAUDE_PLUGIN / "tools" / "shoal_relay.py").exists())
        self.assertEqual(run_render(off, "claude-plugin", "--check").returncode, 0)


class RelayValidationTests(TempCase):
    """S1.9：security role、P1 以外的 role、未知 vendor 與其他不合法設定讓 render 失敗並說明原因。"""

    def fails(self, relay: str, *needles: str, host: str = "claude") -> None:
        root = make_root(self.tmp, relay, host)
        try:
            result = run_render(root, host, "--check")
            self.assertEqual(result.returncode, 2, result.stderr)
            for needle in needles:
                self.assertIn(needle, result.stderr)
        finally:
            shutil.rmtree(root)

    def test_security_roles_are_rejected(self) -> None:
        for role in ("security-reviewer", "security-executor"):
            self.fails(
                f'\n[relay]\nshell_model = "haiku"\n\n[relay.roles]\n{role} = "codex"\n',
                role,
                "security",
            )

    def test_roles_outside_phase_one_are_rejected(self) -> None:
        for role in ("scout", "verifier", "watcher"):
            self.fails(
                f'\n[relay]\nshell_model = "haiku"\n\n[relay.roles]\n{role} = "codex"\n',
                role,
                "phase 1",
            )

    def test_unknown_role_is_rejected(self) -> None:
        self.fails(
            '\n[relay]\nshell_model = "haiku"\n\n[relay.roles]\nnope = "codex"\n',
            "nope",
        )

    def test_unknown_vendor_is_rejected(self) -> None:
        self.fails(
            '\n[relay]\nshell_model = "haiku"\n\n[relay.roles]\nexecutor = "gemini"\n',
            "gemini",
            "vendors.toml",
        )

    def test_shell_model_is_required_and_must_be_a_known_alias(self) -> None:
        self.fails('\n[relay.roles]\nexecutor = "codex"\n', "shell_model")
        self.fails(
            '\n[relay]\nshell_model = "gpt-9"\n\n[relay.roles]\nexecutor = "codex"\n',
            "shell_model",
            "gpt-9",
        )

    def test_bad_shapes_are_rejected(self) -> None:
        self.fails(
            '\n[relay]\nshell_model = "haiku"\nextra = 1\n\n[relay.roles]\nexecutor = "codex"\n',
            "extra",
        )
        self.fails(
            '\n[relay]\nshell_model = "haiku"\n\n[relay.roles]\nexecutor = 3\n',
            "[relay.roles]",
        )
        self.fails(
            '\n[relay]\nshell_model = "haiku"\n\n[relay.roles]\nexecutor = "codex"\n\n[relay.timeouts]\napplier = 5\n',
            "[relay.timeouts]",
        )
        self.fails(
            '\n[relay]\nshell_model = "haiku"\n\n[relay.roles]\nexecutor = "codex"\n\n[relay.timeouts]\nexecutor = 99999\n',
            "executor",
        )

    def test_relay_is_claude_only_in_phase_one(self) -> None:
        self.fails(
            '\n[relay]\nshell_model = "gpt"\n\n[relay.roles]\nexecutor = "codex"\n',
            "phase 1",
            host="codex",
        )


class WriteRelayIsolationTests(TempCase):
    """S1.10：write relay 在外殼與 policy 都要求 worktree 隔離，且寫明 hand-back 是資料、之後派 fresh verifier。"""

    def test_shell_and_policy_require_worktree_isolation(self) -> None:
        dist = render.RENDERERS["claude"](self.relay_root())
        for name in ("executor", "applier"):
            text = dist[f"agents/{name}.md"].decode("utf-8")
            self.assertIn("worktree isolation", text)
            self.assertIn("fresh verifier", text)
            self.assertIn("data from an external model", text)
            self.assertIn(
                "worktree isolation",
                frontmatter(dist[f"agents/{name}.md"])["description"],
            )
        policy = dist[POLICY_DOC].decode("utf-8")
        self.assertIn(
            '`isolation: "worktree"`', policy[policy.index("Relayed roles") :]
        )
        self.assertIn("fresh `verifier`", policy)

    def test_shell_has_only_the_bash_tool_and_no_write_tools(self) -> None:
        dist = render.RENDERERS["claude"](self.relay_root())
        for name in ("executor", "applier"):
            fields = frontmatter(dist[f"agents/{name}.md"])
            self.assertEqual(fields["tools"], "Bash")
            self.assertFalse(
                re.search(r"\b(Write|Edit|MultiEdit|NotebookEdit)\b", fields["tools"])
            )


if __name__ == "__main__":
    unittest.main()
