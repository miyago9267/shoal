"""權限推導：access 與 capabilities 經各 host 的對應表產生權限欄位、role 層級覆寫、read-only 不可被覆寫成可寫、--explain、對應表 mutation。"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from render_helpers import ROOT, render, run_render

HOSTS = ("claude", "codex", "agy", "grok", "opencode")
# 目前 binding 裡保留的 role 層級權限覆寫；新增或移除都要在這裡明確改，並說明原因（見 SPEC）。
EXPECTED_OVERRIDES = {
    "claude": {},
    "codex": {},
    "agy": {},
    "grok": {},
    "opencode": {"security-reviewer": ["required_capabilities"]},
}


def derive(host: str, root: Path = ROOT) -> dict[str, render.Permission]:
    core = render.load_core(root)
    binding = render.load_toml(root / "hosts" / host / "binding.toml")
    return render.derive_permissions(host, core, binding)


class TempRoot(unittest.TestCase):
    """temp 複本：core 與 hosts（不含 plugin、dist），可改 binding / roles 後 render。"""

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

    def path(self, host: str) -> Path:
        return self.root / "hosts" / host / "binding.toml"

    def edit(self, path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def rendered(self, host: str) -> dict[str, bytes]:
        return render.RENDERERS[host](self.root)

    def changed(self, host: str) -> set[str]:
        before, after = render.RENDERERS[host](ROOT), self.rendered(host)
        self.assertEqual(sorted(before), sorted(after))
        return {rel for rel in before if before[rel] != after[rel]}

    def assert_rejected(self, host: str, expected: str) -> None:
        result = run_render(host, self.root, "--check")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(expected, result.stderr)


# ---- 推導規則本身：用合成的 binding，不依賴實際 host ----
class DerivationRuleTests(unittest.TestCase):
    BINDING = {
        "access": {
            "read-only": {"tools": ["Read", "Grep"]},
            "write": {"disallowedTools": ["Agent"]},
            "verify": {
                "tools": ["Read", "Grep", "Bash"],
                "sandbox_mode": "workspace-write",
            },
        },
        "capabilities": {
            "web": {"tools": ["WebSearch", "Read"], "web_search": "live"},
        },
    }

    def derive(
        self,
        access: str,
        caps: list[str] = (),
        spec: dict | None = None,
        host: str = "claude",
        binding: dict | None = None,
    ) -> render.Permission:
        return render.derive_permission(
            host, "r", access, list(caps), binding or self.BINDING, spec or {}
        )

    def test_each_level_uses_its_own_table(self) -> None:
        self.assertEqual(self.derive("read-only").fields, {"tools": ["Read", "Grep"]})
        self.assertEqual(self.derive("write").fields, {"disallowedTools": ["Agent"]})
        self.assertEqual(self.derive("verify").tables, ["access.verify"])

    def test_capability_list_is_appended_without_duplicates(self) -> None:
        perm = self.derive("read-only", ["web"])
        self.assertEqual(perm.fields["tools"], ["Read", "Grep", "WebSearch"])
        self.assertEqual(perm.tables, ["access.read-only", "capabilities.web"])

    def test_capability_list_is_ignored_when_access_has_no_such_list(self) -> None:
        # write 是 denylist，沒有 tools allowlist，capability 的 tools 不輸出
        self.assertEqual(
            self.derive("write", ["web"]).fields,
            {"disallowedTools": ["Agent"], "web_search": "live"},
        )

    def test_capability_scalar_is_set_and_conflict_is_rejected(self) -> None:
        self.assertEqual(self.derive("read-only", ["web"]).fields["web_search"], "live")
        with self.assertRaisesRegex(render.RenderError, "衝突"):
            self.derive(
                "verify",
                ["web"],
                binding={
                    **self.BINDING,
                    "capabilities": {"web": {"sandbox_mode": "read-only"}},
                },
            )

    def test_override_replaces_the_field_not_the_whole_permission(self) -> None:
        perm = self.derive(
            "read-only",
            ["web"],
            {"web_search": "cached"},
            host="codex",
            binding={
                **self.BINDING,
                "access": {"read-only": {"sandbox_mode": "read-only"}},
            },
        )
        self.assertEqual(
            perm.fields, {"sandbox_mode": "read-only", "web_search": "cached"}
        )
        self.assertEqual(perm.overridden, ["web_search"])

    def test_claude_override_of_one_kind_drops_the_other(self) -> None:
        perm = self.derive("write", spec={"tools": ["Read"]})
        self.assertEqual(perm.fields, {"tools": ["Read"]})
        perm = self.derive("read-only", spec={"disallowedTools": ["Agent"]})
        self.assertEqual(perm.fields, {"disallowedTools": ["Agent"]})

    def test_override_wins_over_capability_contribution(self) -> None:
        perm = self.derive("read-only", ["web"], {"tools": ["Read"]})
        self.assertEqual(perm.fields["tools"], ["Read"])

    def test_missing_tables_are_rejected(self) -> None:
        with self.assertRaisesRegex(render.RenderError, r"\[access\.write\]"):
            self.derive("write", binding={"access": {}})
        with self.assertRaisesRegex(render.RenderError, r"\[capabilities\.web\]"):
            self.derive(
                "read-only", ["web"], binding={"access": self.BINDING["access"]}
            )
        with self.assertRaisesRegex(render.RenderError, "access 必須是"):
            self.derive("admin")

    def test_table_validation(self) -> None:
        for binding, expected in (
            ({"access": {"root": {}}}, r"\[access\.root\]"),
            ({"capabilities": {"gpu": {}}}, r"\[capabilities\.gpu\]"),
            ({"access": {"write": {"sandbox_mode": "x"}}}, "不接受欄位 sandbox_mode"),
            ({"access": {"write": {"tools": "Read"}}}, "tools 必須是字串陣列"),
            (
                {"access": {"write": {"disallowedTools": [1]}}},
                "disallowedTools 必須是字串陣列",
            ),
        ):
            with self.assertRaisesRegex(render.RenderError, expected):
                render.validate_access_tables("claude", binding)
        with self.assertRaisesRegex(render.RenderError, "capability_mode 必須是字串"):
            render.validate_access_tables(
                "grok", {"access": {"write": {"capability_mode": ["all"]}}}
            )


# ---- 實際 binding 的推導結果 ----
class ShippedBindingTests(unittest.TestCase):
    def test_core_declares_access_and_host_neutral_capabilities_only(self) -> None:
        text = (ROOT / "core" / "roles.toml").read_text(encoding="utf-8")
        for needle in (
            "tools",
            "Read",
            "Glob",
            "WebSearch",
            "WebFetch",
            "run_command",
            "search_web",
            "sandbox",
            "capability_mode",
            "disallowed",
            "required_capabilities",
            "streaming",
        ):
            # 註解可以說明對應的欄位名稱，所以只檢查資料行
            data = "\n".join(
                line for line in text.splitlines() if not line.lstrip().startswith("#")
            )
            self.assertNotIn(needle, data, needle)
        roles = render.load_core(ROOT)["roles"]
        used = {c for r in roles.values() for c in r.get("capabilities", [])}
        self.assertEqual(used, {"web"})
        self.assertEqual(
            {n for n, r in roles.items() if "web" in r.get("capabilities", [])},
            {"security-reviewer"},
        )

    def test_every_host_derives_every_role_with_core_access(self) -> None:
        core = render.load_core(ROOT)
        for host in HOSTS:
            perms = derive(host)
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            for name in render._bound_roles(core, binding):
                self.assertEqual(
                    perms[name].access, core["roles"][name]["access"], f"{host}: {name}"
                )
                self.assertEqual(
                    perms[name].capabilities,
                    core["roles"][name].get("capabilities", []),
                )

    def test_remaining_role_overrides_are_exactly_the_documented_ones(self) -> None:
        for host in HOSTS:
            actual = {n: p.overridden for n, p in derive(host).items() if p.overridden}
            self.assertEqual(actual, EXPECTED_OVERRIDES[host], host)

    def test_no_override_repeats_the_derived_value(self) -> None:
        for host in HOSTS:
            core = render.load_core(ROOT)
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            for name, perm in derive(host).items():
                for key in perm.overridden:
                    spec = binding["roles"].get(name) or binding["extra_roles"][name]
                    stripped = {k: v for k, v in spec.items() if k != key}
                    base = render.derive_permission(
                        host, name, perm.access, perm.capabilities, binding, stripped
                    )
                    self.assertNotEqual(
                        base.fields.get(key),
                        spec[key],
                        f"{host}: {name}.{key} 的覆寫與推導值相同",
                    )

    def test_claude_derivation(self) -> None:
        perms = {n: p.fields for n, p in derive("claude").items()}
        read_only = {"tools": ["Read", "Glob", "Grep"]}
        self.assertEqual(perms["scout"], read_only)
        self.assertEqual(perms["plan-verifier"], read_only)
        self.assertEqual(perms["Explore"], read_only)
        self.assertEqual(
            perms["security-reviewer"],
            {"tools": ["Read", "Glob", "Grep", "WebSearch", "WebFetch"]},
        )
        self.assertEqual(perms["executor"], {"disallowedTools": ["Agent", "Workflow"]})
        self.assertEqual(perms["security-executor"], perms["mech-executor"])
        self.assertEqual(
            perms["verifier"],
            {"disallowedTools": ["Write", "Edit", "NotebookEdit", "Agent", "Workflow"]},
        )

    def test_codex_derivation(self) -> None:
        perms = {n: p.fields for n, p in derive("codex").items()}
        self.assertEqual(perms["scout"], {"sandbox_mode": "read-only"})
        self.assertEqual(perms["plan-verifier"], {"sandbox_mode": "read-only"})
        self.assertEqual(
            perms["security-reviewer"],
            {"sandbox_mode": "read-only", "web_search": "live"},
        )
        self.assertEqual(perms["verifier"], {"sandbox_mode": "workspace-write"})
        for name in ("mech-executor", "executor", "security-executor", "sol-executor"):
            self.assertEqual(perms[name], {}, name)

    def test_agy_derivation(self) -> None:
        perms = {n: p.fields for n, p in derive("agy").items()}
        base = ["view_file", "grep_search", "find_by_name", "list_dir", "send_message"]
        self.assertEqual(perms["scout"], {"tools": base})
        self.assertEqual(perms["plan-verifier"], {"tools": base})
        self.assertEqual(perms["verifier"], {"tools": [*base, "run_command"]})
        self.assertEqual(
            perms["security-reviewer"],
            {"tools": [*base, "read_url_content", "search_web"]},
        )
        for name in ("mech-executor", "executor", "security-executor"):
            self.assertEqual(perms[name], {}, name)

    def test_grok_derivation(self) -> None:
        modes = {n: p.fields["capability_mode"] for n, p in derive("grok").items()}
        self.assertEqual(
            modes,
            {
                "scout": "read-only",
                "mech-executor": "all",
                "executor": "all",
                "plan-verifier": "read-only",
                "verifier": "execute",
                "security-reviewer": "read-only",
                "security-executor": "all",
            },
        )

    def test_opencode_derivation(self) -> None:
        perms = {n: p for n, p in derive("opencode").items()}
        base = ["tools", "streaming"]
        self.assertEqual(perms["scout"].fields["required_capabilities"], base)
        for name in ("executor", "verifier", "security-executor"):
            self.assertEqual(
                perms[name].fields["required_capabilities"], [*base, "reasoning"], name
            )
        self.assertEqual(
            perms["security-reviewer"].fields["required_capabilities"],
            [*base, "reasoning"],
        )
        self.assertEqual(
            perms["security-reviewer"].overridden, ["required_capabilities"]
        )

    def test_host_specific_roles_derive_from_their_own_access(self) -> None:
        explore = derive("claude")["Explore"]
        self.assertEqual(
            (explore.access, explore.tables, explore.overridden),
            ("read-only", ["access.read-only"], []),
        )
        sol = derive("codex")["sol-executor"]
        self.assertEqual(
            (sol.access, sol.tables, sol.overridden), ("write", ["access.write"], [])
        )
        binding = render.load_toml(ROOT / "hosts" / "claude" / "binding.toml")
        self.assertNotIn("tools", binding["extra_roles"]["Explore"])


# ---- 驗證規則改成對推導結果做檢查 ----
class ValidationOnDerivedResultTests(TempRoot):
    def test_read_only_role_cannot_be_overridden_to_writable_on_any_host(self) -> None:
        cases = (
            (
                "claude",
                "[roles.scout]\n",
                '[roles.scout]\ntools = ["Read", "Edit"]\n',
                "Edit",
            ),
            (
                "claude",
                "[roles.scout]\n",
                '[roles.scout]\ndisallowedTools = ["Agent"]\n',
                "scout",
            ),
            (
                "codex",
                "[roles.scout]\n",
                '[roles.scout]\nsandbox_mode = "workspace-write"\n',
                "scout",
            ),
            (
                "agy",
                "[roles.scout]\n",
                '[roles.scout]\ntools = ["view_file", "run_command"]\n',
                "run_command",
            ),
            (
                "grok",
                "[roles.scout]\n",
                '[roles.scout]\ncapability_mode = "all"\n',
                "scout",
            ),
        )
        for host, old, new, expected in cases:
            with self.subTest(host=host, expected=expected):
                self.setUp()
                self.edit(self.path(host), old, new)
                self.assert_rejected(host, expected)

    def test_override_of_extra_role_is_validated_too(self) -> None:
        self.edit(
            self.path("claude"),
            "[extra_roles.Explore]\n",
            '[extra_roles.Explore]\ntools = ["Read", "Bash"]\n',
        )
        self.assert_rejected("claude", "Explore")

    def test_non_read_only_role_cannot_be_overridden_to_codex_read_only(self) -> None:
        self.edit(
            self.path("codex"),
            "[roles.executor]\n",
            '[roles.executor]\nsandbox_mode = "read-only"\n',
        )
        self.assert_rejected("codex", "executor")

    def test_missing_access_table_for_a_used_level_is_rejected(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.setUp()
                path = self.path(host)
                text = re.sub(
                    r"(?ms)^\[access\.verify\]\n.*?(?=^\[|\Z)",
                    "",
                    path.read_text(encoding="utf-8"),
                )
                path.write_text(text, encoding="utf-8", newline="\n")
                self.assert_rejected(host, "[access.verify]")

    def test_role_capability_without_a_host_mapping_is_rejected(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.setUp()
                path = self.path(host)
                text = re.sub(
                    r"(?ms)^\[capabilities\.web\]\n.*?(?=^\[|\Z)",
                    "",
                    path.read_text(encoding="utf-8"),
                )
                path.write_text(text, encoding="utf-8", newline="\n")
                self.assert_rejected(host, "[capabilities.web]")

    def test_unknown_capability_in_core_is_rejected(self) -> None:
        self.edit(
            self.root / "core" / "roles.toml",
            'capabilities = ["web"]',
            'capabilities = ["web", "gpu"]',
        )
        self.assert_rejected("claude", "capabilities")

    def test_field_from_another_host_is_rejected_in_tables(self) -> None:
        self.edit(
            self.path("claude"),
            "[access.write]\n",
            '[access.write]\nsandbox_mode = "read-only"\n',
        )
        self.assert_rejected("claude", "sandbox_mode")

    def test_claude_derived_permission_needs_exactly_one_kind(self) -> None:
        self.edit(
            self.path("claude"),
            "[access.write]\n",
            '[access.write]\ntools = ["Read"]\n',
        )
        self.assert_rejected("claude", "tools 或 disallowedTools")


# ---- 覆寫、capability 疊加與對應表 mutation ----
class MutationTests(TempRoot):
    def test_role_override_changes_only_that_role(self) -> None:
        self.edit(
            self.path("claude"),
            "[roles.executor]\n",
            '[roles.executor]\ndisallowedTools = ["Agent"]\n',
        )
        self.assertEqual(self.changed("claude"), {"agents/executor.md"})
        self.assertIn(
            b"\ndisallowedTools: Agent\n", self.rendered("claude")["agents/executor.md"]
        )

    def test_capability_stacks_on_each_access_level(self) -> None:
        # verifier（verify 等級）加上 web：agy 的 allowlist 附加；codex 設 web_search；
        # claude 的 verify 是 denylist，本來就允許 web 工具，輸出不變
        self.edit(
            self.root / "core" / "roles.toml",
            '[roles.verifier]\naccess = "verify"\ntier = "strong"\nsecurity = false\n',
            '[roles.verifier]\naccess = "verify"\ntier = "strong"\nsecurity = false\ncapabilities = ["web"]\n',
        )
        self.assertEqual(self.changed("claude"), set())
        self.assertEqual(self.changed("agy"), {"agents/verifier/agent.md"})
        self.assertIn(
            b"    - run_command\n    - read_url_content\n    - search_web\n---",
            self.rendered("agy")["agents/verifier/agent.md"],
        )
        self.assertEqual(self.changed("codex"), {"agents/verifier.toml"})
        self.assertIn(
            b'sandbox_mode = "workspace-write"\nweb_search = "live"\n',
            self.rendered("codex")["agents/verifier.toml"],
        )
        self.assertEqual(self.changed("grok"), set())

    def test_changing_core_access_changes_the_derived_permission(self) -> None:
        # 把 scout 從 read-only 升成 write：不用動任何 binding，輸出就換成 write 等級的權限
        self.edit(
            self.root / "core" / "roles.toml",
            '[roles.scout]\naccess = "read-only"',
            '[roles.scout]\naccess = "write"',
        )
        self.assertEqual(self.changed("claude"), {"agents/scout.md"})
        self.assertIn(
            b"\ndisallowedTools: Agent, Workflow\n",
            self.rendered("claude")["agents/scout.md"],
        )
        self.assertEqual(self.changed("grok"), {"roles/scout.toml"})
        self.assertIn(
            b'default_capability_mode = "all"\n',
            self.rendered("grok")["roles/scout.toml"],
        )

    def test_claude_read_only_table_change_moves_every_read_only_role(self) -> None:
        self.edit(
            self.path("claude"),
            '[access.read-only]\ntools = ["Read", "Glob", "Grep"]',
            '[access.read-only]\ntools = ["Read", "Grep"]',
        )
        self.assertEqual(
            self.changed("claude"),
            {
                "agents/scout.md",
                "agents/plan-verifier.md",
                "agents/security-reviewer.md",
                "agents/Explore.md",
            },
        )
        out = self.rendered("claude")
        self.assertIn(b"\ntools: Read, Grep\n", out["agents/scout.md"])
        self.assertIn(b"\ntools: Read, Grep\n", out["agents/Explore.md"])
        self.assertIn(
            b"\ntools: Read, Grep, WebSearch, WebFetch\n",
            out["agents/security-reviewer.md"],
        )

    def test_agy_read_only_table_change_moves_every_read_only_role(self) -> None:
        self.edit(
            self.path("agy"),
            '[access.read-only]\ntools = ["view_file", "grep_search", "find_by_name", "list_dir", "send_message"]',
            '[access.read-only]\ntools = ["view_file", "grep_search"]',
        )
        self.assertEqual(
            self.changed("agy"),
            {
                "agents/scout/agent.md",
                "agents/plan-verifier/agent.md",
                "agents/security-reviewer/agent.md",
            },
        )
        out = self.rendered("agy")
        self.assertIn(
            b"tools:\n    - view_file\n    - grep_search\n---",
            out["agents/scout/agent.md"],
        )
        self.assertIn(
            b"    - grep_search\n    - read_url_content\n    - search_web\n---",
            out["agents/security-reviewer/agent.md"],
        )

    def test_opencode_read_only_table_change_skips_the_overridden_role(self) -> None:
        self.edit(
            self.path("opencode"),
            '[access.read-only]\nrequired_capabilities = ["tools", "streaming"]',
            '[access.read-only]\nrequired_capabilities = ["tools"]',
        )
        # security-reviewer 有 required_capabilities 覆寫，所以不跟著改；覆寫只影響那個 role
        self.assertEqual(self.changed("opencode"), {"routing.json"})
        routes = json.loads(self.rendered("opencode")["routing.json"])[
            "roles"
        ]
        self.assertEqual(routes["scout"]["requiredCapabilities"], ["tools"])
        self.assertEqual(
            routes["security-reviewer"]["requiredCapabilities"],
            ["tools", "streaming", "reasoning"],
        )

    def test_write_and_verify_table_changes_move_only_their_roles(self) -> None:
        self.edit(
            self.path("claude"),
            '[access.write]\ndisallowedTools = ["Agent", "Workflow"]',
            '[access.write]\ndisallowedTools = ["Workflow"]',
        )
        self.assertEqual(
            self.changed("claude"),
            {
                "agents/mech-executor.md",
                "agents/executor.md",
                "agents/security-executor.md",
            },
        )
        self.setUp()
        self.edit(
            self.path("codex"),
            'sandbox_mode = "workspace-write"',
            'sandbox_mode = "danger-full-access"',
        )
        self.assertEqual(self.changed("codex"), {"agents/verifier.toml"})
        self.setUp()
        self.edit(
            self.path("grok"),
            '[access.verify]\ncapability_mode = "execute"',
            '[access.verify]\ncapability_mode = "all"',
        )
        self.assertEqual(self.changed("grok"), {"roles/verifier.toml"})

    def test_codex_and_grok_read_only_tables_cannot_stop_being_read_only(self) -> None:
        self.edit(
            self.path("codex"),
            '[access.read-only]\nsandbox_mode = "read-only"',
            '[access.read-only]\nsandbox_mode = "workspace-write"',
        )
        self.assert_rejected("codex", "read-only")
        self.edit(
            self.path("grok"),
            '[access.read-only]\ncapability_mode = "read-only"',
            '[access.read-only]\ncapability_mode = "execute"',
        )
        self.assert_rejected("grok", "capability_mode")

    def test_dist_is_untouched_by_explain_and_check(self) -> None:
        before = {h: render.RENDERERS[h](ROOT) for h in HOSTS}
        for host in HOSTS:
            self.assertEqual(run_render(host, ROOT, "--check").returncode, 0, host)
        self.assertEqual(before, {h: render.RENDERERS[h](ROOT) for h in HOSTS})


# ---- --explain ----
class ExplainPermissionTests(TempRoot):
    def explain(self, host: str, root: Path = ROOT) -> str:
        result = run_render(host, root, "--explain")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def block(self, out: str, header: str) -> str:
        return out.split(f"\n{header}", 1)[1].split("\n\n")[0]

    def test_every_bound_role_has_a_permission_line(self) -> None:
        core = render.load_core(ROOT)
        for host in HOSTS:
            out = self.explain(host)
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            for name in render._bound_roles(core, binding):
                block = self.block(out, f"{name}  tier=")
                self.assertRegex(
                    block,
                    rf"權限：access={core['roles'][name]['access']}  ",
                    f"{host}: {name}",
                )

    def test_claude_explain_shows_access_capabilities_tables_and_fields(self) -> None:
        out = self.explain("claude")
        sec = self.block(out, "security-reviewer  tier=strong  security=true")
        self.assertIn(
            "權限：access=read-only  capabilities=web  對應表=[access.read-only]、[capabilities.web]  覆寫=無",
            sec,
        )
        self.assertIn('tools = ["Read", "Glob", "Grep", "WebSearch", "WebFetch"]', sec)
        ver = self.block(out, "verifier  tier=strong  security=false")
        self.assertIn(
            "access=verify  capabilities=無  對應表=[access.verify]  覆寫=無", ver
        )
        self.assertIn(
            'disallowedTools = ["Write", "Edit", "NotebookEdit", "Agent", "Workflow"]',
            ver,
        )

    def test_host_specific_role_shows_its_own_access(self) -> None:
        explore = self.block(self.explain("claude"), "Explore（host 專屬 role）")
        self.assertIn(
            "權限：access=read-only  capabilities=無  對應表=[access.read-only]  覆寫=無",
            explore,
        )
        sol = self.block(self.explain("codex"), "sol-executor（host 專屬 role）")
        self.assertIn("access=write", sol)
        self.assertIn("此等級沒有權限欄位輸出", sol)

    def test_override_is_listed_and_names_the_section(self) -> None:
        sec = self.block(
            self.explain("opencode"), "security-reviewer  tier=strong  security=true"
        )
        self.assertIn("覆寫=required_capabilities（[roles.security-reviewer]）", sec)
        self.edit(
            self.path("claude"),
            "[roles.executor]\n",
            '[roles.executor]\ndisallowedTools = ["Agent"]\n',
        )
        ex = self.block(
            self.explain("claude", self.root), "executor  tier=standard  security=false"
        )
        self.assertIn("覆寫=disallowedTools（[roles.executor]）", ex)
        self.assertIn('disallowedTools = ["Agent"]', ex)

    def test_explain_fails_with_exit_2_on_invalid_access_table(self) -> None:
        # --explain 只推導、不做 host 專屬驗證，但對應表不合法這類來源錯誤同樣 exit 2
        self.edit(self.path("claude"), "[access.write]\n", "[access.nope]\n")
        result = run_render("claude", self.root, "--explain")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("nope", result.stderr)


if __name__ == "__main__":
    unittest.main()
