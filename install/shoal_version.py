"""shoal 自己的版本規則：beta 與 stable 兩個 channel，先比 channel 再比數字。

- beta：`X.Y.Z-beta`（或其他 SemVer prerelease 後綴），以及沒有後綴、不超過
  LEGACY_BETA_MAX 的舊版本（1.x 到 3.11.1）。
- stable：沒有後綴的 `X.Y.Z`，而且不是舊版本。
- 沒有後綴、數字又落在舊版範圍（例如未來的 stable 1.0.0）時，字串本身分不出來，
  由 stable epoch marker 決定：repo 頂層的 `CHANNEL` 檔寫 `stable` 才算 stable，
  沒有這個檔就是 beta。VERSION 保持單純字串，既有讀取端都不用改格式。

只用 stdlib；install、tools 與測試共用。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

LEGACY_BETA_MAX = (3, 11, 1)
CHANNEL_FILE = "CHANNEL"
BETA, STABLE = "beta", "stable"

VERSION_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
# 文字比對用（marker、regex 驗證）：數字三段，可帶 -beta 之類的後綴。
VERSION_PATTERN = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?"

Key = Tuple[int, int, int, int, int, Tuple[Tuple[int, int, str], ...]]


def parse(value: str) -> Optional[Tuple[Tuple[int, int, int], Optional[str]]]:
    """`((major, minor, patch), prerelease 或 None)`；格式不合法回 None。"""
    match = VERSION_RE.fullmatch(value.strip()) if isinstance(value, str) else None
    if match is None:
        return None
    nums = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return nums, match.group(4)


def channel(value: str, *, stable_epoch: bool = False) -> Optional[str]:
    """回傳 "beta" 或 "stable"；stable_epoch＝來源有 stable marker（CHANNEL 檔）。"""
    parsed = parse(value)
    if parsed is None:
        return None
    nums, pre = parsed
    if pre is not None:
        return BETA
    if stable_epoch or nums > LEGACY_BETA_MAX:
        return STABLE
    return BETA


def key(value: str, *, stable_epoch: bool = False) -> Optional[Key]:
    """可排序的 key：channel（beta < stable）、數字、正式 > prerelease、prerelease 識別字。"""
    parsed = parse(value)
    if parsed is None:
        return None
    nums, pre = parsed
    rank = 1 if channel(value, stable_epoch=stable_epoch) == STABLE else 0
    if pre is None:
        return (rank, *nums, 1, ())
    ids = []
    for ident in pre.split("."):
        if ident.isdigit():
            if len(ident) > 1 and ident.startswith("0"):
                return None
            ids.append((0, int(ident), ""))
        else:
            ids.append((1, 0, ident))
    return (rank, *nums, 0, tuple(ids))


def compare(a: str, b: str, *, a_stable: bool = False, b_stable: bool = False) -> int:
    """a < b 回 -1、相等 0、a > b 回 1；格式不合法丟 ValueError。"""
    ka, kb = key(a, stable_epoch=a_stable), key(b, stable_epoch=b_stable)
    if ka is None or kb is None:
        raise ValueError(f"malformed shoal version: {a!r} / {b!r}")
    return (ka > kb) - (ka < kb)


def is_channel_switch(
    installed: str, source: str, *, source_stable: bool = False
) -> bool:
    """已裝的是 beta、來源是 stable：plugin manager 用純 SemVer 會把它當降版，要先移除再裝。"""
    return (
        channel(installed) == BETA
        and channel(source, stable_epoch=source_stable) == STABLE
    )


def stable_marker(text: Optional[str]) -> bool:
    """CHANNEL 檔內容是否宣告 stable。"""
    return (text or "").strip() == STABLE


def repo_is_stable(root: Path) -> bool:
    """repo 頂層 CHANNEL 檔宣告 stable 才算 stable epoch；沒有檔案就是 beta。"""
    try:
        return stable_marker((Path(root) / CHANNEL_FILE).read_text(encoding="utf-8"))
    except OSError:
        return False
