#!/usr/bin/env python3
"""為 Claude Code、Gemini/agy 與 Codex 安裝 shoal dispatch guard（docs/specs/dispatch-enforcement，R7）。

用法：
  python3 tools/install_hooks.py --host claude [--home DIR]               dry-run（預設），不寫入
  python3 tools/install_hooks.py --host agy --apply                       備份後安裝
  python3 tools/install_hooks.py --host claude --uninstall --apply        只移除 shoal 的 entry
  python3 tools/install_hooks.py --host codex --apply                     只管 shoal-guard 的 entry

來源是 repo committed HEAD 的 hooks/shoal_guard.py（git show，不是工作樹；HEAD 沒有就中止）。
腳本裝到 ${XDG_DATA_HOME:-~/.local/share}/shoal/guard/shoal_guard.py（0755），entry 寫進：
  claude  <home>/settings.json（--home，其次 CLAUDE_CONFIG_DIR，預設 ~/.claude）：
          UserPromptSubmit，以及 matcher 為 Edit|Write|NotebookEdit|MultiEdit|Agent|Workflow 的 PreToolUse
  agy     <home>/config/hooks.json（--home 預設 ~/.gemini）：具名群組 "shoal-guard"，
          PreToolUse（matcher "*"）與 PreInvocation
  codex   <home>/hooks.json（--home，其次 CODEX_HOME，預設 ~/.codex）：與 install/install.py 的
          shoal-guard-v1 projection 逐位元組相同的群組（UserPromptSubmit，以及 matcher
          ^(apply_patch|spawn_agent|collaborationspawn_agent)$ 的 PreToolUse，含 commandWindows），
          腳本裝到 <home>/hooks/shoal_guard.py（0600）。這是不能跑 install.py 時的窄路徑：
          不碰 shoal_autoroute_gate.py 等其他 hook，也不寫 hook trust（hooks.state），
          裝完要在互動式 Codex 用 /hooks 核准一次。install.py 之後會收編這些 entry。
          hooks.json 若還有 2.0.0 之前（舊名）的 autoroute 群組只提醒，不動；遷移由 install.py 或
          tools/sync_global.py 做。
設定檔若是 symlink 就寫進它指向的檔案。只有 command 含 "shoal_guard.py --host" 的 handler
算 shoal 的；其他 hook、其他 key、key 順序與 2 空格縮排的 JSON 都原樣保留。重複執行不會改變
結果；寫入前把原檔備份到 ${XDG_STATE_HOME:-~/.local/state}/shoal/install-hooks/backups/
（目錄 0700、檔案 0600）。--uninstall 只移除 entry，不刪腳本（claude 與 agy 共用同一份）；
codex 的 --uninstall 另外刪掉 <home>/hooks/shoal_guard.py（先備份），而且 install.py 的 state
已記錄 guard 時會中止（請改用 install.py，否則 state 驗證會失敗）。

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
sys.path.insert(0, str(REPO / "install"))
from hook_registration import (  # noqa: E402
    GUARD_PROJECTION_ID,
    TRUSTED_PROJECTIONS,
    HookRegistrationError,
    legacy_autoroute_locations,
    load_registration,
)
from legacy_codex import legacy_state_path  # noqa: E402
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


def codex_home_dir(home: Optional[Path], env: Mapping[str, str]) -> Path:
    return (home or Path(env.get("CODEX_HOME") or Path.home() / ".codex")).expanduser()


def config_path(host: str, home: Optional[Path], env: Mapping[str, str]) -> Path:
    if host == "codex":
        return codex_home_dir(home, env) / "hooks.json"
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


def apply_codex(hooks_json: dict[str, Any], command: Optional[str]) -> dict[str, Any]:
    """Codex hooks.json：放回 install/hook_registration.py 的 shoal-guard-v1 群組（command 為 None 時移除）。

    command 只當安裝／移除的開關；寫入的是 canonical 群組本身，install.py 才認得它。
    """
    out = copy.deepcopy(hooks_json)
    if command is None and "hooks" not in out:
        return out
    hooks = out.get("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError("hooks.json 的 hooks 不是物件，不處理")
    for event, group in TRUSTED_PROJECTIONS[GUARD_PROJECTION_ID].items():
        groups = set_groups(
            hooks.get(event),
            None if command is None else copy.deepcopy(group),
            f"hooks.{event}",
        )
        if groups:
            hooks[event] = groups
        elif event in hooks:
            del hooks[event]
    out["hooks"] = hooks  # install.py 要求 hooks 是物件，所以空了也保留
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
    if host in ("claude", "codex"):
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


def install_state_owns_guard(codex_home: Path) -> bool:
    """install.py 的 state 是否已記錄 guard（有就不能繞過它移除 entry）。"""
    # 2.0.0 之前的 state 檔名（legacy_codex.LEGACY_STATE_SUFFIX）也算：它同樣記錄 guard。
    for state in (
        codex_home.with_name(f"{codex_home.name}.shoal-install-state.json"),
        legacy_state_path(codex_home),
    ):
        try:
            if "guard_registration" in json.loads(state.read_text(encoding="utf-8")):
                return True
        except (OSError, ValueError):
            continue
    return False


def legacy_autoroute_note(current: dict[str, Any]) -> Optional[str]:
    """hooks.json 仍有 2.0.0 之前的 autoroute 群組時的提醒（這條窄路徑不碰它；遷移由 install.py／sync_global.py 做）。"""
    try:
        document = load_registration(json.dumps(current).encode("utf-8"), source="hooks.json")
    except HookRegistrationError:
        return None
    if not legacy_autoroute_locations(document):
        return None
    return (
        "注意：hooks.json 仍有 2.0.0 之前的 autoroute 註冊（舊名 gate）；"
        "請用 tools/sync_global.py --apply 或 install/install.py 遷移，這個工具不動它"
    )


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
    emit_json: bool = False,
) -> int:
    codex = host == "codex"
    apply_fn = {"claude": apply_claude, "agy": apply_agy, "codex": apply_codex}[host]
    target = config_path(host, home, env)
    real = Path(os.path.realpath(target))  # symlink 就寫進它指向的檔案
    script = target.parent / "hooks" / "shoal_guard.py" if codex else data_script_path(env)
    if codex and uninstall and install_state_owns_guard(target.parent):
        raise InstallError(
            "install.py 的 state 已記錄 guard；移除請用 install.py，直接移除會讓 state 驗證失敗"
        )
    original, current = read_json(real)

    guard: Optional[bytes] = None
    commit = ""
    if not uninstall:
        guard, commit = load_guard(repo, ref)
    command = (
        None
        if uninstall
        else TRUSTED_PROJECTIONS[GUARD_PROJECTION_ID]["UserPromptSubmit"]["hooks"][0]["command"]
        if codex
        else command_for(script, host)
    )
    desired = apply_fn(current, command)
    new_bytes = render_json(desired, original)
    config_changes = (
        original is None
        and bool(desired)
        or (original is not None and desired != current)
    )
    script_state = "略過（不處理腳本）"
    script_changes = False
    if codex and uninstall:
        script_changes = script.is_file()
        script_state = "移除" if script_changes else "略過（不存在）"
    if guard is not None:
        existing = script.read_bytes() if script.is_file() else None
        script_changes = existing != guard
        script_state = (
            "新增"
            if existing is None
            else ("取代" if script_changes else "略過（已與 HEAD 相同）")
        )

    print(f"host: {host}  設定檔: {target}" + (f" -> {real}" if real != target else ""))
    note = legacy_autoroute_note(current) if codex else None
    if note:
        print(note)
    if codex and uninstall:
        print(f"  [{script_state}] {script}")
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
    if emit_json:
        # 給 tools/sync_global.py：單獨一行，反映寫入前的差異
        print(json.dumps({"changes": bool(config_changes or script_changes)}))
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
            atomic_write(script, guard, 0o600 if codex else 0o755)
        elif script_changes and codex:
            script.unlink()
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
    stripped = apply_fn(after, None)
    base = apply_fn(current, None)
    if codex:  # 安裝會建立空的 hooks 物件；不算動到非 shoal 的內容
        stripped.setdefault("hooks", {})
        base.setdefault("hooks", {})
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
        or (not codex and not os.access(script, os.X_OK))
    ):
        problems.append("腳本與 HEAD 不符或不可執行")
    if codex and uninstall and script.exists():
        problems.append("腳本沒有被移除")
    if problems:
        print("驗證失敗：\n" + "\n".join(f"  {p}" for p in problems), file=sys.stderr)
        return 1
    print("驗證通過")
    if codex and not uninstall and (config_changes or script_changes):
        print(
            "提醒：新 hook 需要在互動式 Codex session 用 /hooks 核准一次才會執行"
            "（這個工具不寫 hook trust）"
        )
        resolved = Path(os.path.realpath(codex_home_dir(None, env)))
        if Path(os.path.realpath(target.parent)) != resolved:
            print(
                f"注意：hook command 在執行時讀 CODEX_HOME（預設 ~/.codex）；"
                f"請確認它指向 {target.parent}"
            )
    return 0


def main(
    argv: Optional[list[str]] = None, env: Optional[Mapping[str, str]] = None
) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], allow_abbrev=False
    )
    parser.add_argument("--host", required=True, choices=("claude", "agy", "codex"))
    parser.add_argument(
        "--apply", action="store_true", help="實際寫入；沒有這個旗標一律 dry-run"
    )
    parser.add_argument(
        "--uninstall", action="store_true", help="只移除 shoal 的 entry，不刪腳本"
    )
    parser.add_argument(
        "--home",
        type=Path,
        help="claude 預設 $CLAUDE_CONFIG_DIR 或 ~/.claude；agy 預設 ~/.gemini；codex 預設 $CODEX_HOME 或 ~/.codex",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help='多印一行 JSON {"changes": bool}（寫入前是否有差異），給 sync_global.py 判斷',
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
            emit_json=args.json,
        )
    except InstallError as exc:
        print(f"中止: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
