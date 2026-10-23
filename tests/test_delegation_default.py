"""delegation-default（S3、S4、S5）：effort 與類型標籤條款、watcher / researcher、補漏模式、預設派工條款。

文字本身的來源是 docs/specs/delegation-default/CLAUSES.md；這裡鎖定結構（條款在 Claude policy 輸出裡、
核心條款不寫 model 名稱、其他 host 只接 role 而不接派工條款），不重複整段文字。
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import render  # noqa: E402

NEW_ROLES = ("watcher", "researcher")
OTHER_HOSTS = ("codex", "grok", "agy", "opencode")
MODEL_NAMES = re.compile(r"\b(haiku|sonnet|opus|fable|gpt-\S+|gemini|flash|luna|grok-\S+)\b", re.IGNORECASE)


def frontmatter(data: bytes) -> dict[str, str]:
    head = data.decode("utf-8").split("\n---\n", 1)[0].removeprefix("---\n")
    return dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)


def clauses(doc: str) -> dict[str, "render.contracts.Clause"]:
    core = render.load_core(ROOT)
    return {c.id: c for c in core["policy"]["docs"][doc]}


class NewRoleRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = render.RENDERERS["claude"](ROOT)

    def test_watcher_is_pinned_haiku_low_and_cannot_edit(self) -> None:
        front = frontmatter(self.files["agents/watcher.md"])
        self.assertEqual((front["model"], front["effort"]), ("haiku", "low"))
        self.assertNotIn("tools", front)
        denied = front["disallowedTools"].split(", ")
        for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit", "Agent", "Workflow"):
            self.assertIn(tool, denied)
        self.assertNotIn("Bash", denied)

    def test_researcher_is_opus_high_read_only_with_web(self) -> None:
        front = frontmatter(self.files["agents/researcher.md"])
        self.assertEqual((front["model"], front["effort"]), ("opus", "high"))
        self.assertEqual(front["tools"], "Read, Glob, Grep, WebSearch, WebFetch")

    def test_new_roles_are_core_roles_with_the_specified_access(self) -> None:
        roles = render.load_core(ROOT)["roles"]
        self.assertEqual(
            roles["watcher"], {"access": "verify", "tier": "fast", "security": False}
        )
        self.assertEqual(
            roles["researcher"],
            {"access": "read-only", "tier": "strong", "security": False, "capabilities": ["web"]},
        )

    def test_claude_named_roles_include_the_new_roles(self) -> None:
        binding = render.load_toml(ROOT / "hosts" / "claude" / "binding.toml")
        listed = binding["policy"]["placeholders"]["named_roles"]
        for name in NEW_ROLES:
            self.assertIn(f"`{name}`", listed)
        self.assertNotIn("`Explore`", listed)


class OtherHostsRoleTests(unittest.TestCase):
    """D17：Codex、Grok、agy、OpenCode 也綁定 watcher 與 researcher，但只接 role，不接派工條款與 guard 規則。"""

    # host -> {role: dist 內的檔案}
    PATHS = {
        "codex": {"watcher": "agents/watcher.toml", "researcher": "agents/researcher.toml"},
        "grok": {"watcher": "agents/watcher.md", "researcher": "agents/researcher.md"},
        "agy": {"watcher": "agents/watcher/agent.md", "researcher": "agents/researcher/agent.md"},
        "opencode": {"watcher": "roles/watcher.md", "researcher": "roles/researcher.md"},
    }
    # Codex 的 policy 有一張 role 表（test_policy 要求列出每個安裝的 role）。
    ROLE_ROW = re.compile(rb"^\| `(watcher|researcher)` \|.*\n", re.MULTILINE)

    @classmethod
    def setUpClass(cls) -> None:
        cls.files = {host: render.RENDERERS[host](ROOT) for host in cls.PATHS}

    def text(self, host: str, role: str) -> str:
        return self.files[host][self.PATHS[host][role]].decode("utf-8")

    def test_every_host_binds_the_new_roles(self) -> None:
        for host in OTHER_HOSTS:
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            with self.subTest(host=host):
                self.assertTrue(set(NEW_ROLES) <= set(binding["roles"]))
                self.assertFalse(set(NEW_ROLES) & set(binding.get("omitted_roles", [])))
        opencode = render.load_toml(ROOT / "hosts" / "opencode" / "binding.toml")
        self.assertEqual(opencode["omitted_roles"], [])

    def test_every_host_renders_both_roles_with_the_core_contract(self) -> None:
        core = render.load_core(ROOT)["contracts"]
        for host in OTHER_HOSTS:
            for role in NEW_ROLES:
                text = self.text(host, role)
                with self.subTest(host=host, role=role):
                    self.assertIn(f"You are a {role} and a leaf role that cannot delegate.", text)
                    self.assertIn("Never spawn further subagents", text)
                    self.assertIn("`status: ok | failed | insufficient`", text)
                    # shoal 只提供 role：Claude 的工具用語與 policy 條款不進其他 host 的 role
                    self.assertNotIn("Claude Code", text)
                    self.assertNotIn("run_in_background", text)
                    self.assertEqual(len([c for c in core[role] if c.text not in text]), 0)

    def test_codex_watcher_runs_commands_and_researcher_is_read_only_with_web(self) -> None:
        watcher = tomllib.loads(self.text("codex", "watcher"))
        researcher = tomllib.loads(self.text("codex", "researcher"))
        # Codex 的 verify 等級沒有比 workspace-write 更窄的 sandbox（verifier 同）；不改檔由 contract 條款約束。
        self.assertEqual(watcher["sandbox_mode"], "workspace-write")
        self.assertNotIn("web_search", watcher)
        self.assertIn("Never edit files", watcher["developer_instructions"])
        self.assertEqual((researcher["sandbox_mode"], researcher["web_search"]), ("read-only", "live"))
        self.assertEqual((watcher["model_reasoning_effort"], researcher["model_reasoning_effort"]), ("low", "high"))
        self.assertEqual((watcher["model"], researcher["model"]), ("gpt-6-luna", "gpt-6-sol"))

    def test_grok_capability_modes(self) -> None:
        roles = {r: tomllib.loads(self.files["grok"][f"roles/{r}.toml"].decode("utf-8")) for r in NEW_ROLES}
        self.assertEqual(roles["watcher"]["default_capability_mode"], "execute")  # 可跑指令、不可改檔
        self.assertEqual(roles["researcher"]["default_capability_mode"], "read-only")
        self.assertEqual((roles["watcher"]["reasoning_effort"], roles["researcher"]["reasoning_effort"]), ("low", "high"))
        for role in NEW_ROLES:
            self.assertEqual(frontmatter(self.files["grok"][f"agents/{role}.md"])["model"], "inherit")

    def test_agy_tool_allowlists(self) -> None:
        def tools(role: str) -> list[str]:
            head = self.text("agy", role).split("\n---\n", 1)[0]
            return re.findall(r"^    - (\S+)$", head, re.MULTILINE)

        base = ["view_file", "grep_search", "find_by_name", "list_dir", "send_message"]
        self.assertEqual(tools("watcher"), [*base, "run_command"])
        self.assertEqual(tools("researcher"), [*base, "read_url_content", "search_web"])
        self.assertEqual(frontmatter(self.files["agy"][self.PATHS["agy"]["watcher"]])["model"], "flash")
        self.assertEqual(frontmatter(self.files["agy"][self.PATHS["agy"]["researcher"]])["model"], "pro")

    def test_opencode_permissions_and_routes(self) -> None:
        def permission(role: str) -> list[str]:
            head = self.text("opencode", role).split("\n---\n", 1)[0]
            return head.split("permission:\n", 1)[1].splitlines()

        self.assertEqual(permission("watcher"), ["  edit: deny", "  task: deny"])  # bash 不禁
        self.assertEqual(
            permission("researcher"),
            ["  edit: deny", "  bash: deny", "  task: deny", "  webfetch: allow", "  websearch: allow"],
        )
        routes = json.loads(self.files["opencode"]["routing.json"])["roles"]
        self.assertEqual(routes["watcher"]["candidates"], [{"provider": "deepseek", "model": "deepseek-v4-flash"}])
        self.assertEqual(routes["researcher"]["candidates"], [{"provider": "openai", "model": "gpt-5.6-sol"}])
        self.assertEqual(routes["watcher"]["requiredCapabilities"], ["tools", "streaming", "reasoning"])
        self.assertEqual(routes["researcher"]["requiredCapabilities"], ["tools", "streaming"])
        self.assertEqual({r: routes[r]["fallback"] for r in NEW_ROLES}, {"watcher": "none", "researcher": "none"})

    def test_no_model_is_pinned_so_the_tier_rules_choose(self) -> None:
        for host in OTHER_HOSTS:
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            for role in NEW_ROLES:
                with self.subTest(host=host, role=role):
                    self.assertNotIn("model", binding["roles"][role])

    def test_main_session_policy_lists_the_new_roles_only_where_expected(self) -> None:
        # grok 的 policy 不新增 watcher / researcher 的條款或路由。
        # agy 已用 core 條款，`watcher-long-commands` 等條款本來就會提到 watcher，所以改為要求 agy 的
        # 常駐文件列出兩個 role（bootstrap-named-roles），而不是禁止。
        for role in NEW_ROLES:
            self.assertNotIn(f"`{role}`".encode(), self.files["grok"]["rules/shoal-grok.md"])
        for role in NEW_ROLES:
            self.assertIn(f"`{role}`".encode(), self.files["agy"]["rules/shoal-agy.md"])
        # codex 同 agy：core 的 watcher-long-commands、research-fanout 等條款使兩個 role 在常駐 bootstrap
        # 出現（intended change，equivalence/codex.md 1.4），role 表仍在 orchestration。
        for role in NEW_ROLES:
            self.assertIn(f"`{role}`".encode(), self.files["codex"]["agents-md.bootstrap.md"])
        codex = self.files["codex"]["agents-md.orchestration.md"]
        self.assertEqual(len(self.ROLE_ROW.findall(codex)), 2)

    def test_codex_renders_every_core_role_plus_sol_executor(self) -> None:
        files = render.RENDERERS["codex"](ROOT)
        self.assertEqual(
            sorted(p for p in files if p.startswith("agents/")),
            sorted([f"agents/{n}.toml" for n in render.load_core(ROOT)["roles"]] + ["agents/sol-executor.toml"]),
        )


class PlanCriticGapModeTests(unittest.TestCase):
    def test_gap_mode_clause_is_in_the_core_contract(self) -> None:
        text = (ROOT / "prompts" / "roles" / "plan-critic.md").read_text(encoding="utf-8")
        self.assertIn("<!-- clause: gap-mode ", text)

    def test_every_host_that_renders_plan_critic_carries_gap_mode(self) -> None:
        paths = {
            "claude": "agents/plan-critic.md",
            "codex": "agents/plan-critic.toml",
            "agy": "agents/plan-critic/agent.md",
            "grok": "agents/plan-critic.md",
        }
        for host, rel in paths.items():
            data = render.RENDERERS[host](ROOT)[rel].decode("utf-8")
            with self.subTest(host=host):
                self.assertIn("`mode: gaps`", data)
        opencode = render.RENDERERS["opencode"](ROOT)["roles/plan-critic.md"].decode("utf-8")
        self.assertIn("`mode: gaps`", opencode)


class PolicyClauseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = render.RENDERERS["claude"](ROOT)
        cls.bootstrap = cls.files["claude-md.bootstrap.md"].decode("utf-8")

    def test_effort_and_label_follow_model_routing(self) -> None:
        ids = [c.id for c in render.load_core(ROOT)["policy"]["docs"]["orchestration"]]
        at = ids.index("model-routing")
        self.assertEqual(ids[at + 1 : at + 3], ["effort-per-delegation", "dispatch-kind-label"])

    def test_leaf_cannot_finish_sits_between_watcher_and_liveness_clauses(self) -> None:
        ids = [c.id for c in render.load_core(ROOT)["policy"]["docs"]["orchestration"]]
        at = ids.index("leaf-cannot-finish")
        self.assertEqual(ids[at - 1 : at + 3], ["watcher-long-commands", "leaf-cannot-finish", "liveness", "subagent-final-message"])

    def test_new_clause_ids_exist_and_the_old_one_is_gone(self) -> None:
        ids = {c.id for c in render.load_core(ROOT)["policy"]["docs"]["orchestration"]}
        for clause_id in (
            "effort-per-delegation",
            "dispatch-kind-label",
            "watcher-long-commands",
            "research-fanout",
            "plan-critic-gaps",
            "followup-by-mode",
            "collect-results",
        ):
            self.assertIn(clause_id, ids)
        self.assertNotIn("long-running-main", ids)

    def test_bootstrap_carries_the_delegation_routes_for_headless_sessions(self) -> None:
        # 第一輪 live gate：headless session 只拿到 bootstrap，所以派工路徑必須寫在常駐的 bootstrap 裡。
        for text in (self.bootstrap, (ROOT / "plugins" / "claude" / "policy" / "claude-md.bootstrap.md").read_text(encoding="utf-8")):
            lines = text.splitlines()
            at = next(i for i, line in enumerate(lines) if line.startswith("- The main session does not edit files itself."))
            nested = []
            for line in lines[at + 1 :]:
                if not line.startswith("  "):
                    break
                nested.append(line)
            routes = [line for line in nested if line.startswith("  - ")]
            self.assertEqual(len(routes), 4, nested)  # 縮排的巢狀條列，不是單一段落
            starts = [line for line in lines if line.startswith("- Explicit instruction:")]
            self.assertEqual(len(starts), 1)

    def test_new_bootstrap_clauses_are_not_required(self) -> None:
        by_id = {c.id: c for c in clauses("bootstrap").values()}
        self.assertNotIn("bootstrap-direct-declare", by_id)
        for clause_id in ("bootstrap-delegate-default", "bootstrap-collect"):
            self.assertFalse(by_id[clause_id].required, clause_id)
        ids = list(by_id)
        self.assertEqual(ids[ids.index("bootstrap-ownership") + 1], "bootstrap-delegate-default")
        self.assertEqual(
            ids[ids.index("bootstrap-security") + 1 : ids.index("bootstrap-collect")],
            ["bootstrap-effort", "bootstrap-dispatch-brake", "bootstrap-kind-label"],
        )
        for clause_id in ("bootstrap-effort", "bootstrap-dispatch-brake", "bootstrap-kind-label"):
            self.assertFalse(by_id[clause_id].required, clause_id)

    def test_bootstrap_dispatch_bullets_are_separate_and_ordered(self) -> None:
        lines = self.bootstrap.splitlines()
        effort = [i for i, line in enumerate(lines) if line.startswith("- Explicit instruction:")]
        brake = [i for i, line in enumerate(lines) if line.startswith("- Omit `model` for named roles.")]
        label = [i for i, line in enumerate(lines) if line.startswith("- Start the `description` of every write-capable call")]
        self.assertEqual((len(effort), len(brake), len(label)), (1, 1, 1))
        self.assertTrue(effort[0] < brake[0] < label[0])

    def test_small_parallel_units_follows_parallel_launch(self) -> None:
        ids = [c.id for c in render.load_core(ROOT)["policy"]["docs"]["orchestration"]]
        self.assertEqual(ids[ids.index("parallel-launch") + 1], "small-parallel-units")

    def test_no_rendered_claude_policy_says_take_over(self) -> None:
        for rel, data in self.files.items():
            if not rel.endswith(".md"):
                continue
            text = " ".join(data.decode("utf-8").split()).lower()
            with self.subTest(file=rel):
                self.assertNotIn("take over", text)
                self.assertNotIn("takeover", text)

    def test_watcher_keeps_the_background_command_shape_and_clause_order(self) -> None:
        text = self.files["agents/watcher.md"].decode("utf-8")
        for token in ("`run_in_background: true`", "EXIT_STATUS="):
            with self.subTest(token=token):
                self.assertIn(token, text)
        ids = [c.id for c in render.load_core(ROOT)["contracts"]["watcher"]]
        self.assertEqual(ids[ids.index("run-to-terminal") + 1], "long-command-background")

    def test_core_policy_and_contract_clauses_name_no_model_and_no_number_threshold(self) -> None:
        core = render.load_core(ROOT)
        texts = [c.text for doc in core["policy"]["docs"].values() for c in doc]
        texts += [c.text for role in ("watcher", "researcher", "plan-critic") for c in core["contracts"][role]]
        for text in texts:
            self.assertIsNone(MODEL_NAMES.search(text), text[:60])

    def test_placeholders_are_declared_for_claude(self) -> None:
        vocab = render.load_core(ROOT)["policy"]["placeholders"]
        binding = render.load_toml(ROOT / "hosts" / "claude" / "binding.toml")["policy"]["placeholders"]
        self.assertIn("effort_param", vocab)
        self.assertIn("label_param", vocab)
        self.assertEqual((binding["effort_param"], binding["label_param"]), ("effort", "description"))


if __name__ == "__main__":
    unittest.main()
