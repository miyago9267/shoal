#!/usr/bin/env python3
"""Shoal dispatch guard: host-neutral hook guard for shoal dispatch rules (claude, codex, grok, agy).

    python3 hooks/shoal_guard.py --host {claude,codex,grok,agy} [--plugin]   (JSON on stdin; SHOAL_GUARD_HOST if no --host)

Per-host adapters normalize the payload into an event; the core decides on the event only, so the TypeScript port
replays tests/fixtures/guard_vectors.json against the same logic.  --plugin (the Claude plugin's hooks.json) does nothing
when the user settings already register the tools/install_hooks.py guard.  Always exits 0 and fails open: a policy
nudge, not a security boundary.  Modes, rules and switches (SHOAL_GUARD, SHOAL_GUARD_R1, SHOAL_GUARD_SUBAGENT_WRITE,
SHOAL_GUARD_STOP, `#direct`, `#fast`) are specified in docs/specs/dispatch-enforcement, docs/specs/guard-declared-direct,
docs/specs/guard-every-gate and docs/specs/shared-rules (B2-B4 completion check).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shlex
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, NamedTuple, Optional, Set, Tuple

try:
    import fcntl
except ImportError:  # Windows: run() is a no-op there
    fcntl = None  # type: ignore[assignment]

MAX_INPUT_BYTES = 256 * 1024
MAX_LOG_BYTES = 1024 * 1024
MAX_STATE_BYTES = 64 * 1024
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
LOCK_WAIT_SECONDS = 2.0

# Per-host table: default mode (None: the host has no Python guard entry) and the traits it has.  Each legacy
# `*_HOSTS` name below is derived from it; the traits (fixture evidence in parentheses):
#   role_aware        the payload identifies the calling role: LEAF / VERIFY_EDIT apply (spec R6).
#   stop              `Stop` payload recorded (tests/fixtures/stop_payload_shapes.json) and blocking accepted (B4);
#                     SHOAL_GUARD_STOP switches the check off here and has no effect elsewhere.
#   stop_shadow       stop defaults to `would_block` only, until SHOAL_GUARD_STOP=enforce (block output unexercised).
#   post              registration carries PostToolUse for the shell tool: `checked` counts a call that really ran
#                     (guard-every-gate E8); PreToolUse is the fallback until the session's first PostToolUse (`post_seen`).
#   role_running      a write dispatch returns at once while the role runs (claude's async Agent, B3).
#   conversation      a subagent runs in its own conversation; main vs subagent is inferred from event order and kept
#                     in `state/agy.conversations.json` (_Guard.agy_route).  Not exact under concurrent dispatch.
#   prompt_direct     the prompt event carries the user's text, so `#direct` exists (agy's PreInvocation has none).
#   composed_turn     turn ids are `conversation:invocation`; the tool payload may lack one.
#   state_turn        the tool payload may lack a turn id (grok: only user_prompt_submit has promptId; claude after
#                     `/login` resumes without prompt_id): the state turn is used.
#   advise_output     PreToolUse accepts a non-blocking `additionalContext` (the R2 reminder); elsewhere log only.
#   prompt_keep       the prompt event may lack a turn id: it clears `dispatched`, keeps turn and edits (M1).
#   deny_main         R1 denies (G1), main's background shell is denied (G4), a shell file write is judged by R1 (G5).
#   declare           SHOAL_GUARD_R1 `declare` / `strict` are selectable (the adapter delivers main's shell calls;
#                     opencode is the TypeScript port, listed so both replay the same vectors); others: `classified`.
#   start_unlock      a write dispatch unlocks only once the role started (M11): the dispatch call records a pending
#                     dispatch, the start event releases it (claude SubagentStart, tests/fixtures/
#                     claude_subagent_start_shape.json; codex SubagentStart or the role's first agent_id call,
#                     `started_agents`; grok `subagent_start`; agy SessionStart of a new conversation).
#   subagent_write_on SHOAL_GUARD_SUBAGENT_WRITE defaults to `on` (E1, docs/specs/guard-every-gate).
#   subagent_direct   a subagent's events can be traced to main's turn, so the user's `#direct` releases it.
#   mapped            a subagent's events carry its own session id; `subagent_start` records the mapping (grok).
#   agent_keyed       a subagent has its own turn id: `#direct` is looked up by agent_id (`direct_agents`, codex).
HOSTS = {
    "claude": ("enforce", "role_aware stop post role_running prompt_direct state_turn advise_output prompt_keep "
                          "deny_main declare start_unlock subagent_write_on subagent_direct"),
    "codex": ("enforce", "role_aware stop post prompt_direct advise_output declare start_unlock subagent_write_on "
                         "subagent_direct agent_keyed"),
    "grok": ("enforce", "role_aware stop stop_shadow prompt_direct state_turn declare start_unlock subagent_write_on "
                        "subagent_direct mapped"),
    "agy": ("enforce", "stop stop_shadow conversation composed_turn state_turn declare start_unlock subagent_write_on"),
    "opencode": (None, "prompt_direct declare"),
}


def _hosts_with(trait: str) -> "frozenset[str]":
    return frozenset(host for host, (_, traits) in HOSTS.items() if trait in traits.split())


HOST_DEFAULT_MODE = {host: mode for host, (mode, _) in HOSTS.items() if mode is not None}
ROLE_AWARE_HOSTS = _hosts_with("role_aware")
STOP_HOSTS = _hosts_with("stop")
STOP_SHADOW_DEFAULT_HOSTS = _hosts_with("stop_shadow")
POST_HOSTS = _hosts_with("post")
ROLE_RUNNING_HOSTS = _hosts_with("role_running")
CONVERSATION_HOSTS = _hosts_with("conversation")
PROMPT_DIRECT_HOSTS = _hosts_with("prompt_direct")
COMPOSED_TURN_HOSTS = _hosts_with("composed_turn")
STATE_TURN_HOSTS = _hosts_with("state_turn")
ADVISE_OUTPUT_HOSTS = _hosts_with("advise_output")
PROMPT_KEEP_HOSTS = _hosts_with("prompt_keep")
DENY_MAIN_HOSTS = _hosts_with("deny_main")
DECLARE_HOSTS = _hosts_with("declare")
START_UNLOCK_HOSTS = _hosts_with("start_unlock")
SUBAGENT_WRITE_DEFAULT_ON_HOSTS = _hosts_with("subagent_write_on")
SUBAGENT_DIRECT_HOSTS = _hosts_with("subagent_direct")
MAPPED_HOSTS = _hosts_with("mapped")
AGENT_KEYED_HOSTS = _hosts_with("agent_keyed")

AGY_RECORD_FILE = "agy.conversations"  # state/<this>.json; not a valid id (dot), so it never collides with a session
AGY_RECORD_MAX = 64
AGY_PENDING_TTL = 600.0  # seconds a dispatch waits for its subagent's SessionStart
AGY_EVENTS = frozenset({"SessionStart", "PreInvocation", "PreToolUse", "Stop"})
GROK_AGENTS_MAX = 64
GROK_AGENTS_FILE = "grok.agents"  # state/<this>.json; not a valid id (no dots), so it never collides with a session
AGENTS_MAX = 32
# The state file remembers this many most recent turn ids that carried `#direct`.
DIRECT_TURNS_MAX = 16

# `#direct` as an instruction the user typed: a standalone token that follows the start of the text or
# whitespace and is followed by the end, whitespace or sentence punctuation (ASCII or CJK).  Anything
# else (`x#direct`, `(#direct)`, `#directly`, a URL fragment) is not.  Code the user quoted does not
# count: fenced blocks and inline spans are masked with NUL (never whitespace) before matching.
def _token_re(name: str) -> "re.Pattern[str]":
    return re.compile(r"(?<!\S)#" + name + r"(?![^\s.,;:!?\u3002\uff0c\u3001\uff1b\uff1a\uff01\uff1f])")


DIRECT_TOKEN_RE = _token_re("direct")
FAST_TOKEN_RE = _token_re("fast")
STRICT_TOKEN_RE = _token_re("strict")
FENCE_OPEN_RE = re.compile(r" {0,3}`{3,}")
FENCE_CLOSE_RE = re.compile(r" {0,3}`{3,}\s*$")
INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)(?:(?!\n[ \t\r]*\n).)+?(?<!`)\1(?!`)", re.DOTALL)


def _unquoted(prompt: Any) -> Optional[str]:
    """The prompt text with fenced blocks and inline code masked, or None when it is not a string."""
    if not isinstance(prompt, str):
        return None
    lines: List[str] = []
    in_fence = False
    for line in prompt.split("\n"):
        if in_fence:
            in_fence = FENCE_CLOSE_RE.match(line) is None
            lines.append("\0")
        elif FENCE_OPEN_RE.match(line):
            in_fence = True
            lines.append("\0")
        else:
            lines.append(line)
    return INLINE_CODE_RE.sub("\0", "\n".join(lines))


def has_direct_token(prompt: Any) -> bool:
    """True when the user's prompt carries `#direct` as typed instruction, outside any code."""
    text = _unquoted(prompt)
    return text is not None and DIRECT_TOKEN_RE.search(text) is not None


def fast_switch(prompt: Any) -> Optional[str]:
    """Fast mode switch typed in the prompt: "off" for `#strict` (wins when both appear), "on" for `#fast`, else None."""
    text = _unquoted(prompt)
    if text is None:
        return None
    if STRICT_TOKEN_RE.search(text) is not None:
        return "off"
    return "on" if FAST_TOKEN_RE.search(text) is not None else None


# Role-name namespaces accepted as the same role (K3).  Explicit allowlist only: any other
# `x:name` stays unknown, so it neither unlocks nor counts as a leaf/verify role.
ROLE_NAMESPACES = ("shoal:",)

# role -> access level.  Must match core/roles.toml and every [extra_roles.*] in
# hosts/*/binding.toml; tests/test_shoal_guard.py asserts it.
ROLE_ACCESS = {
    "scout": "read-only",
    "plan-critic": "read-only",
    "security-reviewer": "read-only",
    "researcher": "read-only",
    "Explore": "read-only",
    "applier": "write",
    "executor": "write",
    "security-executor": "write",
    "sol-executor": "write",
    "verifier": "verify",
    "watcher": "verify",
}

# Dispatch lanes (SHOAL_GUARD_LANES, default on): a main dispatch of a write role must carry a lane label at the start
# of the dispatch's short description, and the label must match the role.  `#direct` / `#fast` do not release it.
LANE_ROLES = {
    "fast": ("applier",),
    "complex": ("executor", "sol-executor"),
    "rigorous": ("security-executor",),
}
LANE_RE = re.compile(r"^\s*\[(fast|complex|rigorous)\]")

CLASSIFIED_ROLE = {"judgment": "executor", "mechanical": "applier"}

# Cross-vendor relay (docs/specs/cross-vendor-relay S1.11, Security review F4/F5): tools/shoal_relay.py runs a role in
# `codex exec` with SHOAL_RELAY_ROLE / SHOAL_RELAY_NONCE set and a `<guard dir>/relay-<nonce>` file holding
# {"role", "pid"}.  Only when all of it checks out is the whole session that named role; the env alone changes nothing.
RELAY_HOST = "codex"
RELAY_ROLES = frozenset({"executor", "applier"})
RELAY_NONCE_RE = re.compile(r"[0-9a-f]{32}")
RELAY_NONCE_MAX_BYTES = 4096
DISPATCH_NAME = {
    "claude": "Agent",
    "codex": "spawn_agent",
    "grok": "spawn_subagent",
    "agy": "invoke_subagent",
}
LOG_FIELDS = (
    "ts",
    "host",
    "event",
    "tool",
    "rule",
    "decision",
    "file",
    "skip_reason",
    "mode",
    "reason",
    "agent_type",  # the subagent's type as the host sent it (raw); absent for main-session events
    "agent_id",
    "session",  # first 8 hex of sha256 of the session id / turn id: attributes lines, never reveals the id
    "turn",
    "fast",
    "member",  # guard chain: the member's configured name
    "ms",  # guard chain: the member call's duration in milliseconds
)

MESSAGES = {
    "en": {
        "ADVISE": (
            "Shoal dispatch brake (a reminder, nothing was blocked): this turn has edited {n} "
            "files directly. If the work is stable same-shape repetition, or bounded judgment "
            "with a stable contract, consider handing it to `applier` / `executor` with "
            "{tool}; otherwise continuing directly is fine."
        ),
        "LEAF": (
            "Shoal dispatch guard: subagents are leaf workers and must not dispatch other "
            "agents. Finish the task yourself and report back to the parent."
        ),
        "RELAY": (
            "Shoal dispatch guard: this session runs the relayed shoal role `{role}` and must not dispatch "
            "or message other agents. Finish the task yourself and report back in the hand-back."
        ),
        "VERIFY_EDIT": (
            "Shoal dispatch guard: verify-level roles must not edit files with editing tools. "
            "Report findings to the parent instead."
        ),
        "R1": (
            "Shoal dispatch guard: this turn is classified as implementation work and no write "
            "role has been dispatched. Dispatch executor or applier, or add #direct to your "
            "prompt to edit directly."
        ),
        "G4": (
            "Shoal dispatch guard: the main session does not start background shells. Dispatch "
            "watcher in the background instead, or add #direct to your prompt."
        ),
        "STRICT": (
            "Shoal dispatch guard: the main session does not edit files itself. Dispatch a "
            "write-capable role (executor or applier), or ask the user to add #direct to the prompt."
        ),
        "STRICT_ND": (
            "Shoal dispatch guard: the main session does not edit files itself. Dispatch a "
            "write-capable role (executor or applier) and wait until it has started, add the role to "
            "SHOAL_GUARD_WRITE_AGENTS, or set SHOAL_GUARD_DIRECT=1 (this host has no prompt marker for it)."
        ),
        "DECLARE_ND": (
            "Shoal dispatch guard: the main session delegates edits by default. Dispatch a "
            "write-capable role (executor or applier), or declare direct work first by running "
            'exactly : shoal-direct "<reason>" as its own shell command, or set SHOAL_GUARD_DIRECT=1 '
            "(this host has no prompt marker for it)."
        ),
        "LANE_MISSING": (
            "Shoal dispatch guard: a write-role dispatch ({role}) must start its description with a lane label: "
            "[fast] -> applier, [complex] -> executor, [rigorous] -> security-executor "
            "(e.g. `[complex] fix: ...`). Add the label, or set SHOAL_GUARD_LANES=off."
        ),
        "LANE_MISMATCH": (
            "Shoal dispatch guard: lane label [{label}] does not match role {role}. "
            "[fast] -> applier, [complex] -> executor, [rigorous] -> security-executor. "
            "Dispatch {expected} for [{label}], or change the label to match {role}."
        ),
        "E1": (
            "Shoal dispatch guard: a subagent that is not a shoal write-capable role does not edit files. "
            "Dispatch a shoal write-capable role (executor or applier), add this agent type to "
            "SHOAL_GUARD_WRITE_AGENTS, or set SHOAL_GUARD_DIRECT=1."
        ),
        "E1D": (
            "Shoal dispatch guard: a subagent that is not a shoal write-capable role does not edit files. "
            "Dispatch a shoal write-capable role (executor or applier), add #direct to the user prompt that "
            "started this work, add this agent type to SHOAL_GUARD_WRITE_AGENTS, or set SHOAL_GUARD_DIRECT=1."
        ),
        "STOP": (
            "Shoal completion check: this turn changed files and no check ran afterwards. Run a "
            "verification now (tests, a verifier or watcher role), or say explicitly in your report "
            "that the change is unverified."
        ),
        "DECLARE": (
            "Shoal dispatch guard: the main session delegates edits by default. Dispatch a "
            "write-capable role (executor or applier), or declare direct work first by running "
            'exactly : shoal-direct "<reason>" as its own shell command, or ask the user to add '
            "#direct to the prompt."
        ),
    },
    "zh-TW": {
        "ADVISE": (
            "Shoal dispatch brake（提醒，沒有擋任何操作）：本輪 main session 已直接改了 {n} 個檔案。"
            "若這是穩定的同形重複，或契約穩定、範圍有界的判斷工作，可考慮用 {tool} 交給 "
            "`applier` / `executor`；否則直接做下去也可以。"
        ),
        "LEAF": "Shoal dispatch guard：subagent 是 leaf worker，不可再派其他 agent。請自己完成並回報給上層。",
        "RELAY": (
            "Shoal dispatch guard：這個 session 是 relay 過來的 shoal role `{role}`，不可派出或聯繫其他 agent。"
            "請自己完成並在 hand-back 回報。"
        ),
        "VERIFY_EDIT": "Shoal dispatch guard：verify 等級的 role 不可用編輯工具改檔，請把發現回報給上層。",
        "R1": (
            "Shoal dispatch guard：本輪已被分類為實作工作，且尚未派出 write role。"
            "請派給 executor 或 applier，或在 prompt 加上 #direct以直接修改。"
        ),
        "G4": (
            "Shoal dispatch guard：main session 不自己開背景 shell。"
            "請改在背景派出 watcher，或在 prompt 加上 #direct。"
        ),
        "STRICT": (
            "Shoal dispatch guard：main session 不自己改檔。"
            "請派出可寫的 role（executor 或 applier），或請使用者在 prompt 加上 #direct。"
        ),
        "STRICT_ND": (
            "Shoal dispatch guard：main session 不自己改檔。請派出可寫的 role（executor 或 applier）並等它啟動、"
            "把 role 加進 SHOAL_GUARD_WRITE_AGENTS，或設定 SHOAL_GUARD_DIRECT=1（這個 host 沒有 prompt 標記可用）。"
        ),
        "DECLARE_ND": (
            "Shoal dispatch guard：main session 預設把改檔交給別的 role。"
            "請派出可寫的 role（executor 或 applier），或先宣告直接做：把 "
            ': shoal-direct "<理由>" 當成單獨一次 shell 指令執行，或設定 SHOAL_GUARD_DIRECT=1（這個 host 沒有 prompt 標記可用）。'
        ),
        "E1": (
            "Shoal dispatch guard：不是 shoal 可寫 role 的 subagent 不改檔。"
            "請派出 shoal 可寫的 role（executor 或 applier）、把這個 agent type 加進 "
            "SHOAL_GUARD_WRITE_AGENTS，或設定 SHOAL_GUARD_DIRECT=1。"
        ),
        "E1D": (
            "Shoal dispatch guard：不是 shoal 可寫 role 的 subagent 不改檔。"
            "請派出 shoal 可寫的 role（executor 或 applier）、請使用者在啟動這項工作的 prompt 加上 #direct、"
            "把這個 agent type 加進 SHOAL_GUARD_WRITE_AGENTS，或設定 SHOAL_GUARD_DIRECT=1。"
        ),
        "LANE_MISSING": (
            "Shoal dispatch guard：派 write role（{role}）時，description 開頭必須有 lane 標籤："
            "[fast] -> applier、[complex] -> executor、[rigorous] -> security-executor"
            "（例如 `[complex] fix: ...`）。請補上標籤，或設定 SHOAL_GUARD_LANES=off。"
        ),
        "LANE_MISMATCH": (
            "Shoal dispatch guard：lane 標籤 [{label}] 與 role {role} 不符。"
            "[fast] -> applier、[complex] -> executor、[rigorous] -> security-executor。"
            "[{label}] 請改派 {expected}，或把標籤改成符合 {role}。"
        ),
        "STOP": (
            "Shoal completion check：本回合改過檔案，之後沒有跑過任何檢查。"
            "請現在做一次驗證（測試、verifier 或 watcher role），或在回報中明確寫出這次修改尚未驗證。"
        ),
        "DECLARE": (
            "Shoal dispatch guard：main session 預設把改檔交給別的 role。"
            "請派出可寫的 role（executor 或 applier），或先宣告直接做：把 "
            ': shoal-direct "<理由>" 當成單獨一次 shell 指令執行，或請使用者在 prompt 加上 #direct。'
        ),
    },
}


