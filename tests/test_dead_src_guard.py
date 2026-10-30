"""R3：core 會產生的輸出，host src/ 內不能再有同路徑的檔案（死檔）。"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from render_helpers import ROOT, run_render

# (host, 放進 src 的檔案, 錯誤訊息必須指名的路徑)
DEAD = (
    ("agy", "rules/shoal-agy.md", "hosts/agy/src/rules/shoal-agy.md"),
    ("claude", "agents/scout.md", "hosts/claude/src/agents/scout.md"),
    ("claude", "claude-md.bootstrap.md", "hosts/claude/src/claude-md.bootstrap.md"),
    ("opencode", "roles/scout.md", "hosts/opencode/src/roles/scout.md"),
)
# legacy host 仍在使用的 src 檔，不是死檔。
LIVE = (
    "hosts/grok/src/rules/shoal-grok.md",
    "hosts/claude/src/agents/Explore.md",
    "hosts/codex/src/agents/sol-executor.md",
)


class DeadSrcGuardTests(unittest.TestCase):
    def temp_root(self, host: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        shutil.copytree(ROOT / "core", root / "core")
        shutil.copytree(ROOT / "prompts", root / "prompts")
        (root / "hooks").mkdir()
        shutil.copy(ROOT / "hooks" / "shoal_guard.py", root / "hooks" / "shoal_guard.py")
        shutil.copytree(ROOT / "hosts" / host, root / "hosts" / host, ignore=shutil.ignore_patterns("plugin"))
        return root

    def test_dead_file_in_src_is_rejected_with_its_path(self) -> None:
        for host, rel, named in DEAD:
            with self.subTest(named=named):
                root = self.temp_root(host)
                dead = root / "hosts" / host / "src" / rel
                dead.parent.mkdir(parents=True, exist_ok=True)
                dead.write_text("stale\n", encoding="utf-8", newline="\n")
                result = run_render(host, root, "--check")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(named, result.stderr)

    def test_real_tree_renders_and_live_legacy_files_do_not_trigger(self) -> None:
        for rel in LIVE:
            self.assertTrue((ROOT / rel).is_file(), rel)
        for host in ("claude", "codex", "agy", "grok", "opencode", "claude-plugin"):
            with self.subTest(host=host):
                result = run_render(host, ROOT, "--check")
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
