from __future__ import annotations

import re
import tomllib
import unittest

import render_helpers as rh
from render_helpers import ROOT, render, run_render

UPSTREAM_RULES = ROOT / "tests" / "fixtures" / "grok" / "rules.pilotfish-grok.upstream-v1.0.6.txt"


class GrokRenderTests(rh.HostRenderCase):
    HOST = "grok"
    GOLDEN_COUNT = 19
    SOURCE_REFS = ("shoal@",)
    DIST_FILE = "roles/scout.toml"
    SRC_FILE = "config.snippet.toml"  # core 模式下 agents/*.md 不參與 render，改用 passthrough 檔

    def test_vendored_files_are_copied_verbatim(self) -> None:
        # Decision 7：agents/ 改由 core 條款產生，不再逐字等於上游；其餘檔案仍逐字複製。
        src = ROOT / "hosts" / "grok" / "src"
        rendered = render.RENDERERS["grok"](ROOT)
        for path in src.rglob("*"):
            rel = path.relative_to(src)
            if path.is_file() and rel.parts[0] not in ("agents", "rules"):
                self.assertEqual(rendered[rel.as_posix()], path.read_bytes())

    # --- G1：orchestration rules 與 grok host 版本（AC-GW-001 至 AC-GW-005）---
    def test_rules_marker_comes_from_host_version(self) -> None:  # AC-GW-001、AC-GW-002
        version = (ROOT / "hosts" / "grok" / "VERSION").read_text(encoding="utf-8").strip()
        rules = render.RENDERERS["grok"](ROOT)["rules/pilotfish-grok.md"].decode("utf-8")
        self.assertEqual(re.findall(r"(?m)^<!-- pilotfish-grok v.+ -->$", rules),
                         [f"<!-- pilotfish-grok v{version} -->"])
        self.assertEqual(version, "1.0.6-shoal.1")

    def test_rules_equal_upstream_except_marker(self) -> None:  # AC-GW-003
        upstream = UPSTREAM_RULES.read_text(encoding="utf-8").splitlines(keepends=True)
        rules = render.RENDERERS["grok"](ROOT)["rules/pilotfish-grok.md"].decode("utf-8").splitlines(keepends=True)
        self.assertEqual(len(rules), len(upstream))
        differing = [(a, b) for a, b in zip(upstream, rules) if a != b]
        self.assertEqual(differing, [("<!-- pilotfish-grok v1.0.6 -->\n", "<!-- pilotfish-grok v1.0.6-shoal.1 -->\n")])

    def test_changing_version_requires_rewriting_dist(self) -> None:  # AC-GW-002
        (self.root / "hosts" / "grok" / "VERSION").write_text("1.0.6-shoal.2\n", encoding="utf-8", newline="\n")
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("內容不同: rules/pilotfish-grok.md", result.stderr)
        self.assertEqual(run_render("grok", self.root, "--write").returncode, 0)
        self.assertIn(b"<!-- pilotfish-grok v1.0.6-shoal.2 -->", (self.dist / "rules" / "pilotfish-grok.md").read_bytes())
        self.assertEqual(self.check().returncode, 0)

    def test_version_must_be_semver_like(self) -> None:  # AC-GW-005
        (self.root / "hosts" / "grok" / "VERSION").write_text("v1\n", encoding="utf-8", newline="\n")
        self.assert_rejected("版本格式不合法")

    def test_missing_version_file_is_rejected(self) -> None:  # AC-GW-005
        (self.root / "hosts" / "grok" / "VERSION").unlink()
        self.assert_rejected("VERSION")

    def test_rules_source_needs_exactly_one_marker(self) -> None:  # AC-GW-005
        src = self.root / "hosts" / "grok" / "src" / "rules" / "pilotfish-grok.md"
        text = src.read_text(encoding="utf-8")
        marker = "<!-- pilotfish-grok v1.0.6-shoal.1 -->\n"
        self.assertIn(marker, text)
        src.write_text(text.replace(marker, ""), encoding="utf-8", newline="\n")
        self.assert_rejected("marker")
        src.write_text(text + marker, encoding="utf-8", newline="\n")
        self.assert_rejected("marker")

    def test_agents_are_rendered_from_core_not_from_src(self) -> None:
        src = ROOT / "hosts" / "grok" / "src" / "agents"
        rendered = render.RENDERERS["grok"](ROOT)
        for path in src.glob("*.md"):
            self.assertNotEqual(rendered[f"agents/{path.name}"], path.read_bytes(), path.name)

    def test_role_toml_carries_reasoning_effort(self) -> None:
        rendered = render.RENDERERS["grok"](ROOT)
        efforts = {n: tomllib.loads(rendered[f"roles/{n}.toml"].decode())["reasoning_effort"]
                   for n in ("scout", "mech-executor", "security-reviewer")}
        self.assertEqual(efforts, {"scout": "low", "mech-executor": "low", "security-reviewer": "high"})

    def test_agent_model_must_match_binding(self) -> None:
        self.edit(self.root / "hosts" / "grok" / "frames" / "scout.md", "model: inherit", "model: grok-4.5")
        self.assert_rejected("scout")

    def test_read_only_role_must_use_read_only_capability(self) -> None:
        self.edit(self.binding, '[access.read-only]\ncapability_mode = "read-only"', '[access.read-only]\ncapability_mode = "all"')
        self.assert_rejected("capability_mode")

    def test_write_role_cannot_use_read_only_capability(self) -> None:
        self.edit(self.binding, '[roles.executor]\neffort = "medium"',
                  '[roles.executor]\neffort = "medium"\ncapability_mode = "read-only"')
        self.assert_rejected("executor")


class UpstreamLockTests(unittest.TestCase):
    def test_lock_pins_every_vendored_or_forked_host(self) -> None:
        lock = tomllib.loads((ROOT / "upstream.lock").read_text(encoding="utf-8"))
        self.assertEqual(lock["grok"]["kind"], "derived")
        self.assertEqual(lock["grok"]["upstream"], "Nanako0129/pilotfish-grok")
        self.assertEqual(lock["grok"]["version"], "v1.0.6")
        self.assertEqual(lock["claude"]["upstream"], "Nanako0129/pilotfish")
        self.assertEqual(lock["claude"]["version"], "v1.4.2")
        self.assertEqual(lock["codex"]["version"], "v1.3.0")
        for host, entry in lock.items():
            for key in ("upstream", "version", "kind", "source"):
                self.assertIn(key, entry, f"{host}.{key}")


if __name__ == "__main__":
    unittest.main()
