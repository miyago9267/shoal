#!/usr/bin/env python3
"""shoal-rebrand 的 rename-aware 檢查（docs/specs/shoal-rebrand，SPEC N7）。

用法：
  python3 tools/check_rename.py [--base-ref 21d5986] [--root DIR] [--lock PATH]

對 LOCK.json 的每個 surface：取 base ref 裡「舊路徑」的內容（舊路徑來自 base 的 LOCK.json，
以 surface id 對應），套用 docs/specs/shoal-rebrand/RENAME.md 的替換規則與版本號 2.0.0，
必須與新路徑的檔案逐位元組相同。逐 surface 印出 OK 或 DIFF（附 diff 節錄）。LOCK 的
mirrors 與 required_fragments 也用同一組規則比對。有任何 DIFF 時 exit 1。

替換規則寫成下面的資料（RULES、PROTECTED、VERSION_RULES）；tools/scan_legacy_names.py
與改名時的一次性 sweep 共用 apply_rename / rename_path，所以三者不會分岔。

stdlib only。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
LOCK_RELATIVE = "docs/specs/prompt-document-lock/LOCK.json"
DEFAULT_BASE_REF = "21d5986"
NEW_VERSION = "2.0.0"

# ---- LEGACY_: 舊名（2.0.0 之前的產品名）只出現在這幾個常數；tools/scan_legacy_names.py 略過它們 ----
# 上游的真實名稱、網址，以及指向「保留的歷史文件」的路徑：原文不動（RENAME「例外」）。
LEGACY_PROTECTED = [
    r"Nanako0129/pilotfish(?:-grok)?",
    r"miyago9267/pilotfish-codex",
    # 指向 docs/specs、docs/plans、docs/benchmarks 歷史紀錄的路徑（檔名保留舊名，改了連結會斷）
    r"docs/(?:specs|plans|benchmarks)/[^\s)\]`\"'<>]*[Pp][Ii][Ll][Oo][Tt][Ff][Ii][Ss][Hh][^\s)\]`\"'<>]*",
    # 歷史 benchmark 工具、schema 與其資料檔名
    r"evaluate_pilotfish_value_matrix",
    r"pilotfish-value-matrix-v1",
    r"role-fitness-v1-pilotfish-value-matrix",
    r"PILOTFISH-VALUE-MATRIX",
    # 上游原文 fixture
    r"rules\.pilotfish-grok\.upstream-v1\.0\.6\.txt",
]

# 具名規則：先於通用規則、依序套用。對應 RENAME.md 規則表中不是「舊名→shoal」的列。
LEGACY_RULES: list[tuple[str, str]] = [
    # Claude marker：`<!-- pilotfish v…` -> `<!-- shoal-claude v…`
    (r"<!-- pilotfish v", "<!-- shoal-claude v"),
    # PILOTFISH_CLAUDE_ROOT / PILOTFISH_OPENCODE_SOURCE -> SHOAL_ROOT
    (r"\bPILOTFISH_(?:CLAUDE_ROOT|OPENCODE_SOURCE)\b", "SHOAL_ROOT"),
    # OpenCode 去重 key
    (r"shoal\.pilotfish-opencode\.route-registered", "shoal.opencode.route-registered"),
    # projection：autoroute v1 與 v2 都換成新的獨立 projection
    (r"pilotfish-autoroute-v[12]\b", "shoal-autoroute-v1"),
]

# 版本號改為 2.0.0（N6）：marker 與 Codex plugin manifest 的 version。
MARKER_VERSION = re.compile(
    r"(<!-- shoal(?:-(?:claude|codex|grok|agy))? v)\d+\.\d+\.\d+\S*( -->)"
)
JSON_VERSION = re.compile(r'("version":\s*")[^"]+(")')
LEGACY_VERSION_JSON_PATHS = (
    "/pilotfish-codex/.codex-plugin/plugin.json",
    "/shoal-codex/.codex-plugin/plugin.json",
)

_SENTINEL = ("\ue000", "\ue001")
LEGACY_NAME = re.compile(r"PILOTFISH|Pilotfish|pilotfish")
LEGACY_NAME_FORMS = (("PILOTFISH", "SHOAL"), ("Pilotfish", "Shoal"), ("pilotfish", "shoal"))
# 句首判斷：行首只有 markdown／註解標記，或前面是句號、冒號、開引號
_MARKERS_ONLY = re.compile(r"[\s>*#\-+|\"'`(\[\d./]*")
_SENTENCE_END = re.compile(r"[.!?:。！？：][)\]\"'”’`*]*\s*$")
_OPEN_QUOTE = re.compile(r"[\"'“‘`(\[]\**$")


def _is_sentence_start(text: str, index: int) -> bool:
    line_start = text.rfind("\n", 0, index) + 1
    prefix = text[line_start:index]
    stripped = prefix.strip()
    if stripped:
        if _MARKERS_ONLY.fullmatch(prefix):
            return True
        return bool(_SENTENCE_END.search(prefix) or _OPEN_QUOTE.search(prefix.rstrip()))
    # 行首（可有縮排）：看上一行是否結束了一個句子
    if line_start == 0:
        return True
    previous = text[: line_start - 1].rstrip(" \t").rsplit("\n", 1)[-1].strip()
    if not previous:
        return True
    return bool(_SENTENCE_END.search(previous)) or previous.startswith(
        ("#", "```", "---")
    )


def _generic(match: re.Match[str], text: str) -> str:
    word = match.group(0)
    if word == LEGACY_NAME_FORMS[0][0]:
        return LEGACY_NAME_FORMS[0][1]
    if word == LEGACY_NAME_FORMS[2][0]:
        return LEGACY_NAME_FORMS[2][1]
    start, end = match.span()
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    if before.isalpha() or after.isalpha():  # CamelCase 識別字
        return "Shoal"
    if re.match(r"-[A-Za-z]", text[end : end + 2]):  # 例：舊名-Codex
        return "Shoal"
    return "Shoal" if _is_sentence_start(text, start) else "shoal"


def apply_rename(text: str, path: Optional[str] = None) -> str:
    """套用 RENAME.md 的內容替換與版本號。path 只用來決定 JSON version 規則。"""
    saved: list[str] = []

    def protect(match: re.Match[str]) -> str:
        saved.append(match.group(0))
        return f"{_SENTINEL[0]}{len(saved) - 1}{_SENTINEL[1]}"

    for pattern in LEGACY_PROTECTED:
        text = re.sub(pattern, protect, text)
    for pattern, repl in LEGACY_RULES:
        text = re.sub(pattern, repl, text)
    text = LEGACY_NAME.sub(lambda m: _generic(m, text), text)
    if path is not None and path.endswith(".md"):
        text = MARKER_VERSION.sub(rf"\g<1>{NEW_VERSION}\g<2>", text)
    if path is not None and path.endswith(LEGACY_VERSION_JSON_PATHS):
        text = JSON_VERSION.sub(rf"\g<1>{NEW_VERSION}\g<2>", text)
    return re.sub(
        f"{_SENTINEL[0]}(\\d+){_SENTINEL[1]}", lambda m: saved[int(m.group(1))], text
    )


def rename_path(path: str) -> str:
    """檔案與目錄名：舊名 -> shoal（受保護的歷史路徑不動）。"""
    saved: list[str] = []

    def protect(match: re.Match[str]) -> str:
        saved.append(match.group(0))
        return f"{_SENTINEL[0]}{len(saved) - 1}{_SENTINEL[1]}"

    for pattern in LEGACY_PROTECTED:
        path = re.sub(pattern, protect, path)
    for old, new in LEGACY_NAME_FORMS:
        path = path.replace(old, new)
    return re.sub(
        f"{_SENTINEL[0]}(\\d+){_SENTINEL[1]}", lambda m: saved[int(m.group(1))], path
    )


# ---- 檢查 ----
def _git_show(root: Path, ref: str, path: str) -> Optional[bytes]:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(root), "show", f"{ref}:{path}"],
        capture_output=True,
        timeout=60,
    )
    return result.stdout if result.returncode == 0 else None


def _excerpt(expected: str, actual: str, limit: int = 12) -> list[str]:
    diff = difflib.unified_diff(
        expected.splitlines(),
        actual.splitlines(),
        "expected (rename of base)",
        "actual (working tree)",
        lineterm="",
        n=1,
    )
    lines = list(diff)
    more = len(lines) - limit
    return lines[:limit] + ([f"... ({more} more diff lines)"] if more > 0 else [])


def check(
    root: Path, base_ref: str, lock_path: str = LOCK_RELATIVE
) -> tuple[list[str], int]:
    """回傳 (輸出行, DIFF 數)。"""
    out: list[str] = []
    bad = 0
    base_raw = _git_show(root, base_ref, lock_path)
    if base_raw is None:
        return [f"DIFF  {lock_path}: base ref {base_ref} 沒有 LOCK.json"], 1
    base = json.loads(base_raw.decode("utf-8"))
    current = json.loads((root / lock_path).read_text(encoding="utf-8"))
    base_surfaces = {s["id"]: s for s in base["surfaces"]}
    for surface in current["surfaces"]:
        old = base_surfaces.get(surface["id"])
        label = f"{surface['id']} ({surface['path']})"
        if old is None:
            out.append(f"DIFF  {label}: base 的 LOCK.json 沒有這個 surface id")
            bad += 1
            continue
        before = _git_show(root, base_ref, old["path"])
        target = root / surface["path"]
        if before is None or not target.is_file():
            out.append(f"DIFF  {label}: 舊路徑 {old['path']} 或新檔案不存在")
            bad += 1
            continue
        expected = apply_rename(before.decode("utf-8"), old["path"])
        actual = target.read_bytes().decode("utf-8")
        problems: list[str] = []
        if expected != actual:
            problems += _excerpt(expected, actual)
        if rename_path(old["path"]) != surface["path"]:
            problems.append(
                f"path: {old['path']} -> {surface['path']} 不符 RENAME 規則"
            )
        want = [apply_rename(f) for f in old["required_fragments"]]
        if want != surface["required_fragments"]:
            problems.append("required_fragments 不等於 base 套用 RENAME 的結果")
        if problems:
            bad += 1
            out.append(f"DIFF  {label}")
            out += [f"      {line}" for line in problems]
        else:
            out.append(f"OK    {label}")
    want_mirrors = [
        {"left": rename_path(m["left"]), "right": rename_path(m["right"])}
        for m in base.get("mirrors", [])
    ]
    if want_mirrors == current.get("mirrors"):
        out.append("OK    mirrors")
    else:
        bad += 1
        out.append("DIFF  mirrors: 不等於 base 套用 RENAME 的結果")
    return out, bad


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], allow_abbrev=False
    )
    parser.add_argument(
        "--base-ref", default=DEFAULT_BASE_REF, help=f"預設 {DEFAULT_BASE_REF}"
    )
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument(
        "--lock", default=LOCK_RELATIVE, help="LOCK.json 的 repo 相對路徑"
    )
    args = parser.parse_args(argv)
    lines, bad = check(args.root.resolve(), args.base_ref, args.lock)
    print("\n".join(lines))
    print(f"rename check: {'FAILED' if bad else 'ok'} ({bad} diff)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
