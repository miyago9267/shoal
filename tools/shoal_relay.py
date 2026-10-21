#!/usr/bin/env python3
"""cross-vendor-relay runner：把 shoal role 交給別家 agent CLI 執行，stdout 只印一份 hand-back JSON。

    python3 tools/shoal_relay.py --vendor codex --role executor --cwd <linked worktree> --brief <file> [--timeout 秒]

規格見 docs/specs/cross-vendor-relay（D3、D6、D7、D10 與 Security review F1、F3、F5–F11）。
- 只接受 executor、applier，cwd 必須是 linked worktree 的根目錄，worktree 內外（含祖先目錄）有 `.codex`
  就拒跑；這些情況回 blocked 且不呼叫 vendor。
- vendor 以 core/vendors.toml 解析出的絕對路徑 exec，argv 用 list、stdin 為 /dev/null，env 只給 allowlist
  加上每次新建的 TMPDIR、SHOAL_RELAY_ROLE、SHOAL_RELAY_NONCE。nonce 檔建在 guard state dir
  （hooks/shoal_guard.py 的 _guard_dir，以子程序的 env 計算）下的 `relay-<nonce>`，結束時刪除。
- 逾時、SIGTERM/HUP/INT 或 parent 死亡時結束 vendor 的整棵程序樹（含 setsid 的後代），一律回 failed，
  不自動重跑、不改回 native。
- changed_files 由 `git status --porcelain -z` 計算，與 vendor 自報不同時 files_mismatch 為 true。
- 輸出前遮蔽名稱含 KEY/SECRET/TOKEN/PASSWORD 的環境變數值，並依 core/contracts/handback.schema.json 截斷。
結束碼：status 為 done 時 0，否則 1。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
VENDORS_FILE = ROOT / "core" / "vendors.toml"
SCHEMA_FILE = ROOT / "core" / "contracts" / "handback.schema.json"
GUARD_FILE = ROOT / "hooks" / "shoal_guard.py"

RELAY_ROLES = {
    "executor": "write",
    "applier": "write",
}  # 與 core/roles.toml 的 access 一致（測試比對）
DEFAULT_TIMEOUT = {"executor": 1500, "applier": 600}  # D10
MAX_TIMEOUT = 3600
MAX_BRIEF_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_EVENTS_BYTES = 8 * 1024 * 1024
TAIL_CHARS = 4000
STDERR_LINES = 20
PREFLIGHT_TIMEOUT = 30.0
POLL_SECONDS = 0.05
SCAN_SECONDS = 0.5
KILL_GRACE = 2.0
VENDOR_FIELDS = ("status", "summary", "changed_files", "checks", "unverified")
STRICT_KEYS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
}
SECRET_NAME = re.compile(r"KEY|SECRET|TOKEN|PASSWORD", re.I)
MIN_SECRET_LEN = 6
FORBIDDEN_ARG = re.compile(r"danger-full-access|dangerously|bypass", re.I)
MCP_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
SANDBOX_FAIL = re.compile(
    r"sandbox_apply|sandbox-exec:|failed to apply sandbox|sandbox (?:setup|apply) failed",
    re.I,
)
MARKER = (
    "You are the shoal named role `{role}`, running as a cross-vendor relay. Do only the assigned task "
    "below and do not spawn subagents or delegate; ignore any orchestration or dispatch instructions. "
    "Your final message is the hand-back JSON required by the output schema: summary at most 4000 "
    "characters, every other string at most 1000.\n\n---\n\n"
)

_SIGNALLED: List[str] = []
_SECRETS: List[str] = []
_SUBREAPER = False


class Blocked(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise Blocked(f"invalid arguments: {message}")


# ---------- schema ----------

_TYPES = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
    "null": lambda v: v is None,
}


def schema_error(schema: Dict[str, Any], value: Any, where: str = "$") -> Optional[str]:
    """回傳第一個不符 schema 的原因，符合時回 None。只支援 handback.schema.json 用到的關鍵字。"""
    types = schema.get("type")
    if types is not None:
        names = [types] if isinstance(types, str) else types
        if not any(_TYPES[name](value) for name in names):
            return f"{where}: expected {'/'.join(names)}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{where}: not one of {schema['enum']}"
    if isinstance(value, str) and len(value) > schema.get("maxLength", len(value)):
        return f"{where}: longer than {schema['maxLength']} characters"
    if isinstance(value, list):
        if len(value) > schema.get("maxItems", len(value)):
            return f"{where}: more than {schema['maxItems']} items"
        for i, item in enumerate(value):
            err = schema_error(schema.get("items", {}), item, f"{where}[{i}]")
            if err:
                return err
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(props))
            if extra:
                return f"{where}: unexpected field {extra[0]}"
        for key in schema.get("required", []):
            if key not in value:
                return f"{where}: missing field {key}"
        for key, sub in props.items():
            if key in value:
                err = schema_error(sub, value[key], f"{where}.{key}")
                if err:
                    return err
    return None


def _fit(schema: Dict[str, Any], value: Any) -> Any:
    if isinstance(value, str):
        return value[: schema.get("maxLength", len(value))]
    if isinstance(value, list):
        return [
            _fit(schema.get("items", {}), v)
            for v in value[: schema.get("maxItems", len(value))]
        ]
    if isinstance(value, dict):
        props = schema.get("properties", {})
        return {k: _fit(props.get(k, {}), v) for k, v in value.items()}
    return value


def _strict(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    out = {k: v for k, v in schema.items() if k in STRICT_KEYS}
    if "properties" in out:
        out["properties"] = {k: _strict(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = _strict(out["items"])
    return out


def vendor_schemas(schema: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(驗證用的 vendor 子集 schema, 交給 vendor 的 strict schema)。

    vendor 只填 VENDOR_FIELDS；交出去的版本只留 T1.0 實測可用的 strict 關鍵字（全 required、
    additionalProperties:false），長度與數量上限由 runner 收到輸出後以驗證用版本檢查。
    """
    check = {
        "type": "object",
        "additionalProperties": False,
        "required": list(VENDOR_FIELDS),
        "properties": {k: schema["properties"][k] for k in VENDOR_FIELDS},
    }
    return check, _strict(check)


