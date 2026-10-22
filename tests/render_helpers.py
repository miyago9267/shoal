"""agy / grok / opencode 三個 host 的 render 測試共用的 helper。"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import render  # noqa: E402

RENDER = ROOT / "tools" / "render.py"


def run_render(host: str, root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(RENDER), "--host", host, "--root", str(root), *flags],
                          capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


class HostRenderCase(unittest.TestCase):
    """子類設定 HOST、DIST_FILE、SRC_FILE；共用 --check/--write 行為。"""

    HOST = ""
    # (dist 內要被改動的檔案, 來源檔（相對 hosts/<host>/src）)
    DIST_FILE = ""
    SRC_FILE = ""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
        shutil.copytree(ROOT / "prompts", self.root / "prompts")
        # grok 的 dist 內有 hooks/shoal_guard.py 的副本，來源是 repo 根的 hooks/shoal_guard.py。
        (self.root / "hooks").mkdir()
        shutil.copy(ROOT / "hooks" / "shoal_guard.py", self.root / "hooks" / "shoal_guard.py")
        # plugin/ 有 node_modules，與 render 無關，不複製。
        shutil.copytree(ROOT / "hosts" / self.HOST, self.root / "hosts" / self.HOST,
                        ignore=shutil.ignore_patterns("plugin"))
        self.dist = self.root / render.DIST_DIRS[self.HOST]
        self.binding = self.root / "hosts" / self.HOST / "binding.toml"

    def check(self) -> subprocess.CompletedProcess[str]:
        return run_render(self.HOST, self.root, "--check")

    def edit(self, path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def assert_rejected(self, expected: str) -> None:
        result = self.check()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(expected, result.stderr)

    # --- --check / --write ---
    def test_check_passes_when_dist_matches(self) -> None:
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_check_fails_when_one_byte_changes(self) -> None:
        target = self.dist / self.DIST_FILE
        target.write_bytes(target.read_bytes() + b"x")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn(self.DIST_FILE, result.stderr)

    def test_check_fails_on_extra_or_missing_file(self) -> None:
        (self.dist / "extra.md").write_text("x", encoding="utf-8", newline="\n")
        (self.dist / self.DIST_FILE).unlink()
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("多出: extra.md", result.stderr)
        self.assertIn(f"缺少: {self.DIST_FILE}", result.stderr)

    def test_check_fails_when_source_changes_without_rewriting_dist(self) -> None:
        src = self.root / "hosts" / self.HOST / "src" / self.SRC_FILE
        src.write_text(src.read_text(encoding="utf-8") + "extra line\n", encoding="utf-8", newline="\n")
        result = self.check()
        self.assertEqual(result.returncode, 1)

    def test_write_repairs_dist(self) -> None:
        (self.dist / self.DIST_FILE).write_bytes(b"broken")
        (self.dist / "extra.md").write_text("x", encoding="utf-8", newline="\n")
        self.assertEqual(run_render(self.HOST, self.root, "--write").returncode, 0)
        self.assertEqual(self.check().returncode, 0)
        self.assertFalse((self.dist / "extra.md").exists())

    # --- 共通驗證 ---
    def test_binding_must_declare_models_or_inherit(self) -> None:
        text = self.binding.read_text(encoding="utf-8").replace('selection = "inherit"\n', "")
        text = re.sub(r"(?ms)^\[models\]\n.*?(?=^\[|\Z)", "", text)
        self.binding.write_text(text, encoding="utf-8", newline="\n")
        self.assert_rejected("[models]")

    def test_every_role_needs_a_binding_or_omission(self) -> None:
        roles = self.root / "core" / "roles.toml"
        roles.write_text(roles.read_text(encoding="utf-8")
                         + '\n[roles.ghost]\naccess = "write"\ntier = "fast"\nsecurity = false\n', encoding="utf-8", newline="\n")
        self.assert_rejected("ghost")
