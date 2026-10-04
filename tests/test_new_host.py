"""tools/new_host.py 與端到端流程（new-host 的 N3）：scaffold 一個假 host，只填 [models] 與對應表的值，
不改任何 tools/ 檔案，render --write 與 --check 都成功，七個 role 都有輸出。
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from render_helpers import ROOT, render

NEW_HOST = ROOT / "tools" / "new_host.py"
CORE_ROLES = tuple(render.load_toml(ROOT / "core" / "roles.toml")["roles"])
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                          encoding="utf-8", env=ENV)


def tree_digest(path: Path) -> dict[str, str]:
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


class TempRepo(unittest.TestCase):
    """temp 複本：tools/ 與 core/（hosts/ 是空的），腳本都從複本執行，預設 --root 就是複本。"""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
        shutil.copytree(ROOT / "tools", self.root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "hosts").mkdir()
        self.host = self.root / "hosts" / "demo"

    def new_host(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run(self.root / "tools" / "new_host.py", *(args or ("demo",)))

    def render(self, *flags: str) -> subprocess.CompletedProcess[str]:
        return run(self.root / "tools" / "render.py", "--host", "demo", *flags)

    def fill(self, models: str, replacements: dict[str, str]) -> None:
        path = self.host / "binding.toml"
        text = path.read_text(encoding="utf-8")
        text, count = re.subn(r"(?m)^# \[models\]\n(?:# [^\n]*\n)*", models, text)
        self.assertEqual(count, 1)
        for old, new in replacements.items():
            self.assertIn(old, text)
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8", newline="\n")


class ScaffoldTests(TempRepo):
    def test_creates_the_skeleton(self) -> None:
        result = self.new_host()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.host / "frames" / "default.md").is_file())
        self.assertTrue((self.host / "addenda").is_dir())
        self.assertEqual((self.host / "frames" / "default.md").read_text(encoding="utf-8"), "{{role_body}}")
        binding = render.load_toml(self.host / "binding.toml")
        self.assertEqual(binding["renderer"], "generic-md")
        self.assertEqual(binding["role_text"], "core")
        self.assertNotIn("models", binding)
        self.assertEqual(set(binding["access"]), {"read-only", "write", "verify"})
        self.assertEqual(binding["capabilities"], {"web": {}})
        self.assertEqual(list(binding["roles"]), list(CORE_ROLES))
        self.assertTrue(all(spec["description"] for spec in binding["roles"].values()))
        self.assertEqual(binding["output"]["permissions"], {"tools": {"type": "list"}})
        self.assertEqual(binding["output"]["role_fields"], ["effort"])
        self.assertIn("role.effort", [f.get("source") for f in binding["output"]["frontmatter"]])
        self.assertTrue(all(spec["effort"] for spec in binding["roles"].values()))
        self.assertIn("# [models]", (self.host / "binding.toml").read_text(encoding="utf-8"))

    def test_existing_host_is_never_overwritten(self) -> None:
        self.assertEqual(self.new_host().returncode, 0)
        marker = self.host / "binding.toml"
        marker.write_text("# mine\n", encoding="utf-8", newline="\n")
        result = self.new_host()
        self.assertEqual(result.returncode, 2)
        self.assertIn("已存在", result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "# mine\n")

    def test_builtin_names_and_bad_names_are_rejected(self) -> None:
        for name in ("claude", "agy", "Bad_Name", "-x", "a b", "../x"):
            with self.subTest(name=name):
                result = self.new_host(name)
                self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(sorted(p.name for p in (self.root / "hosts").iterdir()), [])

    def test_check_asks_for_models_until_they_are_filled(self) -> None:
        self.new_host()
        for flag in ("--check", "--write", "--explain"):
            with self.subTest(flag=flag):
                result = self.render(flag)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("[models]", result.stderr)
        self.assertFalse((self.host / "dist").exists())


class EndToEndTests(TempRepo):
    def test_fill_models_and_tool_names_then_render_without_touching_tools(self) -> None:
        before = tree_digest(self.root / "tools")
        self.assertEqual(self.new_host().returncode, 0)
        self.fill('[models]\n"anthropic/haiku" = "haiku"\n"anthropic/sonnet" = "sonnet"\n"anthropic/opus" = "opus"\n',
                  {'tools = ["read", "grep", "glob"]': 'tools = ["view", "search"]',
                   'tools = ["read", "grep", "glob", "bash"]': 'tools = ["view", "search", "shell"]'})
        binding = self.host / "binding.toml"
        text = binding.read_text(encoding="utf-8")
        text, count = re.subn(r'(\[roles\.scout\]\n[^\[]*?)effort = "medium"', r'\1effort = "low"', text)
        self.assertEqual(count, 1)
        binding.write_text(text, encoding="utf-8", newline="\n")
        result = self.render("--write")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.render("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.render("--explain").returncode, 0)

        dist = self.host / "dist" / "agents"
        self.assertEqual(sorted(p.name for p in dist.iterdir()), sorted(f"{r}.md" for r in CORE_ROLES))
        scout = (dist / "scout.md").read_text(encoding="utf-8")
        self.assertTrue(scout.startswith("---\nname: scout\ndescription: TODO"), scout)
        self.assertIn("\nmodel: sonnet\neffort: low\ntools: view, search\n---\n\nYou are a fast, read-only scout", scout)
        self.assertIn("\ntools: view, search, shell\n", (dist / "verifier.md").read_text(encoding="utf-8"))
        self.assertNotIn("tools:", (dist / "executor.md").read_text(encoding="utf-8"))
        for role in CORE_ROLES:
            expected = "low" if role == "scout" else "medium"
            self.assertIn(f"\neffort: {expected}\n", (dist / f"{role}.md").read_text(encoding="utf-8"))
        self.assertEqual(tree_digest(self.root / "tools"), before)

    def test_host_without_effort_deletes_the_declarations(self) -> None:
        self.new_host()
        self.fill('selection = "inherit"\n', {'role_fields = ["effort"]\n': "", 'effort = "medium"\n': ""})
        binding = self.host / "binding.toml"
        text = re.sub(r'\[\[output\.frontmatter\]\]\nkey = "effort"\n[^\[]*', "", binding.read_text(encoding="utf-8"))
        binding.write_text(text, encoding="utf-8", newline="\n")
        self.assertEqual(self.render("--write").returncode, 0)
        self.assertNotIn("effort", (self.host / "dist" / "agents" / "scout.md").read_text(encoding="utf-8").split("---")[1])

    def test_inherit_selection_also_renders(self) -> None:
        self.new_host()
        self.fill('selection = "inherit"\n', {})
        self.assertEqual(self.render("--write").returncode, 0)
        self.assertIn("\nmodel: inherit\n", (self.host / "dist" / "agents" / "scout.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
