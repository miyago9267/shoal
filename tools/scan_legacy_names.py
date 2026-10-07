#!/usr/bin/env python3
"""產品面舊名掃描（docs/specs/shoal-rebrand/RENAME.md「掃描範圍」，SPEC N1）。

用法：
  python3 tools/scan_legacy_names.py [--root DIR]

掃描 git 追蹤的檔案，找不分大小寫的 2.0.0 之前的產品名。有任何命中就 exit 1，並印出
`path:line: text`。RENAME 列出的例外不掃：

  - docs/specs/、docs/benchmarks/、docs/plans/ 的歷史紀錄、tests/golden/（由 render 產生）
  - CHANGELOG.md 與 hosts/codex/CHANGELOG.md 在 v2.0.0 以前的段落
  - LICENSE、ATTRIBUTION.md、upstream.lock、README「來源與致謝」一節
  - 歷史 benchmark 工具 install/evaluate_pilotfish_value_matrix.py、上游原文 fixture
  - 遷移用的舊名清單：LEGACY_ 常數所在的行（Python 的整個 LEGACY_ 賦值陳述式），以及
    tests/fixtures/legacy_install/ 的舊名安裝 fixture
  - 上游的真實名稱與網址，以及指向保留的歷史文件的路徑（tools/check_rename.py 的
    LEGACY_PROTECTED，從行內剔除後再比對）

stdlib only。
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from check_rename import LEGACY_PROTECTED  # noqa: E402

# 掃的字：用兩段字串組成，這個檔案本身不出現舊名。
NAME = re.compile("pilot" + "fish", re.IGNORECASE)

EXEMPT_PREFIXES = (
    "docs/specs/",
    "docs/benchmarks/",
    "docs/plans/",
    "tests/golden/",
    ".reticle/",
    "tests/fixtures/legacy_install/",
)
EXEMPT_FILES = frozenset(
    {
        "LICENSE",
        "ATTRIBUTION.md",
        "upstream.lock",
        "install/evaluate_" + "pilot" + "fish_value_matrix.py",
        "tests/fixtures/grok/rules." + "pilot" + "fish-grok.upstream-v1.0.6.txt",
    }
)
HISTORICAL_CHANGELOGS = frozenset({"CHANGELOG.md", "hosts/codex/CHANGELOG.md"})
CREDIT_FILE = "README.md"
CREDIT_HEADING = "## 來源與致謝"

_PROTECTED = [re.compile(p) for p in LEGACY_PROTECTED]
_VERSION_HEADING = re.compile(r"^## v(\d+)\.(\d+)\.(\d+)")
_OPENERS = ("[", "(", "{", "=")
_CLOSERS = ("]", ")", "}")


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout
    return [f for f in out.decode("utf-8").split("\0") if f]


def _python_legacy_lines(text: str) -> set[int]:
    """整個以 LEGACY_ 名稱賦值的陳述式涵蓋的行（1-based）。"""
    lines: set[int] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return lines
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        if any(isinstance(t, ast.Name) and t.id.startswith("LEGACY_") for t in targets):
            lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return lines


def _generic_legacy_lines(lines: list[str]) -> set[int]:
    """其他語言：含 LEGACY_ 的行；那行以開括號或 = 結尾時，延伸到縮排相同的收尾括號行。"""
    exempt: set[int] = set()
    i = 0
    while i < len(lines):
        if "LEGACY_" in lines[i]:
            exempt.add(i + 1)
            if lines[i].rstrip().endswith(_OPENERS):
                indent = len(lines[i]) - len(lines[i].lstrip())
                j = i + 1
                while j < len(lines):
                    exempt.add(j + 1)
                    stripped = lines[j].lstrip()
                    if (
                        len(lines[j]) - len(stripped)
                    ) <= indent and stripped.startswith(_CLOSERS):
                        break
                    j += 1
                i = j
        i += 1
    return exempt


def _skipped_ranges(path: str, lines: list[str]) -> set[int]:
    """整段不掃的行（1-based）：CHANGELOG 的 v2.0.0 以前、README 的致謝一節。"""
    skip: set[int] = set()
    if path in HISTORICAL_CHANGELOGS:
        for index, line in enumerate(lines):
            match = _VERSION_HEADING.match(line)
            if match and tuple(int(g) for g in match.groups()) < (2, 0, 0):
                skip.update(range(index + 1, len(lines) + 1))
                break
    if path == CREDIT_FILE:
        start = next(
            (i for i, line in enumerate(lines) if line.startswith(CREDIT_HEADING)), None
        )
        if start is not None:
            end = next(
                (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
                len(lines),
            )
            skip.update(range(start + 1, end + 1))
    return skip


def scan_file(path: str, text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    exempt = _skipped_ranges(path, lines)
    exempt |= _python_legacy_lines(text) if path.endswith(".py") else set()
    exempt |= _generic_legacy_lines(lines)
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        if number in exempt or not NAME.search(line):
            continue
        cleaned = line
        for pattern in _PROTECTED:
            cleaned = pattern.sub("", cleaned)
        if NAME.search(cleaned):
            hits.append((number, line.strip()))
    return hits


def scan(root: Path) -> list[str]:
    found: list[str] = []
    for path in tracked_files(root):
        if path in EXEMPT_FILES or path.startswith(EXEMPT_PREFIXES):
            continue
        target = root / path
        if not target.is_file() or target.is_symlink():
            continue
        raw = target.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            if NAME.search(raw.decode("latin-1")):
                found.append(f"{path}: binary file contains a legacy name")
            continue
        if NAME.search(path):
            found.append(f"{path}: file name contains a legacy name")
        for number, line in scan_file(path, text):
            found.append(f"{path}:{number}: {line[:160]}")
    return found


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], allow_abbrev=False
    )
    parser.add_argument("--root", type=Path, default=REPO)
    args = parser.parse_args(argv)
    hits = scan(args.root.resolve())
    if hits:
        print("\n".join(hits))
    print(f"legacy name scan: {len(hits)} hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
