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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import render  # noqa: E402
import shoal_relay  # noqa: E402
from repo_fixtures import git  # noqa: E402
from test_relay_runner import FAKE, SCHEMA, report  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "relay" / "relay.binding.toml"
OVERLAY = ROOT / "bench" / "ab" / "relay.binding.toml"
POLICY_DOC = "skills/shoal-orchestration/references/orchestration-policy.md"
RELAY_FILES = (
    "tools/shoal_relay.py",
    "core/vendors.toml",
    "core/contracts/handback.schema.json",
)
GUARD_COPY = "tools/shoal_guard.py"  # hooks/shoal_guard.py 的副本；plugin 的 hooks/shoal_guard.py 是 compat shim
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
                if "shoal_relay" in rel
                or rel.endswith("vendors.toml")
                or rel.endswith(GUARD_COPY)
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

    def test_default_timeouts_run_in_the_foreground(self) -> None:
        for name, seconds, bash_ms in (("executor", 540, 600000), ("applier", 300, 360000)):
            text = self.dist[f"agents/{name}.md"].decode("utf-8")
            self.assertIn(f"--timeout {seconds}", text)
            self.assertIn(f"`timeout: {bash_ms}`", text)
            self.assertNotIn("run_in_background", text)

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
        self.assertEqual(render.RELAY_DEFAULT_TIMEOUT, {"executor": 540, "applier": 300})
        self.assertEqual(render.RELAY_MAX_TIMEOUT + render.BASH_MARGIN_SECONDS, render.BASH_LIMIT_SECONDS)
        for seconds in (1, *render.RELAY_DEFAULT_TIMEOUT.values(), render.RELAY_MAX_TIMEOUT):
            step = render._relay_run_step(seconds)
            self.assertNotIn("run_in_background", step)
            self.assertIn(f"`timeout: {(seconds + render.BASH_MARGIN_SECONDS) * 1000}`", step)

    def test_max_timeout_is_accepted_and_one_more_is_rejected(self) -> None:
        root = self.relay_root(extra="\n[relay.timeouts]\nexecutor = 540\n")
        executor = render.RENDERERS["claude"](root)["agents/executor.md"].decode("utf-8")
        self.assertIn("`timeout: 600000`", executor)
        for seconds in (541, 600, 1500):
            root = self.relay_root(extra=f"\n[relay.timeouts]\nexecutor = {seconds}\n")
            result = run_render(root, "claude", "--check")
            self.assertEqual(result.returncode, 2, seconds)
            self.assertIn("540", result.stderr)


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
            (self.plugin / GUARD_COPY).read_bytes(),
            (ROOT / "hooks" / "shoal_guard.py").read_bytes(),
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

    def test_check_fails_when_the_guard_copy_is_missing(self) -> None:
        (self.plugin / GUARD_COPY).unlink()
        result = run_render(self.root, "claude-plugin", "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"缺少: plugins/claude/{GUARD_COPY}", result.stderr)
        self.assertEqual(run_render(self.root, "claude", "--check").returncode, 1)

    def test_check_fails_when_a_packaged_data_file_changes(self) -> None:
        for rel in (*RELAY_FILES, GUARD_COPY):
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

    def fake_vendor(self) -> tuple[Path, Path, Path, dict[str, str]]:
        """把 plugin 的 vendors.toml 指向假 codex，建 linked worktree；回傳 (bin, worktree, brief, env)。"""
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "codex"
        fake.write_text(f"#!{sys.executable}\n{FAKE}", encoding="utf-8")
        fake.chmod(0o755)
        (bin_dir / "mode.json").write_text(
            json.dumps({"handback": report(), "write": ["a.txt"], "mcp": []}), encoding="utf-8"
        )
        vendors = self.plugin / "core" / "vendors.toml"
        text = re.sub(r"^paths = .*$", f"paths = [{json.dumps(str(fake))}]",
                      vendors.read_text(encoding="utf-8"), flags=re.M)
        vendors.write_text(re.sub(r"^search_path = true$", "search_path = false", text, flags=re.M),
                           encoding="utf-8")
        main, wt = self.tmp / "main", self.tmp / "wt"
        main.mkdir()
        (main / "README").write_text("r")
        git(main, "init", "-q")
        git(main, "add", "README")
        git(main, "commit", "-q", "-m", "init")
        git(main, "worktree", "add", "-q", "-b", "relay", str(wt))
        brief = self.tmp / "brief.md"
        brief.write_text("Implement the thing.\n", encoding="utf-8")
        home, tmpdir = self.tmp / "home", self.tmp / "t"
        home.mkdir()
        tmpdir.mkdir()
        env = {"PATH": os.environ["PATH"], "HOME": str(home), "LANG": "C.UTF-8", "TMPDIR": str(tmpdir)}
        return bin_dir, wt, brief, env

    def run_packaged(self, wt: Path, brief: Path, env: dict[str, str]) -> dict:
        result = subprocess.run(
            [sys.executable, str(self.plugin / "tools" / "shoal_relay.py"), "--vendor", "codex",
             "--role", "executor", "--cwd", str(wt), "--brief", str(brief), "--timeout", "60"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env, timeout=120,
        )
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout + result.stderr)
        hand_back = json.loads(lines[0])
        self.assertIsNone(shoal_relay.schema_error(SCHEMA, hand_back))
        return hand_back

    def test_packaged_runner_relays_through_the_fake_vendor(self) -> None:
        bin_dir, wt, brief, env = self.fake_vendor()
        hand_back = self.run_packaged(wt, brief, env)
        self.assertEqual(hand_back["status"], "done", hand_back)
        self.assertEqual(hand_back["changed_files"], ["a.txt"])
        calls = [json.loads(line) for line in (bin_dir / "calls.jsonl").read_text().splitlines()]
        exec_call = [c for c in calls if c["argv"][:1] == ["exec"]][0]
        self.assertEqual(exec_call["nonce_body"]["role"], "executor")  # nonce 由打包的 guard 副本建立
        self.assertEqual(exec_call["nonce_mode"], "0o600")
        self.assertFalse(os.path.exists(exec_call["nonce_path"]))  # 結束時刪除

    def test_shim_only_layout_returns_blocked(self) -> None:
        # 回歸：plugin 的 hooks/shoal_guard.py 是沒有 _guard_dir/_open_private 的 compat shim
        bin_dir, wt, brief, env = self.fake_vendor()
        (self.plugin / GUARD_COPY).unlink()
        hand_back = self.run_packaged(wt, brief, env)
        self.assertEqual(hand_back["status"], "blocked", hand_back)
        self.assertIn("guard", hand_back["reason"])
        self.assertFalse((bin_dir / "calls.jsonl").exists())  # 沒有呼叫 vendor

    def test_relay_files_are_removed_by_write_when_relay_is_off(self) -> None:
        other = self.tmp / "off"
        other.mkdir()
        off = make_root(other, None)
        shutil.copytree(self.plugin, off / render.CLAUDE_PLUGIN)
        self.assertEqual(run_render(off, "claude-plugin", "--check").returncode, 1)
        self.assertEqual(run_render(off, "claude-plugin", "--write").returncode, 0)
        self.assertFalse((off / render.CLAUDE_PLUGIN / "tools" / "shoal_relay.py").exists())
        self.assertFalse((off / render.CLAUDE_PLUGIN / GUARD_COPY).exists())
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

    def test_shell_and_policy_explain_landing(self) -> None:
        """fix/relay-landing：landed 為 true 時改動已在 primary checkout；false 時給 worktree 路徑與合併指令。"""
        dist = render.RENDERERS["claude"](self.relay_root())
        for name in ("executor", "applier"):
            text = dist[f"agents/{name}.md"].decode("utf-8")
            self.assertIn("`landing`", text)
            self.assertIn("Do not commit, merge, apply or copy anything", text)
        policy = dist[POLICY_DOC].decode("utf-8")
        policy = policy[policy.index("Relayed roles") :]
        self.assertIn("`landing.landed` is true they are already there", policy)
        self.assertIn("`landing.worktree`", policy)
        self.assertIn("diff --cached --binary HEAD | git apply`", policy)
        self.assertNotIn("--3way", policy)

    def test_policy_limits_the_merge_fallback(self) -> None:
        """M1：只有 reason 以 `patch does not apply` 開頭才給合併指令；其他先檢查 worktree；非 done 不合併。M2：寫明 revert 指令。"""
        dist = render.RENDERERS["claude"](self.relay_root())
        policy = dist[POLICY_DOC].decode("utf-8")
        policy = policy[policy.index("Relayed roles") :]
        self.assertIn("starts with `patch does not apply`", policy)
        self.assertIn("inspect that worktree first", policy)
        self.assertIn("is not `done`, do not merge", policy)
        self.assertIn("git diff --binary --no-ext-diff --no-textconv --no-color --src-prefix=a/ --dst-prefix=b/ <tree> <head> | git -C <primary> apply", policy)
        for name in ("executor", "applier"):
            text = dist[f"agents/{name}.md"].decode("utf-8")
            self.assertNotIn("--3way", text)

    def test_shell_has_only_the_bash_tool_and_no_write_tools(self) -> None:
        dist = render.RENDERERS["claude"](self.relay_root())
        for name in ("executor", "applier"):
            fields = frontmatter(dist[f"agents/{name}.md"])
            self.assertEqual(fields["tools"], "Bash")
            self.assertEqual(fields["isolation"], "worktree")
            self.assertFalse(
                re.search(r"\b(Write|Edit|MultiEdit|NotebookEdit)\b", fields["tools"])
            )


class OverlayTests(TempCase):
    """--overlay：claude-plugin 在記憶體中把 overlay 合併進 claude binding 再 render；不寫回 hosts/*/binding.toml。"""

    def test_overlay_renders_relay_shell_and_runner(self) -> None:
        root = make_root(self.tmp, relay=None)
        result = run_render(root, "claude-plugin", "--write", "--overlay", str(OVERLAY))
        self.assertEqual(result.returncode, 0, result.stderr)
        plugin = root / render.CLAUDE_PLUGIN
        self.assertIn("tools: Bash", (plugin / "agents" / "executor.md").read_text(encoding="utf-8"))
        self.assertTrue((plugin / "tools" / "shoal_relay.py").is_file())
        self.assertEqual(
            (root / "hosts" / "claude" / "binding.toml").read_bytes(),
            (ROOT / "hosts" / "claude" / "binding.toml").read_bytes(),
        )

    def test_without_overlay_output_matches_committed_plugin(self) -> None:
        root = make_root(self.tmp, relay=None)
        result = run_render(root, "claude-plugin", "--write")
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in (root / render.CLAUDE_PLUGIN).rglob("*"):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                self.assertEqual(path.read_bytes(), (ROOT / rel).read_bytes(), rel)

    def test_check_without_overlay_passes_on_the_repo(self) -> None:
        self.assertEqual(run_render(ROOT, "claude-plugin", "--check").returncode, 0)

    def test_overlay_naming_a_security_role_fails(self) -> None:
        overlay = self.tmp / "security.binding.toml"
        overlay.write_text(
            '[relay]\nshell_model = "haiku"\n\n[relay.roles]\nsecurity-reviewer = "codex"\n',
            encoding="utf-8",
        )
        root = make_root(self.tmp, relay=None)
        result = run_render(root, "claude-plugin", "--check", "--overlay", str(overlay))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("security-reviewer", result.stderr)
        self.assertIn("security", result.stderr)

    def test_overlay_redefining_an_existing_key_fails(self) -> None:
        overlay = self.tmp / "clash.binding.toml"
        overlay.write_text('role_text = "core"\n', encoding="utf-8")
        root = make_root(self.tmp, relay=None)
        result = run_render(root, "claude-plugin", "--check", "--overlay", str(overlay))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("role_text", result.stderr)

    def test_overlay_is_only_for_claude_plugin(self) -> None:
        root = make_root(self.tmp, relay=None)
        result = run_render(root, "claude", "--check", "--overlay", str(OVERLAY))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("claude-plugin", result.stderr)


if __name__ == "__main__":
    unittest.main()
