"""agy / grok / opencode 三個 host 的 render 測試共用的 helper。"""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import render  # noqa: E402

RENDER = ROOT / "tools" / "render.py"


# golden 內只存 sha256 的檔案（golden 根目錄起算的路徑）。這兩份是 hooks/shoal_guard.py 的完整副本，
# 存全文只會讓每次改 guard 都多兩份 3000 行的 diff。golden 改存 <path>.sha256，一行 hex digest。
GOLDEN_HASHED = frozenset({
    "plugins/claude-guard/hooks/shoal_guard.py",
    "hooks/shoal-grok/shoal_guard.py",
})
GUARD_SOURCE = "hooks/shoal_guard.py"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def golden_files(host: str) -> dict[str, bytes | str]:
    """golden 內容；GOLDEN_HASHED 的檔案以 hex digest（str）表示。"""
    golden = ROOT / "tests" / "golden" / host
    out: dict[str, bytes | str] = {}
    for p in golden.rglob("*"):
        if not p.is_file() or p.name == "SOURCE":
            continue
        rel = p.relative_to(golden).as_posix()
        if rel.endswith(".sha256") and rel[:-7] in GOLDEN_HASHED:
            out[rel[:-7]] = p.read_text(encoding="utf-8").strip()
        else:
            out[rel] = p.read_bytes()
    return out


def golden_view(files: dict[str, bytes]) -> dict[str, bytes | str]:
    """把實際輸出轉成與 golden_files 同形：GOLDEN_HASHED 的檔案換成 digest。"""
    return {rel: sha256_hex(data) if rel in GOLDEN_HASHED else data for rel, data in files.items()}


def assert_golden_equal(case: unittest.TestCase, actual: dict[str, bytes], golden: dict[str, bytes | str]) -> None:
    case.assertEqual(sorted(actual), sorted(golden))
    for rel, value in golden_view(actual).items():
        if rel in GOLDEN_HASHED:
            case.assertEqual(value, golden[rel],
                             f"{rel}: expected sha256 {golden[rel]}, actual {value}; diff against {GUARD_SOURCE}")
        else:
            case.assertEqual(value, golden[rel], rel)


def dist_files(host: str) -> dict[str, bytes]:
    dist = ROOT / render.DIST_DIRS[host]
    return {p.relative_to(dist).as_posix(): p.read_bytes() for p in dist.rglob("*") if p.is_file()}


def run_render(host: str, root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(RENDER), "--host", host, "--root", str(root), *flags],
                          capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


class HostRenderCase(unittest.TestCase):
    """子類設定 HOST、GOLDEN_COUNT、SOURCE_REFS；共用 golden 與 --check/--write 行為。"""

    HOST = ""
    GOLDEN_COUNT = 0
    SOURCE_REFS: tuple[str, ...] = ()
    # (dist 內要被改動的檔案, 來源檔（相對 hosts/<host>/src）)
    DIST_FILE = ""
    SRC_FILE = ""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
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

    # --- golden ---
    def test_render_is_byte_identical_to_golden(self) -> None:
        golden = golden_files(self.HOST)
        self.assertEqual(len(golden), self.GOLDEN_COUNT)
        assert_golden_equal(self, render.RENDERERS[self.HOST](ROOT), golden)

    def test_golden_records_source(self) -> None:
        source = (ROOT / "tests" / "golden" / self.HOST / "SOURCE").read_text(encoding="utf-8")
        for ref in self.SOURCE_REFS:
            self.assertRegex(source, rf"(?m)^ref: {ref}[0-9a-f]{{7}}$")

    def test_committed_dist_matches_golden(self) -> None:
        assert_golden_equal(self, dist_files(self.HOST), golden_files(self.HOST))

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
