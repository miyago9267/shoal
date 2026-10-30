from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import render  # noqa: E402

RENDER = ROOT / "tools" / "render.py"


def run_render(root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RENDER), "--host", "claude", "--root", str(root), *flags],
        capture_output=True,
        text=True,
        # Windows 預設 cp1252，強制 UTF-8 才讀得到中文輸出
        encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


class HostVersionTests(unittest.TestCase):
    """Claude host 版本的正式位置是 hosts/claude/VERSION；所有 marker 與記錄都要等於它（Decision 6）。"""

    VERSION = (ROOT / "hosts" / "claude" / "VERSION").read_text(encoding="utf-8").strip()
    SKILL = "skills/shoal-orchestration/SKILL.md"

    def test_version_file_format(self) -> None:
        self.assertRegex(self.VERSION, r"^\d+\.\d+\.\d+(?:-beta)?$")

    def test_upstream_lock_and_readme_record_the_version(self) -> None:
        lock = tomllib.loads((ROOT / "upstream.lock").read_text(encoding="utf-8"))
        self.assertEqual(lock["claude"]["marker_version"], self.VERSION)
        # 版本表在 README 改成產品首頁後移到 docs/reference.md。
        readme = (ROOT / "docs" / "reference.md").read_text(encoding="utf-8")
        self.assertRegex(readme, rf"(?m)^\| claude host \| {re.escape(self.VERSION)}")


class CheckCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
        shutil.copytree(ROOT / "prompts", self.root / "prompts")
        shutil.copytree(ROOT / "hosts" / "claude", self.root / "hosts" / "claude")

    def test_check_passes_when_dist_matches(self) -> None:
        result = run_render(self.root, "--check")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_check_does_not_compare_a_dist_directory(self) -> None:
        # claude 沒有 committed dist；即使目錄裡有東西，--check 也只驗證 render 成功。
        dist = self.root / "hosts" / "claude" / "dist"
        (dist / "agents").mkdir(parents=True)
        (dist / "agents" / "scout.md").write_bytes(b"not the render")
        self.assertEqual(run_render(self.root, "--check").returncode, 0)

    def test_write_creates_nothing(self) -> None:
        result = run_render(self.root, "--write")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "hosts" / "claude" / "dist").exists())


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
        shutil.copytree(ROOT / "prompts", self.root / "prompts")
        shutil.copytree(ROOT / "hosts" / "claude", self.root / "hosts" / "claude")
        self.roles = self.root / "core" / "roles.toml"
        self.binding = self.root / "hosts" / "claude" / "binding.toml"

    def assert_rejected(self, expected: str) -> None:
        result = run_render(self.root, "--check")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(expected, result.stderr)

    def edit(self, path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def test_security_role_on_frontier_tier_skips_flagged_model(self) -> None:
        # fable 帶 refuses_defensive_security，frontier 的 security role 改選次高的 opus，與 dist 一致
        self.edit(
            self.roles,
            '[roles.security-reviewer]\naccess = "read-only"\ntier = "strong"',
            '[roles.security-reviewer]\naccess = "read-only"\ntier = "frontier"',
        )
        self.assertEqual(run_render(self.root, "--check").returncode, 0)
        self.assertIn(b"\nmodel: opus\n", render.RENDERERS["claude"](self.root)["agents/security-reviewer.md"])

    def test_read_only_role_must_use_tools_allowlist(self) -> None:
        self.edit(self.binding, '[access.read-only]\ntools = ["Read", "Glob", "Grep"]',
                  '[access.read-only]\ndisallowedTools = ["Agent"]')
        self.assert_rejected("scout")

    def test_read_only_role_cannot_include_write_tools(self) -> None:
        self.edit(self.binding, '[access.read-only]\ntools = ["Read", "Glob", "Grep"]',
                  '[access.read-only]\ntools = ["Read", "Bash", "Edit"]')
        self.assert_rejected("Bash")

    def test_role_override_cannot_give_read_only_role_write_tools(self) -> None:
        self.edit(self.binding, '[roles.scout]\neffort = "low"\n', '[roles.scout]\neffort = "low"\ntools = ["Read", "Write"]\n')
        self.assert_rejected("Write")
        self.edit(self.binding, 'tools = ["Read", "Write"]\n', 'disallowedTools = ["Agent"]\n')
        self.assert_rejected("scout")

    def test_every_role_needs_a_binding(self) -> None:
        self.roles.write_text(
            self.roles.read_text(encoding="utf-8")
            + '\n[roles.ghost]\naccess = "write"\ntier = "fast"\nsecurity = false\n',
            encoding="utf-8", newline="\n")
        self.assert_rejected("ghost")


class RolesCatalogTests(unittest.TestCase):
    def test_roles_toml_has_no_model_names(self) -> None:
        text = (ROOT / "core" / "roles.toml").read_text(encoding="utf-8").lower()
        for needle in ("opus", "sonnet", "haiku", "fable", "gpt-", "gemini", "claude"):
            self.assertNotIn(needle, text)

    def test_catalog_shape(self) -> None:
        roles = render.load_toml(ROOT / "core" / "roles.toml")["roles"]
        self.assertNotIn("Explore", roles)
        self.assertEqual(
            {n for n, r in roles.items() if r["security"]},
            {"security-reviewer", "security-executor"},
        )
        self.assertTrue(all(r["access"] in render.ACCESS and r["tier"] in render.TIERS for r in roles.values()))


if __name__ == "__main__":
    unittest.main()
