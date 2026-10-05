#!/usr/bin/env python3
"""為 Claude Code 與 Gemini/agy 安裝 shoal dispatch guard（docs/specs/dispatch-enforcement，R7）。

用法：
  python3 tools/install_hooks.py --host claude [--home DIR]               dry-run（預設），不寫入
  python3 tools/install_hooks.py --host agy --apply                       備份後安裝
  python3 tools/install_hooks.py --host claude --uninstall --apply        只移除 shoal 的 entry

來源是 repo committed HEAD 的 hooks/shoal_guard.py（git show，不是工作樹；HEAD 沒有就中止）。
腳本裝到 ${XDG_DATA_HOME:-~/.local/share}/shoal/guard/shoal_guard.py（0755），entry 寫進：
  claude  <home>/settings.json（--home，其次 CLAUDE_CONFIG_DIR，預設 ~/.claude）：
          UserPromptSubmit，以及 matcher 為 Edit|Write|NotebookEdit|MultiEdit|Agent|Workflow 的 PreToolUse
  agy     <home>/config/hooks.json（--home 預設 ~/.gemini）：具名群組 "shoal-guard"，
          PreToolUse（matcher "*"）與 PreInvocation
設定檔若是 symlink 就寫進它指向的檔案。只有 command 含 "shoal_guard.py --host" 的 handler
算 shoal 的；其他 hook、其他 key、key 順序與 2 空格縮排的 JSON 都原樣保留。重複執行不會改變
結果；寫入前把原檔備份到 ${XDG_STATE_HOME:-~/.local/state}/shoal/install-hooks/backups/
（目錄 0700、檔案 0600）。--uninstall 只移除 entry，不刪腳本（claude 與 agy 共用同一份）。

exit code：0 成功；1 寫入後驗證失敗；2 中止（來源或設定檔不符預期，沒有寫入）。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional

REPO = Path(__file__).resolve().parents[1]
GUARD_SOURCE = "hooks/shoal_guard.py"
CLAUDE_MATCHER = "Edit|Write|NotebookEdit|MultiEdit|Agent|Workflow"
AGY_GROUP = "shoal-guard"
TIMEOUT = 10
# 標記是 "shoal_guard.py --host"；路徑被引號包住時 "shoal_guard.py'" 後面才接空白與 --host。
OWNED = re.compile(r"shoal_guard\.py[\"']?\s+--host\b")


class InstallError(Exception):
    """中止（exit 2）。"""


# ---- 路徑 ----
def _abs_dir(value: Optional[str], default: Path) -> Path:
    """XDG 規則：未設定、空字串或相對路徑都用預設。"""
    return Path(value) if value and os.path.isabs(value) else default


def data_script_path(env: Mapping[str, str]) -> Path:
    base = _abs_dir(env.get("XDG_DATA_HOME"), Path.home() / ".local" / "share")
    return base / "shoal" / "guard" / "shoal_guard.py"


def backup_root(env: Mapping[str, str]) -> Path:
    base = _abs_dir(env.get("XDG_STATE_HOME"), Path.home() / ".local" / "state")
    return base / "shoal" / "install-hooks" / "backups"


def config_path(host: str, home: Optional[Path], env: Mapping[str, str]) -> Path:
    if host == "claude":
        base = home or Path(env.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
        return base.expanduser() / "settings.json"
    return (home or Path.home() / ".gemini").expanduser() / "config" / "hooks.json"


# ---- 來源 ----
def git(repo: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            timeout=60,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        detail = (
            exc.stderr.decode("utf-8", "replace").strip()
            if isinstance(exc, subprocess.CalledProcessError)
            else exc
        )
        raise InstallError(f"git {' '.join(args)} 失敗: {detail}") from exc


def load_guard(repo: Path, ref: str) -> tuple[bytes, str]:
    commit = git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    try:
        return git(repo, "show", f"{commit}:{GUARD_SOURCE}"), commit
    except InstallError as exc:
        raise InstallError(
            f"{commit[:7]} 沒有 {GUARD_SOURCE}（先 commit 再安裝；不安裝工作樹的版本）"
        ) from exc


# ---- 設定檔內容 ----
def command_for(script: Path, host: str) -> str:
    return f"python3 {shlex.quote(str(script))} --host {host}"


def _handler(command: str) -> dict[str, Any]:
    return {"type": "command", "command": command, "timeout": TIMEOUT}


def is_owned(handler: Any) -> bool:
    return (
        isinstance(handler, dict)
        and isinstance(handler.get("command"), str)
        and OWNED.search(handler["command"]) is not None
    )


def _group_handlers(group: Any) -> list[Any]:
    return (
        group["hooks"]
        if isinstance(group, dict) and isinstance(group.get("hooks"), list)
        else []
    )


def strip_owned_groups(groups: list[Any]) -> tuple[list[Any], Optional[int]]:
    """移除 matcher group 內 shoal 的 handler；回傳 (剩下的 groups, 第一個 shoal handler 原本的位置)。

    只含 shoal handler 的 group 整個移除；混有其他 handler 的 group 留下其他 handler。
    """
    kept: list[Any] = []
    first: Optional[int] = None
    for group in groups:
        handlers = _group_handlers(group)
        if not any(is_owned(h) for h in handlers):
            kept.append(group)
            continue
        if first is None:
            first = len(kept)
        rest = [h for h in handlers if not is_owned(h)]
        if rest:
            kept.append({**group, "hooks": rest})
    return kept, first


def set_groups(groups: Any, desired: Optional[dict[str, Any]], where: str) -> list[Any]:
    """matcher group 清單：先移除 shoal 的 handler，再把 desired（None 表示解除安裝）放回原位或結尾。"""
    if groups is None:
        groups = []
    if not isinstance(groups, list):
        raise InstallError(f"{where} 不是陣列，不處理")
    kept, first = strip_owned_groups(groups)
    if desired is not None:
        kept.insert(len(kept) if first is None else first, desired)
    return kept


def apply_claude(settings: dict[str, Any], command: Optional[str]) -> dict[str, Any]:
    """回傳新的 settings（command 為 None 時移除 shoal 的 entry）。其他內容與 key 順序不變。"""
    out = copy.deepcopy(settings)
    had_hooks = "hooks" in out
    hooks = out.get("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError("settings.json 的 hooks 不是物件，不處理")
    was_empty = not hooks
    desired: dict[str, Optional[dict[str, Any]]] = {
        "UserPromptSubmit": None if command is None else {"hooks": [_handler(command)]},
        "PreToolUse": None
        if command is None
        else {"matcher": CLAUDE_MATCHER, "hooks": [_handler(command)]},
    }
    for event, group in desired.items():
        existing = hooks.get(event)
        if existing is None and group is None:
            continue
        groups = set_groups(existing, group, f"hooks.{event}")
        if groups == existing:
            continue
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]  # 解除安裝後只剩 shoal 的 entry 時，連空陣列一起移除
    if hooks or (had_hooks and was_empty):
        out["hooks"] = hooks
    else:
        out.pop("hooks", None)
    return out


def apply_agy(config: dict[str, Any], command: Optional[str]) -> dict[str, Any]:
    out = copy.deepcopy(config)
    group = out.get(AGY_GROUP)
    if group is None:
        group = {}
    if not isinstance(group, dict):
        raise InstallError(f'hooks.json 的 "{AGY_GROUP}" 不是物件，不處理')
    # PreInvocation 是 handler 平鋪的陣列；PreToolUse 是 matcher group 的陣列。
    flat = group.get("PreInvocation")
    if flat is None:
        flat = []
    if not isinstance(flat, list):
        raise InstallError(f'"{AGY_GROUP}".PreInvocation 不是陣列，不處理')
    flat_kept = [h for h in flat if not is_owned(h)]
    if command is not None:
        flat_kept.append(_handler(command))
    tool_groups = set_groups(
        group.get("PreToolUse"),
        None if command is None else {"matcher": "*", "hooks": [_handler(command)]},
        f'"{AGY_GROUP}".PreToolUse',
    )
    for event, value in (("PreInvocation", flat_kept), ("PreToolUse", tool_groups)):
        if value:
            group[event] = value
        elif event in group:
            del group[event]
    if group:
        out[AGY_GROUP] = group
    elif AGY_GROUP in out:
        del out[AGY_GROUP]
    return out


# ---- 讀寫 ----
def read_json(path: Path) -> tuple[Optional[bytes], dict[str, Any]]:
    if not path.exists():
        return None, {}
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise InstallError(f"{path} 不是合法的 JSON，不處理: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError(f"{path} 最上層不是物件，不處理")
    return raw, data


def render_json(data: dict[str, Any], original: Optional[bytes]) -> bytes:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    final_newline = original is None or original.endswith(b"\n")
    return (text + ("\n" if final_newline else "")).encode("utf-8")


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.shoal-", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def make_backup(root: Path, host: str, items: dict[str, bytes]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    root.mkdir(parents=True, exist_ok=True)
    n = 0
    while True:
        target = root / (f"{host}-{stamp}" if n == 0 else f"{host}-{stamp}-{n}")
        try:
            target.mkdir(mode=0o700)
            break
        except FileExistsError:
            n += 1
    os.chmod(root, 0o700)
    os.chmod(target, 0o700)
    for name, data in items.items():
        atomic_write(target / name, data, 0o600)
    return target


def owned_entries(host: str, data: dict[str, Any]) -> int:
    """設定檔裡 shoal handler 的數量（驗證用）。"""
    count = 0
    if host == "claude":
        for groups in (data.get("hooks") or {}).values():
            for group in groups if isinstance(groups, list) else []:
                count += sum(is_owned(h) for h in _group_handlers(group))
    else:
        group = data.get(AGY_GROUP) or {}
        for event, value in group.items():
            for item in value if isinstance(value, list) else []:
                count += is_owned(item) + sum(
                    is_owned(h) for h in _group_handlers(item)
                )
    return count


# ---- 主流程 ----
def run(
    host: str,
    *,
    apply: bool,
    uninstall: bool,
    home: Optional[Path],
    repo: Path,
    ref: str,
    env: Mapping[str, str],
) -> int:
    target = config_path(host, home, env)
    real = Path(os.path.realpath(target))  # symlink 就寫進它指向的檔案
    script = data_script_path(env)
    original, current = read_json(real)

    guard: Optional[bytes] = None
    commit = ""
    if not uninstall:
        guard, commit = load_guard(repo, ref)
    command = None if uninstall else command_for(script, host)
    desired = (apply_claude if host == "claude" else apply_agy)(current, command)
    new_bytes = render_json(desired, original)
    config_changes = (
        original is None
        and bool(desired)
        or (original is not None and desired != current)
    )
    script_state = "略過（不處理腳本）"
    script_changes = False
    if guard is not None:
        existing = script.read_bytes() if script.is_file() else None
        script_changes = existing != guard
        script_state = (
            "新增"
            if existing is None
            else ("取代" if script_changes else "略過（已與 HEAD 相同）")
        )

    print(f"host: {host}  設定檔: {target}" + (f" -> {real}" if real != target else ""))
    if guard is not None:
        print(f"來源: committed {commit[:7]} 的 {GUARD_SOURCE}")
        print(f"  [{script_state}] {script}")
        print(f"  command: {command}")
    print(
        f"  [{'移除' if uninstall else '安裝'} entry] "
        + (
            "（內容已是最新，不變更）"
            if not config_changes
            else f"目前有 {owned_entries(host, current)} 個 shoal handler"
        )
    )
    if not apply:
        print("dry-run：沒有寫入任何檔案；加 --apply 才會寫入")
        return 0
    if not config_changes and not script_changes:
        print("沒有需要變更的檔案，不建立備份")
    else:
        saved: dict[str, bytes] = {}
        if original is not None and config_changes:
            saved[real.name] = original
        if script.is_file() and script_changes:
            saved["shoal_guard.py"] = script.read_bytes()
        if saved:
            print(f"備份: {make_backup(backup_root(env), host, saved)}")
        if script_changes and guard is not None:
            atomic_write(script, guard, 0o755)
        if config_changes:
            mode = stat.S_IMODE(real.stat().st_mode) if real.exists() else 0o644
            atomic_write(real, new_bytes, mode)
        print(
            "已寫入"
            + ("設定檔" if config_changes else "")
            + (
                "與腳本"
                if script_changes and config_changes
                else "腳本"
                if script_changes
                else ""
            )
        )
    # 驗證：重新讀檔，shoal handler 數量與其餘內容都符合預期
    _, after = read_json(real)
    expected_owned = 0 if uninstall else owned_entries(host, desired)
    stripped = (apply_claude if host == "claude" else apply_agy)(after, None)
    base = (apply_claude if host == "claude" else apply_agy)(current, None)
    problems = []
    if after != desired:
        problems.append("設定檔內容與預期不符")
    if owned_entries(host, after) != expected_owned:
        problems.append("shoal handler 數量與預期不符")
    if stripped != base:
        problems.append("非 shoal 的內容被改動")
    if guard is not None and (
        not script.is_file()
        or script.read_bytes() != guard
        or not os.access(script, os.X_OK)
    ):
        problems.append("腳本與 HEAD 不符或不可執行")
    if problems:
        print("驗證失敗：\n" + "\n".join(f"  {p}" for p in problems), file=sys.stderr)
        return 1
    print("驗證通過")
    return 0


def main(
    argv: Optional[list[str]] = None, env: Optional[Mapping[str, str]] = None
) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], allow_abbrev=False
    )
    parser.add_argument("--host", required=True, choices=("claude", "agy"))
    parser.add_argument(
        "--apply", action="store_true", help="實際寫入；沒有這個旗標一律 dry-run"
    )
    parser.add_argument(
        "--uninstall", action="store_true", help="只移除 shoal 的 entry，不刪腳本"
    )
    parser.add_argument(
        "--home",
        type=Path,
        help="claude 預設 $CLAUDE_CONFIG_DIR 或 ~/.claude；agy 預設 ~/.gemini",
    )
    parser.add_argument("--repo", type=Path, default=REPO, help="shoal repo（測試用）")
    parser.add_argument("--ref", default="HEAD", help="要安裝的 ref，預設 HEAD")
    args = parser.parse_args(argv)
    try:
        return run(
            args.host,
            apply=args.apply,
            uninstall=args.uninstall,
            home=args.home,
            repo=args.repo,
            ref=args.ref,
            env=os.environ if env is None else env,
        )
    except InstallError as exc:
        print(f"中止: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
