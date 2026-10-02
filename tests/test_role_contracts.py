"""role 條款機制：core/contracts 的格式、frames 與 addenda 的定位語法、role_text 開關、R1 / R5 / R7 / R9。

機制測試用 temp 目錄的假 contract 與假 host 外框，不依賴實際條款內容；
R1、R5 與 replace 清單則直接檢查 repo 目前的 core/contracts 與各 host 的 addenda。
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from render_helpers import ROOT, render, run_render

sys.path.insert(0, str(ROOT / "tools"))
import contracts  # noqa: E402

HOSTS = ("claude", "codex", "agy", "grok", "opencode")

# 每個 host 目前被 replace 取代的條款（host -> role -> 條款 id）。
# 新增 replace 必須同時改這裡（R5）；host 沒有 addenda 就是空。
EXPECTED_REPLACES: dict[str, dict[str, list[str]]] = {
    "claude": {},
    "codex": {"mech-executor": ["route-judgment"]},
    "agy": {
        role: ["foreground-timeout"]
        for role in ("mech-executor", "executor", "verifier", "security-executor")
    },
    "grok": {},
    # OpenCode 的用語是 parent session；沒有 plan-verifier，main-session-carries 改寫成 parent session 的 Plan。
    "opencode": {
        "scout": ["no-delegate"],
        "executor": ["no-spawn"],
        "security-executor": ["no-spawn"],
        "security-reviewer": ["main-session-carries", "no-delegate"],
        "verifier": ["orchestrator-owns", "no-spawn"],
    },
}

# 2b-2：已切到 core 的 host（切換順序 agy、grok、OpenCode、Claude）與其 core role；
# host 專屬 role（Claude 的 Explore）與 omitted_roles 不在內。
CORE_ROLES = (
    "scout",
    "mech-executor",
    "executor",
    "plan-verifier",
    "verifier",
    "security-reviewer",
    "security-executor",
)
EXPECTED_CORE_HOSTS: dict[str, tuple[str, ...]] = {
    "agy": CORE_ROLES,
    "grok": CORE_ROLES,
    "claude": CORE_ROLES,
    # OpenCode 只有 5 個 role（Decision 9），omitted_roles 不變。
    "opencode": tuple(r for r in CORE_ROLES if r not in ("mech-executor", "plan-verifier")),
}

# host 專屬內容（工具限制、capability 說明、foreground 用語、brief 用語對照等）只能放在這些 addenda；
# 新增 addendum 要同時改這裡。codex 另由 CODEX_ADDENDA 鎖定。
EXPECTED_ADDENDA: dict[str, dict[str, list[str]]] = {
    "agy": {
        "scout": ["tool-limits"],
        "mech-executor": ["foreground-limit"],
        "executor": ["foreground-limit"],
        "plan-verifier": [
            "tool-limits",
            "envelope-scope-nongoals",
            "brief-unit-kinds",
            "security-proportionate",
            "revise-shape",
        ],
        "verifier": ["tool-limits", "default-contract", "foreground-limit"],
        "security-reviewer": ["tool-limits", "tunnel-vision"],
        "security-executor": ["proportionate-security", "foreground-limit"],
    },
    "grok": {
        "scout": ["tool-templates"],
        "plan-verifier": [
            "capability-note",
            "envelope-scope-nongoals",
            "brief-unit-kinds",
            "revise-shape",
        ],
        "verifier": ["capability-note", "default-contract"],
        "security-reviewer": ["capability-note"],
        "security-executor": ["reasoning-effort"],
    },
    "claude": {
        "scout": ["final-message-channel"],
        "mech-executor": ["tools-disabled", "timeout-param", "background-note"],
        "executor": ["tools-disabled", "timeout-param", "background-note"],
        "plan-verifier": [
            "tool-allowlist",
            "brief-unit-kinds",
            "read-needed-evidence",
            "revise-shape",
            "orchestrator-owns-writes",
        ],
        "verifier": [
            "tools-disabled",
            "default-contract",
            "blocked-primary-flow",
            "timeout-param",
            "background-note",
            "do-not-start",
            "checkpoint-details",
        ],
        "security-reviewer": ["tool-allowlist", "follow-codebase-evidence"],
        "security-executor": [
            "tools-disabled",
            "opus-routing",
            "contract-contents",
            "timeout-param",
            "background-note",
            "do-not-start",
        ],
    },
    "opencode": {
        "scout": ["assigned-paths", "parent-session-owns", "parent-session-wording"],
        "executor": ["assigned-scope", "parent-session-owns", "parent-session-wording"],
        "verifier": [
            "permission-checks",
            "default-contract",
            "report-extras",
            "parent-session-owns",
            "parent-session-wording",
        ],
        "security-reviewer": [
            "inspect-surfaces",
            "parent-session-carries",
            "no-permission-grants",
            "parent-session-wording",
        ],
        "security-executor": [
            "credentials-and-blockers",
            "parent-session-owns",
            "parent-session-wording",
        ],
    },
}

# R1：core 條款不得出現 host 專屬的工具、模型或機制名稱（不分大小寫，整詞比對）。
HOST_SPECIFIC_TERMS = (
    "gpt-",
    "luna",
    "sol",
    "astra",
    "claude",
    "codex",
    "gemini",
    "grok",
    "opencode",
    "opus",
    "sonnet",
    "haiku",
    "fable",
    "workflow",
    "agents.md",
    "semantic_adjudication",
    "escalate_to_executor",
    "reasoning effort",
    "model_reasoning_effort",
    "sandbox_mode",
    "web_search",
)


def clause(cid: str, text: str, sep: str = "paragraph", kind: str = "procedure") -> str:
    return f"[[clause]]\nid = \"{cid}\"\nkind = \"{kind}\"\nsep = \"{sep}\"\ntext = '''\n{text}'''\n\n"


def addendum(aid: str, at: str, text: str, sep: str | None = None, join: str | None = None) -> str:
    sep_line = ("" if sep is None else f'sep = "{sep}"\n') + ("" if join is None else f'join = "{join}"\n')
    return f"[[addendum]]\nid = \"{aid}\"\nat = \"{at}\"\n{sep_line}text = '''\n{text}'''\n\n"


def parse_clauses(text: str) -> list[contracts.Clause]:
    return contracts.parse_contract(tomllib.loads(text))


def parse_addenda(text: str) -> list[contracts.Addendum]:
    return contracts.parse_addenda(tomllib.loads(text))


ABC = (
    clause("a", "A one.", "space")
    + clause("b", "B two.\nwrapped.", "paragraph")
    + clause("c", "C three.", "newline")
    + clause("d", "D four.")
)


class ComposeTests(unittest.TestCase):
    def compose(self, addenda_text: str = "") -> str:
        return contracts.compose(parse_clauses(ABC), parse_addenda(addenda_text))

    def test_clauses_keep_order_and_each_separator(self) -> None:
        self.assertEqual(
            self.compose(), "A one. B two.\nwrapped.\n\nC three.\nD four.\n"
        )

    def test_start_and_end(self) -> None:
        text = self.compose(
            addendum("s", "start", "START") + addendum("e", "end", "END")
        )
        self.assertEqual(
            text, "START\n\nA one. B two.\nwrapped.\n\nC three.\nD four.\n\nEND\n"
        )

    def test_after_and_before(self) -> None:
        text = self.compose(
            addendum("x", "after:b", "AFTER-B")
            + addendum("y", "before:c", "BEFORE-C", "space")
        )
        self.assertEqual(
            text, "A one. B two.\nwrapped.\n\nAFTER-B\n\nBEFORE-C C three.\nD four.\n"
        )

    def test_after_the_last_clause_and_before_the_first(self) -> None:
        text = self.compose(
            addendum("x", "after:d", "TAIL") + addendum("y", "before:a", "HEAD")
        )
        self.assertEqual(
            text, "HEAD\n\nA one. B two.\nwrapped.\n\nC three.\nD four.\n\nTAIL\n"
        )

    def test_same_anchor_keeps_file_order(self) -> None:
        text = self.compose(
            addendum("x1", "end", "ONE")
            + addendum("x2", "end", "TWO")
            + addendum("y1", "after:a", "Y1", "space")
            + addendum("y2", "after:a", "Y2", "space")
        )
        self.assertEqual(
            text, "A one. Y1 Y2 B two.\nwrapped.\n\nC three.\nD four.\n\nONE\n\nTWO\n"
        )

    def test_replace_inherits_the_clause_separator(self) -> None:
        text = self.compose(addendum("r", "replace:a", "A host."))
        self.assertTrue(text.startswith("A host. B two."), text)

    def test_replace_may_set_its_own_separator(self) -> None:
        text = self.compose(addendum("r", "replace:a", "A host.", "paragraph"))
        self.assertTrue(text.startswith("A host.\n\nB two."), text)

    def test_after_and_before_attach_to_a_replaced_clause(self) -> None:
        text = self.compose(
            addendum("r", "replace:b", "B host.")
            + addendum("x", "after:b", "AFTER")
            + addendum("y", "before:b", "BEFORE", "space")
        )
        self.assertEqual(text, "A one. BEFORE B host.\n\nAFTER\n\nC three.\nD four.\n")

    def test_join_changes_only_the_gap_before_the_addendum(self) -> None:
        # core 在 d 之後是換段；host 句子接在同一行，之後再換段
        text = self.compose(addendum("x", "after:b", "HOST.", "paragraph", "space"))
        self.assertEqual(text, "A one. B two.\nwrapped. HOST.\n\nC three.\nD four.\n")
        # 沒有 addendum 時 core 的版面不變
        self.assertEqual(self.compose(), "A one. B two.\nwrapped.\n\nC three.\nD four.\n")

    def test_join_at_start_is_rejected(self) -> None:
        with self.assertRaisesRegex(contracts.ContractError, "join"):
            self.compose(addendum("x", "start", "X", join="space"))

    def test_single_clause_has_no_trailing_separator(self) -> None:
        self.assertEqual(
            contracts.compose(parse_clauses(clause("only", "Only.", "space")), []),
            "Only.\n",
        )

    def test_unknown_target_is_rejected(self) -> None:
        for at in ("after:zzz", "before:zzz", "replace:zzz"):
            with (
                self.subTest(at=at),
                self.assertRaisesRegex(contracts.ContractError, "zzz"),
            ):
                self.compose(addendum("x", at, "X"))

    def test_clause_cannot_be_replaced_twice(self) -> None:
        with self.assertRaisesRegex(contracts.ContractError, "replace 兩次"):
            self.compose(
                addendum("x", "replace:a", "X") + addendum("y", "replace:a", "Y")
            )

    def test_unknown_anchor_syntax_is_rejected(self) -> None:
        for at in ("middle", "after:", "replace", "start:a", ""):
            with (
                self.subTest(at=at),
                self.assertRaisesRegex(contracts.ContractError, "at 必須"),
            ):
                parse_addenda(addendum("x", at, "X"))


class FormatTests(unittest.TestCase):
    def test_contract_rejects_bad_clauses(self) -> None:
        good = clause("a", "A.")
        cases = {
            "重複": good + good,
            "kind": good.replace('kind = "procedure"', 'kind = "vibes"'),
            "id": good.replace('id = "a"', 'id = "Not_Valid"'),
            "sep": good.replace('sep = "paragraph"', 'sep = "tab"'),
            "未知欄位": good.replace(
                'kind = "procedure"', 'kind = "procedure"\nextra = 1'
            ),
            "缺少欄位": '[[clause]]\nid = "a"\ntext = "A."\n',
            "頭尾不可有空白": '[[clause]]\nid = "a"\nkind = "procedure"\ntext = " A. "\n',
            "至少要有": "",
            "未知的頂層": "stray = 1\n" + good,
        }
        for expected, text in cases.items():
            with (
                self.subTest(expected=expected),
                self.assertRaisesRegex(contracts.ContractError, expected),
            ):
                parse_clauses(text)

    def test_addenda_reject_bad_entries(self) -> None:
        good = addendum("a", "end", "A.")
        for expected, text in {
            "重複": good + good,
            "缺少欄位": '[[addendum]]\nid = "a"\ntext = "A."\n',
            "頭尾不可有空白": addendum("a", "end", "A.\n\n"),
        }.items():
            with (
                self.subTest(expected=expected),
                self.assertRaisesRegex(contracts.ContractError, expected),
            ):
                parse_addenda(text)

    def test_missing_addenda_file_means_no_addenda(self) -> None:
        self.assertEqual(contracts.load_addenda(Path("/nonexistent/addenda.toml")), [])

    def test_frame_needs_exactly_one_placeholder_and_role_frame_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            frames = Path(tmp)
            self.assertIsNone(contracts.load_frame(frames, "scout"))
            (frames / "default.md").write_bytes(b"# Default\n\n{{role_body}}")
            (frames / "scout.md").write_bytes(b"# Scout\r\n\r\n{{role_body}}\n-- end\n")
            self.assertEqual(
                contracts.load_frame(frames, "executor"), "# Default\n\n{{role_body}}"
            )
            self.assertEqual(
                contracts.load_frame(frames, "scout"),
                "# Scout\r\n\r\n{{role_body}}\n-- end\n",
            )
            (frames / "default.md").write_bytes(b"no placeholder")
            with self.assertRaisesRegex(contracts.ContractError, "恰好有一個"):
                contracts.load_frame(frames, "executor")
            (frames / "default.md").write_bytes(b"{{role_body}}{{role_body}}")
            with self.assertRaisesRegex(contracts.ContractError, "恰好有一個"):
                contracts.load_frame(frames, "executor")

    def test_apply_frame(self) -> None:
        self.assertEqual(
            contracts.apply_frame("# T\n\n{{role_body}}", "body\n"), "# T\n\nbody\n"
        )
        self.assertEqual(contracts.apply_frame(None, "body\n"), "body\n")


class TempHost(unittest.TestCase):
    """temp 複本：core 與全部 hosts（不含 plugin、dist）；contract 換成假的以免依賴實際條款。"""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
        shutil.copytree(
            ROOT / "hosts",
            self.root / "hosts",
            ignore=shutil.ignore_patterns("plugin", "dist"),
        )
        shutil.rmtree(self.root / "core" / "contracts", ignore_errors=True)
        for host in HOSTS:
            shutil.rmtree(self.root / "hosts" / host / "addenda", ignore_errors=True)
            shutil.rmtree(self.root / "hosts" / host / "frames", ignore_errors=True)
            # 不管 repo 目前哪個 host 已切到 core，這裡都從 legacy 開始
            path = self.binding(host)
            path.write_text(
                path.read_text(encoding="utf-8").replace('\nrole_text = "core"\n', '\nrole_text = "legacy"\n', 1),
                encoding="utf-8",
                newline="\n",
            )

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def contract(self, role: str, *clauses: str) -> None:
        self.write(f"core/contracts/{role}.toml", "".join(clauses))

    def fake_contracts(self) -> None:
        for role in render.load_toml(self.root / "core" / "roles.toml")["roles"]:
            self.contract(
                role,
                clause("one", f"{role} one.", "space"),
                clause("two", f"{role} two."),
            )

    def binding(self, host: str) -> Path:
        return self.root / "hosts" / host / "binding.toml"

    def edit(self, path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def render(self, host: str) -> dict[str, bytes]:
        return render.RENDERERS[host](self.root)

    def assert_rejected(self, host: str, expected: str) -> None:
        result = run_render(host, self.root, "--check")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(expected, result.stderr)


class RoleTextSwitchTests(TempHost):
    def test_legacy_ignores_contracts_entirely(self) -> None:
        before = {h: self.render(h) for h in HOSTS}
        self.fake_contracts()
        self.write("hosts/claude/frames/default.md", "# frame\n\n{{role_body}}")
        self.write("hosts/claude/addenda/scout.toml", addendum("x", "end", "X"))
        self.assertEqual({h: self.render(h) for h in HOSTS}, before)

    def test_core_renders_frontmatter_frame_clauses_and_addenda(self) -> None:
        self.fake_contracts()
        self.edit(self.binding("claude"), 'role_text = "legacy"', 'role_text = "core"')
        self.write("hosts/claude/frames/default.md", "# Host preamble\n\n{{role_body}}")
        self.write("hosts/claude/frames/scout.md", "# Scout only\n\n{{role_body}}")
        self.write(
            "hosts/claude/addenda/scout.toml",
            addendum("x", "after:one", "Host sentence.", "space"),
        )
        files = self.render("claude")
        scout = files["agents/scout.md"].decode("utf-8")
        head, body = scout.split("\n---\n\n", 1)
        self.assertTrue(head.startswith("---\nname: scout\n"))
        self.assertEqual(body, "# Scout only\n\nscout one. Host sentence. scout two.\n")
        self.assertTrue(
            files["agents/executor.md"]
            .decode("utf-8")
            .endswith("\n---\n\n# Host preamble\n\nexecutor one. executor two.\n")
        )

    def test_frames_and_addenda_never_reach_dist(self) -> None:
        self.fake_contracts()
        for host in HOSTS:
            self.write(f"hosts/{host}/frames/default.md", "{{role_body}}")
            self.write(f"hosts/{host}/addenda/scout.toml", addendum("x", "end", "X"))
        for host in HOSTS:
            for rel in self.render(host):
                self.assertFalse(rel.startswith(("frames/", "addenda/")), (host, rel))

    def test_role_level_override_switches_one_role(self) -> None:
        self.fake_contracts()
        legacy = self.render("claude")
        self.edit(
            self.binding("claude"),
            "[roles.scout]\n",
            '[roles.scout]\nrole_text = "core"\n',
        )
        after = self.render("claude")
        changed = {rel for rel in legacy if legacy[rel] != after[rel]}
        self.assertEqual(changed, {"agents/scout.md"})
        self.assertTrue(
            after["agents/scout.md"].endswith(b"\n---\n\nscout one. scout two.\n")
        )

    def test_role_level_legacy_overrides_a_core_host(self) -> None:
        self.fake_contracts()
        legacy = self.render("claude")
        self.edit(self.binding("claude"), 'role_text = "legacy"', 'role_text = "core"')
        self.edit(
            self.binding("claude"),
            "[roles.scout]\n",
            '[roles.scout]\nrole_text = "legacy"\n',
        )
        after = self.render("claude")
        self.assertEqual(after["agents/scout.md"], legacy["agents/scout.md"])
        self.assertNotEqual(after["agents/executor.md"], legacy["agents/executor.md"])
        # host 專屬 role 一律 legacy
        self.assertEqual(after["agents/Explore.md"], legacy["agents/Explore.md"])

    def test_core_role_without_contract_is_rejected(self) -> None:
        self.edit(self.binding("claude"), 'role_text = "legacy"', 'role_text = "core"')
        self.assert_rejected("claude", "core/contracts/")

    def test_invalid_role_text_is_rejected(self) -> None:
        self.edit(self.binding("claude"), 'role_text = "legacy"', 'role_text = "both"')
        self.assert_rejected("claude", "role_text")

    def test_invalid_role_level_role_text_is_rejected(self) -> None:
        self.edit(
            self.binding("codex"),
            "[roles.scout]\n",
            '[roles.scout]\nrole_text = "both"\n',
        )
        self.assert_rejected("codex", "scout")

    def test_missing_role_text_is_rejected(self) -> None:
        self.edit(self.binding("grok"), 'role_text = "legacy"\n', "")
        self.assert_rejected("grok", "role_text")

    def test_host_specific_role_cannot_set_role_text(self) -> None:
        self.edit(
            self.binding("codex"),
            "[extra_roles.sol-executor]\n",
            '[extra_roles.sol-executor]\nrole_text = "core"\n',
        )
        self.assert_rejected("codex", "sol-executor")

    def test_contract_file_must_name_a_core_role(self) -> None:
        self.contract("ghost", clause("a", "A."))
        self.assert_rejected("claude", "ghost")

    def test_broken_contract_or_addendum_is_rejected_with_the_role_name(self) -> None:
        self.fake_contracts()
        self.edit(self.binding("claude"), 'role_text = "legacy"', 'role_text = "core"')
        self.write("hosts/claude/addenda/scout.toml", addendum("x", "after:nope", "X"))
        self.assert_rejected("claude", "scout")
        self.contract("executor", clause("a", "A.", kind="vibes"))
        self.assert_rejected("claude", "executor.toml")


class OmittedRoleTests(TempHost):
    def test_omitted_roles_are_not_rendered_in_core_mode(self) -> None:
        self.fake_contracts()
        self.edit(
            self.binding("opencode"), 'role_text = "legacy"', 'role_text = "core"'
        )
        files = self.render("opencode")
        omitted = render.load_toml(self.binding("opencode"))["omitted_roles"]
        self.assertEqual(sorted(omitted), ["mech-executor", "plan-verifier"])
        for role in omitted:
            self.assertNotIn(f"roles/{role}.md", files)
        self.assertEqual(files["roles/scout.md"], b"scout one. scout two.\n")


def rendered_text(host: str, name: str, files: dict[str, bytes]) -> str:
    rel = {
        "claude": f"agents/{name}.md",
        "codex": f"agents/{name}.toml",
        "agy": f"agents/{name}/agent.md",
        "grok": f"agents/{name}.md",
        "opencode": f"roles/{name}.md",
    }[host]
    return files[rel].decode("utf-8")


def unreplaced_texts(
    clauses: list[contracts.Clause], addenda: list[contracts.Addendum]
) -> list[str]:
    replaced = set(contracts.replaced_ids(addenda))
    return [c.text for c in clauses if c.id not in replaced]


def load_host_addenda(root: Path, host: str, role: str) -> list[contracts.Addendum]:
    return contracts.load_addenda(root / "hosts" / host / "addenda" / f"{role}.toml")


class VerbatimClauseTests(unittest.TestCase):
    """R5：core 模式的 role 逐字包含每個未被 replace 的條款。"""

    def test_every_core_role_contains_every_unreplaced_clause(self) -> None:
        core = render.load_core(ROOT)
        for host in HOSTS:
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            files = render.RENDERERS[host](ROOT)
            for name in render._bound_roles(core, binding):
                if render.role_text_mode(name, binding) != "core":
                    continue
                text = rendered_text(host, name, files)
                for needle in unreplaced_texts(
                    core["contracts"][name], load_host_addenda(ROOT, host, name)
                ):
                    with self.subTest(host=host, role=name, clause=needle[:40]):
                        self.assertIn(needle, text)

    def test_replace_lists_are_locked(self) -> None:
        actual: dict[str, dict[str, list[str]]] = {}
        for host in HOSTS:
            actual[host] = {}
            for path in sorted((ROOT / "hosts" / host / "addenda").glob("*.toml")):
                ids = contracts.replaced_ids(contracts.load_addenda(path))
                if ids:
                    actual[host][path.stem] = ids
        self.assertEqual(actual, EXPECTED_REPLACES)

    def test_switched_hosts_use_core_for_exactly_the_expected_roles(self) -> None:
        core = render.load_core(ROOT)
        for host, expected in EXPECTED_CORE_HOSTS.items():
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            actual = [
                n for n in render._bound_roles(core, binding)
                if render.role_text_mode(n, binding) == "core"
            ]
            with self.subTest(host=host):
                self.assertEqual(sorted(actual), sorted(expected))

    def test_host_addenda_are_locked(self) -> None:
        for host, expected in EXPECTED_ADDENDA.items():
            actual = {
                path.stem: [a.id for a in contracts.load_addenda(path)]
                for path in sorted((ROOT / "hosts" / host / "addenda").glob("*.toml"))
            }
            with self.subTest(host=host):
                self.assertEqual(actual, expected)

    def test_verifier_defaults_to_outcome_verification_and_unit_kinds_are_mapped(self) -> None:
        # 各 host 的 orchestrator 不一定在 brief 點名 contract 或 readiness_review；
        # 這兩條 addendum 避免 verifier 因 brief 格式不符而拒絕工作。
        core = render.load_core(ROOT)
        for host in EXPECTED_CORE_HOSTS:
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            files = render.RENDERERS[host](ROOT)
            roles = render._bound_roles(core, binding)
            with self.subTest(host=host, role="verifier"):
                text = rendered_text(host, "verifier", files)
                self.assertIn("treat it as `outcome_verification`", text)
            if "plan-verifier" in roles:
                with self.subTest(host=host, role="plan-verifier"):
                    text = rendered_text(host, "plan-verifier", files)
                    self.assertIn("treat a `program envelope` as a `readiness_review` envelope", text)

    def test_claude_explore_keeps_its_legacy_text(self) -> None:
        # Decision 8：host 專屬 role 維持 host 自己的文字
        binding = render.load_toml(ROOT / "hosts" / "claude" / "binding.toml")
        self.assertNotIn("role_text", binding["extra_roles"]["Explore"])
        legacy = (ROOT / "hosts" / "claude" / "src" / "agents" / "Explore.md").read_bytes()
        rendered = render.RENDERERS["claude"](ROOT)["agents/Explore.md"]
        self.assertTrue(rendered.endswith(b"\n---\n\n" + legacy))

    def test_addenda_files_belong_to_core_roles(self) -> None:
        roles = render.load_core(ROOT)["roles"]
        for host in HOSTS:
            for path in (ROOT / "hosts" / host / "addenda").glob("*.toml"):
                self.assertIn(path.stem, roles, path)

    def test_check_logic_excludes_only_replaced_clauses(self) -> None:
        clauses = parse_clauses(ABC)
        addenda = parse_addenda(addendum("r", "replace:b", "B host."))
        text = contracts.compose(clauses, addenda)
        needles = unreplaced_texts(clauses, addenda)
        self.assertEqual(needles, ["A one.", "C three.", "D four."])
        for needle in needles:
            self.assertIn(needle, text)
        self.assertNotIn("B two.", text)
        # 條款被悄悄改寫時，逐字檢查會抓到
        self.assertNotIn(needles[0], text.replace("A one.", "A  one."))


class CoreContractTests(unittest.TestCase):
    """R1：repo 內的 core/contracts 一律 host 中立。"""

    def contract_files(self) -> list[Path]:
        return sorted((ROOT / "core" / "contracts").glob("*.toml"))

    def test_contracts_are_valid_and_name_core_roles(self) -> None:
        roles = render.load_toml(ROOT / "core" / "roles.toml")["roles"]
        for path in self.contract_files():
            self.assertIn(path.stem, roles, path)
            self.assertTrue(contracts.load_contract(path))

    def test_contract_text_has_no_host_specific_names(self) -> None:
        for path in self.contract_files():
            for item in contracts.load_contract(path):
                lowered = item.text.lower()
                for term in HOST_SPECIFIC_TERMS:
                    pattern = (
                        re.escape(term)
                        if not term[0].isalnum() or not term[-1].isalnum()
                        else rf"\b{re.escape(term)}\b"
                    )
                    with self.subTest(file=path.name, clause=item.id, term=term):
                        self.assertIsNone(re.search(pattern, lowered), item.text)


CODEX_CORE_ROLES = (
    "scout",
    "mech-executor",
    "executor",
    "plan-verifier",
    "verifier",
    "security-reviewer",
    "security-executor",
)
# Codex 專屬內容（模型、reasoning effort、semantic_adjudication）只能放在這些 addenda；新增要同時改這裡。
CODEX_ADDENDA = {
    "mech-executor": ["model-binding"],
    "plan-verifier": ["semantic-adjudication"],
    "security-executor": ["reasoning-effort"],
}


class CodexCutTests(unittest.TestCase):
    """2b-1：core 條款加 Codex addenda 逐位元組拼回 Codex 1.8.1 原文，Codex 因此能切到 core。"""

    def test_codex_is_core_for_the_seven_shared_roles_only(self) -> None:
        binding = render.load_toml(ROOT / "hosts" / "codex" / "binding.toml")
        self.assertEqual(binding["role_text"], "core")
        self.assertEqual(sorted(binding["roles"]), sorted(CODEX_CORE_ROLES))
        for name in CODEX_CORE_ROLES:
            self.assertEqual(render.role_text_mode(name, binding), "core", name)
        self.assertNotIn("role_text", binding["extra_roles"]["sol-executor"])

    def test_core_and_addenda_reassemble_the_legacy_text(self) -> None:
        for name in CODEX_CORE_ROLES:
            clauses = contracts.load_contract(ROOT / "core" / "contracts" / f"{name}.toml")
            addenda = load_host_addenda(ROOT, "codex", name)
            legacy = (ROOT / "hosts" / "codex" / "src" / "agents" / f"{name}.md").read_bytes()
            with self.subTest(role=name):
                self.assertGreater(len(clauses), 1)
                self.assertEqual(contracts.compose(clauses, addenda).encode("utf-8"), legacy)

    def test_codex_specific_content_lives_only_in_the_expected_addenda(self) -> None:
        actual = {
            path.stem: [a.id for a in contracts.load_addenda(path)]
            for path in sorted((ROOT / "hosts" / "codex" / "addenda").glob("*.toml"))
        }
        self.assertEqual(actual, CODEX_ADDENDA)

    def test_sol_executor_keeps_its_legacy_text(self) -> None:
        legacy = (ROOT / "hosts" / "codex" / "src" / "agents" / "sol-executor.md").read_text(encoding="utf-8")
        self.assertIn(legacy, render.RENDERERS["codex"](ROOT)["agents/sol-executor.toml"].decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