# ---------- 輸入檢查 ----------


def _load_vendor(name: str) -> Dict[str, Any]:
    try:
        import tomllib
    except ImportError:
        raise Blocked("python 3.11+ is required to read core/vendors.toml") from None
    try:
        with open(VENDORS_FILE, "rb") as fh:
            vendors = tomllib.load(fh).get("vendors", {})
    except (OSError, ValueError) as exc:
        raise Blocked(f"cannot read core/vendors.toml: {exc}") from None
    if name not in vendors:
        raise Blocked(f"unknown vendor {name!r}")
    return vendors[name]


def _git(cwd: Path, env: Dict[str, str], *args: str) -> Optional[str]:
    try:
        done = subprocess.run(
            ["git", "-C", str(cwd), "-c", "core.fsmonitor=false", *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=env,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (
        done.stdout.decode("utf-8", "surrogateescape") if done.returncode == 0 else None
    )


def _check_worktree(cwd: str, env: Dict[str, str], home: str) -> Path:
    real = Path(os.path.realpath(cwd))
    if not real.is_dir():
        raise Blocked("cwd is not a directory")
    out = _git(
        real,
        env,
        "rev-parse",
        "--path-format=absolute",
        "--git-dir",
        "--git-common-dir",
        "--show-toplevel",
    )
    lines = out.splitlines() if out else []
    if len(lines) != 3:
        raise Blocked("cwd is not inside a git repository")
    git_dir, common, top = (os.path.realpath(p) for p in lines)
    if git_dir == common:
        raise Blocked(
            "cwd is not a linked worktree (refusing to run in the main checkout)"
        )
    if str(real) != top:
        raise Blocked("cwd must be the root of the linked worktree")
    _refuse_codex_dirs(real, Path(common), home)
    return real


def _refuse_codex_dirs(top: Path, common: Path, home: str) -> None:
    """F3：worktree 任何層級、main checkout 根目錄與 HOME 以外的祖先目錄有 `.codex` 都拒跑。"""
    for base, dirs, files in os.walk(str(top)):
        if ".codex" in dirs or ".codex" in files:
            raise Blocked(
                "worktree contains .codex/ (repo-level codex config is refused)"
            )
        dirs[:] = [d for d in dirs if d != ".git"]
    home_real = os.path.realpath(home) if home else ""
    suspects = [p for p in top.parents if str(p) != home_real]
    if common.name == ".git":
        suspects.append(common.parent)
    for parent in suspects:
        if os.path.lexists(str(parent / ".codex")):
            raise Blocked(
                f"{parent / '.codex'} exists (repo-level codex config is refused)"
            )


def _read_brief(path: str) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise Blocked(
            f"cannot open brief (symlinks are refused): {exc.strerror}"
        ) from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Blocked("brief is not a regular file")
        if info.st_size > MAX_BRIEF_BYTES:
            raise Blocked(f"brief is larger than {MAX_BRIEF_BYTES} bytes")
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, MAX_BRIEF_BYTES + 1 - size)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_BRIEF_BYTES:
                raise Blocked(f"brief is larger than {MAX_BRIEF_BYTES} bytes")
    finally:
        os.close(fd)
    try:
        text = b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError:
        raise Blocked("brief is not UTF-8") from None
    if not text.strip():
        raise Blocked("brief is empty")
    return text


def _resolve_binary(cfg: Dict[str, Any], home: str) -> str:
    candidates = []
    for raw in cfg.get("paths", []):
        if raw.startswith("~/"):
            if not home:
                continue
            raw = os.path.join(home, raw[2:])
        if os.path.isabs(raw):
            candidates.append(raw)
    if cfg.get("search_path"):
        candidates += [
            os.path.join(d, cfg["binary"])
            for d in os.environ.get("PATH", "").split(os.pathsep)
            if os.path.isabs(d)
        ]
    for path in candidates:
        real = os.path.realpath(path)
        if os.path.isfile(real) and os.access(real, os.X_OK):
            return real
    raise Blocked("vendor binary not found (resolved by absolute path only)")


def _version_ok(text: str, minimum: str) -> bool:
    found, want = VERSION_RE.search(text), VERSION_RE.search(minimum)
    return bool(found and want) and tuple(map(int, found.groups())) >= tuple(
        map(int, want.groups())
    )


# ---------- 程序樹 ----------


def _on_signal(signum: int, _frame: Any) -> None:
    _SIGNALLED.append(signal.Signals(signum).name)


def _enable_subreaper() -> None:
    """Linux：成為 child subreaper，setsid 後被遺棄的後代會掛回 runner，掃描時不會漏掉。"""
    global _SUBREAPER
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes

        _SUBREAPER = (
            ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
        )  # PR_SET_CHILD_SUBREAPER
    except (OSError, AttributeError):
        _SUBREAPER = False


def _ps_table() -> Dict[int, Tuple[int, int]]:
    try:
        out = subprocess.run(
            ["ps", "-A", "-o", "pid=,ppid=,pgid="],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    table = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            table[int(parts[0])] = (int(parts[1]), int(parts[2]))
    return table


def _expand(tracked: Set[int], table: Dict[int, Tuple[int, int]]) -> Set[int]:
    """tracked 中仍存活者，加上它們的後代、同 process group 的程序，以及 subreaper 收養的孤兒。"""
    if not table:
        return set(tracked)
    me, my_group = os.getpid(), os.getpgrp()
    live = {p for p in tracked if p in table and table[p][1] != my_group}
    groups = {table[p][1] for p in live}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, pgid) in table.items():
            if pid in live or pid == me or pgid == my_group:
                continue
            if ppid in live or pgid in groups or (_SUBREAPER and ppid == me):
                live.add(pid)
                groups.add(pgid)
                changed = True
    return live


def _signal_tree(sig: int, pids: Set[int], groups: Set[int]) -> None:
    my_group = os.getpgrp()
    for group in groups:
        if group > 1 and group != my_group:
            try:
                os.killpg(group, sig)
            except OSError:
                pass
    for pid in pids:
        if pid > 1 and pid != os.getpid():
            try:
                os.kill(pid, sig)
            except OSError:
                pass


def _group_alive(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except OSError:
        return False
    return True


def _kill_tree(proc: subprocess.Popen, tracked: Set[int]) -> None:
    """先 SIGTERM 整個 group 給 KILL_GRACE 秒，再 SIGSTOP 凍結全部後代（避免繼續 fork）後 SIGKILL。"""
    groups = {proc.pid}

    def rescan() -> Set[int]:
        table = _ps_table()
        live = _expand(tracked | {proc.pid}, table)
        groups.update(table[p][1] for p in live if p in table)
        return live

    tracked = rescan()
    if proc.poll() is not None and not tracked and not _group_alive(proc.pid):
        return
    if proc.poll() is None:
        _signal_tree(signal.SIGTERM, tracked, groups)
        try:
            proc.wait(timeout=KILL_GRACE)
        except subprocess.TimeoutExpired:
            pass
    for _ in range(2):
        tracked = rescan()
        _signal_tree(signal.SIGSTOP, tracked, groups)
    tracked = rescan()
    _signal_tree(signal.SIGKILL, tracked, groups)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _supervise(
    argv: List[str],
    env: Dict[str, str],
    cwd: Path,
    out: Path,
    err: Path,
    deadline: float,
    parent: int,
) -> Tuple[Optional[int], Optional[str]]:
    """跑一個 vendor 指令到結束；回 (exit code, 中斷原因)。不論如何結束都清掉整棵程序樹。"""
    if _SIGNALLED:
        return None, f"interrupted by {_SIGNALLED[0]}"
    try:
        with open(out, "wb") as fo, open(err, "wb") as fe:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=fo,
                stderr=fe,
                cwd=str(cwd),
                env=env,
                start_new_session=True,
                close_fds=True,
            )
    except OSError as exc:
        return None, f"cannot start vendor: {exc.strerror}"
    tracked: Set[int] = {proc.pid}
    reason = None
    next_scan = 0.0
    try:
        while proc.poll() is None:
            now = time.monotonic()
            if _SIGNALLED:
                reason = f"interrupted by {_SIGNALLED[0]}"
            elif os.getppid() != parent:
                reason = "parent process exited"
            elif now >= deadline:
                reason = "timeout"
            if reason:
                break
            if now >= next_scan:
                tracked = _expand(tracked | {proc.pid}, _ps_table())
                next_scan = now + SCAN_SECONDS
            time.sleep(POLL_SECONDS)
    finally:
        _kill_tree(proc, tracked)
    return (None if reason else proc.returncode), reason


# ---------- 輸出 ----------


def _redact(text: str) -> str:
    for value in _SECRETS:
        text = text.replace(value, "[REDACTED]")
    return text


def _redact_all(value: Any) -> Any:
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, list):
        return [_redact_all(v) for v in value]
    if isinstance(value, dict):
        return {k: _redact_all(v) for k, v in value.items()}
    return value


