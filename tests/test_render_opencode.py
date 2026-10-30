from __future__ import annotations

import json
import unittest

import render_helpers as rh
from render_helpers import ROOT, render


class OpencodeRenderTests(rh.HostRenderCase):
    HOST = "opencode"
    DIST_FILE = "roles/scout.md"
    SRC_FILE = ""  # core 模式下 hosts/opencode/src 已不存在；改來源的測試覆寫成改 prompts/hosts/opencode/frames/executor.md

    def test_every_core_role_is_rendered_and_none_is_omitted(self) -> None:
        rendered = render.RENDERERS["opencode"](ROOT)
        catalog, routing = json.loads(rendered["catalog.json"]), json.loads(rendered["routing.json"])
        expected = {"scout", "applier", "executor", "plan-critic", "verifier", "security-reviewer",
                    "security-executor", "watcher", "researcher"}
        self.assertEqual(set(catalog["agents"]), expected)
        self.assertEqual(set(routing["roles"]), expected)
        for name in expected:
            self.assertIn(f"roles/{name}.md", rendered)
        self.assertEqual(render.load_toml(self.binding)["omitted_roles"], [])

    def test_plan_critic_is_read_only_and_applier_may_edit(self) -> None:
        rendered = render.RENDERERS["opencode"](ROOT)
        critic = rendered["roles/plan-critic.md"].decode().split("---\n")[1]
        for deny in ("edit", "bash", "task"):
            self.assertIn(f"  {deny}: deny\n", critic)
        applier = rendered["roles/applier.md"].decode().split("---\n")[1]
        self.assertIn("  task: deny\n", applier)
        self.assertNotIn("edit: deny", applier)
        self.assertNotIn("bash: deny", applier)

    def test_every_role_denies_task_so_none_can_dispatch_subagents(self) -> None:
        # dispatch-enforcement R6：write 等級（executor、security-executor）也是 leaf，不可再派 subagent。
        rendered = render.RENDERERS["opencode"](ROOT)
        for name in ("scout", "applier", "executor", "plan-critic", "verifier", "security-reviewer",
                     "security-executor", "watcher", "researcher"):
            front = rendered[f"roles/{name}.md"].decode().split("---\n")[1]
            self.assertIn("permission:\n", front, name)
            self.assertIn("  task: deny\n", front, name)

    def test_pi_routing_is_not_owned_here(self) -> None:
        self.assertNotIn("pi-routing.json", render.RENDERERS["opencode"](ROOT))

    def test_catalog_agent_model_is_first_routing_candidate(self) -> None:
        rendered = render.RENDERERS["opencode"](ROOT)
        catalog, routing = json.loads(rendered["catalog.json"]), json.loads(rendered["routing.json"])
        for name, agent in catalog["agents"].items():
            self.assertEqual(agent["model"], routing["roles"][name]["candidates"][0])

    def test_omitted_role_cannot_also_be_bound(self) -> None:
        self.edit(self.binding, "omitted_roles = []", 'omitted_roles = ["applier"]')
        self.assert_rejected("applier")

    def test_omitted_role_must_exist_in_catalog(self) -> None:
        self.edit(self.binding, "omitted_roles = []", 'omitted_roles = ["ghost"]')
        self.assert_rejected("ghost")

    def test_role_missing_from_binding_and_omitted_roles_is_rejected(self) -> None:
        self.edit(self.binding, "[roles.plan-critic]\nfallback", "[roles.ghost]\nfallback")
        self.assert_rejected("plan-critic")

    def test_fallback_none_cannot_have_candidates(self) -> None:
        self.edit(self.binding, '[roles.security-reviewer]\nfallback = "none"\nfallback_candidates = []',
                  '[roles.security-reviewer]\nfallback = "none"\nfallback_candidates = [{ provider = "xai", model = "grok-4.6" }]')
        self.assert_rejected("security-reviewer")

    def test_candidate_must_be_in_providers(self) -> None:
        self.edit(self.binding, '{ provider = "xai", model = "grok-4.6" }]\n\n[roles.verifier]',
                  '{ provider = "xai", model = "grok-9" }]\n\n[roles.verifier]')
        self.assert_rejected("grok-9")

    def test_candidate_must_support_required_capabilities(self) -> None:
        self.edit(self.binding, 'supported = ["tools", "streaming"]', 'supported = ["tools"]')
        self.assert_rejected("streaming")

    def test_check_fails_when_source_changes_without_rewriting_dist(self) -> None:
        frame = self.root / "prompts" / "hosts" / "opencode" / "frames" / "executor.md"
        frame.write_text(frame.read_text(encoding="utf-8") + "extra line\n", encoding="utf-8", newline="\n")
        self.assertEqual(self.check().returncode, 1)

    def test_stray_role_md_is_rejected(self) -> None:
        ghost = self.root / "hosts" / "opencode" / "src" / "roles" / "ghost.md"
        ghost.parent.mkdir(parents=True, exist_ok=True)
        ghost.write_text("x\n", encoding="utf-8", newline="\n")
        self.assert_rejected("ghost.md")


if __name__ == "__main__":
    unittest.main()