# ---------------------------------------------------------------------------
# State and log files (spec R4)
# ---------------------------------------------------------------------------


def _uid() -> int:
    return os.getuid()


def _no_symlink_below(path: Path, anchor: Path) -> bool:
    """True when no component from path up to (not including) anchor is a symlink."""
    try:
        path.relative_to(anchor)
    except ValueError:
        return False
    cursor = path
    while cursor != anchor:
        if cursor.is_symlink():
            return False
        cursor = cursor.parent
    return True


def _open_private(path: Path, flags: int) -> Optional[int]:
    """Open a regular file owned by us with O_NOFOLLOW; force mode 0600."""
    try:
        fd = os.open(str(path), flags | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != _uid():
            os.close(fd)
            return None
        os.fchmod(fd, 0o600)
    except OSError:
        os.close(fd)
        return None
    return fd


def _state_base(env: Dict[str, str], home: Path) -> Path:
    xdg = env.get("XDG_STATE_HOME", "")
    if xdg and os.path.isabs(xdg):
        return Path(xdg)
    return home / ".local" / "state"


def _guard_dir(env: Dict[str, str], home: Path) -> Optional[Path]:
    """${state}/shoal/guard with state/ and turns/ beneath it; None if it cannot be trusted."""
    base = _state_base(env, home)
    try:
        base.relative_to(home)
        anchor = home
    except ValueError:
        anchor = base  # XDG outside HOME: only dirs we own below it are checked
    try:
        if not _no_symlink_below(base, anchor):
            return None
        os.makedirs(str(base), exist_ok=True)
        for rel, strict in (("shoal", False), ("shoal/guard", True),
                            ("shoal/guard/state", True), ("shoal/guard/turns", True)):
            cursor = base / rel
            try:
                os.mkdir(str(cursor), 0o700)
            except FileExistsError:
                pass
            info = os.lstat(str(cursor))
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != _uid():
                return None
            if strict and stat.S_IMODE(info.st_mode) & 0o077:
                return None
    except OSError:
        return None
    return base / "shoal" / "guard"


def _read_json(path: Path) -> Dict[str, Any]:
    fd = _open_private(path, os.O_RDONLY)
    if fd is None:
        return {}
    try:
        data = json.loads(os.read(fd, MAX_STATE_BYTES))
    except ValueError:
        return {}
    finally:
        os.close(fd)
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, obj: Dict[str, Any]) -> bool:
    fd = _open_private(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    if fd is None:
        return False
    try:
        os.write(fd, json.dumps(obj).encode())
    finally:
        os.close(fd)
    return True


@contextlib.contextmanager
def _state_lock(path: Path) -> Iterator[Optional[str]]:
    """Advisory flock on `path` (0600, O_NOFOLLOW) around a state read-modify-write.

    Yields None once held, else the skip reason (the caller then fails open).  Waits at
    most LOCK_WAIT_SECONDS; the lock dies with the process, so a crash never wedges it.
    """
    fd = _open_private(path, os.O_RDWR | os.O_CREAT) if fcntl is not None else None
    if fd is None:
        yield "state_unavailable"
        return
    try:
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    yield "lock_timeout"
                    return
                time.sleep(0.01)
        yield None
    finally:
        os.close(fd)  # closing the descriptor releases the lock


def _safe_text(value: Any) -> Optional[str]:
    return value[:200] if isinstance(value, str) else None


def short_hash(value: Any) -> Optional[str]:
    """Non-reversible 8-hex tag of a session or turn id, for the log (None when there is no id)."""
    if not isinstance(value, str) or not value:
        return None
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:8]


