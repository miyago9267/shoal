"""core/policy 機制：條款格式、placeholder、omit、required、policy_text 開關與 preview（core-policy P1）。

機制測試用 temp 目錄的假條款與 repo 的 Claude 設定副本；鎖定測試（EXPECTED_*）直接檢查 repo 目前的
core/policy 與各 host 的 binding / policy-addenda，變更要同時改這裡。P1 時所有 host 都是 legacy。
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

from render_helpers import ROOT, render, run_render
from test_role_contracts import (
    HOST_SPECIFIC_TERMS,
    addendum,
    clause,
    parse_addenda,
    parse_clauses,
)

import contracts  # noqa: E402  (render_helpers 已把 tools/ 放進 sys.path)

HOSTS = ("claude", "codex", "agy", "grok", "opencode")

# 每個 host 的 policy_text；切換是逐 host 的 migration（core-policy P2、P3），改這裡要同時有核准。
EXPECTED_POLICY_TEXT = {host: "core" if host == "claude" else "legacy" for host in HOSTS}
# 每個 host 目前省略（binding [policy].omit）與取代（policy-addenda 的 replace:）的條款；
# 全部 legacy，所以都是空。新增 omit 或 replace 要同時改這裡（P3、P3a）。
EXPECTED_POLICY_OMITS: dict[str, list[str]] = {host: [] for host in HOSTS}
EXPECTED_POLICY_REPLACES: dict[str, dict[str, list[str]]] = {host: {} for host in HOSTS}
# host 專屬的 policy addenda 目前沒有（Claude 是 canonical，其他 host 還沒切）。
EXPECTED_POLICY_ADDENDA: dict[str, dict[str, list[str]]] = {host: {} for host in HOSTS}

# required 條款（不可 omit、不可 replace）；新增或移除要改這裡。
EXPECTED_REQUIRED = {
    # named-role 豁免
    "bootstrap-named-roles",
    "intro-named-roles",
    # risk trigger 與核准
    "bootstrap-risk",
    "risk-triggers",
    "risk-review-mandatory",
    "approval-gate",
    # security-reviewer -> 核准 -> security-executor
    "bootstrap-security",
    "security-sensitive-routing",
    "security-reviewer-first",
    "security-executor-after-approval",
    "security-no-preapproval-write",
    # destructive / external 確認與 credentials（AUTO 的權限上限、gate 優先、自由文字不算核准）
    "auto-limits",
    "material-gates-first",
    "explicit-approval-only",
    # extension 規則不得擴大任何權限
    "ext-no-authority",
}
EXPECTED_DOCS = ("bootstrap", "extensions", "orchestration", "skill")

# Claude 的 core 輸出與 legacy 原文逐字（忽略空白）相同，只有這些因禁字詞而改寫的地方（P1 對照表有說明）。
KNOWN_WORDING_CHANGES = [
    ("workflow", "procedure"),
    ("workflow", "policy"),
]


def policy_doc(text: str) -> list[contracts.Clause]:
    return contracts.parse_contract(
        tomllib.loads(text), kinds=contracts.POLICY_KINDS, allow_required=True
    )


def normalized(text: str) -> str:
    return " ".join(text.split())


class PolicyContractFormatTests(unittest.TestCase):
    def test_policy_clauses_accept_required_and_policy_kinds(self) -> None:
        text = (
            "[[clause]]\nid = \"a\"\nkind = \"gate\"\nrequired = true\ntext = '''\nA.'''\n\n"
            "[[clause]]\nid = \"b\"\nkind = \"heading\"\ntext = '''\n## B'''\n"
        )
        clauses = policy_doc(text)
        self.assertEqual([c.required for c in clauses], [True, False])

    def test_role_contracts_do_not_accept_required(self) -> None:
        text = clause("a", "A.") + "\n"
        with self.assertRaisesRegex(contracts.ContractError, "未知欄位 required"):
            contracts.parse_contract(
                tomllib.loads(
                    text.replace(
                        'kind = "procedure"', 'kind = "procedure"\nrequired = true'
                    )
                )
            )

    def test_required_must_be_a_boolean(self) -> None:
        text = "[[clause]]\nid = \"a\"\nkind = \"gate\"\nrequired = \"yes\"\ntext = '''\nA.'''\n"
        with self.assertRaisesRegex(
            contracts.ContractError, "required 必須是 true 或 false"
        ):
            policy_doc(text)

    def test_policy_kind_vocabulary_is_separate_from_role_kinds(self) -> None:
        with self.assertRaisesRegex(contracts.ContractError, "kind 必須是"):
            policy_doc(
                "[[clause]]\nid = \"a\"\nkind = \"identity\"\ntext = '''\nA.'''\n"
            )
        with self.assertRaisesRegex(contracts.ContractError, "kind 必須是"):
            parse_clauses(clause("a", "A.", kind="gate"))


class PlaceholderTests(unittest.TestCase):
    def test_substitution_is_single_pass(self) -> None:
        # 值裡的 "{" 與後面的 "{b}}" 拼成 "{{b}}"，單次代入不會再掃描它。
        self.assertEqual(
            contracts.substitute("{{a}}{b}}", {"a": "{", "b": "B"}, "t"), "{{b}}"
        )

    def test_unknown_key_is_an_error(self) -> None:
        with self.assertRaisesRegex(
            contracts.ContractError, "未知的 placeholder {{nope}}"
        ):
            contracts.substitute("use {{nope}}", {"a": "x"}, "t")

    def test_malformed_braces_are_an_error(self) -> None:
        for text in ("{{ a }}", "{{A}}", "{{a}", "oops {{", "{{a-b}}"):
            with self.subTest(text=text), self.assertRaises(contracts.ContractError):
                contracts.substitute(text, {"a": "x"}, "t")

    def test_values_may_not_contain_braces_or_newlines(self) -> None:
        for value in ("a {{b}} c", "{{", "two\nlines", "cr\rhere", ""):
            with self.subTest(value=value), self.assertRaises(contracts.ContractError):
                contracts.check_placeholder_values("p", {"k": value})
        with self.assertRaises(contracts.ContractError):
            contracts.check_placeholder_values("p", {"Bad-Key": "x"})
        self.assertEqual(
            contracts.check_placeholder_values("p", {"k": "a `b` c"}), {"k": "a `b` c"}
        )

    def test_addenda_are_substituted_too(self) -> None:
        clauses = parse_clauses(clause("a", "Call {{tool}}."))
        addenda = parse_addenda(addendum("h", "end", "Host uses {{tool}}."))
        text = contracts.compose_policy(
            "doc", clauses, addenda, set(), {"tool": "Agent"}
        )
        self.assertEqual(text, "Call Agent.\n\nHost uses Agent.\n")


class OmitAndRequiredTests(unittest.TestCase):
    def doc(self) -> list[contracts.Clause]:
        return policy_doc(
            "[[clause]]\nid = \"a\"\nkind = \"gate\"\ntext = '''\nA.'''\n\n"
            "[[clause]]\nid = \"b\"\nkind = \"gate\"\ntext = '''\nB.'''\n\n"
            "[[clause]]\nid = \"c\"\nkind = \"gate\"\nrequired = true\ntext = '''\nC.'''\n"
        )

    def test_omit_removes_exactly_that_clause(self) -> None:
        self.assertEqual(
            contracts.compose_policy("d", self.doc(), [], {"b"}, {}), "A.\n\nC.\n"
        )

    def test_required_clause_cannot_be_omitted(self) -> None:
        with self.assertRaisesRegex(
            contracts.ContractError, "required 條款不可 omit：c"
        ):
            contracts.compose_policy("d", self.doc(), [], {"c"}, {})

    def test_required_clause_cannot_be_replaced(self) -> None:
        addenda = parse_addenda(addendum("x", "replace:c", "Host C."))
        with self.assertRaisesRegex(
            contracts.ContractError, "不可 replace required 條款 c"
        ):
            contracts.compose_policy("d", self.doc(), addenda, set(), {})

    def test_non_required_clause_can_be_replaced(self) -> None:
        addenda = parse_addenda(addendum("x", "replace:b", "Host B."))
        self.assertEqual(
            contracts.compose_policy("d", self.doc(), addenda, set(), {}),
            "A.\n\nHost B.\n\nC.\n",
        )

    def test_addendum_cannot_anchor_to_an_omitted_clause(self) -> None:
        addenda = parse_addenda(addendum("x", "after:b", "Host."))
        with self.assertRaisesRegex(contracts.ContractError, "指向被 omit 的條款 b"):
            contracts.compose_policy("d", self.doc(), addenda, {"b"}, {})

    def test_document_with_every_clause_omitted_is_skipped(self) -> None:
        clauses = policy_doc(
            "[[clause]]\nid = \"a\"\nkind = \"gate\"\ntext = '''\nA.'''\n"
        )
        self.assertIsNone(contracts.compose_policy("d", clauses, [], {"a"}, {}))


class RepoPolicyTests(unittest.TestCase):
    """repo 內 core/policy 與各 host 設定的鎖定檢查。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.core = render.load_core(ROOT)
        cls.policy = cls.core["policy"]
        cls.bindings = {
            h: render.load_toml(ROOT / "hosts" / h / "binding.toml") for h in HOSTS
        }

    def clauses(self) -> list[contracts.Clause]:
        return [c for doc in self.policy["docs"].values() for c in doc]

    def test_documents_are_the_expected_set(self) -> None:
        self.assertEqual(tuple(sorted(self.policy["docs"])), EXPECTED_DOCS)

    def test_clause_ids_are_unique_across_documents(self) -> None:
        ids = [c.id for c in self.clauses()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_required_set_is_locked(self) -> None:
        self.assertEqual(
            {c.id for c in self.clauses() if c.required}, EXPECTED_REQUIRED
        )

    def test_policy_text_is_locked_per_host(self) -> None:
        actual = {h: render.policy_text_mode(b) for h, b in self.bindings.items()}
        self.assertEqual(actual, EXPECTED_POLICY_TEXT)
        for host, binding in self.bindings.items():
            self.assertIn("policy", binding, host)

    def test_omit_lists_are_locked_and_every_omit_has_a_reason(self) -> None:
        for host, binding in self.bindings.items():
            for item in binding["policy"].get("omit", []):
                self.assertTrue(item["reason"].strip(), f"{host}: {item['id']}")
            self.assertEqual(
                sorted(render.policy_omits(binding)), EXPECTED_POLICY_OMITS[host], host
            )

    def test_replace_lists_and_addenda_are_locked(self) -> None:
        for host in HOSTS:
            replaces: dict[str, list[str]] = {}
            addenda: dict[str, list[str]] = {}
            for path in sorted(
                (ROOT / "hosts" / host / "policy-addenda").glob("*.toml")
            ):
                loaded = contracts.load_addenda(path)
                self.assertIn(path.stem, self.policy["docs"], path)
                addenda[path.stem] = [a.id for a in loaded]
                if contracts.replaced_ids(loaded):
                    replaces[path.stem] = contracts.replaced_ids(loaded)
            with self.subTest(host=host):
                self.assertEqual(replaces, EXPECTED_POLICY_REPLACES[host])
                self.assertEqual(addenda, EXPECTED_POLICY_ADDENDA[host])

    def test_core_clauses_have_no_host_specific_names(self) -> None:
        for path in sorted((ROOT / "core" / "policy").glob("*.toml")):
            if path.name == "placeholders.toml":
                continue
            for item in contracts.load_policy_contract(path):
                lowered = item.text.lower()
                for term in HOST_SPECIFIC_TERMS:
                    pattern = (
                        re.escape(term)
                        if not term[0].isalnum() or not term[-1].isalnum()
                        else rf"\b{re.escape(term)}\b"
                    )
                    with self.subTest(file=path.name, clause=item.id, term=term):
                        self.assertIsNone(re.search(pattern, lowered), item.text)

    def test_core_clauses_do_not_hardcode_dispatch_vocabulary(self) -> None:
        # P2：派工工具、問答工具、shell 等名稱只能經 placeholder 進來。
        for item in self.clauses():
            for word in (
                "Agent",
                "AskUserQuestion",
                "Bash",
                "NotebookEdit",
                "run_in_background",
                "/goal",
            ):
                with self.subTest(clause=item.id, word=word):
                    self.assertNotRegex(
                        item.text, rf"(?<![\w`]){re.escape(word)}(?!\w)"
                    )

    def test_every_placeholder_in_the_vocabulary_is_used(self) -> None:
        used: set[str] = set()
        for item in self.clauses():
            used |= contracts.placeholder_keys(item.text)
        self.assertEqual(used, set(self.policy["placeholders"]))

    def test_claude_binding_covers_vocabulary_and_documents(self) -> None:
        policy = self.bindings["claude"]["policy"]
        self.assertEqual(set(policy["placeholders"]), set(self.policy["placeholders"]))
        self.assertEqual(set(policy["documents"]), set(self.policy["docs"]))
        contracts.check_placeholder_values("claude", policy["placeholders"])

    def test_claude_core_preview_has_no_leftover_braces(self) -> None:
        for rel, data in render.policy_files(
            self.core, self.bindings["claude"], ROOT / "hosts" / "claude"
        ).items():
            self.assertNotIn("{{", data.decode("utf-8"), rel)

    def test_claude_core_preview_equals_legacy_apart_from_known_wording(self) -> None:
        """P1 的行為等價檢查：忽略空白後逐詞相同，只允許 KNOWN_WORDING_CHANGES。"""
        files = render.policy_files(
            self.core, self.bindings["claude"], ROOT / "hosts" / "claude"
        )
        self.assertEqual(
            sorted(files),
            sorted(self.bindings["claude"]["policy"]["documents"].values()),
        )
        changes: list[tuple[str, str]] = []
        for rel, data in files.items():
            legacy = (
                (ROOT / "hosts" / "claude" / "src" / rel)
                .read_text(encoding="utf-8")
                .split()
            )
            core = data.decode("utf-8").split()
            matcher = difflib.SequenceMatcher(None, legacy, core, autojunk=False)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag != "equal":
                    changes.append((" ".join(legacy[i1:i2]), " ".join(core[j1:j2])))
        self.assertEqual(changes, KNOWN_WORDING_CHANGES)

    def test_claude_core_preview_keeps_lock_required_fragments(self) -> None:
        """Decision 4：core 條款保留各 lock surface 的 required_fragments 原文。"""
        lock = json.loads(
            (ROOT / "docs/specs/prompt-document-lock/LOCK.json").read_text(
                encoding="utf-8"
            )
        )
        surfaces = {s["path"]: s for s in lock["surfaces"]}
        files = render.policy_files(
            self.core, self.bindings["claude"], ROOT / "hosts" / "claude"
        )
        checked = 0
        for rel, data in files.items():
            surface = surfaces.get(f"hosts/claude/dist/{rel}")
            if surface is None:  # bootstrap 不是 lock surface
                continue
            content = normalized(data.decode("utf-8")).casefold()
            for fragment in surface["required_fragments"]:
                checked += 1
                with self.subTest(surface=surface["id"], fragment=fragment[:40]):
                    self.assertIn(normalized(fragment).casefold(), content)
        self.assertEqual(checked, 12)


class PolicyRenderCase(unittest.TestCase):
    """在 temp 目錄的 Claude 副本上測 policy_text、omit、preview 與錯誤。"""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
        shutil.copytree(
            ROOT / "hosts" / "claude",
            self.root / "hosts" / "claude",
            ignore=shutil.ignore_patterns("plugin"),
        )
        self.binding = self.root / "hosts" / "claude" / "binding.toml"
        self.dist = self.root / "hosts" / "claude" / "dist"
        # repo 的 Claude 已是 core；這組測試以 legacy 為基準，副本改回 legacy 並重寫 dist。
        self.edit(self.binding, 'policy_text = "core"', 'policy_text = "legacy"')
        self.assertEqual(self.render("--write").returncode, 0)

    def edit(self, path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def core_mode(self) -> None:
        self.edit(self.binding, 'policy_text = "legacy"', 'policy_text = "core"')

    def render(self, *flags: str):
        return run_render("claude", self.root, *flags)

    def rejected(self, *flags: str, expected: str) -> None:
        result = self.render(*flags)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(expected, result.stderr)

    # --- legacy 與 core 開關（P4） ---
    def test_legacy_is_byte_identical_to_dist(self) -> None:
        self.assertEqual(self.render("--check").returncode, 0)

    def test_core_replaces_exactly_the_four_policy_documents(self) -> None:
        legacy = render.render_host(self.root, "claude")
        self.core_mode()
        core = render.render_host(self.root, "claude")
        documents = set(render.load_toml(self.binding)["policy"]["documents"].values())
        self.assertEqual(sorted(core), sorted(legacy))
        self.assertTrue(all(core[p] == legacy[p] for p in core if p not in documents))
        self.assertNotEqual(
            core["claude-md.bootstrap.md"], legacy["claude-md.bootstrap.md"]
        )

    def test_core_check_fails_until_dist_is_rewritten(self) -> None:
        self.core_mode()
        self.assertEqual(self.render("--check").returncode, 1)
        self.assertEqual(self.render("--write").returncode, 0)
        self.assertEqual(self.render("--check").returncode, 0)

    def test_core_is_rejected_for_hosts_that_are_not_ready(self) -> None:
        for host in ("codex", "agy", "grok", "opencode"):
            with self.subTest(host=host):
                core = render.load_core(ROOT)
                binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
                binding["policy"]["policy_text"] = "core"
                with self.assertRaisesRegex(render.RenderError, "尚未支援這個 host"):
                    render.validate_catalog(core, binding)

    def test_policy_text_must_be_core_or_legacy(self) -> None:
        self.edit(self.binding, 'policy_text = "legacy"', 'policy_text = "both"')
        self.rejected("--check", expected="policy_text")

    def test_unknown_policy_field_is_rejected(self) -> None:
        self.edit(self.binding, "omit = []", "omit = []\nextra = 1")
        self.rejected("--check", expected="未知欄位 extra")

    # --- omit（P3） ---
    def omit(self, *items: tuple[str, str]) -> None:
        body = ", ".join(f'{{ id = "{i}", reason = "{r}" }}' for i, r in items)
        self.edit(self.binding, "omit = []", f"omit = [{body}]")

    def test_omit_requires_a_reason(self) -> None:
        self.edit(self.binding, "omit = []", 'omit = [{ id = "baton-dispatch" }]')
        self.rejected("--check", expected="必須恰好有 id 與 reason")
        self.edit(
            self.binding,
            'omit = [{ id = "baton-dispatch" }]',
            'omit = [{ id = "baton-dispatch", reason = "  " }]',
        )
        self.rejected("--check", expected="reason 必須是非空字串")

    def test_omit_of_unknown_or_duplicate_clause_is_rejected(self) -> None:
        self.omit(("no-such-clause", "x"))
        self.rejected("--check", expected="沒有條款 no-such-clause")

    def test_omit_of_required_clause_is_rejected(self) -> None:
        for cid in sorted(EXPECTED_REQUIRED):
            with self.subTest(clause=cid):
                text = self.binding.read_text(encoding="utf-8")
                self.omit((cid, "not allowed"))
                self.rejected("--check", expected=f"required 條款 {cid} 不可 omit")
                self.binding.write_text(text, encoding="utf-8", newline="\n")

    def test_omitted_clause_disappears_from_core_output_and_explain(self) -> None:
        self.core_mode()
        self.omit(("baton-dispatch", "this host has no baton skill"))
        files = render.render_host(self.root, "claude")
        policy = files[
            "skills/pilotfish-orchestration/references/orchestration-policy.md"
        ].decode("utf-8")
        self.assertNotIn("baton-dispatch", policy)
        self.assertNotIn("inspect available skills", policy)
        self.assertIn("Interaction shape precedes", policy)
        explained = self.render("--explain-policy")
        self.assertEqual(explained.returncode, 0, explained.stderr)
        self.assertIn(
            "baton-dispatch [routing] omitted：this host has no baton skill",
            explained.stdout,
        )
        self.assertIn("risk-triggers [gate, required] core", explained.stdout)

    # --- placeholder（P2） ---
    def test_missing_placeholder_value_is_rejected_in_core(self) -> None:
        self.core_mode()
        self.edit(self.binding, 'shell_tool = "Bash"\n', "")
        self.rejected("--check", expected="[policy.placeholders] 缺少 shell_tool")

    def test_unknown_placeholder_key_in_binding_is_rejected(self) -> None:
        self.edit(
            self.binding,
            'shell_tool = "Bash"\n',
            'shell_tool = "Bash"\nmystery = "x"\n',
        )
        self.rejected("--check", expected="未知的 key mystery")

    def test_placeholder_value_with_braces_or_newline_is_rejected(self) -> None:
        self.edit(
            self.binding, 'shell_tool = "Bash"', 'shell_tool = "{{dispatch_tool}}"'
        )
        self.rejected("--check", expected="不可含")
        self.edit(
            self.binding, 'shell_tool = "{{dispatch_tool}}"', 'shell_tool = "a\\nb"'
        )
        self.rejected("--check", expected="不可含")

    def test_unknown_placeholder_in_a_core_clause_is_rejected(self) -> None:
        self.edit(
            self.root / "core" / "policy" / "bootstrap.toml",
            "{{named_roles}}",
            "{{unlisted}}",
        )
        self.rejected(
            "--check",
            expected="placeholder unlisted 不在 core/policy/placeholders.toml",
        )

    # --- addenda 與 frame ---
    def addenda(self, doc: str, text: str) -> None:
        folder = self.root / "hosts" / "claude" / "policy-addenda"
        folder.mkdir(exist_ok=True)
        (folder / f"{doc}.toml").write_text(text, encoding="utf-8", newline="\n")

    def test_addendum_can_replace_a_non_required_clause(self) -> None:
        self.core_mode()
        self.addenda(
            "orchestration",
            addendum("my-baton", "replace:baton-dispatch", "- Host baton rule."),
        )
        text = render.render_host(self.root, "claude")[
            "skills/pilotfish-orchestration/references/orchestration-policy.md"
        ].decode("utf-8")
        self.assertIn("- Host baton rule.", text)
        self.assertNotIn("baton-dispatch", text)

    def test_addendum_cannot_replace_a_required_clause(self) -> None:
        self.addenda(
            "orchestration", addendum("bad", "replace:risk-triggers", "- Weaker.")
        )
        self.rejected(
            "--policy-preview",
            str(self.root / "out"),
            expected="不可 replace required 條款 risk-triggers",
        )
        self.assertFalse((self.root / "out").exists())

    def test_addendum_file_must_name_a_core_document(self) -> None:
        self.addenda("nonsense", addendum("x", "end", "X."))
        self.rejected(
            "--policy-preview",
            str(self.root / "out"),
            expected="core/policy 沒有對應的文件",
        )

    def test_addendum_may_add_host_text_after_a_clause(self) -> None:
        self.core_mode()
        self.addenda("bootstrap", addendum("extra", "end", "- Host-only rule."))
        text = render.render_host(self.root, "claude")["claude-md.bootstrap.md"].decode(
            "utf-8"
        )
        self.assertTrue(text.endswith("- Host-only rule.\n"))

    def test_document_with_every_clause_omitted_is_not_emitted(self) -> None:
        (self.root / "core" / "policy" / "extra.toml").write_text(
            "[[clause]]\nid = \"extra-note\"\nkind = \"extension\"\ntext = '''\nExtra.'''\n",
            encoding="utf-8",
        )
        self.edit(
            self.binding,
            "[policy.documents]\n",
            '[policy.documents]\nextra = "extra.md"\n',
        )
        self.core_mode()
        self.assertIn("extra.md", render.render_host(self.root, "claude"))
        self.omit(("extra-note", "not needed"))
        files = render.render_host(self.root, "claude")
        self.assertNotIn("extra.md", files)
        self.assertEqual(len(files), len(render.render_host(ROOT, "claude")))

    # --- preview ---
    def test_preview_writes_core_documents_without_touching_dist(self) -> None:
        before = {p: p.read_bytes() for p in self.dist.rglob("*") if p.is_file()}
        out = self.root / "preview"
        result = self.render("--policy-preview", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        written = sorted(
            p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()
        )
        self.assertEqual(
            written,
            sorted(render.load_toml(self.binding)["policy"]["documents"].values()),
        )
        self.assertEqual(
            {p: p.read_bytes() for p in self.dist.rglob("*") if p.is_file()}, before
        )
        self.assertEqual(
            render.load_toml(self.binding)["policy"]["policy_text"], "legacy"
        )

    def test_preview_does_not_delete_other_files_in_the_target(self) -> None:
        out = self.root / "preview"
        out.mkdir()
        (out / "keep.txt").write_text("keep", encoding="utf-8")
        self.assertEqual(self.render("--policy-preview", str(out)).returncode, 0)
        self.assertTrue((out / "keep.txt").exists())

    def test_preview_refuses_a_directory_inside_dist(self) -> None:
        self.rejected("--policy-preview", str(self.dist / "agents"), expected="不可在")
        self.rejected("--policy-preview", str(self.dist), expected="不可在")

    def test_preview_is_rejected_for_a_host_without_documents(self) -> None:
        shutil.copytree(ROOT / "hosts" / "codex", self.root / "hosts" / "codex")
        result = run_render(
            "codex", self.root, "--policy-preview", str(self.root / "out")
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("[policy.documents] 缺少文件", result.stderr)


if __name__ == "__main__":
    unittest.main()
