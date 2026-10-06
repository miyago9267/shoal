#!/usr/bin/env python3
"""Shoal dispatch guard: host-neutral PreToolUse guard for Pilotfish dispatch rules.

One script serves claude, codex, grok and agy.  Each host gets a small adapter that
normalizes the hook payload into an event; the core decides on the event only, so a
TypeScript port can replay tests/fixtures/guard_vectors.json against the same logic.

    python3 hooks/shoal_guard.py --host {claude,codex,grok,agy} [--plugin]   (JSON on stdin)

--plugin is set only by the Claude plugin's hooks.json.  When the user settings already
register the tools/install_hooks.py guard (and its script exists) the plugin copy does
nothing, so each event is judged once; in every other case it runs normally.

SHOAL_GUARD_HOST supplies the host when --host is absent (grok runs the hook path
directly and sets it through the hook's env map).

Always exits 0 and fails open: any exception means "no opinion".  The guard is a
policy nudge, not a security boundary (see docs/specs/dispatch-enforcement/SPEC.md).

Modes (SHOAL_GUARD, alias PILOTFISH_GUARD): enforce | shadow | off.  Only the hard rules (LEAF,
VERIFY_EDIT) deny; the main-session rules R1/R2 decide `advise` and, on claude/codex in enforce,
print a one-per-turn `additionalContext` reminder.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

try:
    import fcntl
except ImportError:  # Windows: run() is a no-op there
    fcntl = None  # type: ignore[assignment]

MAX_INPUT_BYTES = 256 * 1024
MAX_LOG_BYTES = 1024 * 1024
MAX_STATE_BYTES = 64 * 1024
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
LOCK_WAIT_SECONDS = 2.0

# Default mode per host.  E6: claude/codex enforce; grok/agy stay shadow (evidence pending / forced).
HOST_DEFAULT_MODE = {
    "claude": "enforce",
    "codex": "enforce",
    "grok": "shadow",
    "agy": "shadow",
}
# Hosts that cannot tell main from subagent: enforce is never allowed (spec R5).
FORCED_SHADOW_HOSTS = frozenset({"agy"})
# Hosts whose payload identifies the calling role: LEAF / VERIFY_EDIT apply (spec R6).
ROLE_AWARE_HOSTS = frozenset({"claude", "codex", "grok"})
# agy turn ids are composed `conversation:invocation`; its tool payload may not carry one.
COMPOSED_TURN_HOSTS = frozenset({"agy"})
# Hosts whose tool payload may lack a turn id (grok: only user_prompt_submit has promptId; claude
# after `/login` resumes without prompt_id); use the state turn.
STATE_TURN_HOSTS = frozenset({"agy", "grok", "claude"})
# Hosts whose PreToolUse accepts a non-blocking `additionalContext`: only they print the advise
# reminder.  grok, agy (and opencode in the TS port) have no verified equivalent: log only.
ADVISE_OUTPUT_HOSTS = frozenset({"claude", "codex"})
# Hosts whose prompt event may lack a turn id: it clears `dispatched` and keeps turn and edits (M1).
PROMPT_KEEP_HOSTS = frozenset({"claude"})
# Role-name namespaces accepted as the same role (K3).  Explicit allowlist only: any other
# `x:name` stays unknown, so it neither unlocks nor counts as a leaf/verify role.
ROLE_NAMESPACES = ("shoal:",)

# role -> access level.  Must match core/roles.toml and every [extra_roles.*] in
# hosts/*/binding.toml; tests/test_shoal_guard.py asserts it.
ROLE_ACCESS = {
    "scout": "read-only",
    "plan-verifier": "read-only",
    "security-reviewer": "read-only",
    "Explore": "read-only",
    "mech-executor": "write",
    "executor": "write",
    "security-executor": "write",
    "sol-executor": "write",
    "verifier": "verify",
}

CLASSIFIED_ROLE = {"judgment": "executor", "mechanical": "mech-executor"}
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
)

MESSAGES = {
    "en": {
        "ADVISE": (
            "Shoal dispatch brake (a reminder, nothing was blocked): this turn has edited {n} "
            "files directly. If the work is stable same-shape repetition, or bounded judgment "
            "with a stable contract, consider handing it to `mech-executor` / `executor` with "
            "{tool}; otherwise continuing directly is fine."
        ),
        "LEAF": (
            "Shoal dispatch guard: subagents are leaf workers and must not dispatch other "
            "agents. Finish the task yourself and report back to the parent."
        ),
        "VERIFY_EDIT": (
            "Shoal dispatch guard: verify-level roles must not edit files with editing tools. "
            "Report findings to the parent instead."
        ),
    },
    "zh-TW": {
        "ADVISE": (
            "Shoal dispatch brake（提醒，沒有擋任何操作）：本輪 main session 已直接改了 {n} 個檔案。"
            "若這是穩定的同形重複，或契約穩定、範圍有界的判斷工作，可考慮用 {tool} 交給 "
            "`mech-executor` / `executor`；否則直接做下去也可以。"
        ),
        "LEAF": "Shoal dispatch guard：subagent 是 leaf worker，不可再派其他 agent。請自己完成並回報給上層。",
        "VERIFY_EDIT": "Shoal dispatch guard：verify 等級的 role 不可用編輯工具改檔，請把發現回報給上層。",
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


def _append_log(guard: Optional[Path], record: Dict[str, Any]) -> None:
    """Append one whitelisted record to guard.jsonl (1 MiB cap).  Never raises."""
    if guard is None:
        return
    line: Dict[str, Any] = {"ts": datetime.now(timezone.utc).isoformat()}
    for key in LOG_FIELDS[1:]:
        value = record.get(key)
        if key == "file" and isinstance(value, str):
            value = os.path.basename(value)
        value = _safe_text(value)
        if value is not None:
            line[key] = value
    path = guard / "guard.jsonl"
    try:
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            return
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


def resolve_mode(host: str, env: Dict[str, str]) -> str:
    """Unset -> host default; an unrecognized value -> shadow (as the legacy guard did)."""
    raw = env.get("SHOAL_GUARD") or env.get("PILOTFISH_GUARD") or ""
    if not raw:
        mode = HOST_DEFAULT_MODE.get(host, "shadow")
    else:
        mode = raw if raw in ("enforce", "shadow", "off") else "shadow"
    if mode == "enforce" and host in FORCED_SHADOW_HOSTS:
        mode = "shadow"
    return mode


def _max_files(env: Dict[str, str]) -> Optional[int]:
    """None when the configured value is not an integer (the guard then fails open)."""
    raw = (
        env.get("SHOAL_GUARD_MAX_FILES") or env.get("PILOTFISH_GUARD_MAX_FILES") or "2"
    )
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


def _text(env: Dict[str, str], key: str, **fmt: Any) -> str:
    lang = "zh-TW" if env.get("SHOAL_GUARD_LANG") == "zh-TW" else "en"
    return MESSAGES[lang][key].format(**fmt)


class _Guard:
    """One evaluation: holds env, home, host, mode and the lazily verified state dir."""

    def __init__(self, event: Dict[str, Any], env: Dict[str, str], home: Path) -> None:
        self.event = event
        self.env = env
        self.home = home
        self.host = str(event.get("host") or "")
        self.mode = resolve_mode(self.host, env)
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
        }
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
    ) -> Dict[str, Any]:
        if decision in ("skip", "deny", "would_deny", "advise", "allow", "state"):
            self.log(decision, rule=rule, skip_reason=skip, file=file)
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
        rule = None
        if tool_kind == "dispatch":
            rule = "LEAF"
        elif tool_kind == "edit" and role_access(role) == "verify":
            rule = "VERIFY_EDIT"
        if rule is None:
            return {
                "decision": "none",
                "rule": None,
                "skip_reason": None,
                "reason": None,
                "mode": self.mode,
            }
        paths = self.event.get("paths") or []
        decision = "deny" if self.mode == "enforce" else "would_deny"
        return self.result(
            decision,
            rule,
            reason=_text(self.env, rule),
            file=paths[0] if paths else None,
        )

    # -- main session -------------------------------------------------------
    def main(self) -> Dict[str, Any]:
        event = self.event
        kind = event.get("kind")
        sid, tid = event.get("session_id"), event.get("turn_id")
        is_boundary = kind in ("prompt", "turn_boundary")
        if kind == "tool" and event.get("tool_kind") not in ("edit", "dispatch"):
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
                edited = prior.get("edited") if isinstance(prior.get("edited"), list) else []
                prior_tid = prior.get("turn_id")
                state = {"turn_id": prior_tid if isinstance(prior_tid, str) else None,
                         "dispatched": False, "advised": False, "edited": edited}
            else:
                state = {"turn_id": tid, "dispatched": False, "advised": False, "edited": []}
            if not _write_json(state_path, state):
                return self.result("skip", skip="state_write_failed")
            return self.result("state")

        state = _read_json(state_path)
        if tid is not None and state.get("turn_id") != tid:
            state = {}
        edited = state.get("edited") if isinstance(state.get("edited"), list) else []
        state = {
            "turn_id": tid if tid is not None else state.get("turn_id"),
            "dispatched": state.get("dispatched") is True,
            "advised": state.get("advised") is True,
            "edited": edited,
        }

        if event.get("tool_kind") == "dispatch":
            if role_access(event.get("dispatched_role")) == "write":
                state["dispatched"] = True
                _write_json(state_path, state)
            return self.result("allow", "dispatch")
        return self.edit(state, state_path, guard)

    def edit(self, state: Dict[str, Any], state_path: Path, guard: Path) -> Dict[str, Any]:
        raw_paths = [
            p for p in (self.event.get("paths") or []) if isinstance(p, str) and p
        ]
        if not raw_paths:
            return self.result("skip", skip="no_path")
        cwd = self.event.get("cwd") or os.getcwd()
        resolved = [resolve_path(p, cwd) for p in raw_paths]
        edited: List[str] = list(state["edited"])
        direct = self.env.get("SHOAL_GUARD_DIRECT") == "1"
        limit = _max_files(self.env)
        classified: Optional[str] = None
        tid = state["turn_id"]  # effective turn (agy tool events may omit it)
        if not direct and not state["dispatched"] and tid is not None:
            turn = _read_json(
                guard / "turns" / (str(self.event.get("session_id")) + ".json")
            )
            match = turn.get("turn_id", turn.get("prompt_id")) == tid
            role = turn.get("role") if match else None
            classified = role if role in CLASSIFIED_ROLE else None

        first_rule = "exempt"
        advise_rule: Optional[str] = None
        for index, path in enumerate(resolved):
            if is_exempt(path, self.host, self.env, self.home):
                continue
            if direct:
                rule = "direct"
            elif state["dispatched"]:
                rule = "dispatched"
            else:
                rule = "count"
                if classified:
                    fired: Optional[str] = "R1"
                elif path not in edited and (limit is None or len(edited) >= limit):
                    if limit is None:
                        return self.result("skip", skip="invalid_config")
                    fired = "R2"
                else:
                    fired = None
                if fired and advise_rule is None:
                    advise_rule = fired  # R1 and R2 only remind; the edit goes ahead (spec amendment)
            if first_rule == "exempt":
                first_rule = rule
            if path not in edited:
                edited.append(path)
        if first_rule == "exempt":
            return self.result("allow", first_rule, file=raw_paths[0])
        state["edited"] = edited
        notify = (
            advise_rule is not None
            and not state["advised"]
            and self.mode == "enforce"
            and self.host in ADVISE_OUTPUT_HOSTS
        )
        if notify:
            state["advised"] = True  # the one reminder of this turn is spent
        _write_json(state_path, state)
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


def evaluate(event: Dict[str, Any], env: Dict[str, str], home: Path) -> Dict[str, Any]:
    """Decide on a normalized event.  Raises only on programming/OS errors (caller fails open)."""
    guard = _Guard(event, env, home)
    if guard.mode == "off":
        return {
            "decision": "none",
            "rule": None,
            "skip_reason": None,
            "reason": None,
            "mode": "off",
        }
    if event.get("is_subagent"):
        if guard.host in ROLE_AWARE_HOSTS and event.get("kind") == "tool":
            return guard.subagent()
        return {
            "decision": "none",
            "rule": None,
            "skip_reason": None,
            "reason": None,
            "mode": guard.mode,
        }
    return guard.main()


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
) -> Dict[str, Any]:
    return {
        "host": host,
        "kind": kind,
        "session_id": _str(sid),
        "turn_id": _str(tid),
        "cwd": _str(cwd),
        "is_subagent": subagent,
        "role": _str(role),
        "tool_name": _str(tool),
        "tool_kind": tool_kind,
        "paths": paths or [],
        "dispatched_role": _str(dispatched_role),
    }


def adapt_claude(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if (
        "hookEventName" in payload
    ):  # grok running Claude-compat hooks: grok's own entry handles it
        return None
    name = payload.get("hook_event_name")
    sub = bool(payload.get("agent_id"))
    base = (
        payload.get("session_id"),
        payload.get("prompt_id"),
        payload.get("cwd"),
        sub,
        payload.get("agent_type"),
    )
    if name == "UserPromptSubmit":
        return _event("claude", "prompt", *base)
    if name != "PreToolUse":
        return None
    tool, tin = payload.get("tool_name"), _dict(payload.get("tool_input"))
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = _str(tin.get("file_path")) or _str(tin.get("notebook_path"))
        return _event(
            "claude",
            "tool",
            *base,
            tool=tool,
            tool_kind="edit",
            paths=[path] if path else [],
        )
    if tool in ("Agent", "Workflow"):
        return _event(
            "claude",
            "tool",
            *base,
            tool=tool,
            tool_kind="dispatch",
            dispatched_role=tin.get("subagent_type") if tool == "Agent" else None,
        )
    return _event("claude", "tool", *base, tool=tool, tool_kind="other")


def patch_paths(command: Any) -> List[str]:
    if isinstance(command, list):
        command = "\n".join(str(part) for part in command)
    if not isinstance(command, str):
        return []
    return PATCH_HEADER_RE.findall(command)


def adapt_codex(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = payload.get("hook_event_name")
    sub = bool(payload.get("agent_id"))
    base = (
        payload.get("session_id"),
        payload.get("turn_id"),
        payload.get("cwd"),
        sub,
        payload.get("agent_type"),
    )
    if name == "UserPromptSubmit":
        return _event("codex", "prompt", *base)
    if name != "PreToolUse":
        return None
    tool, tin = payload.get("tool_name"), _dict(payload.get("tool_input"))
    if tool == "apply_patch":
        return _event(
            "codex",
            "tool",
            *base,
            tool=tool,
            tool_kind="edit",
            paths=patch_paths(tin.get("command")),
        )
    if tool in ("collaborationspawn_agent", "spawn_agent"):
        return _event(
            "codex",
            "tool",
            *base,
            tool=tool,
            tool_kind="dispatch",
            dispatched_role=tin.get("agent_type"),
        )
    return _event("codex", "tool", *base, tool=tool, tool_kind="other")


def adapt_grok(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = payload.get("hookEventName")
    sub_type = _str(payload.get("subagentType"))
    base = (
        payload.get("sessionId"),
        payload.get("promptId"),
        payload.get("cwd"),
        sub_type is not None,
        sub_type,
    )
    if name == "user_prompt_submit":
        return _event("grok", "prompt", *base)
    if name != "pre_tool_use":
        return None
    tool, tin = payload.get("toolName"), _dict(payload.get("toolInput"))
    if tool in ("search_replace", "write", "write_file", "edit", "multi_edit", "create_file"):
        path = None
        for key in ("file_path", "path", "target_file", "filePath"):
            path = _str(tin.get(key))
            if path:
                break
        return _event(
            "grok",
            "tool",
            *base,
            tool=tool,
            tool_kind="edit",
            paths=[path] if path else [],
        )
    if tool == "spawn_subagent":
        return _event(
            "grok",
            "tool",
            *base,
            tool=tool,
            tool_kind="dispatch",
            dispatched_role=tin.get("subagent_type"),
        )
    return _event("grok", "tool", *base, tool=tool, tool_kind="other")


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


def adapt_agy(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    cid = payload.get("conversationId")
    call = payload.get("toolCall")
    if not isinstance(call, dict):
        # PreInvocation fires on every model call; only invocationNum 0 starts a turn.
        if payload.get("invocationNum") != 0 or not _is_int(payload.get("invocationNum")):
            return None
        steps = payload.get("initialNumSteps")
        turn = "%s:%d" % (cid, steps) if isinstance(cid, str) and _is_int(steps) else None
        return _event("agy", "turn_boundary", cid, turn, payload.get("cwd"), False, None)
    tool, args = call.get("name"), _dict(call.get("args"))
    base = (cid, None, payload.get("cwd"), False, None)  # tool payloads carry no turn id
    if isinstance(tool, str) and (tool == "write_to_file" or "replace_file_content" in tool):
        path = _str(args.get("TargetFile"))
        return _event("agy", "tool", *base, tool=tool, tool_kind="edit", paths=[path] if path else [])
    if tool == "invoke_subagent":
        return _event("agy", "tool", *base, tool=tool, tool_kind="dispatch",
                      dispatched_role=_agy_dispatched_role(args))
    return _event("agy", "tool", *base, tool=tool, tool_kind="other")


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
    if resolve_mode(host, env) == "off":
        return
    _append_log(
        _guard_dir(env, home),
        {
            "host": host,
            "decision": "skip",
            "skip_reason": reason,
            "mode": resolve_mode(host, env),
        },
    )


MAX_SETTINGS_BYTES = 1024 * 1024


def _abs_env_dir(env: Dict[str, str], key: str, default: Path) -> Path:
    value = env.get(key, "")
    return Path(value) if value and os.path.isabs(value) else default


def _expand_home(token: str, home: Path) -> str:
    """The `~` and `$HOME` spellings a hand-written hook command may use for the script path."""
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


def _runs_global_guard(command: Any, script: str, host: str, home: Path) -> bool:
    """`command` invokes the install_hooks.py script (same resolved path) with `--host <host>`."""
    if not isinstance(command, str):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    for index, token in enumerate(tokens):
        if os.path.basename(token) != "shoal_guard.py":
            continue
        if tokens[index + 1:index + 3] != ["--host", host]:
            continue
        if os.path.realpath(_expand_home(token, home)) == script:
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
    script = _abs_env_dir(env, "XDG_DATA_HOME", home / ".local" / "share") / "shoal" / "guard" / "shoal_guard.py"
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
        if name == "PreToolUse" and not _matcher_covers(group.get("matcher"), tool if isinstance(tool, str) else None):
            continue
        handlers = group.get("hooks")
        for handler in handlers if isinstance(handlers, list) else []:
            if _runs_global_guard(_dict(handler).get("command"), str(script), host, home):
                return True
    return False


def _open_readable(path: Path) -> Optional[int]:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
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
        event = ADAPTERS[host](payload)
        if event is None:
            return None
        result = evaluate(event, env, home)
        if result["decision"] == "deny":
            return deny_output(host, result["reason"])
        if result["decision"] == "advise" and result.get("notify"):
            return advise_output(result["reason"])
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
