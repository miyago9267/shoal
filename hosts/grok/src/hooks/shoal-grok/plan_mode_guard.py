#!/usr/bin/env python3
"""shoal-grok 的 plan mode 防護（shoal docs/specs/grok-workflow R12）。

plan mode 不會擋 subagent 的寫入（Grok 19-plan-mode.md）。permissionMode 為 plan 時，
這支 PreToolUse hook 拒絕 spawn_subagent 產生可寫入的 subagent。可寫入的判斷順序：
1. toolInput.capability_mode 有值時以它為準；
2. 缺值時讀 <grok-home>/roles/<subagent_type>.toml 的 default_capability_mode；
3. 內建 explore、plan 視為不可寫入，general-purpose 視為可寫入；
4. 任何解析失敗都放行（fail-open，exit 0 且不輸出）。
capability mode 的寫入定義與 Grok 文件一致：read-write、all 可編輯檔案；read-only、
execute 不能（plan mode 本身也不檢查 shell），所以放行。
grok home 的優先順序：--grok-home 參數、SHOAL_GROK_HOME、GROK_HOME、~/.grok。
只用標準函式庫；tomllib 需要 Python 3.11，載入失敗時走 fail-open。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

WRITABLE = {"read-only": False, "execute": False, "read-write": True, "all": True}
BUILTIN_TYPES = {"explore": False, "plan": False, "general-purpose": True}
TYPE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def grok_home(argv: list[str]) -> Path:
    for i, arg in enumerate(argv):
        if arg == "--grok-home" and i + 1 < len(argv):
            return Path(argv[i + 1]).expanduser()
        if arg.startswith("--grok-home="):
            return Path(arg.split("=", 1)[1]).expanduser()
    for name in ("SHOAL_GROK_HOME", "GROK_HOME"):
        if os.environ.get(name):
            return Path(os.environ[name]).expanduser()
    return Path.home() / ".grok"


def _role_mode(home: Path, subagent_type: str) -> str | None:
    import tomllib

    path = home / "roles" / f"{subagent_type}.toml"
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        mode = tomllib.load(handle).get("default_capability_mode")
    return mode if isinstance(mode, str) else None


def writable(tool_input: object, home: Path) -> tuple[bool, str] | None:
    """(是否可寫入, 判斷依據)；None 代表無法判斷，由呼叫端放行。"""
    if not isinstance(tool_input, dict):
        return None
    mode = tool_input.get("capability_mode")
    if isinstance(mode, str) and mode:
        return (WRITABLE[mode], f"capability_mode={mode}") if mode in WRITABLE else None
    subagent_type = tool_input.get("subagent_type") or "general-purpose"
    if not isinstance(subagent_type, str) or not TYPE_NAME_RE.match(subagent_type):
        return None
    role_mode = _role_mode(home, subagent_type)
    if role_mode in WRITABLE:
        return WRITABLE[role_mode], f"{subagent_type} role default_capability_mode={role_mode}"
    if subagent_type in BUILTIN_TYPES:
        return BUILTIN_TYPES[subagent_type], f"built-in {subagent_type}"
    return None


def decide(payload: object, home: Path) -> dict | None:
    """回傳 deny decision；None 表示放行。"""
    if not isinstance(payload, dict) or payload.get("permissionMode") != "plan":
        return None
    verdict = writable(payload.get("toolInput"), home)
    if verdict is None or not verdict[0]:
        return None
    reason = (f"Plan mode is active, and this subagent can write files ({verdict[1]}); Grok's plan mode does not "
              "restrict subagents. Finish the verified Plan and leave plan mode with exit_plan_mode after "
              "the user approves it, then spawn this subagent. Inside plan mode use only read-only roles "
              "(scout, plan-verifier, security-reviewer).")
    return {"decision": "deny", "reason": reason}


def main(argv: list[str]) -> int:
    try:
        result = decide(json.loads(sys.stdin.buffer.read()), grok_home(argv))
        if result is not None:
            sys.stdout.write(json.dumps(result))
    except Exception:  # fail-open：任何錯誤都不擋下工具呼叫
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