def _tail(text: str, lines: Optional[int] = None) -> Optional[str]:
    text = _redact(text)
    if lines is not None:
        text = "\n".join(text.splitlines()[-lines:])
    return text[-TAIL_CHARS:] if text else None


def _read_tail(path: Path, limit: int) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(max(0, os.fstat(fh.fileno()).st_size - limit))
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _int_or_none(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _digest(stdout_path: Path) -> Dict[str, Any]:
    """codex --json 事件：session id、token usage、可讀的部分輸出，以及是否回報 sandbox 套用失敗。"""
    session, usage, lines, sandbox_failed = None, None, [], False
    for raw in _read_tail(stdout_path, MAX_EVENTS_BYTES).splitlines():
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "thread.started" and isinstance(event.get("thread_id"), str):
            session = event["thread_id"]
        elif kind == "turn.completed" and isinstance(event.get("usage"), dict):
            u = event["usage"]
            usage = {
                k: _int_or_none(u.get(k))
                for k in ("input_tokens", "cached_input_tokens", "output_tokens")
            }
        elif kind in ("error", "turn.failed"):
            nested = event.get("error") if isinstance(event.get("error"), dict) else {}
            msg = str(event.get("message") or nested.get("message") or "")
            lines.append(f"error: {msg}")
            sandbox_failed |= bool(SANDBOX_FAIL.search(msg))
        elif kind == "item.completed" and isinstance(event.get("item"), dict):
            item = event["item"]
            if item.get("type") == "agent_message":
                lines.append(str(item.get("text", "")))
            elif item.get("type") == "command_execution":
                code = item.get("exit_code")
                lines.append(f"$ {item.get('command')} (exit {code})")
                if code not in (0, None):
                    sandbox_failed |= bool(
                        SANDBOX_FAIL.search(str(item.get("aggregated_output", "")))
                    )
            elif item.get("type") == "error":
                msg = str(item.get("message", ""))
                lines.append(f"error: {msg}")
                sandbox_failed |= bool(SANDBOX_FAIL.search(msg))
    return {
        "session_id": session,
        "usage": usage,
        "partial": "\n".join(lines),
        "sandbox_failed": sandbox_failed,
    }


def _changed_files(top: Path, env: Dict[str, str]) -> Optional[List[str]]:
    out = _git(
        top,
        env,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--no-renames",
    )
    if out is None:
        return None
    return sorted({entry[3:] for entry in out.split("\0") if len(entry) > 3})


def _normalize_path(path: str, top: Path) -> str:
    if os.path.isabs(path):
        try:
            return os.path.relpath(os.path.realpath(path), str(top))
        except ValueError:
            return path
    return os.path.normpath(path)


def _read_output(path: Path) -> Tuple[Optional[Any], Optional[str]]:
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None, "vendor exited 0 but wrote no output file"
    except OSError as exc:
        return None, f"cannot open vendor output: {exc.strerror}"
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None, "vendor output is not a regular file"
        data = os.read(fd, MAX_OUTPUT_BYTES + 1)
    finally:
        os.close(fd)
    if not data.strip():
        return None, "vendor exited 0 but the output file is empty"
    if len(data) > MAX_OUTPUT_BYTES:
        return None, "vendor output is too large"
    try:
        return json.loads(data.decode("utf-8")), None
    except ValueError:
        return None, "vendor output is not valid JSON"


def _handback(
    vendor: str, status: str, reason: Optional[str] = None, **fields: Any
) -> Dict[str, Any]:
    hb = {
        "status": status,
        "summary": reason or "",
        "changed_files": [],
        "checks": [],
        "unverified": [],
        "vendor": vendor,
        "session_id": None,
        "usage": None,
        "reported_files": None,
        "files_mismatch": False,
        "reason": reason,
        "exit_code": None,
        "stderr_tail": None,
        "partial_output": None,
    }
    hb.update(fields)
    return hb


def emit(hb: Dict[str, Any], schema: Optional[Dict[str, Any]]) -> int:
    """遮蔽、截斷、驗證後印出一行 JSON；萬一仍不合 schema，改印固定的 failed hand-back。"""
    hb = _redact_all(hb)
    if schema is not None:
        hb = _fit(schema, hb)
        if schema_error(schema, hb):
            hb = _handback("unknown", "failed", "runner produced an invalid hand-back")
    try:
        sys.stdout.write(json.dumps(hb, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except OSError:
        pass
    return 0 if hb.get("status") == "done" else 1


# ---------- 主流程 ----------


def build_argv(
    binary: str,
    cfg: Dict[str, Any],
    access: str,
    schema_path: Path,
    out_path: Path,
    cwd: Path,
    prompt: str,
    mcp_ids: List[str],
) -> List[str]:
    """組 vendor 指令（D6）；任何 token 含 danger-full-access / bypass 類字樣就拒絕。"""
    sandbox = cfg.get("sandbox", {}).get(access)
    if not sandbox:
        raise Blocked(f"no sandbox mapping for access {access!r}")
    argv = [
        binary,
        *cfg["exec_args"],
        "--output-schema",
        str(schema_path),
        "-o",
        str(out_path),
        "--sandbox",
        sandbox,
        "-C",
        str(cwd),
    ]
    for pin in [*cfg["pins"], *(cfg["mcp_disable"].format(id=i) for i in mcp_ids)]:
        argv += ["-c", pin]
    if any(FORBIDDEN_ARG.search(token) for token in argv):
        raise Blocked("refusing a vendor command with a sandbox-bypass flag")
    return argv + [prompt]


def _preflight(
    binary: str,
    cfg: Dict[str, Any],
    env: Dict[str, str],
    top: Path,
    private: Path,
    deadline: float,
    parent: int,
) -> List[str]:
    """版本 ≥ min_version、已登入、列出要關閉的 MCP server id。輸出不轉印（F7）。"""

    def run(name: str, args: List[str]) -> str:
        out, err = private / f"{name}.out", private / f"{name}.err"
        rc, reason = _supervise(
            [binary, *args],
            env,
            top,
            out,
            err,
            min(deadline, time.monotonic() + PREFLIGHT_TIMEOUT),
            parent,
        )
        if reason:
            raise Blocked(f"vendor {name} check did not finish: {reason}")
        if rc != 0:
            raise Blocked(
                "vendor reports not logged in"
                if name == "login"
                else f"vendor {name} check failed (exit {rc})"
            )
        return _read_tail(out, MAX_OUTPUT_BYTES)

    if not _version_ok(run("version", cfg["version_args"]), cfg["min_version"]):
        raise Blocked(f"vendor version is older than {cfg['min_version']}")
    run("login", cfg["login_args"])
    try:
        servers = json.loads(run("mcp", cfg["mcp_list_args"]))
    except ValueError:
        raise Blocked("cannot parse the vendor MCP server list") from None
    if not isinstance(servers, list):
        raise Blocked("unexpected vendor MCP server list")
    ids = [s.get("name") if isinstance(s, dict) else None for s in servers]
    if not all(isinstance(i, str) and MCP_ID.match(i) for i in ids):
        raise Blocked("an MCP server id cannot be disabled safely")
    return ids  # type: ignore[return-value]


def _create_nonce(env: Dict[str, str], role: str) -> Path:
    """F5：在 guard state dir 建 relay-<nonce>（0600、O_EXCL、O_NOFOLLOW），guard 以此確認 SHOAL_RELAY_ROLE。"""
    try:
        spec = importlib.util.spec_from_file_location(
            "shoal_guard_for_relay", str(GUARD_FILE)
        )
        guard = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(guard)  # type: ignore[union-attr]
    except Exception:
        raise Blocked("cannot load hooks/shoal_guard.py") from None
    guard_dir = guard._guard_dir(env, Path(env["HOME"]))
    if guard_dir is None:
        raise Blocked("guard state dir is missing or not private")
    path = guard_dir / f"relay-{env['SHOAL_RELAY_NONCE']}"
    fd = guard._open_private(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    if fd is None:
        raise Blocked("cannot create the relay nonce file")
    try:
        os.write(fd, json.dumps({"role": role, "pid": os.getpid()}).encode())
    finally:
        os.close(fd)
    return path


def relay(
    argv: List[str], parent: int
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    parser = _Parser(prog="shoal_relay.py", add_help=False)
    parser.add_argument("--vendor", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--brief", required=True)
    parser.add_argument("--timeout", type=int)
    vendor = "unknown"
    try:
        schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _handback(
            vendor, "blocked", f"cannot read hand-back schema: {exc}"
        ), None
    try:
        args = parser.parse_args(argv)
        vendor = args.vendor
        return _relay(args, schema, parent), schema
    except Blocked as exc:
        return _handback(vendor, "blocked", str(exc)), schema
    except Exception as exc:  # stdout 仍要是一份 hand-back
        return _handback(
            vendor, "failed", f"runner error: {type(exc).__name__}"
        ), schema


def _relay(
    args: argparse.Namespace, schema: Dict[str, Any], parent: int
) -> Dict[str, Any]:
    vendor = args.vendor
    if args.role not in RELAY_ROLES:
        raise Blocked(
            f"role {args.role!r} cannot be relayed (only {', '.join(sorted(RELAY_ROLES))})"
        )
    timeout = args.timeout or DEFAULT_TIMEOUT[args.role]
    if not 0 < timeout <= MAX_TIMEOUT:
        raise Blocked(f"timeout must be between 1 and {MAX_TIMEOUT} seconds")
    deadline = time.monotonic() + timeout
    cfg = _load_vendor(vendor)
    env = {k: os.environ[k] for k in cfg["env"] if k in os.environ}
    home = env.get("HOME", "")
    if not os.path.isabs(home):
        raise Blocked("HOME is not set")
    top = _check_worktree(args.cwd, env, home)
    prompt = MARKER.format(role=args.role) + _read_brief(args.brief)
    binary = _resolve_binary(cfg, home)
    check_schema, strict_schema = vendor_schemas(schema)

    private = Path(tempfile.mkdtemp(prefix="shoal-relay-"))
    vendor_tmp = Path(tempfile.mkdtemp(prefix="shoal-relay-tmp-"))
    nonce_path = None
    try:
        for path in (private, vendor_tmp):
            if str(path.resolve()).startswith(str(top) + os.sep):
                raise Blocked("temp dir would be inside the worktree")
        env.update(
            TMPDIR=str(vendor_tmp),
            SHOAL_RELAY_ROLE=args.role,
            SHOAL_RELAY_NONCE=secrets.token_hex(16),
        )
        schema_path, out_path = (
            private / "handback.schema.json",
            private / "last-message.json",
        )
        schema_path.write_text(json.dumps(strict_schema), encoding="utf-8")
        (private / "brief.md").write_text(prompt, encoding="utf-8")
        nonce_path = _create_nonce(env, args.role)
        mcp_ids = _preflight(binary, cfg, env, top, private, deadline, parent)
        command = build_argv(
            binary,
            cfg,
            RELAY_ROLES[args.role],
            schema_path,
            out_path,
            top,
            prompt,
            mcp_ids,
        )
        rc, reason = _supervise(
            command,
            env,
            top,
            private / "events.jsonl",
            private / "stderr.txt",
            deadline,
            parent,
        )
        return _collect(vendor, rc, reason, top, env, private, out_path, check_schema)
    finally:
        if nonce_path is not None:
            try:
                os.unlink(str(nonce_path))
            except OSError:
                pass
        shutil.rmtree(str(private), ignore_errors=True)
        shutil.rmtree(str(vendor_tmp), ignore_errors=True)


def _collect(
    vendor: str,
    rc: Optional[int],
    reason: Optional[str],
    top: Path,
    env: Dict[str, str],
    private: Path,
    out_path: Path,
    check_schema: Dict[str, Any],
) -> Dict[str, Any]:
    events = _digest(private / "events.jsonl")
    changed = _changed_files(top, env)
    stderr_text = _read_tail(private / "stderr.txt", 64 * 1024)
    base = {
        "session_id": events["session_id"],
        "usage": events["usage"],
        "exit_code": rc,
        "changed_files": changed or [],
        "stderr_tail": _tail(stderr_text, STDERR_LINES),
        "partial_output": _tail(events["partial"]),
    }
    if reason:
        return _handback(vendor, "failed", reason, **base)
    if events["sandbox_failed"] or SANDBOX_FAIL.search(stderr_text):
        return _handback(
            vendor, "failed", "vendor sandbox failed to apply; not retried", **base
        )
    if rc != 0:
        return _handback(vendor, "failed", f"vendor exited with code {rc}", **base)
    report, error = _read_output(out_path)
    if error is None:
        error = schema_error(check_schema, report)
        error = f"hand-back does not match the schema: {error}" if error else None
    if error:
        return _handback(vendor, "failed", error, **base)
    if changed is None:
        return _handback(
            vendor, "failed", "git status failed after the vendor run", **base
        )
    reported = report["changed_files"]
    mismatch = {_normalize_path(p, top) for p in reported} != set(changed)
    return _handback(
        vendor,
        report["status"],
        None,
        **{
            **base,
            "summary": report["summary"],
            "checks": report["checks"],
            "unverified": report["unverified"],
            "reported_files": reported,
            "files_mismatch": mismatch,
            "partial_output": None,
            "stderr_tail": None,
        },
    )


def main(argv: Optional[List[str]] = None) -> int:
    parent = os.getppid()
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, _on_signal)
    _SECRETS[:] = sorted(
        {
            v
            for k, v in os.environ.items()
            if SECRET_NAME.search(k) and len(v) >= MIN_SECRET_LEN
        },
        key=len,
        reverse=True,
    )
    _enable_subreaper()
    hb, schema = relay(sys.argv[1:] if argv is None else argv, parent)
    return emit(hb, schema)


if __name__ == "__main__":
    raise SystemExit(main())
