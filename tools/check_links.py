#!/usr/bin/env python3
"""檢查指定 Markdown 檔案中的相對連結是否指到存在的路徑（去掉 #anchor 與 ?query）。

用法：python3 tools/check_links.py [--root DIR] [FILE ...]
不給 FILE 時檢查 DEFAULT_FILES；有任何缺失就 exit 1。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

DEFAULT_FILES = (
    "README.md",
    "hosts/codex/README.md",
    "hosts/codex/CHANGELOG.md",
    "docs/README.zh-TW.md",
    "docs/README.zh-CN.md",
)

FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_LINK_RE = re.compile(r"\]\(\s*<?([^)\s>]+)")
HTML_ATTR_RE = re.compile(r"""\b(?:src|href)=["']([^"']+)["']""")
REFERENCE_RE = re.compile(r"^\s*\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)")
EXTERNAL_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)")


def relative_targets(text: str) -> list[tuple[int, str]]:
    """回傳 (行號, 相對路徑) 清單；略過 fenced code、外部 URL 與純 anchor。"""
    found: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        candidates = INLINE_LINK_RE.findall(line) + HTML_ATTR_RE.findall(line)
        reference = REFERENCE_RE.match(line)
        if reference:
            candidates.append(reference.group(1))
        for raw in candidates:
            if EXTERNAL_RE.match(raw) or raw.startswith("#"):
                continue
            path = unquote(re.split(r"[#?]", raw, maxsplit=1)[0])
            if path:
                found.append((number, path))
    return found


def check(root: Path, files: list[str]) -> list[str]:
    """回傳缺失清單；檔案本身不存在也算缺失。"""
    missing: list[str] = []
    for name in files:
        source = root / name
        if not source.is_file():
            missing.append(f"{name}: 檔案不存在")
            continue
        text = source.read_text(encoding="utf-8")
        for number, target in relative_targets(text):
            if not (source.parent / target).exists():
                missing.append(f"{name}:{number}: {target}")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()
    files = args.files or list(DEFAULT_FILES)
    missing = check(args.root, files)
    for item in missing:
        print(f"missing: {item}", file=sys.stderr)
    print(f"checked {len(files)} files, {len(missing)} missing")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