def _append_log(guard: Optional[Path], record: Dict[str, Any]) -> None:
    """Append one whitelisted record to guard.jsonl; past 1 MiB it becomes guard.jsonl.1 (one generation).  Never raises."""
    if guard is None:
        return
    line: Dict[str, Any] = {"ts": datetime.now(timezone.utc).isoformat()}
    for key in LOG_FIELDS[1:]:
        value = record.get(key)
        if key == "fast":  # the only boolean field: present only when fast mode was on
            if value is True:
                line[key] = True
            continue
        if key == "file" and isinstance(value, str):
            value = os.path.basename(value)
        value = _safe_text(value)
        if value is not None:
            line[key] = value
    path = guard / "guard.jsonl"
    try:
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            os.replace(path, guard / "guard.jsonl.1")
        fd = _open_private(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
        if fd is None:
            return
        try:
            os.write(fd, (json.dumps(line, separators=(",", ":")) + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        return


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def valid_id(value: Any, composed: bool = False) -> bool:
    """Session ids and turn ids; composed (agy `conversation:invocation`) ids map ':' to '_'."""
    if not isinstance(value, str):
        return False
    return bool(ID_RE.match(value.replace(":", "_") if composed else value))


def normalize_role(role: Any) -> Optional[str]:
    """Bare role name; a leading allowlisted namespace (`shoal:`) is removed once (K3)."""
    if not isinstance(role, str):
        return None
    for prefix in ROLE_NAMESPACES:
        if role.startswith(prefix):
            return role[len(prefix):]
    return role


def role_access(role: Any) -> Optional[str]:
    return ROLE_ACCESS.get(normalize_role(role))


def resolve_mode(host: str, env: Dict[str, str], home: Optional[Path] = None) -> str:
    """Unset -> host default; an unrecognized value -> shadow (as the legacy guard did).

    With `home`, the installed module manifest can switch the guard off for this host (modular-install S3,
    `--without dispatch-guard`): that is the persistent switch for hosts where the guard ships inside a plugin."""
    if home is not None and not dispatch_guard_selected(host, env, home):
        return "off"
    raw = env.get("SHOAL_GUARD") or ""
    if not raw:
        mode = HOST_DEFAULT_MODE.get(host, "shadow")
    else:
        mode = raw if raw in ("enforce", "shadow", "off") else "shadow"
    return mode


def subagent_write_enabled(host: str, env: Dict[str, str]) -> bool:
    """SHOAL_GUARD_SUBAGENT_WRITE: `on` enables E1, `off` disables it; unset (or any other value) follows the
    host default: on for claude, codex, grok and agy (SUBAGENT_WRITE_DEFAULT_ON_HOSTS)."""
    raw = env.get("SHOAL_GUARD_SUBAGENT_WRITE")
    if raw in ("on", "off"):
        return raw == "on"
    return host in SUBAGENT_WRITE_DEFAULT_ON_HOSTS


def _direct_turns(state: Dict[str, Any]) -> List[str]:
    """The `direct_turns` list of a state file: strings only, the last DIRECT_TURNS_MAX."""
    raw = state.get("direct_turns")
    if not isinstance(raw, list):
        return []
    return [t for t in raw if isinstance(t, str)][-DIRECT_TURNS_MAX:]


def _agents(state: Dict[str, Any], key: str) -> List[str]:
    """`direct_agents` / `started_agents` of a state file (codex): ids that pass valid_id, the last AGENTS_MAX."""
    raw = state.get(key)
    if not isinstance(raw, list):
        return []
    return [a for a in raw if valid_id(a)][-AGENTS_MAX:]


# Per-turn booleans of a state file: dispatched, advised, direct (this turn's prompt carried #direct), declared (main
# declared direct work, M3), changed (B2, see _mark_changed), checked (B2: a check after the latest change),
# stop_blocked (B3: this turn's one block is spent).
_STATE_FLAGS = ("dispatched", "advised", "direct", "declared", "changed", "checked", "stop_blocked")


def _new_state(turn_id: Optional[str], edited: List[Any], **values: Any) -> Dict[str, Any]:
    """A turn's state with the fixed defaults and key order of the state file; `values` are explicit per-key results
    computed by the caller, never a prior state (docs/specs/code-restructure F7).  `pending` counts write dispatches
    whose role has not started yet (M11)."""
    state: Dict[str, Any] = {"turn_id": turn_id, "dispatched": False, "advised": False, "edited": edited,
                             "direct": False, "declared": False, "pending": 0, "changed": False, "checked": False,
                             "stop_blocked": False}
    unknown = set(values) - set(state)
    if unknown:
        raise KeyError(sorted(unknown))
    state.update(values)
    return state


def _carry_agents(state: Dict[str, Any], prior: Dict[str, Any]) -> None:
    """Keep the two agent lists and the `post_seen` flag of `prior` in `state` (they live across turns, like `direct_turns`)."""
    if prior.get("post_seen") is True:
        state["post_seen"] = True
    for key in ("direct_agents", "started_agents"):
        kept = _agents(prior, key)
        if kept:
            state[key] = kept


def write_agent_allowed(role: Any, env: Dict[str, str]) -> bool:
    """SHOAL_GUARD_WRITE_AGENTS: the raw agent type, or the type without a `shoal:` prefix, is in the list."""
    if not isinstance(role, str) or not role:
        return False
    wanted = {item.strip() for item in (env.get("SHOAL_GUARD_WRITE_AGENTS") or "").split(",")}
    wanted.discard("")
    return role in wanted or normalize_role(role) in wanted


def lanes_enabled(env: Dict[str, str]) -> bool:
    """SHOAL_GUARD_LANES: `off` disables the dispatch-lane rule only; any other value (or none) leaves it on."""
    return env.get("SHOAL_GUARD_LANES") != "off"


def lane_label(desc: Any) -> Optional[str]:
    """The lane label a dispatch description starts with (`[fast]`, `[complex]`, `[rigorous]`), else None."""
    match = LANE_RE.match(desc) if isinstance(desc, str) else None
    return match.group(1) if match else None


def lane_violation(role: Any, desc: Any) -> Optional[Tuple[str, Dict[str, str]]]:
    """(message key, format args) when dispatching `role` with `desc` breaks the lane rule; None otherwise.
    Only write roles are subject to it."""
    bare = normalize_role(role)
    if role_access(role) != "write" or bare is None:
        return None
    label = lane_label(desc)
    if label is None:
        return "LANE_MISSING", {"role": bare}
    if bare in LANE_ROLES[label]:
        return None
    return "LANE_MISMATCH", {"label": label, "role": bare, "expected": LANE_ROLES[label][0]}


def stop_enabled(host: str, env: Dict[str, str]) -> bool:
    """SHOAL_GUARD_STOP: `off` disables the completion check on claude, codex, grok and agy; any other value (or none)
    keeps it on (grok: logging only, see stop_blocks).  No effect on a host outside STOP_HOSTS."""
    return host in STOP_HOSTS and env.get("SHOAL_GUARD_STOP") != "off"


def stop_blocks(host: str, env: Dict[str, str]) -> bool:
    """False on a host whose block output is unverified (STOP_SHADOW_DEFAULT_HOSTS) unless SHOAL_GUARD_STOP=enforce."""
    return host not in STOP_SHADOW_DEFAULT_HOSTS or env.get("SHOAL_GUARD_STOP") == "enforce"


def _agent_entries(raw: Any) -> List[Dict[str, Any]]:
    """The valid entries of a grok agent-map file's content, the last GROK_AGENTS_MAX."""
    items = raw.get("agents") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    kept = [
        e for e in items
        if isinstance(e, dict) and valid_id(e.get("id")) and valid_id(e.get("session"))
        and isinstance(e.get("role"), str) and isinstance(e.get("direct"), bool)
    ]
    return kept[-GROK_AGENTS_MAX:]


def _agy_record(raw: Any) -> Dict[str, List[Dict[str, Any]]]:
    """The valid content of the agy conversation record: {"conversations": [...], "pending": [...]}, each the last
    AGY_RECORD_MAX.  conversations: {id, kind main|sub, role, cls write|nonwrite|unknown|"", dispatcher}.
    pending (one per Subagents[] item of an invoke_subagent call): {dispatcher, role, workspace, ts}."""
    data = raw if isinstance(raw, dict) else {}
    convs = data.get("conversations")
    pend = data.get("pending")
    keep_c = [
        c for c in (convs if isinstance(convs, list) else [])
        if isinstance(c, dict) and valid_id(c.get("id")) and c.get("kind") in ("main", "sub")
        and isinstance(c.get("role"), str) and c.get("cls") in ("write", "nonwrite", "unknown", "")
        and (c.get("dispatcher") == "" or valid_id(c.get("dispatcher")))
    ]
    keep_p = [
        e for e in (pend if isinstance(pend, list) else [])
        if isinstance(e, dict) and valid_id(e.get("dispatcher")) and isinstance(e.get("role"), str)
        and isinstance(e.get("workspace"), str) and isinstance(e.get("ts"), (int, float))
        and not isinstance(e.get("ts"), bool)
    ]
    return {"conversations": keep_c[-AGY_RECORD_MAX:], "pending": keep_p[-AGY_RECORD_MAX:]}


def resolve_r1(host: str, env: Dict[str, str]) -> str:
    """SHOAL_GUARD_R1: `classified` and `off` as given; `strict` and `declare` where the host can gate.

    Unset, unrecognized, or `strict` / `declare` on a host that cannot gate -> the host default
    (`strict` on claude, codex, grok, agy and opencode, `classified` elsewhere)."""
    raw = env.get("SHOAL_GUARD_R1") or ""
    if raw in ("classified", "off"):
        return raw
    if host not in DECLARE_HOSTS:
        return "classified"
    return "declare" if raw == "declare" else "strict"


# ---------------------------------------------------------------------------
# Declaration (M3): a shell call that is exactly `: shoal-direct <reason>`
# ---------------------------------------------------------------------------

_DECLARE_PREFIX_RE = re.compile(r":[ \t]+shoal-direct[ \t]+")
# Controls other than TAB: a declaration is one line of printable text.
_DECLARE_CONTROL_RE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f-\x9f]")
# A bare reason is plain words: no shell syntax, expansion or globbing (bash and zsh alike).
_DECLARE_BARE_BAD_RE = re.compile(r"[;&|<>()$`\\\"'*?\[\]{}~^!#]")
_DECLARE_SPLIT_RE = re.compile(r"[ \t]+")
MAX_REASON_CHARS = 200


def parse_declaration(command: Any) -> Optional[str]:
    """The reason when `command` is, after trimming, exactly `: shoal-direct <reason>`; else None.

    `:` is the shell's no-op, so the call does nothing; the guard only reads it.  The reason is
    double-quoted (a backslash escapes only `"`, `\\`, `$` and the backtick; an unescaped `$` or
    backtick would expand and is refused), single-quoted, or bare (plain words, see
    _DECLARE_BARE_BAD_RE, no word starting with `=`).  It must be non-empty after trimming.  Nothing
    may follow it and nothing may precede the `:`: no `;`, `&&`, `||`, `|`, newline, subshell,
    redirection or comment.  The TypeScript port (guard/declaration.ts) must return the same value
    for every case in tests/fixtures/declaration_cases.json.
    """
    if not isinstance(command, str):
        return None
    text = command.strip(" \t\r\n")
    if _DECLARE_CONTROL_RE.search(text):
        return None
    head = _DECLARE_PREFIX_RE.match(text)
    if head is None:
        return None
    rest = text[head.end():]
    if not rest:
        return None
    reason: Optional[str]
    if rest[0] == "'":
        end = rest.find("'", 1)
        reason = rest[1:end] if end == len(rest) - 1 else None
    elif rest[0] == '"':
        reason = _double_quoted_reason(rest)
    elif _DECLARE_BARE_BAD_RE.search(rest) or any(w.startswith("=") for w in _DECLARE_SPLIT_RE.split(rest)):
        reason = None
    else:
        reason = rest
    if reason is None:
        return None
    reason = reason.strip(" \t")
    return reason or None


def _double_quoted_reason(rest: str) -> Optional[str]:
    """`rest` starts with `"`: the unescaped text when the string closes at the very end, else None."""
    buf: List[str] = []
    i, n = 1, len(rest)
    while i < n:
        c = rest[i]
        if c == "\\" and i + 1 < n and rest[i + 1] in '"\\$`':
            buf.append(rest[i + 1])
            i += 2
        elif c == '"':
            return "".join(buf) if i == n - 1 else None
        elif c in "$`":
            return None
        else:
            buf.append(c)
            i += 1
    return None


def log_reason(reason: str) -> str:
    """The reason as logged: control characters removed, at most MAX_REASON_CHARS characters."""
    return _DECLARE_CONTROL_RE.sub("", reason.replace("\t", ""))[:MAX_REASON_CHARS]


def _max_files(env: Dict[str, str]) -> Optional[int]:
    """None when the configured value is not an integer (the guard then fails open)."""
    raw = env.get("SHOAL_GUARD_MAX_FILES") or "2"
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def resolve_path(path: str, cwd: str) -> str:
    """Absolute, symlink-resolved path (`..` collapsed); non-existent tails are kept."""
    if not os.path.isabs(path):
        path = os.path.join(cwd or os.getcwd(), path)
    return os.path.realpath(path)


def _under(path: str, root: str) -> bool:
    root = root.rstrip("/")
    return bool(root) and (path == root or path.startswith(root + "/"))


def repo_under_test(cwd: str) -> str:
    """Root of the repository under test: the nearest ancestor of `cwd` holding `.git` (a directory or a
    worktree file); `cwd` itself (resolved) when there is none."""
    start = os.path.realpath(cwd or os.getcwd())
    cursor = start
    while True:
        if os.path.exists(os.path.join(cursor, ".git")):
            return cursor
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return start
        cursor = parent


def is_exempt(path: str, host: str, env: Dict[str, str], home: Path) -> bool:
    """`path` is already resolved.  Exempt: /tmp, $TMPDIR, any `.ai` directory, transcripts."""
    if ".ai" in path.split("/")[:-1]:
        return True
    roots = ["/tmp", "/private/tmp", os.path.realpath("/tmp")]
    tmpdir = env.get("TMPDIR", "")
    if tmpdir and os.path.isabs(tmpdir) and os.path.realpath(tmpdir) != "/":
        roots.append(os.path.realpath(tmpdir))
    if host == "claude":
        roots.append(os.path.realpath(str(home / ".claude" / "projects")))
        config = env.get("CLAUDE_CONFIG_DIR", "")
        if config and os.path.isabs(config):
            roots.append(os.path.realpath(os.path.join(config, "projects")))
    return any(_under(path, root) for root in roots)


# ---------------------------------------------------------------------------
# Shell writes (G5): a literal check of a `Bash` command string, not a shell parser
# ---------------------------------------------------------------------------

# Target reported when a write is certain but its file is not: `sed -i` without file operands
# (xargs / find -exec feed them), or a redirect to a variable.  Never exempt.
UNKNOWN_TARGET = "$?"
_WORD_BREAK = " \t\r\n;|&<>()"
_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# `$NAME` / `${NAME}` leading a target word, and the literal bases a tracked value or `cd` target may have.
_VAR_REF_RE = re.compile(r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})(?=/|\Z)")
_KNOWN_BASE_RE = re.compile(r"/|~(?=/|\Z)|\$(?:HOME|TMPDIR|\{HOME\}|\{TMPDIR\})(?=/|\Z)")
_SET_COMMANDS = frozenset(("export", "declare", "local", "typeset", "readonly"))
_CD_NAMES = frozenset(("cd", "pushd", "popd"))
_DOUBLE_BRACKET_END_RE = re.compile(r"(?:^|\s)\]\](?=$|[\s;&|)])")
# Words after which the next word is still a command (`FOO=1 tee f`, `then tee f`).
_COMMAND_KEEP = frozenset(("then", "do", "else", "elif", "if", "while", "until", "!", "{"))
# Wrappers: the next word is the real command, after any options.  `-exec` / `-execdir` work
# anywhere on a `find` line, so they are matched at argument position too.
_COMMAND_WRAPPERS = frozenset(("sudo", "command", "exec", "env", "time", "nohup", "builtin", "xargs"))
_FIND_EXEC = frozenset(("-exec", "-execdir"))
# sed flags that take no value; the first other letter ends a short-option cluster.
_SED_FLAG_LETTERS = "Enrsuzb"
# Python file writes, matched over the whole command only when a `python[0-9.]*` runs in it.
_PYTHON_NAME_RE = re.compile(r"python[0-9.]*")
_PY_WRITE_RE = re.compile(
    r"""\bopen\(\s*(?:(['"])([^'"\n]*)\1)?[^\n]{0,200}?,\s*(?:mode=)?['"][rbt]*[wax][rbt+]*['"]"""
    r"|\.write_(?:text|bytes)\("
    r"|\bshutil\.(?:copy\w*|move)\("
    r"|\bos\.(?:remove|unlink|rename|replace)\(",
    re.ASCII,
)


def _skip_parens(text: str, start: int) -> int:
    """`text[start]` is `(`: index just after the matching `)` (len(text) when unbalanced)."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = text.find("'", i + 1)
            i = n if j < 0 else j + 1
            continue
        if c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _read_word(text: str, start: int) -> Tuple[str, int]:
    """One shell word from `start`: quotes removed, `$(...)` / `${...}` / backticks kept raw."""
    buf: List[str] = []
    i, n = start, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c in _WORD_BREAK:
            break
        if c == "\\":
            if nxt and nxt != "\n":
                buf.append(nxt)
            i += 2
        elif c == "'":
            j = text.find("'", i + 1)
            j = n if j < 0 else j
            buf.append(text[i + 1:j])
            i = j + 1
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            buf.append(text[i + 1:min(j, n)])
            i = j + 1
        elif c == "$" and nxt == "(":
            j = _skip_parens(text, i + 1)
            buf.append(text[i:j])
            i = j
        elif c == "$" and nxt == "{":
            j = text.find("}", i + 2)
            j = n if j < 0 else j + 1
            buf.append(text[i:j])
            i = j
        elif c == "$" and nxt == "'":
            j = i + 2
            while j < n and text[j] != "'":
                j += 2 if text[j] == "\\" else 1
            buf.append(text[i + 2:min(j, n)])
            i = j + 1
        elif c == "`":
            j = text.find("`", i + 1)
            j = n if j < 0 else j + 1
            buf.append(text[i:j])
            i = j
        else:
            buf.append(c)
            i += 1
    return "".join(buf), min(i, n)


def _tee_files(args: List[str]) -> List[str]:
    return [a for a in args if a and not a.startswith("-")]


def _sed_in_place_files(args: List[str]) -> List[str]:
    """File operands of a `sed -i` / `--in-place` call; [] when the call does not edit in place."""
    in_place, have_script = False, False
    positional: List[str] = []
    k = 0
    while k < len(args):
        a = args[k]
        if a == "--":
            positional.extend(args[k + 1:])
            break
        if a.startswith("--"):
            if a == "--in-place" or a.startswith("--in-place="):
                in_place = True
            elif a in ("--expression", "--file"):
                have_script = True
                k += 1
            elif a.startswith(("--expression=", "--file=")):
                have_script = True
        elif a.startswith("-") and len(a) > 1:
            for index, letter in enumerate(a[1:]):
                if letter == "i":
                    in_place = True
                    break
                if letter in "efl":
                    have_script = have_script or letter != "l"
                    if index == len(a) - 2:
                        k += 1  # the value is the next argument
                    break
        elif a:  # an empty word is macOS's `-i ''` suffix, never a file or the script
            positional.append(a)
        k += 1
    if not in_place:
        return []
    files = positional if have_script else positional[1:]
    return files or [UNKNOWN_TARGET]


def _perl_in_place_files(args: List[str]) -> List[str]:
    """File operands of a `perl -i` call (`-pi`, `-0pi`, `-i.bak`, `--in-place`); [] when it does not edit in place."""
    in_place, have_script = False, False
    positional: List[str] = []
    k = 0
    while k < len(args):
        a = args[k]
        if a == "--":
            positional.extend(args[k + 1:])
            break
        if a.startswith("--"):
            in_place = in_place or a == "--in-place" or a.startswith("--in-place=")
        elif a.startswith("-") and len(a) > 1:
            for index, letter in enumerate(a[1:]):
                if letter == "i":
                    in_place = True
                    break
                if letter in "eE":
                    have_script = True
                    if index == len(a) - 2:
                        k += 1  # the script is the next argument
                    break
                if letter in "IMmFxdDVC":  # the rest of the word (or the next argument) is its value
                    break
        elif a:
            positional.append(a)
        k += 1
    if not in_place:
        return []
    files = positional if have_script else positional[1:]
    return files or [UNKNOWN_TARGET]


def _known_path(value: str) -> bool:
    """An absolute path, or one led by `~` / `$HOME` / `$TMPDIR` (braces ok), with no other `$` or backtick."""
    m = _KNOWN_BASE_RE.match(value)
    return bool(m) and "$" not in value[m.end():] and "`" not in value[m.end():]


def _in_dir(word: str, base: Optional[str]) -> str:
    """A relative literal `word` joined to `base`; anything else (absolute, `~`, `$...`, UNKNOWN_TARGET) as is."""
    if base and word and word != UNKNOWN_TARGET and word[0] not in "/~$`":
        return base.rstrip("/") + "/" + word
    return word


def shell_write_targets(command: str) -> List[str]:
    """File targets that `command` writes by a literal reading of its text (G5).

    Counts `>`, `>>`, `>|`, `&>` redirects to a word, `tee [-a] file...`, `sed -i` /
    `--in-place` and `perl -i` (`-pi`, `-0pi`, `-i.bak`), each at command position (after `;`, `|`, `&&`, newline, `(`, `then`, `do`, or
    wrappers such as `sudo`, `env`, `xargs`, `find -exec`).  Never counts: `>&2` / `2>&1`
    duplications, `<` input, here-document bodies, quoted text, `[[ ]]`, `(( ))`, `$(( ))`,
    comments and `>(...)`.  Targets are returned as written (quotes removed); a target holding
    `$` or a backtick has no known value and is the caller's call.  Writes through any other
    interpreter or command (python, node, `perl -e` code that opens a file, cp, mv, patch,
    git apply, dd, ...) are not detected.  The TypeScript port (guard/shell-writes.ts) must return the same list.

    Python (`python[0-9.]*` at command position, absolute path included): when one runs, the whole
    command text (here-document body and `-c` code alike) is scanned for `open(..., '<w|a|x mode>')`
    with a literal mode, `.write_text(` / `.write_bytes(`, `shutil.copy*(` / `shutil.move(` and
    `os.remove|unlink|rename|replace(`.  `open('literal', ...)` reports that path; every other hit
    reports UNKNOWN_TARGET; these come after the shell targets.  This is a guardrail against routine
    edits, not a sandbox: exec/eval, getattr, subprocess, script files (`python x.py`), computed modes,
    `node -e`, cp and mv are not covered.

    Two literal rewrites make routine temp-dir work readable.  (1) A standalone `NAME=<known path>` (or
    `export NAME=...`) that runs unconditionally -- not after `&&` / `||` / `|` of a non-assignment command, not
    inside `( )`, `if`, `do`, `case` -- is substituted into a later target that starts with `$NAME` / `${NAME}`;
    a value that is not a known path (see `_known_path`) makes NAME unknown again.  (2) A `cd <known path>`
    (also via a known NAME) followed by `;`, `&&` or a newline, while every command so far was an assignment
    or a `cd`, makes later relative targets (python `open('x')` too) absolute under it.  `cd -`, `cd $(...)`,
    a relative or unknown `cd`, `pushd` / `popd`, a `cd` in a subshell, pipeline or `||` leave relative
    targets as written.
    """
    if (">" not in command and "tee" not in command and "sed" not in command and "perl" not in command
            and "python" not in command):
        return []
    targets: List[str] = []
    n = len(command)
    i = 0
    cmd_pos, wrapped = True, False
    name: Optional[str] = None
    args: List[str] = []
    heredocs: List[Tuple[str, bool]] = []
    python_ran = False
    variables: Dict[str, Optional[str]] = {}
    pending: List[str] = []  # assignments before the current command word
    cur_dir: Optional[str] = None
    py_dirs: Set[Optional[str]] = set()
    leading = True  # every command so far was an assignment or a `cd`
    sticky = False  # saw a keyword, `(` or `)`: later assignments may not run as written
    guarded = False  # the next statement follows `&&` / `||` / `|` / `&` of a command that may not succeed

    def resolve(word: str) -> str:
        m = _VAR_REF_RE.match(word)
        value = variables.get(m.group(1) or m.group(2)) if m else None
        return value + word[m.end():] if m and value else word

    def locate(word: str) -> str:
        return _in_dir(resolve(word), cur_dir)

    def set_var(assignment: str) -> None:
        key, _, value = assignment.partition("=")
        value = resolve(value)
        variables[key] = value if not (sticky or guarded) and _known_path(value) else None

    def flush(sep: str = "") -> None:
        nonlocal name, args, cmd_pos, wrapped, python_ran, cur_dir, leading, guarded
        if name is None:
            for assignment in pending:
                set_var(assignment)
        elif name in _CD_NAMES:
            positional = [a for a in args if not (a.startswith("-") and a != "-")]
            if name == "cd" and leading and sep in (";", "&&", "\n"):
                target = resolve(positional[0]) if len(positional) == 1 else ""
                cur_dir = target if _known_path(target) else None
            else:
                cur_dir, leading = None, False
        elif name in _SET_COMMANDS:
            for a in args:
                if _ASSIGNMENT_RE.match(a):
                    set_var(a)
        else:
            leading = False
            if _PYTHON_NAME_RE.fullmatch(name):
                python_ran = True
                py_dirs.add(cur_dir)
            elif name == "tee":
                targets.extend(locate(f) for f in _tee_files(args))
            elif name == "sed":
                targets.extend(locate(f) for f in _sed_in_place_files(args))
            elif name == "perl":
                targets.extend(locate(f) for f in _perl_in_place_files(args))
        pending.clear()
        if sep in ("||", "|", "|&", "&") or (sep == "&&" and not leading):
            guarded = True
        elif sep in (";", ";;", "\n"):
            guarded = False
        name, args, cmd_pos, wrapped = None, [], True, False

    while i < n:
        c = command[i]
        nxt = command[i + 1] if i + 1 < n else ""
        if c in " \t\r":
            i += 1
        elif c == "\n":
            flush("\n")
            i += 1
            for delim, strip in heredocs:  # bodies start on the next line
                while i < n:
                    end = command.find("\n", i)
                    end = n if end < 0 else end
                    line = command[i:end]
                    i = min(end + 1, n)
                    if (line.lstrip("\t") if strip else line) == delim:
                        break
            heredocs = []
        elif c == "#" and (i == 0 or command[i - 1] in " \t\n;|&()"):
            end = command.find("\n", i)
            i = n if end < 0 else end
        elif c in ";|" or (c == "&" and nxt != ">"):
            sep = c
            i += 1
            if i < n and command[i] in ";|&":
                sep += command[i]
                i += 1
            flush(sep)
        elif c == ">" or c == "&":  # `&>` writes both streams to a file
            i += 2 if c == "&" else 1
            if i < n and command[i] in ">|":
                i += 1
            elif i < n and command[i] == "(":
                continue  # process substitution `>(cmd)`
            dup = c == ">" and i < n and command[i] == "&"
            if dup:
                i += 1
            while i < n and command[i] in " \t":
                i += 1
            word, i = _read_word(command, i)
            fd_only = dup and (word in ("", "-") or word.isdigit() or word.startswith("$"))
            if word and not fd_only:
                targets.append(locate(word))
        elif c == "<":
            if command.startswith("<<<", i):
                i += 3
                while i < n and command[i] in " \t":
                    i += 1
                _, i = _read_word(command, i)
            elif nxt == "<":
                i += 2
                strip = i < n and command[i] == "-"
                i += 1 if strip else 0
                while i < n and command[i] in " \t":
                    i += 1
                delim, i = _read_word(command, i)
                heredocs.append((delim, strip))
            elif nxt == "(":
                i += 1  # process substitution `<(cmd)`
            else:
                i += 1
                if i < n and command[i] in "&>":
                    i += 1
                while i < n and command[i] in " \t":
                    i += 1
                _, i = _read_word(command, i)
        elif c == "(":
            if nxt == "(":
                i = _skip_parens(command, i)  # `(( ... ))`
                flush()
                cmd_pos = False
            else:
                flush()
                sticky, leading = True, False
                i += 1
        elif c == ")":
            flush()
            sticky = True
            i += 1
        elif c.isdigit() and _fd_prefix(command, i):
            while command[i].isdigit():
                i += 1
        else:
            word, i = _read_word(command, i)
            if word in _FIND_EXEC and not cmd_pos:
                flush()
                wrapped = True
            elif word == "[[" and cmd_pos:
                found = _DOUBLE_BRACKET_END_RE.search(command, i)
                i = found.end() if found else n
                cmd_pos = False
            elif not cmd_pos:
                args.append(word)
            elif _ASSIGNMENT_RE.match(word):
                pending.append(word)
            elif word in _COMMAND_KEEP:
                sticky, leading = True, False
            elif wrapped and word.startswith("-"):
                pass
            elif word in _COMMAND_WRAPPERS:
                wrapped = True
            else:
                name, args, cmd_pos, wrapped = word.rsplit("/", 1)[-1], [], False, False
    flush()
    if python_ran:
        base = next(iter(py_dirs)) if len(py_dirs) == 1 else None
        targets.extend(_in_dir(m.group(2), base) if m.group(2) else UNKNOWN_TARGET for m in _PY_WRITE_RE.finditer(command))
    return targets


def _fd_prefix(text: str, i: int) -> bool:
    """`text[i]` starts a digit run directly followed by `<` or `>` (a file-descriptor number)."""
    n = len(text)
    while i < n and text[i].isdigit():
        i += 1
    return i < n and text[i] in "<>"


def _pending(state: Dict[str, Any]) -> int:
    value = state.get("pending")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _mark_changed(state: Dict[str, Any]) -> None:
    """B2: a change after a check puts the turn back to "unchecked"; a write role's own check no longer covers it."""
    state["changed"] = True
    state.pop("role_running", None)
    state["checked"] = False
    state.pop("role_changed", None)


def _text(env: Dict[str, str], key: str, **fmt: Any) -> str:
    lang = "zh-TW" if env.get("SHOAL_GUARD_LANG") == "zh-TW" else "en"
    return MESSAGES[lang][key].format(**fmt)


def _exit_text(env: Dict[str, str], host: str, key: str) -> str:
    """STRICT / DECLARE, or their variant without the `#direct` exit on a host whose prompt event carries no text."""
    return _text(env, key if host in PROMPT_DIRECT_HOSTS else key + "_ND")


class _Guard:
    """One evaluation: holds env, home, host, mode and the lazily verified state dir."""

    def __init__(self, event: Dict[str, Any], env: Dict[str, str], home: Path) -> None:
        self.event = event
        # Fast mode (SHOAL_GUARD_FAST=1) marks the light lane only; it does not release main edits.
        self.fast = env.get("SHOAL_GUARD_FAST") == "1"
        self.env = env
        self.home = home
        self.host = str(event.get("host") or "")
        self.started = time.monotonic()  # the chain's budget counts from here
        self.mode = resolve_mode(self.host, env, home)
        # Chain-only: the manifest switched the dispatch guard off for this host but it has chain members, so the
        # dispatch rules stay off and the chain still runs (the mode the chain denies with is the host's own).
        self.chain_only = False
        if self.mode == "off" and resolve_mode(self.host, env) != "off" and chain_members(self.host, env, home):
            self.chain_only = True
            self.mode = resolve_mode(self.host, env)
        self.r1 = resolve_r1(self.host, env)
        self.fast_state = False  # the session's fast flag as persisted by this prompt event
        self.pending_change: Optional[Path] = None  # state file of an allowed write not yet counted as a change
        self._dir: Optional[Path] = None
        self._dir_tried = False

    @property
    def guard_dir(self) -> Optional[Path]:
        if not self._dir_tried:
            self._dir_tried = True
            self._dir = _guard_dir(self.env, self.home)
        return self._dir

    def log(self, decision: str, **extra: Any) -> None:
        record = {
            "host": self.host,
            "event": self.event.get("kind"),
            "tool": self.event.get("tool_name"),
            "decision": decision,
            "mode": self.mode,
            "session": short_hash(self.event.get("session_id")),
            "turn": short_hash(self.event.get("turn_id")),
        }
        if self.event.get("is_subagent") or self.event.get("kind") == "subagent_start":
            record["agent_type"] = self.event.get("role")
            record["agent_id"] = self.event.get("agent_id")
        if self.fast:
            record["fast"] = True
        record.update(extra)
        _append_log(self.guard_dir, record)

    def result(
        self,
        decision: str,
        rule: Optional[str] = None,
        skip: Optional[str] = None,
        reason: Optional[str] = None,
        file: Optional[str] = None,
        notify: bool = False,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        if decision in ("skip", "deny", "would_deny", "advise", "allow", "state", "block", "would_block"):
            self.log(decision, rule=rule, skip_reason=skip, file=file, reason=note)
        return {
            "decision": decision,
            "rule": rule,
            "skip_reason": skip,
            "reason": reason,
            "mode": self.mode,
            "notify": notify,
        }

    # -- subagent backstop (spec R6) ----------------------------------------
    def subagent(self) -> Dict[str, Any]:
        role = self.event.get("role")
        tool_kind = self.event.get("tool_kind")
        if self.host in AGENT_KEYED_HOSTS and role_access(role) == "write" and tool_kind in ("edit", "shell"):
            self.note_started_by_tool()  # logs its own record; the call itself is judged below as before
        rule = None
        if tool_kind == "dispatch":
            rule = "LEAF"
        elif tool_kind == "edit" and role_access(role) == "verify":
            rule = "VERIFY_EDIT"
        if rule is None and subagent_write_enabled(self.host, self.env):
            rule = self._subagent_write_rule(role, tool_kind)
        if rule is None:
            if role_access(role) == "write" and tool_kind in ("edit", "shell"):
                self.note_role_call(tool_kind)
            return {
                "decision": "none",
                "rule": None,
                "skip_reason": None,
                "reason": None,
                "mode": self.mode,
            }
        paths = self.event.get("paths") or []
        decision = "deny" if self.mode == "enforce" else "would_deny"
        file = paths[0] if paths else None
        if rule in ("E1", "E1_UNKNOWN") and tool_kind == "shell":
            file = self.shell_write_target(role_access(role) == "verify")
        if rule == "E1_UNKNOWN":  # the role cannot be established: never denied, only logged
            return self.result("skip", "E1", skip="would_deny_unknown_class", file=file)
        key = "E1D" if rule == "E1" and self.host in SUBAGENT_DIRECT_HOSTS else rule
        return self.result(decision, rule, reason=_text(self.env, key), file=file)

    def lane_rule(self) -> Optional[Dict[str, Any]]:
        """Lane rule for a main session's dispatch: a result when it breaks the rule (deny, or would_deny in
        shadow), else None.  agy judges every Subagents[] entry (role = TypeName, label from its Role field)."""
        event = self.event
        listed = event.get("dispatched_roles") if self.host in CONVERSATION_HOSTS else None
        if listed is not None:
            descs = event.get("dispatch_descs") or []
            pairs = [(r, descs[i] if i < len(descs) else None) for i, r in enumerate(listed)]
        else:
            pairs = [(event.get("dispatched_role"), event.get("dispatch_desc"))]
        for role, desc in pairs:
            violation = lane_violation(role, desc)
            if violation is not None:
                key, fmt = violation
                decision = "deny" if self.mode == "enforce" else "would_deny"
                return self.result(decision, "LANE", reason=_text(self.env, key, **fmt))
        return None

    def _subagent_write_rule(self, role: Any, tool_kind: Any) -> Optional[str]:
        """E1: "E1" when this subagent call writes a non-exempt file and nothing releases it, else None.
        agy: the conversation's class decides (write: free; unknown: "E1_UNKNOWN", which is only logged)."""
        conv_class = self.event.get("conv_class") if self.host in CONVERSATION_HOSTS else None
        if conv_class == "write" or (conv_class is None and role_access(role) == "write"):
            return None
        if tool_kind == "edit":
            cwd = self.event.get("cwd") or os.getcwd()
            writes = any(
                not is_exempt(resolve_path(p, cwd), self.host, self.env, self.home)
                for p in self.event.get("paths") or []
            )
        elif tool_kind == "shell":
            writes = self.shell_write_target(role_access(role) == "verify") is not None
        else:
            return None
        if not writes:
            return None
        if write_agent_allowed(role, self.env) or self.env.get("SHOAL_GUARD_DIRECT") == "1":
            return None
        if self.subagent_direct_released():
            return None
        return "E1_UNKNOWN" if conv_class == "unknown" else "E1"

    def subagent_direct_released(self) -> bool:
        """The user's `#direct` releases a subagent when the turn named by the subagent event's (session_id,
        turn_id) is in the main session's `direct_turns` (codex: when its agent_id is in `direct_agents`).  Read-only; any problem (host without the payload
        evidence, bad ids, no state dir, unreadable or corrupt state) means "not released", never an exception."""
        try:
            if self.host not in SUBAGENT_DIRECT_HOSTS:
                return False
            if self.host in MAPPED_HOSTS:
                entry = self.agent_entry(self.event.get("session_id"))
                return entry is not None and entry["direct"] is True
            if self.host in AGENT_KEYED_HOSTS:
                sid, agent = self.event.get("session_id"), self.event.get("agent_id")
                guard = self.guard_dir
                if not valid_id(sid) or not valid_id(agent) or guard is None:
                    return False
                return agent in _agents(_read_json(guard / "state" / (sid + ".json")), "direct_agents")
            sid, tid = self.event.get("session_id"), self.event.get("turn_id")
            if not valid_id(sid) or not valid_id(tid):
                return False
            guard = self.guard_dir
            if guard is None:
                return False
            state = _read_json(guard / "state" / (sid + ".json"))
            return tid in _direct_turns(state)
        except Exception:
            return False

    def agent_entry(self, agent: Any) -> Optional[Dict[str, Any]]:
        """Grok: the recorded `subagent_start` of the subagent whose own session id is `agent`, or None.  Read-only; any
        problem (bad id, no state dir, unreadable file) means "no record"."""
        try:
            guard = self.guard_dir
            if guard is None or not valid_id(agent):
                return None
            for entry in reversed(_agent_entries(_read_json(guard / "state" / (GROK_AGENTS_FILE + ".json")))):
                if entry["id"] == agent:
                    return entry
        except Exception:
            return None
        return None

    def resolve_mapped_agent(self) -> None:
        """Grok: a tool event under a recorded subagent's session id is that subagent's call, whatever its own payload
        says (a generic subagent may carry no `subagentType`).  Fills `is_subagent` and a missing role."""
        entry = self.agent_entry(self.event.get("session_id"))
        if entry is None:
            return
        self.event = dict(self.event, is_subagent=True)
        if not self.event.get("role"):
            self.event["role"] = entry["role"] or None

    def register_agent(self) -> None:
        """Grok `subagent_start`: record subagent id -> {main session, role, direct flag of main's current turn}.
        Silent and best effort: without a record the subagent is judged by its own payload and `#direct` is not available."""
        try:
            sid, agent = self.event.get("session_id"), self.event.get("agent_id")
            guard = self.guard_dir
            if not valid_id(sid) or not valid_id(agent) or guard is None:
                return
            direct = _read_json(guard / "state" / (sid + ".json")).get("direct") is True
            path = guard / "state" / (GROK_AGENTS_FILE + ".json")
            with _state_lock(guard / "state" / (GROK_AGENTS_FILE + ".lock")) as lock_skip:
                if lock_skip is not None:
                    return
                entries = [e for e in _agent_entries(_read_json(path)) if e["id"] != agent]
                entries.append({"id": agent, "session": sid, "role": self.event.get("role") or "", "direct": direct})
                _write_json(path, {"agents": entries[-GROK_AGENTS_MAX:]})
        except Exception:
            return

    # -- cross-vendor relay (S1.11) ------------------------------------------
    def relay_check(self) -> Tuple[Optional[str], Optional[str]]:
        """(role, None) when this session is a relayed named role; (None, reason) when relay env is present but not
        trusted; (None, None) when there is no relay env.  Trusted only on codex, for executor / applier, with the
        runner's `relay-<nonce>` file: opened without following symlinks, regular, ours, exactly {"role", "pid"}
        with the same role and a live pid.  Read-only; any doubt is a rejection."""
        role, nonce = self.env.get("SHOAL_RELAY_ROLE"), self.env.get("SHOAL_RELAY_NONCE")
        if role is None and nonce is None:
            return None, None
        if self.host != RELAY_HOST:
            return None, "relay_host"
        if role not in RELAY_ROLES:
            return None, "relay_role"
        if not isinstance(nonce, str) or RELAY_NONCE_RE.fullmatch(nonce) is None:
            return None, "relay_nonce_format"
        guard = self.guard_dir
        if guard is None:
            return None, "state_unavailable"
        fd = _open_private(guard / ("relay-" + nonce), os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        if fd is None:
            return None, "relay_nonce_file"
        try:
            data = json.loads(os.read(fd, RELAY_NONCE_MAX_BYTES))
        except (OSError, ValueError):
            return None, "relay_nonce_content"
        finally:
            os.close(fd)
        if not isinstance(data, dict) or set(data) != {"role", "pid"} or not _is_int(data["pid"]) or data["pid"] <= 1:
            return None, "relay_nonce_content"
        if data["role"] != role:
            return None, "relay_role_mismatch"
        try:
            os.kill(data["pid"], 0)
        except OSError:  # gone, or a recycled pid we may not signal: not our runner
            return None, "relay_pid_dead"
        return role, None

    def relay(self) -> Optional[Dict[str, Any]]:
        """An adopted relay session is judged as a subagent of its role (edits allowed, no dispatch required); a
        dispatch or any other collaboration tool is denied whatever the mode (it replaces Codex's ineffective
        `features.multi_agent=false`, SPEC "T1.0 後的決策").  None: judge the event as usual."""
        role, reason = self.relay_check()
        if reason is not None:
            if self.mode != "off":  # an off guard writes nothing, as before
                self.log("relay_ignore", rule="RELAY", skip_reason=reason, tool=None)  # vectors: no tool name
            return None
        if role is None:
            return None
        self.event = dict(self.event, is_subagent=True, role=role)
        self.log("relay_adopt", rule="RELAY")
        tool = self.event.get("tool_name")
        if self.event.get("kind") == "tool" and (
            self.event.get("tool_kind") == "dispatch" or (isinstance(tool, str) and tool.startswith("collaboration"))
        ):
            return self.result("deny", "RELAY", reason=_text(self.env, "RELAY", role=role))
        return None

    def _none(self) -> Dict[str, Any]:
        return {"decision": "none", "rule": None, "skip_reason": None, "reason": None, "mode": self.mode}

    # -- agy: main vs subagent by conversation order --------------------------
    def _agy_paths(self) -> Optional[Tuple[Path, Path]]:
        guard = self.guard_dir
        if guard is None:
            return None
        return guard / "state" / (AGY_RECORD_FILE + ".json"), guard / "state" / (AGY_RECORD_FILE + ".lock")

    def agy_conversation(self, cid: Any) -> Optional[Dict[str, Any]]:
        """The recorded conversation `cid`, or None (no record, bad id, no state dir: all mean "main").  Read-only."""
        try:
            paths = self._agy_paths()
            if paths is None or not valid_id(cid):
                return None
            for entry in reversed(_agy_record(_read_json(paths[0]))["conversations"]):
                if entry["id"] == cid:
                    return entry
        except Exception:
            return None
        return None

    def agy_push_pending(self) -> None:
        """PreToolUse of invoke_subagent: one pending entry per listed subagent.  Silent, best effort."""
        try:
            cid = self.event.get("session_id")
            paths = self._agy_paths()
            if paths is None or not valid_id(cid):
                return
            roles = self.event.get("dispatched_roles") or [""]
            with _state_lock(paths[1]) as lock_skip:
                if lock_skip is not None:
                    return
                record = _agy_record(_read_json(paths[0]))
                now = time.time()
                pending = [e for e in record["pending"] if now - e["ts"] <= AGY_PENDING_TTL]
                for role in roles:
                    pending.append({"dispatcher": cid, "role": role if isinstance(role, str) else "",
                                    "workspace": self.event.get("workspace") or "", "ts": now})
                record["pending"] = pending[-AGY_RECORD_MAX:]
                _write_json(paths[0], record)
        except Exception:
            return

    def _agy_class(self, role: str) -> str:
        """write for a shoal write role or an allowlisted type, unknown for no role name, else nonwrite."""
        if not role:
            return "unknown"
        return "write" if role_access(role) == "write" or write_agent_allowed(role, self.env) else "nonwrite"

    def agy_session_start(self) -> Dict[str, Any]:
        """SessionStart of an unseen conversation: a subagent when a dispatch is pending (oldest first, preferring the
        same workspace), else a main conversation.  The role is known only when every candidate dispatch names the same
        one; otherwise the access class is recorded when all candidates share it, else "unknown".  A write class
        releases the dispatcher's pending write dispatch (the "started" evidence of M11); a verify role counts as a check."""
        cid = self.event.get("session_id")
        paths = self._agy_paths()
        if not valid_id(cid):
            return self.result("skip", skip="invalid_id")
        if paths is None:
            return self.result("skip", skip="state_unavailable")
        with _state_lock(paths[1]) as lock_skip:
            if lock_skip is not None:
                return self.result("skip", skip=lock_skip)
            record = _agy_record(_read_json(paths[0]))
            if any(c["id"] == cid for c in record["conversations"]):
                return self._none()
            now = time.time()
            pending = [e for e in record["pending"] if now - e["ts"] <= AGY_PENDING_TTL]
            ws = self.event.get("workspace") or ""
            cands = [e for e in pending if ws and e["workspace"] == ws] or pending
            if cands:
                roles = [e["role"] for e in cands]
                role = roles[0] if len(set(roles)) == 1 else ""
                classes = {self._agy_class(r) for r in roles}
                cls = classes.pop() if len(classes) == 1 else "unknown"
                taken = cands[0]
                pending.remove(taken)
                entry = {"id": cid, "kind": "sub", "role": role, "cls": cls, "dispatcher": taken["dispatcher"]}
            else:
                entry = {"id": cid, "kind": "main", "role": "", "cls": "", "dispatcher": ""}
            record["conversations"] = (record["conversations"] + [entry])[-AGY_RECORD_MAX:]
            record["pending"] = pending
            if not _write_json(paths[0], record):
                return self.result("skip", skip="state_write_failed")
        if entry["kind"] == "main":
            return self.result("state", "conversation_main")
        if entry["cls"] == "write":
            self.event = dict(self.event, session_id=entry["dispatcher"])
            return self._release_pending(entry["dispatcher"], None, None)
        if role_access(entry["role"]) == "verify":
            self.event = dict(self.event, session_id=entry["dispatcher"])
            self.note_verify_started()
        return self.result("state", "conversation_sub", note="class_" + entry["cls"])

    def agy_route(self) -> Optional[Dict[str, Any]]:
        """agy: the result for SessionStart and for a subagent conversation's events; None = judge as main (a
        conversation without a record is main).  The adapter's own `is_subagent` is never used on this host."""
        kind, tool_kind = self.event.get("kind"), self.event.get("tool_kind")
        if kind == "session_start":
            return self.agy_session_start()
        if kind == "tool" and tool_kind == "dispatch":
            self.agy_push_pending()
        rec = self.agy_conversation(self.event.get("session_id"))
        if rec is None or rec["kind"] != "sub":
            self.event = dict(self.event, is_subagent=False)
            return None
        if kind != "tool":
            return self._none()  # a subagent's invocation boundary or stop is not main's
        if tool_kind == "dispatch":  # a misclassified main must never be blocked from dispatching: log only
            return self.result("skip", "LEAF", skip="leaf_dispatch_not_enforced")
        self.event = dict(self.event, is_subagent=True, role=rec["role"] or None, conv_class=rec["cls"])
        return self.subagent()

    # -- completion check (B2, B3) -------------------------------------------
    def _check_state_path(self, wanted_turn: Optional[str]) -> Optional[Tuple[Path, Path]]:
        """(state file, lock file) of this event's session for a silent state update, or None.  `wanted_turn`
        is only used to validate its shape; the caller compares the turn recorded in the state."""
        sid = self.event.get("session_id")
        if not valid_id(sid) or (wanted_turn is not None and not valid_id(wanted_turn)):
            return None
        guard = self.guard_dir
        if guard is None:
            return None
        return guard / "state" / (str(sid) + ".json"), guard / "state" / (str(sid) + ".lock")

    def note_check(self, ran: bool = False, counts: bool = True, role: bool = False) -> None:
        """B2: main ran a plain foreground shell call.  When the turn is changed and unchecked, mark it checked.

        `role` is True for a write-level role's own call: it counts only while that role's edit is the latest
        change (`role_changed`, see note_role_change), so a subagent never checks main's own edit.

        `ran` is True for the PostToolUse of that call (claude, codex): it also records `post_seen`, which turns the
        PreToolUse path off for the rest of the session.  A PreToolUse call (`ran` False) on a POST_HOSTS host
        counts only while no PostToolUse has been seen: an old registration without PostToolUse keeps working.

        Cheap by construction: hosts outside STOP_HOSTS, SHOAL_GUARD_STOP=off and a missing or invalid id return
        at once; otherwise one unlocked read of the state file, and the lock and the write only happen when the
        turn is changed and not yet checked.  Never logs, never raises into the caller's decision."""
        if not stop_enabled(self.host, self.env):
            return
        tid = self.event.get("turn_id")
        paths = self._check_state_path(tid)
        if paths is None:
            return
        state_path, lock_path = paths

        def pending_check(state: Dict[str, Any]) -> bool:
            if not counts:
                return False  # a write or declaration: not a check itself, but its PostToolUse still proves the hook fires
            if not ran and self.host in POST_HOSTS and state.get("post_seen") is True:
                return False  # the PostToolUse path owns the check on this session
            if role and state.get("role_changed") is not True:
                return False  # the latest change is not this role's edit
            return (
                state.get("changed") is True
                and state.get("checked") is not True
                and (tid is None or state.get("turn_id") == tid)
            )

        def needs_write(state: Dict[str, Any]) -> bool:
            return pending_check(state) or (ran and bool(state) and state.get("post_seen") is not True)

        if not needs_write(_read_json(state_path)):
            return
        with _state_lock(lock_path) as lock_skip:
            if lock_skip is not None:
                return
            state = _read_json(state_path)
            if not needs_write(state):
                return
            if ran:
                state["post_seen"] = True
            if pending_check(state):
                state["checked"] = True
            _write_json(state_path, state)

    def note_role_call(self, tool_kind: str) -> None:
        """B2 for a write-level role's own allowed call: its edit or shell write (non-exempt) puts the turn back
        to unchecked; a plain foreground shell call after it counts as the check, exactly like main's (on claude
        and codex at its PostToolUse once the session has seen one, see route)."""
        if tool_kind == "edit":
            cwd = self.event.get("cwd") or os.getcwd()
            if any(not is_exempt(resolve_path(p, cwd), self.host, self.env, self.home)
                   for p in self.event.get("paths") or []):
                self.note_role_change()
        elif self.shell_write_target() is not None:
            self.note_role_change()
        elif parse_declaration(self.event.get("command")) is None:
            self.note_check(role=True)

    def note_role_change(self) -> None:
        """A write-level role edited: the turn (already changed by the role's start) is unchecked, and the role's own
        later plain shell call may count as the check (`role_changed`; any main-side change clears it)."""
        if not stop_enabled(self.host, self.env):
            return
        tid = self.event.get("turn_id")
        paths = self._check_state_path(tid)
        if paths is None:
            return
        state_path, lock_path = paths

        def due(state: Dict[str, Any]) -> bool:
            return (state.get("changed") is True
                    and (state.get("checked") is True or state.get("role_changed") is not True)
                    and (tid is None or state.get("turn_id") == tid))

        if not due(_read_json(state_path)):
            return
        with _state_lock(lock_path) as lock_skip:
            if lock_skip is not None:
                return
            state = _read_json(state_path)
            if not due(state):
                return
            state["checked"] = False
            state["role_changed"] = True
            state.pop("role_running", None)  # the role's edit is observed: no longer only a pending start
            _write_json(state_path, state)

    def note_verify_started(self) -> None:
        """B2 on claude: the SubagentStart of a verify-level role counts as a check, like its dispatch call."""
        if not stop_enabled(self.host, self.env):
            return
        paths = self._check_state_path(None)
        if paths is None:
            return
        state_path, lock_path = paths
        with _state_lock(lock_path) as lock_skip:
            if lock_skip is not None:
                return
            state = _read_json(state_path)
            if state.get("changed") is not True or state.get("checked") is True:
                return
            state["checked"] = True
            _write_json(state_path, state)

    def stop(self) -> Dict[str, Any]:
        """B3: the main session is about to end its turn.  Blocks once per turn when files changed and nothing
        checked them (see the module docstring); every other path has no opinion (fail open)."""
        event = self.event
        if not stop_enabled(self.host, self.env):
            return self._none()
        flag = event.get("stop_hook_active")
        if flag is True:
            return self._none()  # the host says this stop is the retry after a block
        conv = self.host in CONVERSATION_HOSTS
        if conv and event.get("fully_idle") is not True:
            return self._none()  # agy: only the stop that leaves the whole session idle ends main's turn
        sid, tid = event.get("session_id"), event.get("turn_id")
        if sid is None or (tid is None and not conv):  # agy's Stop carries no turn: the state's turn is used
            return self.result("skip", skip="missing_id")
        if not valid_id(sid) or (tid is not None and not valid_id(tid)):
            return self.result("skip", skip="invalid_id")
        if flag is not False:
            return self.result("skip", skip="bad_payload")
        guard = self.guard_dir
        if guard is None:
            return self.result("skip", skip="state_unavailable")
        state_path = guard / "state" / (sid + ".json")

        def due(state: Dict[str, Any]) -> bool:
            return (
                (tid is None or state.get("turn_id") == tid)
                and (not conv or isinstance(state.get("turn_id"), str))
                and state.get("changed") is True
                and state.get("checked") is not True
                and state.get("stop_blocked") is not True
            )

        if not due(_read_json(state_path)):
            return self._none()  # not this turn's state, no change, already checked or already blocked
        with _state_lock(guard / "state" / (sid + ".lock")) as lock_skip:
            if lock_skip is not None:
                return self.result("skip", skip=lock_skip)
            state = _read_json(state_path)
            if not due(state):
                return self._none()
            if state.get("role_running") is True:  # a write role started this turn and may still be running
                state.pop("role_running", None)  # one skip only: the next Stop after the hand-back is judged
                _write_json(state_path, state)
                return self.result("skip", skip="role_running")
            if self.mode != "enforce" or not stop_blocks(self.host, self.env):
                return self.result("would_block", "STOP", note="unverified_change")
            state["stop_blocked"] = True
            if not _write_json(state_path, state):  # without the flag a block could repeat: do not block
                return self.result("skip", skip="state_write_failed")
            return self.result("block", "STOP", reason=_text(self.env, "STOP"), note="unverified_change")

    def post_shell(self) -> Dict[str, Any]:
        """B2 on claude and codex: PostToolUse of a main-session shell call, i.e. the call really ran.  A plain
        foreground call (neither a declaration nor a file write) after a change marks the turn checked; any such
        event also records `post_seen`.  It never decides anything, so the result is always "none"."""
        if self.host in POST_HOSTS:
            plain = parse_declaration(self.event.get("command")) is None and self.shell_write_target() is None
            self.note_check(ran=True, counts=plain, role=self.event.get("is_subagent") is True)
        return {"decision": "none", "rule": None, "skip_reason": None, "reason": None, "mode": self.mode}

    # -- main session -------------------------------------------------------
    def main(self) -> Dict[str, Any]:
        event = self.event
        kind = event.get("kind")
        if kind == "subagent_start":
            return self.subagent_start()
        if kind == "stop":
            return self.stop()
        if kind == "post_shell":
            return self.post_shell()
        sid, tid = event.get("session_id"), event.get("turn_id")
        is_boundary = kind in ("prompt", "turn_boundary")
        tool_kind = event.get("tool_kind")
        if kind == "tool" and tool_kind == "background_shell" and self.host not in DENY_MAIN_HOSTS:
            tool_kind = None  # G4 exists on claude only
        if kind == "tool" and tool_kind == "shell":
            # A foreground shell call that is neither a declaration nor a file write has no opinion,
            # and touches no log.  `declare` reads declarations and judges writes (G5);
            # `strict` only judges writes (a declaration is an ordinary no-op there); `classified` judges
            # writes on claude only (v3.1.0); `off` has no G5.
            declaration = parse_declaration(event.get("command")) is not None
            write_target = self.shell_write_target()
            if self.r1 == "declare":
                if not declaration and write_target is None:
                    tool_kind = None
            elif self.r1 == "strict":
                if write_target is None:
                    tool_kind = None
            elif self.r1 != "classified" or self.host not in DENY_MAIN_HOSTS or write_target is None:
                tool_kind = None
            if tool_kind is None and write_target is None and not declaration:
                self.note_check()  # B2: a plain foreground call after a change counts as a check
        if kind == "tool" and tool_kind not in ("edit", "dispatch", "background_shell", "shell"):
            return {
                "decision": "none",
                "rule": None,
                "skip_reason": None,
                "reason": None,
                "mode": self.mode,
            }
        if sid is None:
            return self.result("skip", skip="missing_id")
        if not valid_id(sid):
            return self.result("skip", skip="invalid_id")
        turn_optional = kind == "tool" and self.host in STATE_TURN_HOSTS
        keep_turn = kind == "prompt" and self.host in PROMPT_KEEP_HOSTS
        if tid is None and not (turn_optional or keep_turn):
            return self.result("skip", skip="missing_id")
        if tid is not None and not valid_id(tid, composed=self.host in COMPOSED_TURN_HOSTS):
            return self.result("skip", skip="invalid_id")
        guard = self.guard_dir
        if guard is None:
            return self.result("skip", skip="state_unavailable")
        state_path = guard / "state" / (sid + ".json")

        with _state_lock(guard / "state" / (sid + ".lock")) as lock_skip:
            if lock_skip is not None:
                return self.result("skip", skip=lock_skip)
            return self._locked(is_boundary, keep_turn and tid is None, tid, state_path, guard)

    def _prompt_direct(self, prior: Dict[str, Any]) -> bool:
        """Prompt event: update the session's fast flag (`#fast` on, `#strict` off, otherwise unchanged) and return
        whether this turn counts as `#direct` (its own token only; fast mode does not release edits)."""
        switch = self.event.get("fast")
        self.fast_state = switch == "on" or (prior.get("fast") is True and switch != "off")
        if self.fast_state:
            self.fast = True
        return self.event.get("direct") is True

    def _locked(
        self, is_boundary: bool, keep: bool, tid: Optional[str], state_path: Path, guard: Path
    ) -> Dict[str, Any]:
        """The state read-modify-write; the caller holds the per-session lock."""
        event = self.event
        if is_boundary:
            if keep:
                # M1: id-less prompt.  Clear the unlock, keep turn and edits; no state, nothing to do.
                prior = _read_json(state_path)
                if not prior:
                    return self.result("skip", skip="missing_id")
                prior_turns = _direct_turns(prior)
                direct = self._prompt_direct(prior)
                edited = prior.get("edited") if isinstance(prior.get("edited"), list) else []
                prior_tid = prior.get("turn_id")
                state = _new_state(prior_tid if isinstance(prior_tid, str) else None, edited, direct=direct)
                if direct and isinstance(prior_tid, str):
                    prior_turns = (prior_turns + [prior_tid])[-DIRECT_TURNS_MAX:]
                if prior_turns:
                    state["direct_turns"] = prior_turns
                if self.fast_state:
                    state["fast"] = True
                _carry_agents(state, prior)
            else:
                prior = _read_json(state_path)
                prior_turns = _direct_turns(prior)
                direct = self._prompt_direct(prior)
                if direct and isinstance(tid, str):
                    prior_turns = (prior_turns + [tid])[-DIRECT_TURNS_MAX:]
                state = _new_state(tid, [], direct=direct)
                if prior_turns:
                    state["direct_turns"] = prior_turns
                if self.fast_state:
                    state["fast"] = True
                _carry_agents(state, prior)
            if not _write_json(state_path, state):
                return self.result("skip", skip="state_write_failed")
            return self.result("state")

        state = _read_json(state_path)
        kept_turns = _direct_turns(state)
        prior_state = state
        if tid is not None and state.get("turn_id") != tid:
            state = {}
        edited = state.get("edited") if isinstance(state.get("edited"), list) else []
        state = _new_state(tid if tid is not None else state.get("turn_id"), edited, pending=_pending(state),
                           **{flag: state.get(flag) is True for flag in _STATE_FLAGS})
        if state["changed"] and prior_state.get("role_changed") is True:
            state["role_changed"] = True  # B2: the latest change is a write role's own edit (note_role_change)
        if state["changed"] and prior_state.get("role_running") is True:
            state["role_running"] = True  # B3: the latest change is a write role's start, no edit seen yet
        if kept_turns:
            state["direct_turns"] = kept_turns  # E1: turns that carried #direct, kept across turns
        if prior_state.get("fast") is True:
            state["fast"] = True  # fast mode lasts for the session (set by #fast, cleared by #strict)
            self.fast = True
        _carry_agents(state, prior_state)  # codex: agents released by #direct / already counted as started

        if event.get("tool_kind") == "dispatch":
            listed = event.get("dispatched_roles") if self.host in CONVERSATION_HOSTS else None
            if listed is not None:  # agy: one pending start per listed write role
                writes = sum(1 for r in listed if role_access(r) == "write")
                access = "write" if writes else "verify" if any(role_access(r) == "verify" for r in listed) else None
            else:
                writes = 1
                access = role_access(event.get("dispatched_role"))
            if access == "write":
                if self.host in START_UNLOCK_HOSTS:
                    state["pending"] += writes  # released by the role's start; the call itself is allowed
                    _write_json(state_path, state)
                    return self.result("allow", "dispatch_pending")
                state["dispatched"] = True
                _mark_changed(state)
                _write_json(state_path, state)
            elif access == "verify":
                state["checked"] = True  # B2: a verify-level role was dispatched
                _write_json(state_path, state)
            return self.result("allow", "dispatch")
        if event.get("tool_kind") == "background_shell":
            return self.background_shell(state)
        if event.get("tool_kind") == "shell":
            return self.shell(state, state_path, guard)
        return self.edit(state, state_path, guard)

    def subagent_start(self) -> Dict[str, Any]:
        """M11: a role has started.  A write-level role of the main session's session releases one pending
        write dispatch and unlocks the turn; any other start (read-only or verify role, no pending dispatch,
        a host without this rule) changes nothing.

        The event is tied to the main session by session id.  Its `prompt_id` is only compared with the
        guard's current turn: a different one still releases (the association stays the session) and the
        log line says so (skip_reason prompt_id_mismatch).  Bad ids fail open with a skip record.

        Codex (AGENT_KEYED_HOSTS): the started agent's own turn_id says nothing about main's turn, so it is not
        compared; the agent is released from E1 when main's current turn carried `#direct` (`direct_agents`), and a
        write role counts once per agent_id (`started_agents`)."""
        event = self.event
        access = role_access(event.get("role"))
        if self.host in MAPPED_HOSTS:
            self.register_agent()
        if self.host in AGENT_KEYED_HOSTS:
            self.note_direct_agent()
        if self.host not in START_UNLOCK_HOSTS or access not in ("write", "verify"):
            return {"decision": "none", "rule": None, "skip_reason": None, "reason": None, "mode": self.mode}
        if access == "verify":
            self.note_verify_started()
            return self._none()
        return self._release_pending(event.get("session_id"), event.get("turn_id"), event.get("agent_id"))

    def _release_pending(self, sid: Any, tid: Any, agent: Any) -> Dict[str, Any]:
        """A write role has started: one pending dispatch of session `sid` is released, once per codex agent_id."""
        keyed = self.host in AGENT_KEYED_HOSTS
        if sid is None:
            return self.result("skip", skip="missing_id")
        if not valid_id(sid):
            return self.result("skip", skip="invalid_id")
        if keyed and not valid_id(agent):
            return self.result("skip", skip="missing_id")  # no agent_id: nothing to count the start by
        guard = self.guard_dir
        if guard is None:
            return self.result("skip", skip="state_unavailable")
        state_path = guard / "state" / (sid + ".json")
        with _state_lock(guard / "state" / (sid + ".lock")) as lock_skip:
            if lock_skip is not None:
                return self.result("skip", skip=lock_skip)
            state = _read_json(state_path)
            started = _agents(state, "started_agents")
            if keyed and agent in started:
                return self.result("skip", skip="agent_already_started")
            if _pending(state) < 1:
                return self.result("skip", skip="start_without_pending")
            mismatch = isinstance(tid, str) and not keyed and state.get("turn_id") != tid
            state["pending"] = _pending(state) - 1
            state["dispatched"] = True
            _mark_changed(state)  # B2: the write role has started, so the turn counts as changed
            if self.host in ROLE_RUNNING_HOSTS:
                state["role_running"] = True  # B3: until an edit or the next Stop (see the module docstring)
            if keyed:
                state["started_agents"] = (started + [agent])[-AGENTS_MAX:]
            if not _write_json(state_path, state):
                return self.result("skip", skip="state_write_failed")
            return self.result("state", "dispatch_started", skip="prompt_id_mismatch" if mismatch else None)

    def note_direct_agent(self) -> None:
        """Codex SubagentStart: when main's current turn carried `#direct`, remember the new agent_id as released
        (E1; the last AGENTS_MAX).  Silent and best effort: any problem leaves the agent unreleased."""
        try:
            sid, agent = self.event.get("session_id"), self.event.get("agent_id")
            guard = self.guard_dir
            if not valid_id(sid) or not valid_id(agent) or guard is None:
                return
            state_path = guard / "state" / (sid + ".json")
            if _read_json(state_path).get("direct") is not True:
                return
            with _state_lock(guard / "state" / (sid + ".lock")) as lock_skip:
                if lock_skip is not None:
                    return
                state = _read_json(state_path)
                if state.get("direct") is not True:
                    return
                state["direct_agents"] = (_agents(state, "direct_agents") + [agent])[-AGENTS_MAX:]
                _write_json(state_path, state)
        except Exception:
            return

    def note_started_by_tool(self) -> Optional[Dict[str, Any]]:
        """Codex: the first tool call of a write-level role's agent releases one pending dispatch when its
        SubagentStart has not (hook not approved yet).  Cheap: one unlocked read decides; None = nothing to do."""
        try:
            sid, agent = self.event.get("session_id"), self.event.get("agent_id")
            guard = self.guard_dir
            if not valid_id(sid) or not valid_id(agent) or guard is None:
                return None
            state = _read_json(guard / "state" / (sid + ".json"))
            if _pending(state) < 1 or agent in _agents(state, "started_agents"):
                return None
            return self._release_pending(sid, None, agent)
        except Exception:
            return None

    def background_shell(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """G4: main starting a background shell.  Reads state only; nothing is recorded."""
        if self.env.get("SHOAL_GUARD_DIRECT") == "1" or state["direct"]:
            return self.result("allow", "direct")
        return self.result(
            "deny" if self.mode == "enforce" else "would_deny", "G4", reason=_text(self.env, "G4")
        )

    def shell_write_target(self, outside_repo_ok: bool = False) -> Optional[str]:
        """G5: the first non-exempt file that main's shell command writes (UNKNOWN_TARGET or the
        raw text when its value is not known), or None.  `/dev/...`, exempt paths and nothing
        else are skipped; the check reads no state.  `outside_repo_ok` (verify roles, E1) also skips a
        target that resolves outside the repository under test (`repo_under_test(cwd)`)."""
        command = self.event.get("command")
        if not isinstance(command, str) or not command:
            return None
        cwd = self.event.get("cwd") or os.getcwd()
        repo = repo_under_test(cwd) if outside_repo_ok else None
        for raw in shell_write_targets(command):
            target = self._expand_target(raw)
            if target is None:
                return raw  # `$var`, `$(...)`, backticks: a redirect to a non-/dev target
            if target == "/dev" or target.startswith("/dev/"):
                continue
            resolved = resolve_path(target, cwd)
            if is_exempt(resolved, self.host, self.env, self.home):
                continue
            if repo is not None and not _under(resolved, repo):
                continue
            return raw
        return None

    def _expand_target(self, raw: str) -> Optional[str]:
        """Leading `~`, `$HOME`, `${HOME}`, `$TMPDIR`, `${TMPDIR}` expanded; None while unknown."""
        target = raw
        for prefix, base in (("~", str(self.home)), ("$HOME", str(self.home)), ("${HOME}", str(self.home)),
                             ("$TMPDIR", self.env.get("TMPDIR", "")), ("${TMPDIR}", self.env.get("TMPDIR", ""))):
            if target == prefix or target.startswith(prefix + "/"):
                if not base or not os.path.isabs(base):
                    return None
                target = base + target[len(prefix):]
                break
        return None if ("$" in target or "`" in target) else target

    def shell(self, state: Dict[str, Any], state_path: Path, guard: Path) -> Dict[str, Any]:
        """A main-session foreground shell call: a declaration (`declare` mode) or G5, R1 for a
        command that writes a file.  A shell write is never recorded as an edit, so R2's count is
        unaffected; only a declaration changes state."""
        if self.r1 == "declare":
            reason = parse_declaration(self.event.get("command"))
            if reason is not None:
                state["declared"] = True
                if not _write_json(state_path, state):
                    return self.result("skip", skip="state_write_failed")
                return self.result("state", "declare", note=log_reason(reason))
        target = self.shell_write_target()
        if self.env.get("SHOAL_GUARD_DIRECT") == "1" or state["direct"]:
            return self.result("allow", "direct", file=target)  # main's own declared work: not a STOP change
        if state["dispatched"]:
            self._shell_wrote(state_path, target)
            return self.result("allow", "dispatched", file=target)
        if self.r1 == "strict":
            return self._shell_r1(state, state_path, target, _exit_text(self.env, self.host, "STRICT"))
        if self.r1 == "declare":
            if self._declared(state, guard):
                return self.result("allow", "declared", file=target)  # not a STOP change (write roles only)
            return self._shell_r1(state, state_path, target, _exit_text(self.env, self.host, "DECLARE"))
        if self._classified(state, guard) is None:
            self._shell_wrote(state_path, target)
            return self.result("allow", "uncounted", file=target)
        return self._shell_r1(state, state_path, target, _text(self.env, "R1"))

    def _shell_r1(self, state: Dict[str, Any], state_path: Path, target: Optional[str], reason: str) -> Dict[str, Any]:
        """R1 on a shell write: enforce denies (nothing was written); shadow lets it through and logs it."""
        if self.mode == "enforce":
            return self.result("deny", "R1", reason=reason, file=target)
        self._shell_wrote(state_path, target)
        return self.result("would_deny", "R1", reason=reason, file=target)

    def _shell_wrote(self, state_path: Path, target: Optional[str]) -> None:
        """B2: an allowed shell write counts as a change once the chain has allowed it too (commit_change)."""
        if target is not None:
            self.pending_change = state_path

    def commit_change(self) -> None:
        """B2: count the allowed write as a change.  evaluate() calls it only when the final decision, chain
        included, lets the write through (issue #6).  Best effort: a failed write only loses the record."""
        path, self.pending_change = self.pending_change, None
        if path is None:
            return
        with _state_lock(path.with_suffix(".lock")) as lock_skip:
            if lock_skip is None:
                state = _read_json(path)
                _mark_changed(state)
                _write_json(path, state)

    def _turn_role(self, state: Dict[str, Any], guard: Path) -> Optional[str]:
        """The role in this turn's classification file, or None (no, stale or unreadable file)."""
        tid = state["turn_id"]  # effective turn (agy tool events may omit it)
        if tid is None:
            return None
        turn = _read_json(guard / "turns" / (str(self.event.get("session_id")) + ".json"))
        role = turn.get("role") if turn.get("turn_id", turn.get("prompt_id")) == tid else None
        return role if isinstance(role, str) else None

    def _classified(self, state: Dict[str, Any], guard: Path) -> Optional[str]:
        """The turn's `judgment` / `mechanical` classification, or None (no or stale classifier file)."""
        role = self._turn_role(state, guard)
        return role if role in CLASSIFIED_ROLE else None

    def _declared(self, state: Dict[str, Any], guard: Path) -> bool:
        """`declare` mode: main declared direct work this turn, or the optional classification file
        says `parent_local` (M5).  Any other role, or no file, changes nothing."""
        return state["declared"] or self._turn_role(state, guard) == "parent_local"

    def edit(self, state: Dict[str, Any], state_path: Path, guard: Path) -> Dict[str, Any]:
        raw_paths = [
            p for p in (self.event.get("paths") or []) if isinstance(p, str) and p
        ]
        if not raw_paths:
            return self.result("skip", skip="no_path")
        cwd = self.event.get("cwd") or os.getcwd()
        resolved = [resolve_path(p, cwd) for p in raw_paths]
        edited: List[str] = list(state["edited"])
        direct = self.env.get("SHOAL_GUARD_DIRECT") == "1" or state["direct"]
        limit = _max_files(self.env)
        declare = self.r1 == "declare"
        strict = self.r1 == "strict"
        classified: Optional[str] = None
        declared = False
        if not direct and not state["dispatched"]:
            if declare:
                declared = self._declared(state, guard)
            elif self.r1 == "classified":
                classified = self._classified(state, guard)

        first_rule = "exempt"
        advise_rule: Optional[str] = None
        deny_r1 = False
        for index, path in enumerate(resolved):
            if is_exempt(path, self.host, self.env, self.home):
                continue
            if direct:
                rule = "direct"
            elif state["dispatched"]:
                rule = "dispatched"
            else:
                rule = "declared" if declared else "count"
                if classified or strict or (declare and not declared):
                    fired: Optional[str] = "R1"
                elif path not in edited and (limit is None or len(edited) >= limit):
                    if limit is None:
                        return self.result("skip", skip="invalid_config")
                    fired = "R2"
                else:
                    fired = None
                if fired == "R1" and (declare or strict or self.host in DENY_MAIN_HOSTS):
                    deny_r1 = True  # G1: R1 denies on claude; everywhere else it only reminds
                elif fired and advise_rule is None:
                    advise_rule = fired  # R2 (and R1 off claude) only remind; the edit goes ahead
            if first_rule == "exempt":
                first_rule = rule
            if path not in edited:
                edited.append(path)
        if first_rule == "exempt":
            return self.result("allow", first_rule, file=raw_paths[0])
        if deny_r1 and self.mode == "enforce":
            return self.result(
                "deny", "R1",
                reason=(_exit_text(self.env, self.host, "STRICT" if strict else "DECLARE") if strict or declare
                        else _text(self.env, "R1")),
                file=raw_paths[0],
            )
        state["edited"] = edited
        if not (direct or declared):  # B2: main's own direct/declared edits are not a change; STOP is for write roles
            self.pending_change = state_path
        notify = (
            advise_rule is not None
            and not state["advised"]
            and self.mode == "enforce"
            and self.host in ADVISE_OUTPUT_HOSTS
        )
        if notify:
            state["advised"] = True  # the one reminder of this turn is spent
        _write_json(state_path, state)
        if deny_r1:  # shadow: the edit goes ahead, the log says what enforce would have done
            return self.result("would_deny", "R1", file=raw_paths[0])
        if advise_rule is None:
            return self.result("allow", first_rule, file=raw_paths[0])
        reason = None
        if notify:
            reason = _text(
                self.env,
                "ADVISE",
                n=len(edited),
                tool=DISPATCH_NAME.get(self.host, "the dispatch tool"),
            )
        return self.result(
            "advise", advise_rule, reason=reason, file=raw_paths[0], notify=notify
        )


def _decide(guard: "_Guard", event: Dict[str, Any]) -> Dict[str, Any]:
    """shoal's own decision on a normalized event."""
    if guard.chain_only or event.get("kind") in CHAIN_ONLY_KINDS:
        return {
            "decision": "none",
            "rule": None,
            "skip_reason": None,
            "reason": None,
            "mode": guard.mode,
        }
    if guard.mode == "off":
        return {
            "decision": "none",
            "rule": None,
            "skip_reason": None,
            "reason": None,
            "mode": "off",
        }
    if (
        event.get("kind") == "tool"
        and event.get("tool_kind") == "dispatch"
        and not event.get("is_subagent")
        and lanes_enabled(guard.env)
    ):
        lane = guard.lane_rule()
        if lane is not None:
            return lane
    if guard.host in CONVERSATION_HOSTS:
        routed = guard.agy_route()
        if routed is not None:
            return routed
        event = guard.event
    elif guard.host in MAPPED_HOSTS and event.get("kind") == "tool":
        guard.resolve_mapped_agent()
        event = guard.event
    if event.get("is_subagent"):
        if guard.host in ROLE_AWARE_HOSTS and event.get("kind") == "tool":
            return guard.subagent()
        if event.get("kind") == "post_shell" and role_access(event.get("role")) == "write":
            return guard.post_shell()  # B2: a write-level role's own check, after its edit, counts like main's
        return {
            "decision": "none",
            "rule": None,
            "skip_reason": None,
            "reason": None,
            "mode": guard.mode,
        }
    return guard.main()


def evaluate(event: Dict[str, Any], env: Dict[str, str], home: Path) -> Dict[str, Any]:
    """Decide on a normalized event: shoal's own decision, then the guard chain.  Raises only on
    programming/OS errors (caller fails open); a chain failure never changes shoal's decision."""
    guard = _Guard(event, env, home)
    result = guard.relay() or _decide(guard, guard.event)
    try:
        result = _apply_chain(guard, event, result)
    except BaseException:
        pass  # fail open: shoal's own decision stands
    if result["decision"] not in ("deny", "block"):
        guard.commit_change()  # a chain deny means the write never happened, so the turn stays unchanged
    return result


# ---------------------------------------------------------------------------
# Guard chain: external members attached by configuration only
# ---------------------------------------------------------------------------
# Config: the `chain` array of the installed module manifest, `${XDG_DATA_HOME:-~/.local/share}/shoal/modules.json`
# (SHOAL_GUARD_CHAIN_FILE overrides the path).  Entry: {"name": str, "command": [argv...], "hosts": [host...],
# "order": number, "events": [event...]} (docs/specs/modular-install SPEC, issue miyago9267/shoal#3).
#
# Member interface:
# - Events: a member gets an event only when its `events` lists it (default ["PreToolUse"]; known names are
#   CHAIN_EVENTS).  The guard forwards PreToolUse, PostToolUse, UserPromptSubmit, SessionEnd and Stop where the host
#   hook reaches it; an event no shoal rule and no member needs exits before any state write or member spawn.
# - Exec: argv without a shell, the raw hook payload on stdin, cwd unchanged, env inherited plus SHOAL_GUARD_HOST
#   (the host name) and SHOAL_GUARD_EVENT (the canonical event name).
# - Output: one JSON object.  `decision` allow|deny (no output allows); `reason` on deny; optional `context`
#   (advisory, never blocks); `member` and `version` are only logged (decision chain_report); other fields are ignored.
# - Verdict: after shoal's own decision, members run in ascending `order` (stable).  The first deny wins and later
#   members are not run; shoal's own deny/block skips the chain.  Only a PreToolUse deny blocks (deny output) and a
#   Stop deny blocks the stop (as before); a deny on any other event is logged only.  Non-zero exit, timeout,
#   unparseable or unknown output is fail-open (allow) with a chain_error / chain_timeout log line.
# - Context: the members' contexts are joined with a newline.  Claude turns them into
#   hookSpecificOutput.additionalContext on PreToolUse, PostToolUse and UserPromptSubmit; every other host and event
#   only logs (chain_context).
# - Time: each member gets min(5 s, SHOAL_GUARD_CHAIN_TIMEOUT_MS, remaining budget); the whole chain gets the host
#   hook timeout minus a margin (CHAIN_BUDGET_MS), counted from the start of the evaluation.  A member that finds the
#   budget used up is skipped with a chain_budget log line (fail-open).
# - Chain-only: when the manifest has a record for the host without `dispatch-guard` and the host has chain
#   members, the dispatch rules are off but the chain still runs.

CHAIN_TIMEOUT_MS = 5000
# The hosts' hook timeout is 10 s (tools/render.py CLAUDE_PLUGIN_TIMEOUT, tools/install_hooks.py TIMEOUT and the
# Codex groups' `timeout` in install/hook_registration.py); the chain must end before the host kills the hook.
HOST_HOOK_TIMEOUT_MS = 10000
CHAIN_BUDGET_MARGIN_MS = 2000
CHAIN_BUDGET_MS = HOST_HOOK_TIMEOUT_MS - CHAIN_BUDGET_MARGIN_MS
CHAIN_MAX_TIMEOUT_MS = CHAIN_BUDGET_MS
CHAIN_MIN_SLICE_MS = 100  # less budget than this left: the member is skipped
CHAIN_MAX_OUTPUT = 65536
CHAIN_MAX_CONTEXT = 8192
CHAIN_EVENTS = ("PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionEnd", "Stop")
CHAIN_DEFAULT_EVENTS = ("PreToolUse",)
CHAIN_CONTEXT_EVENTS = ("PreToolUse", "PostToolUse", "UserPromptSubmit")  # Claude's additionalContext events
CHAIN_ONLY_KINDS = ("post_tool", "session_end")  # events only the chain looks at
KIND_EVENT = {
    "tool": "PreToolUse",
    "post_shell": "PostToolUse",
    "post_tool": "PostToolUse",
    "prompt": "UserPromptSubmit",
    "session_end": "SessionEnd",
    "stop": "Stop",
}


def chain_manifest_path(env: Dict[str, str], home: Path) -> Path:
    override = env.get("SHOAL_GUARD_CHAIN_FILE", "")
    if override and os.path.isabs(override):
        return Path(override)
    return _abs_env_dir(env, "XDG_DATA_HOME", home / ".local" / "share") / "shoal" / "modules.json"


def dispatch_guard_selected(host: str, env: Dict[str, str], home: Path) -> bool:
    """False only when the module manifest has a record for `host` whose modules lack `dispatch-guard`.

    No manifest, an unreadable one, or no record for this host: True (the guard stays on, as before the manifest)."""
    fd = _open_readable(chain_manifest_path(env, home))
    if fd is None:
        return True
    try:
        with os.fdopen(fd, "rb") as handle:
            doc = json.loads(handle.read(MAX_SETTINGS_BYTES + 1)[:MAX_SETTINGS_BYTES])
    except (OSError, ValueError):
        return True
    entry = doc.get(host) if isinstance(doc, dict) else None
    modules = entry.get("modules") if isinstance(entry, dict) else None
    return not (isinstance(modules, list) and "dispatch-guard" not in modules)


def _env_ms(env: Dict[str, str], key: str, default: int, cap: int) -> int:
    try:
        value = int(env.get(key, ""))
    except ValueError:
        return default
    return value if 0 < value <= cap else default


def chain_timeout_ms(env: Dict[str, str]) -> int:
    return _env_ms(env, "SHOAL_GUARD_CHAIN_TIMEOUT_MS", CHAIN_TIMEOUT_MS, CHAIN_MAX_TIMEOUT_MS)


def chain_budget_ms(env: Dict[str, str]) -> int:
    """The whole chain's time; SHOAL_GUARD_CHAIN_BUDGET_MS can only shorten it."""
    return _env_ms(env, "SHOAL_GUARD_CHAIN_BUDGET_MS", CHAIN_BUDGET_MS, CHAIN_BUDGET_MS)


def chain_members(host: str, env: Dict[str, str], home: Path) -> Optional[List[Dict[str, Any]]]:
    """Members for `host` in run order; [] when none; None when the manifest exists but cannot be read."""
    fd = _open_readable(chain_manifest_path(env, home))
    if fd is None:
        return []
    try:
        with os.fdopen(fd, "rb") as handle:
            doc = json.loads(handle.read(MAX_SETTINGS_BYTES + 1)[:MAX_SETTINGS_BYTES])
    except (OSError, ValueError):
        return None
    entries = doc.get("chain") if isinstance(doc, dict) else None
    members: List[Dict[str, Any]] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        name, command, hosts, order = entry.get("name"), entry.get("command"), entry.get("hosts"), entry.get("order", 0)
        events = entry.get("events", list(CHAIN_DEFAULT_EVENTS))
        if not (isinstance(name, str) and name and isinstance(command, list) and command
                and all(isinstance(a, str) and a for a in command)
                and isinstance(hosts, list) and host in hosts
                and isinstance(order, (int, float)) and not isinstance(order, bool)
                and isinstance(events, list) and all(isinstance(e, str) for e in events)):
            continue
        members.append({"name": name, "command": command, "order": order,
                        "events": [e for e in events if e in CHAIN_EVENTS]})
    members.sort(key=lambda m: m["order"])
    return members


def chain_event_name(event: Dict[str, Any]) -> Optional[str]:
    """The canonical hook event a normalized event came from (None: not one a member can subscribe to)."""
    name = event.get("hook_event")
    if not isinstance(name, str):
        name = KIND_EVENT.get(str(event.get("kind")))
    return name if name in CHAIN_EVENTS else None


def _chain_call(command: List[str], raw: bytes, env: Dict[str, str], timeout_ms: int) -> Dict[str, Any]:
    """{"outcome": allow|deny|chain_error|chain_timeout, "reason", "context", "report"} for one member call."""
    import subprocess  # lazy: only a chain member call needs these (hook start-up cost, lean-default D5)
    import threading

    out: Dict[str, Any] = {"outcome": "chain_error", "reason": "", "context": None, "report": None}
    deadline = time.monotonic() + timeout_ms / 1000.0
    try:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    except (OSError, ValueError):
        return out
    chunks: List[bytes] = []
    state = {"size": 0, "overflow": False}

    def feed() -> None:
        try:
            proc.stdin.write(raw)  # type: ignore[union-attr]
            proc.stdin.close()  # type: ignore[union-attr]
        except (OSError, ValueError):
            pass  # a member that never reads stdin

    def drain() -> None:
        try:
            while True:
                chunk = proc.stdout.read1(65536)  # type: ignore[union-attr]
                if not chunk:
                    return
                state["size"] += len(chunk)
                if state["size"] > CHAIN_MAX_OUTPUT:
                    state["overflow"] = True
                    proc.kill()
                    return
                chunks.append(chunk)
        except (OSError, ValueError):
            return

    writer = threading.Thread(target=feed, daemon=True)
    reader = threading.Thread(target=drain, daemon=True)
    writer.start()
    reader.start()
    reader.join(max(0.0, deadline - time.monotonic()))
    if reader.is_alive():
        proc.kill()
        proc.wait()
        out["outcome"] = "chain_timeout"
        return out
    try:
        returncode = proc.wait(timeout=max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        out["outcome"] = "chain_timeout"
        return out
    finally:
        try:
            proc.stdout.close()  # type: ignore[union-attr]
        except OSError:
            pass
    if state["overflow"] or returncode != 0:
        return out
    text = b"".join(chunks).decode("utf-8", "replace").strip()
    if not text:
        out["outcome"] = "allow"
        return out
    try:
        obj = json.loads(text)
    except ValueError:
        return out
    decision = obj.get("decision") if isinstance(obj, dict) else None
    if decision == "allow":
        out["outcome"] = "allow"
    elif decision == "deny":
        reason = obj.get("reason")
        out["outcome"] = "deny"
        out["reason"] = reason.strip() if isinstance(reason, str) and reason.strip() else "denied"
    else:
        return out
    context = obj.get("context")
    if isinstance(context, str) and context.strip():
        out["context"] = context.strip()[:CHAIN_MAX_CONTEXT]
    parts = []
    for key, value in (("id", obj.get("member")), ("version", obj.get("version"))):
        if isinstance(value, (int, float)):  # bool is an int; a JSON number or boolean is reported as its text
            value = json.dumps(value)
        if isinstance(value, str) and value:
            parts.append("%s=%s" % (key, value[:60]))
    out["report"] = " ".join(parts) or None
    return out


def _apply_chain(guard: "_Guard", event: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    if result.get("mode") == "off" or result["decision"] in ("deny", "block"):
        return result
    members = chain_members(guard.host, guard.env, guard.home)
    if members is None:
        guard.log("chain_error", rule="chain", member="manifest")
        return result
    name = chain_event_name(event)
    members = [m for m in members if name in m["events"]]
    if not members:
        return result
    raw = event.get("_raw_bytes")
    if not isinstance(raw, bytes):
        text = event.get("raw_payload")
        raw = text.encode("utf-8") if isinstance(text, str) else json.dumps(
            {k: v for k, v in event.items() if not k.startswith("_")}).encode("utf-8")
    member_env = dict(guard.env, SHOAL_GUARD_HOST=guard.host, SHOAL_GUARD_EVENT=str(name))
    timeout_ms = chain_timeout_ms(guard.env)
    deadline = guard.started + chain_budget_ms(guard.env) / 1000.0
    enforce = guard.mode == "enforce"
    contexts: List[str] = []
    for member in members:
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms < CHAIN_MIN_SLICE_MS:
            guard.log("chain_budget", rule="chain", member=member["name"], ms="0")
            continue
        started = time.monotonic()
        called = _chain_call(member["command"], raw, member_env, min(timeout_ms, remaining_ms))
        outcome = called["outcome"]
        ms = int((time.monotonic() - started) * 1000)
        guard.log(outcome if outcome.startswith("chain_") else "chain_" + outcome, rule="chain", member=member["name"], ms=str(ms))
        if called["report"]:
            guard.log("chain_report", rule="chain", member=member["name"], reason=called["report"])
        if called["context"]:
            guard.log("chain_context", rule="chain", member=member["name"])
            contexts.append(called["context"])
        if outcome != "deny":
            continue
        kind = event.get("kind")
        if name not in ("PreToolUse", "Stop") or kind not in ("tool", "stop"):
            break  # first deny wins: later members do not run; elsewhere the deny is logged only
        base = "deny" if kind == "tool" else "block"
        return {
            "decision": base if enforce else "would_" + base,
            "rule": "chain",
            "skip_reason": None,
            "reason": "%s: %s" % (member["name"], called["reason"]),
            "mode": guard.mode,
            "context": None,
        }
    if contexts:
        result = dict(result, context="\n".join(contexts))
    return result


# ---------------------------------------------------------------------------
# Adapters: raw hook payload -> normalized event (None = no-op)
# ---------------------------------------------------------------------------

PATCH_HEADER_RE = re.compile(
    r"^\*\*\* (?:Add File|Update File|Delete File|Move to):[ \t]*(.+?)[ \t]*$", re.M
)


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _event(
    host: str,
    kind: str,
    sid: Any,
    tid: Any,
    cwd: Any,
    subagent: bool,
    role: Any,
    tool: Any = None,
    tool_kind: Optional[str] = None,
    paths: Optional[List[str]] = None,
    dispatched_role: Any = None,
    direct: bool = False,
    command: Any = None,
    stop_hook_active: Any = None,
    agent_id: Any = None,
    workspace: Any = None,
    dispatched_roles: Optional[List[str]] = None,
    fully_idle: Any = None,
    fast: Optional[str] = None,
    dispatch_desc: Any = None,
    dispatch_descs: Optional[List[Optional[str]]] = None,
) -> Dict[str, Any]:
    return {
        "host": host,
        "kind": kind,
        "session_id": _str(sid),
        "turn_id": _str(tid),
        "cwd": _str(cwd),
        "is_subagent": subagent,
        "role": _str(role),
        "agent_id": _str(agent_id),  # codex only: the subagent's id (its own turn_id differs from main's)
        "tool_name": _str(tool),
        "tool_kind": tool_kind,
        "paths": paths or [],
        "dispatched_role": _str(dispatched_role),
        "direct": direct,
        "fast": fast,  # prompt events: "on" (`#fast`), "off" (`#strict`) or None (no switch typed)
        "command": command if isinstance(command, str) else None,
        "stop_hook_active": stop_hook_active,  # `stop` events only: the host's raw value, judged by the guard
        "workspace": _str(workspace),  # agy only: the conversation's workspace paths, joined
        "dispatched_roles": dispatched_roles,  # agy only: every listed subagent's role name ("" when unnamed)
        "fully_idle": fully_idle,  # agy `stop` only: the host's raw value
        "dispatch_desc": _str(dispatch_desc),  # dispatch events: the short description the lane label is read from
        "dispatch_descs": dispatch_descs,  # agy only: each Subagents[] entry's Role field, parallel to dispatched_roles
    }


def patch_paths(command: Any) -> List[str]:
    if isinstance(command, list):
        command = "\n".join(str(part) for part in command)
    if not isinstance(command, str):
        return []
    return PATCH_HEADER_RE.findall(command)


def _codex_lane_text(tin: Dict[str, Any]) -> Optional[str]:
    """Codex spawn_agent's input has no description (tests/fixtures/codex_subagent_tool_shapes.json: agent_type, message,
    task_name): the lane label is read from the start of `task_name`, else of `message`."""
    texts = [t for t in (tin.get("task_name"), tin.get("message")) if isinstance(t, str)]
    return next((t for t in texts if lane_label(t)), texts[0] if texts else None)


class AdapterSpec(NamedTuple):
    """How one host's hook payload maps onto an event (claude, codex, grok; agy has no event name, see adapt_agy).
    Classification by content stays a predicate (docs/specs/code-restructure F3); only names are table data."""

    host: str
    keys: Tuple[str, str, str, str, str, str, str]  # event, session, turn, agent type, tool, tool input, stop flag
    events: Dict[str, str]  # host event name -> prompt | subagent_start | stop | post | pre
    is_sub: Callable[[Dict[str, Any]], bool]
    agent_key: Optional[str]  # copied to every event's agent_id (claude, codex)
    start_agent_key: str  # names the NEW subagent on subagent_start
    start_turn: bool  # subagent_start keeps the payload's turn id (claude prompt_id; codex/grok: the subagent's own)
    stop_ok: Callable[[Dict[str, Any], bool], bool]
    post_shell: Callable[[Any, Dict[str, Any]], bool]
    background: Callable[[Any, Dict[str, Any]], bool]  # checked first: one G4 deny, not two
    shell: Callable[[Any, Dict[str, Any]], bool]
    edit_tools: "frozenset[str]"
    path_keys: Tuple[str, ...]  # first non-empty string wins; () reads apply_patch headers
    dispatch_tools: "frozenset[str]"
    role_tools: "frozenset[str]"  # dispatch tools that carry a role and lane text (F2: claude Workflow carries none)
    role_key: str
    lane: Callable[[Dict[str, Any]], Any]
    foreign_key: Optional[str] = None  # a payload with this key belongs to another host's entry


def _never(*_: Any) -> bool:
    return False


def _str_command(tin: Dict[str, Any]) -> bool:
    return isinstance(tin.get("command"), str)


# claude: SubagentStart's agent_id/agent_type name the NEW subagent under main's session (tests/fixtures/
# claude_subagent_start_shape.json); PostToolUseFailure is a Bash call that ran too (only tool_name, tool_input,
# agent_id, session_id, prompt_id are relied on); a subagent's call carries agent_id (claude_subagent_tool_shapes.json).
# A payload with `hookEventName` is grok running Claude-compat hooks: grok's own entry handles it.
CLAUDE = AdapterSpec(
    host="claude",
    keys=("hook_event_name", "session_id", "prompt_id", "agent_type", "tool_name", "tool_input", "stop_hook_active"),
    events={"SubagentStart": "subagent_start", "Stop": "stop", "UserPromptSubmit": "prompt",
            "PostToolUse": "post", "PostToolUseFailure": "post", "PreToolUse": "pre"},
    is_sub=lambda p: bool(p.get("agent_id")),
    agent_key="agent_id",
    start_agent_key="agent_id",
    start_turn=True,
    stop_ok=lambda p, sub: True,
    post_shell=lambda tool, tin: tool == "Bash" and tin.get("run_in_background") is not True,
    background=lambda tool, tin: tool == "Bash" and tin.get("run_in_background") is True,
    shell=lambda tool, tin: tool == "Bash",
    edit_tools=frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"}),
    path_keys=("file_path", "notebook_path"),
    dispatch_tools=frozenset({"Agent", "Workflow"}),
    role_tools=frozenset({"Agent"}),
    role_key="subagent_type",
    lane=lambda tin: tin.get("description"),
    foreign_key="hookEventName",
)
# codex (tests/fixtures/codex_subagent_tool_shapes.json): SubagentStart's turn_id is the subagent's own, not main's;
# PostToolUse does not fire for a call that failed to start; the shell tool's input is exactly {"command": str}.
CODEX = AdapterSpec(
    host="codex",
    keys=("hook_event_name", "session_id", "turn_id", "agent_type", "tool_name", "tool_input", "stop_hook_active"),
    events={"SubagentStart": "subagent_start", "Stop": "stop", "UserPromptSubmit": "prompt",
            "PostToolUse": "post", "PreToolUse": "pre"},
    is_sub=lambda p: bool(p.get("agent_id")),
    agent_key="agent_id",
    start_agent_key="agent_id",
    start_turn=False,
    stop_ok=lambda p, sub: True,
    post_shell=lambda tool, tin: tool == "Bash" and _str_command(tin),
    background=_never,
    shell=lambda tool, tin: tool == "Bash" and _str_command(tin),
    edit_tools=frozenset({"apply_patch"}),
    path_keys=(),
    dispatch_tools=frozenset({"collaborationspawn_agent", "spawn_agent"}),
    role_tools=frozenset({"collaborationspawn_agent", "spawn_agent"}),
    role_key="agent_type",
    lane=_codex_lane_text,
)
# grok (tests/fixtures/grok_guard_event_shapes.json): subagent_start is sent under MAIN's sessionId and names the new
# subagent, whose own events carry sessionId == subagentId.  Two stops fire per run; only `reason == end_turn` ends a
# turn, and a subagent's own stop is not main's.
GROK = AdapterSpec(
    host="grok",
    keys=("hookEventName", "sessionId", "promptId", "subagentType", "toolName", "toolInput", "stopHookActive"),
    events={"user_prompt_submit": "prompt", "subagent_start": "subagent_start", "stop": "stop", "pre_tool_use": "pre"},
    is_sub=lambda p: _str(p.get("subagentType")) is not None,
    agent_key=None,
    start_agent_key="subagentId",
    start_turn=False,
    stop_ok=lambda p, sub: p.get("reason") == "end_turn" and not sub,
    post_shell=_never,
    background=_never,
    shell=lambda tool, tin: tool == "run_terminal_command" and _str_command(tin),
    edit_tools=frozenset({"search_replace", "write", "write_file", "edit", "multi_edit", "create_file"}),
    path_keys=("file_path", "path", "target_file", "filePath"),
    dispatch_tools=frozenset({"spawn_subagent"}),
    role_tools=frozenset({"spawn_subagent"}),
    role_key="subagent_type",
    lane=lambda tin: tin.get("description"),
)


def adapt(spec: AdapterSpec, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize one claude / codex / grok hook payload into an event, or None when the guard has no use for it.
    The prompt text is read for the `#direct` / `#fast` tokens only; it is never stored or logged."""
    if spec.foreign_key is not None and spec.foreign_key in payload:
        return None
    ev_key, sid_key, tid_key, type_key, tool_key, tin_key, stop_key = spec.keys
    name = payload.get(ev_key)
    kind = spec.events.get(name) if isinstance(name, str) else None
    host, cwd, role = spec.host, payload.get("cwd"), payload.get(type_key)
    if kind == "subagent_start":
        return _event(host, "subagent_start", payload.get(sid_key), payload.get(tid_key) if spec.start_turn else None,
                      cwd, False, role, agent_id=payload.get(spec.start_agent_key))
    agent_id = payload.get(spec.agent_key) if spec.agent_key else None
    sub = spec.is_sub(payload)
    base = (payload.get(sid_key), payload.get(tid_key), cwd, sub, role)
    if kind == "stop":
        if not spec.stop_ok(payload, sub):
            return None
        return _event(host, "stop", *base, stop_hook_active=payload.get(stop_key), agent_id=agent_id)
    if kind == "prompt":
        prompt = payload.get("prompt")
        return _event(host, "prompt", *base, direct=has_direct_token(prompt), fast=fast_switch(prompt),
                      agent_id=agent_id)
    if kind not in ("post", "pre"):
        return None
    tool, tin = payload.get(tool_key), _dict(payload.get(tin_key))
    if kind == "post":
        if not spec.post_shell(tool, tin):
            return None
        return _event(host, "post_shell", *base, tool=tool, tool_kind="shell", command=tin.get("command"),
                      agent_id=agent_id)
    extra: Dict[str, Any] = {"tool": tool, "agent_id": agent_id}
    named = tool if isinstance(tool, str) else None  # a list or dict tool name is unhashable: never a set member
    if spec.background(tool, tin):
        return _event(host, "tool", *base, tool_kind="background_shell", **extra)
    if spec.shell(tool, tin):
        return _event(host, "tool", *base, tool_kind="shell", command=tin.get("command"), **extra)
    if named in spec.edit_tools:
        if spec.path_keys:
            path = next((p for p in (_str(tin.get(k)) for k in spec.path_keys) if p), None)
            paths = [path] if path else []
        else:
            paths = patch_paths(tin.get("command"))
        return _event(host, "tool", *base, tool_kind="edit", paths=paths, **extra)
    if named in spec.dispatch_tools:
        carries = named in spec.role_tools
        return _event(host, "tool", *base, tool_kind="dispatch", **extra,
                      dispatched_role=tin.get(spec.role_key) if carries else None,
                      dispatch_desc=spec.lane(tin) if carries else None)
    return _event(host, "tool", *base, tool_kind="other", **extra)


def adapt_claude(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return adapt(CLAUDE, payload)


def adapt_codex(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return adapt(CODEX, payload)


def adapt_grok(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return adapt(GROK, payload)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _agy_dispatched_role(args: Dict[str, Any]) -> Optional[str]:
    """TypeName (fallback Role) of each listed subagent.  Unlocking needs every one to be a
    write-level role, so a single non-write entry is reported instead."""
    listed = args.get("Subagents")
    if not isinstance(listed, list) or not listed:
        return None
    roles = []
    for item in listed:
        item = _dict(item)
        roles.append(_str(item.get("TypeName")) or _str(item.get("Role")) or "")
    for role in roles:
        if role_access(role) != "write":
            return role or None
    return roles[0]


def _agy_lane_descs(args: Dict[str, Any]) -> List[Optional[str]]:
    """Each Subagents[] entry's `Role` field (the free-text role description), where the lane label is read."""
    listed = args.get("Subagents")
    return [_str(_dict(i).get("Role")) for i in listed] if isinstance(listed, list) else []


def _agy_workspace(payload: Dict[str, Any]) -> Optional[str]:
    paths = payload.get("workspacePaths")
    items = [p for p in paths if isinstance(p, str) and p] if isinstance(paths, list) else []
    return "\n".join(items) or None


def _agy_dispatched_roles(args: Dict[str, Any]) -> List[str]:
    listed = args.get("Subagents")
    if not isinstance(listed, list):
        return []
    return [_str(_dict(i).get("TypeName")) or _str(_dict(i).get("Role")) or "" for i in listed]


def adapt_agy(payload: Dict[str, Any], event_name: Any = None) -> Optional[Dict[str, Any]]:
    """The payload names no event (tests/fixtures/agy_guard_event_shapes.json): `event_name` is what the registration
    passed (`--event` / SHOAL_GUARD_EVENT).  Without it (a registration from before 3.5) the shape decides, as before:
    a toolCall is a tool event, an invocationNum a turn boundary, everything else is ignored."""
    cid = payload.get("conversationId")
    call = payload.get("toolCall")
    workspace = _agy_workspace(payload)
    cwd = _str(payload.get("cwd")) or (workspace or "").split("\n")[0] or None
    if isinstance(event_name, str) and event_name and event_name not in AGY_EVENTS:
        return None  # a registration for an event the guard does not use
    name = event_name or None
    if name == "SessionStart":
        return _event("agy", "session_start", cid, None, cwd, False, None, workspace=workspace)
    if name == "Stop":
        # No turn id, no re-entry flag: the state's turn is used, and a block cannot loop (stop_blocked).
        return _event("agy", "stop", cid, None, cwd, False, None, stop_hook_active=False,
                      fully_idle=payload.get("fullyIdle"))
    if name == "PreInvocation" or (name is None and not isinstance(call, dict)):
        # PreInvocation fires on every model call; only invocationNum 0 starts a turn.
        if payload.get("invocationNum") != 0 or not _is_int(payload.get("invocationNum")):
            return None
        steps = payload.get("initialNumSteps")
        turn = "%s:%d" % (cid, steps) if isinstance(cid, str) and _is_int(steps) else None
        return _event("agy", "turn_boundary", cid, turn, cwd, False, None)
    if not isinstance(call, dict):
        return None
    tool, args = call.get("name"), _dict(call.get("args"))
    base = (cid, None, cwd, False, None)  # tool payloads carry no turn id
    if isinstance(tool, str) and (tool == "write_to_file" or "replace_file_content" in tool):
        path = _str(args.get("TargetFile"))
        return _event("agy", "tool", *base, tool=tool, tool_kind="edit", paths=[path] if path else [],
                      workspace=workspace)
    if tool == "invoke_subagent":
        return _event("agy", "tool", *base, tool=tool, tool_kind="dispatch",
                      dispatched_role=_agy_dispatched_role(args), workspace=workspace,
                      dispatched_roles=_agy_dispatched_roles(args), dispatch_descs=_agy_lane_descs(args))
    if tool == "run_command" and isinstance(args.get("CommandLine"), str):
        return _event("agy", "tool", cid, None, _str(args.get("Cwd")) or cwd, False, None, tool=tool,
                      tool_kind="shell", command=args["CommandLine"], workspace=workspace)
    return _event("agy", "tool", *base, tool=tool, tool_kind="other", workspace=workspace)


ADAPTERS = {
    "claude": adapt_claude,
    "codex": adapt_codex,
    "grok": adapt_grok,
    "agy": adapt_agy,
}


def advise_output(reason: str) -> str:
    """Non-blocking PreToolUse context (claude, codex): no permissionDecision, the tool still runs."""
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": reason}}
    )


def block_output(reason: str) -> str:
    """A `Stop` block: the documented `{"decision": "block", "reason": ...}` on stdout, exit 0 (claude and
    codex alike).  The model receives `reason` and continues.  If a host ignored this shape the turn would just
    end: the check can only fail open."""
    return json.dumps({"decision": "block", "reason": reason})


def context_output(event_name: str, context: str) -> str:
    """Advisory chain context for Claude: hookSpecificOutput.additionalContext (non-blocking)."""
    return json.dumps({"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": context}})


def chain_only_event(host: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """An event no shoal rule reads but a chain member may subscribe to: Claude/Codex PostToolUse of a tool the
    adapters ignore (edit tools, apply_patch) and SessionEnd.  Carries no state; None for anything else."""
    if host not in ("claude", "codex") or "hookEventName" in payload:
        return None
    name = payload.get("hook_event_name")
    kind = {"PostToolUse": "post_tool", "SessionEnd": "session_end"}.get(name) if isinstance(name, str) else None
    if kind is None:
        return None
    event = _event(host, kind, payload.get("session_id"), payload.get("turn_id") or payload.get("prompt_id"),
                   payload.get("cwd"), bool(payload.get("agent_id")), payload.get("agent_type"),
                   tool=payload.get("tool_name") if kind == "post_tool" else None)
    event["agent_id"] = _str(payload.get("agent_id"))
    return event


def deny_output(host: str, reason: str) -> str:
    if host in ("claude", "codex"):
        return json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    return json.dumps({"decision": "deny", "reason": reason})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _skip_log(host: str, env: Dict[str, str], home: Path, reason: str) -> None:
    if resolve_mode(host, env, home) == "off":
        return
    _append_log(
        _guard_dir(env, home),
        {
            "host": host,
            "decision": "skip",
            "skip_reason": reason,
            "mode": resolve_mode(host, env, home),
        },
    )


MAX_SETTINGS_BYTES = 1024 * 1024


def _abs_env_dir(env: Dict[str, str], key: str, default: Path) -> Path:
    value = env.get(key, "")
    return Path(value) if value and os.path.isabs(value) else default


PORTABLE_DATA_DIR = "${XDG_DATA_HOME:-$HOME/.local/share}"  # what install_hooks.py writes into settings


def _expand_home(token: str, home: Path, data_dir: Optional[Path] = None) -> str:
    """The `~`, `$HOME` and portable XDG spellings a hook command may use for the script path."""
    if data_dir is not None and token.startswith(PORTABLE_DATA_DIR + "/"):
        token = str(data_dir) + token[len(PORTABLE_DATA_DIR):]
    if token == "~" or token.startswith("~/"):
        token = str(home) + token[1:]
    return token.replace("${HOME}", str(home)).replace("$HOME", str(home))


def _matcher_covers(matcher: Any, tool: Optional[str]) -> bool:
    if matcher is None or matcher in ("", "*"):
        return True
    if not isinstance(matcher, str) or tool is None:
        return False
    try:
        return re.fullmatch(matcher, tool) is not None
    except re.error:
        return False


# install_hooks.portable_command_for: f="<path>"; [ -f "$f" ] || exit 0; exec python3 "$f" --host <host>
_GUARDED_COMMAND = re.compile(
    r'f="([^"]+)";\s*\[ -f "\$f" \]\s*\|\|\s*exit 0;\s*exec python3 "\$f"\s+--host\s+(\S+)\s*'
)


def _runs_global_guard(command: Any, script: str, host: str, home: Path, data_dir: Optional[Path] = None) -> bool:
    """`command` invokes the install_hooks.py script (same resolved path) with `--host <host>`.

    The script token may be absolute (older installs), the portable `${XDG_DATA_HOME:-$HOME/.local/share}`
    form, or that path inside the guarded `f=...; [ -f "$f" ] || exit 0; exec python3 "$f"` form.
    `data_dir` is what the XDG variable resolves to for this process.
    """
    if not isinstance(command, str):
        return False
    guarded = _GUARDED_COMMAND.fullmatch(command.strip())
    if guarded is not None:
        path, command_host = guarded.groups()
        return command_host == host and os.path.realpath(_expand_home(path, home, data_dir)) == script
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    for index, token in enumerate(tokens):
        if os.path.basename(token) != "shoal_guard.py":
            continue
        if tokens[index + 1:index + 3] != ["--host", host]:
            continue
        if os.path.realpath(_expand_home(token, home, data_dir)) == script:
            return True
    return False


def global_guard_covers(host: str, name: Any, tool: Any, env: Dict[str, str], home: Path) -> bool:
    """K4: the effective user settings file already runs the install_hooks.py guard for this event.

    Decided by where the entry lives (the user settings file, symlinks resolved) and which script
    it names: ${XDG_DATA_HOME:-~/.local/share}/shoal/guard/shoal_guard.py, which must exist.  The
    plugin's own command also matches install_hooks.OWNED, so a regex on the command is not enough.
    """
    if not isinstance(name, str):
        return False
    data_dir = _abs_env_dir(env, "XDG_DATA_HOME", home / ".local" / "share")
    script = data_dir / "shoal" / "guard" / "shoal_guard.py"
    script = Path(os.path.realpath(str(script)))
    if not script.is_file():
        return False
    settings = _abs_env_dir(env, "CLAUDE_CONFIG_DIR", home / ".claude") / "settings.json"
    fd = _open_readable(Path(os.path.realpath(str(settings))))
    if fd is None:
        return False
    try:
        data = json.loads(os.read(fd, MAX_SETTINGS_BYTES))
    except ValueError:
        return False
    finally:
        os.close(fd)
    hooks = _dict(data).get("hooks")
    groups = _dict(hooks).get(name)
    if not isinstance(groups, list):
        return False
    for group in groups:
        group = _dict(group)
        if name in ("PreToolUse", "PostToolUse", "PostToolUseFailure") and not _matcher_covers(group.get("matcher"), tool if isinstance(tool, str) else None):
            continue
        handlers = group.get("hooks")
        for handler in handlers if isinstance(handlers, list) else []:
            if _runs_global_guard(_dict(handler).get("command"), str(script), host, home, data_dir):
                return True
    return False


def _open_readable(path: Path) -> Optional[int]:
    """fd of `path` when it is a regular file owned by the current user, else None.

    O_NONBLOCK keeps a FIFO from blocking the open; it is then refused as not regular (#26)."""
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (hasattr(os, "getuid") and info.st_uid != os.getuid()):
            os.close(fd)
            return None
    except OSError:
        os.close(fd)
        return None
    return fd


def defer_to_global(host: str, raw: bytes, env: Dict[str, str]) -> bool:
    """True when the plugin copy must stay silent.  Any doubt returns False: never zero evaluations."""
    if os.name == "nt" or host != "claude" or not raw or len(raw) > MAX_INPUT_BYTES:
        return False
    try:
        payload = json.loads(raw)
        home = Path(env.get("HOME") or os.path.expanduser("~"))
        return global_guard_covers(host, _dict(payload).get("hook_event_name"), _dict(payload).get("tool_name"), env, home)
    except BaseException:
        return False


def run(host: str, raw: bytes, env: Dict[str, str]) -> Optional[str]:
    """Process one stdin payload; returns the stdout text, if any."""
    if os.name == "nt":  # POSIX-only semantics (O_NOFOLLOW, uid ownership); fail-open no-op
        return None
    home = Path(env.get("HOME") or os.path.expanduser("~"))
    try:
        if not raw:
            return None
        if len(raw) > MAX_INPUT_BYTES:
            _skip_log(host, env, home, "oversize_payload")
            return None
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            _skip_log(host, env, home, "bad_payload")
            return None
        event = (adapt_agy(payload, env.get("SHOAL_GUARD_EVENT")) if host == "agy" else ADAPTERS[host](payload))
        if event is None:
            event = chain_only_event(host, payload)
        if event is None:
            return None
        if host in ("claude", "codex") and isinstance(payload.get("hook_event_name"), str):
            event["hook_event"] = payload["hook_event_name"]  # the chain's canonical event name
        event["_raw_bytes"] = raw  # the guard chain receives the payload exactly as it arrived
        result = evaluate(event, env, home)
        if result["decision"] == "deny":
            return deny_output(host, result["reason"])
        if result["decision"] == "block":
            return block_output(result["reason"])
        advice = result["reason"] if result["decision"] == "advise" and result.get("notify") else None
        context, name = result.get("context"), chain_event_name(event)
        if context and host == "claude" and name in CHAIN_CONTEXT_EVENTS:
            return context_output(name, "\n".join(part for part in (advice, context) if part))
        if advice is not None:
            return advise_output(advice)
    except BaseException:
        try:
            _skip_log(host, env, home, "exception")
        except BaseException:
            pass
    return None


def main(argv: Optional[List[str]] = None) -> int:
    try:
        args = list(sys.argv[1:] if argv is None else argv)
        host = args[args.index("--host") + 1] if "--host" in args else ""
        if not host:
            # Hosts that exec the hook path directly (grok) cannot pass argv.
            host = os.environ.get("SHOAL_GUARD_HOST", "")
        if host not in ADAPTERS:
            return 0
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        env = dict(os.environ)
        if "--event" in args and args.index("--event") + 1 < len(args):
            env["SHOAL_GUARD_EVENT"] = args[args.index("--event") + 1]  # agy: the payload names no event
        if "--plugin" in args and defer_to_global(host, raw, env):
            return 0
        out = run(host, raw, env)
        if out:
            sys.stdout.write(out)
            sys.stdout.flush()
    except BaseException:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
