from __future__ import annotations

import re
import unittest

import render_helpers as rh
from render_helpers import ROOT, render, run_render


class AgyRenderTests(rh.HostRenderCase):
    HOST = "agy"
    GOLDEN_COUNT = 13
    SOURCE_REFS = ("shoal@",)
    DIST_FILE = "agents/scout/agent.md"
    # agy 已切到 core：agents/*.md、rules、SKILL.md 的 legacy 原文（hosts/agy/src）都不參與 render，
    # 所以「改來源」的測試改在下面覆寫，改 policy-frames/bootstrap.md。
    SRC_FILE = ""

    # --- 3.0.0：agy 有自己的 VERSION，rules 的 marker 由它產生（同 grok） ---
    def test_rules_marker_comes_from_host_version(self) -> None:
        version = (ROOT / "hosts" / "agy" / "VERSION").read_text(encoding="utf-8").strip()
        rules = render.RENDERERS["agy"](ROOT)["rules/shoal-agy.md"].decode("utf-8")
        self.assertEqual(re.findall(r"(?m)^<!-- shoal-agy v.+ -->$", rules), [f"<!-- shoal-agy v{version} -->"])
        self.assertEqual(version, "3.8.1")

    def test_check_fails_when_source_changes_without_rewriting_dist(self) -> None:
        frame = self.root / "hosts" / "agy" / "policy-frames" / "bootstrap.md"
        frame.write_text(frame.read_text(encoding="utf-8") + "extra line\n", encoding="utf-8", newline="\n")
        self.assertEqual(self.check().returncode, 1)

    def test_changing_version_requires_rewriting_dist(self) -> None:
        # 常駐文件的 marker 是 policy-frames/bootstrap.md 的字面值（同 claude），VERSION 只做格式檢查。
        frame = self.root / "hosts" / "agy" / "policy-frames" / "bootstrap.md"
        self.edit(frame, "<!-- shoal-agy v3.8.1 -->", "<!-- shoal-agy v2.0.1 -->")
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("內容不同: rules/shoal-agy.md", result.stderr)
        self.assertEqual(run_render("agy", self.root, "--write").returncode, 0)
        self.assertIn(b"<!-- shoal-agy v2.0.1 -->", (self.dist / "rules" / "shoal-agy.md").read_bytes())
        self.assertEqual(self.check().returncode, 0)

    def test_version_must_be_semver_like_and_present(self) -> None:
        version = self.root / "hosts" / "agy" / "VERSION"
        version.write_text("v1\n", encoding="utf-8", newline="\n")
        self.assert_rejected("版本格式不合法")
        version.unlink()
        self.assert_rejected("VERSION")

    def test_policy_documents_are_core_and_cover_every_mapped_path(self) -> None:
        binding = render.load_toml(ROOT / "hosts" / "agy" / "binding.toml")
        self.assertEqual(binding["policy"]["policy_text"], "core")
        rendered = render.RENDERERS["agy"](ROOT)
        for path in binding["policy"]["documents"].values():
            self.assertIn(path, rendered)
        self.assertEqual(len(rendered), 13)

    def test_resident_frame_has_no_unavailable_escape_hatch(self) -> None:
        # R02：舊文字在 invoke_subagent 不可用時整節忽略（等於 main 自己做）；core 改為回報使用者，frame 不可再放這個出口。
        rules = render.RENDERERS["agy"](ROOT)["rules/shoal-agy.md"].decode("utf-8")
        self.assertNotIn("unavailable, ignore it", rules)

    def test_effort_is_never_rendered(self) -> None:
        for rel, data in render.RENDERERS["agy"](ROOT).items():
            if rel.startswith("agents/"):
                self.assertNotIn(b"effort", data.split(b"\n---\n", 1)[0], rel)

    def test_binding_must_declare_effort_unsupported(self) -> None:
        self.edit(self.binding, "supports_effort = false", "supports_effort = true")
        self.assert_rejected("supports_effort")

    def test_role_cannot_set_effort(self) -> None:
        self.edit(self.binding, "[roles.executor]\n", '[roles.executor]\neffort = "high"\n')
        self.assert_rejected("effort")

    def test_model_must_be_flash_pro_or_inherit(self) -> None:
        self.edit(self.binding, '"google/gemini-flash" = "flash"', '"google/gemini-flash" = "gemini-3"')
        self.assert_rejected("gemini-3")

    def test_read_only_role_needs_tools_without_run_command(self) -> None:
        self.edit(self.binding, '[access.read-only]\ntools = ["view_file", "grep_search", "find_by_name", "list_dir", "send_message"]',
                  '[access.read-only]\ntools = ["view_file", "grep_search", "find_by_name", "list_dir", "run_command"]')
        self.assert_rejected("run_command")

    def test_role_override_cannot_give_read_only_role_run_command(self) -> None:
        self.edit(self.binding, "[roles.scout]\n", '[roles.scout]\ntools = ["view_file", "run_command"]\n')
        self.assert_rejected("run_command")

    def test_read_only_role_without_tools_is_rejected(self) -> None:
        text = self.binding.read_text(encoding="utf-8")
        head, tail = text.split("[access.read-only]\ntools = ", 1)
        self.binding.write_text(head + "[access.read-only]\n" + tail.split("\n", 1)[1], encoding="utf-8", newline="\n")
        self.assert_rejected("scout")

    def test_tiers_map_to_expected_models(self) -> None:
        binding = render.load_toml(ROOT / "hosts" / "agy" / "binding.toml")
        core = render.load_core(ROOT)
        models = {n: render.resolve_model(n, core, binding) for n in render._bound_roles(core, binding)}
        self.assertEqual({n for n, m in models.items() if m == "flash"}, {"scout", "applier", "watcher"})
        self.assertEqual(len(models), 9)


if __name__ == "__main__":
    unittest.main()
