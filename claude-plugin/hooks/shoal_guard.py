#!/usr/bin/env python3
"""Shoal dispatch guard: host-neutral PreToolUse guard for shoal dispatch rules.

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

Modes (SHOAL_GUARD): enforce | shadow | off.  The hard rules (LEAF, VERIFY_EDIT) deny on every
host.  Main-session rules: R2 (file count) only advises, on claude/codex in enforce with a
one-per-turn `additionalContext` reminder.  G4 (claude only) denies main's background shell (`Bash`
with run_in_background); it is released for one turn by a standalone `#direct` token in the user's
prompt, or for good by SHOAL_GUARD_DIRECT=1.

The main-session edit rule (R1 for edit tools, G5 for a foreground `Bash` that literally writes a
file, see shell_write_targets) is chosen by SHOAL_GUARD_R1 (docs/specs/guard-declared-direct):
  strict      (default on claude and codex) deny unless this turn has a dispatched write role,
              `#direct` / SHOAL_GUARD_DIRECT=1, or the target is exempt.  A `: shoal-direct` command is an
              ordinary no-op here and a classification file has no effect (docs/specs/guard-declared-direct,
              M9).  The only exits are dispatch and the user's `#direct`.
  declare     (3.2.x default) deny unless this turn has a dispatched write role, `#direct` /
              SHOAL_GUARD_DIRECT=1, a declaration (a shell call that is exactly
              `: shoal-direct <reason>`, see parse_declaration) or a classification file whose role
              is `parent_local`.  No classification file, or any other role, has no effect.
  classified  the v3.1.0 rule: deny (claude) or advise (other hosts) only when the turn is
              classified judgment/mechanical by the optional classification file.  Default on every
              host that cannot gate (grok, agy, opencode).
  off         no R1/G5; the hard rules, G4 and R2 are untouched.

"A write-level role was dispatched" (the unlock in every mode) means, on claude, that the role has started
(M11): the dispatch call records a pending write dispatch and the SubagentStart event of the same session
releases it.  On every other host the dispatch call itself unlocks.  See START_UNLOCK_HOSTS.
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
from typing import Any, Dict, Iterator, List, Optional, Tuple

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
# Hosts where R1 denies (claude only, G1), where main's background shell is denied (G4) and where a
# shell command that writes a file is judged by R1 (G5).
DENY_MAIN_HOSTS = frozenset({"claude"})
# SHOAL_GUARD_R1 (main-session edit rule).  `declare` needs a way to declare, so it is selectable only on
# hosts whose adapter delivers main's shell calls to the guard: claude's `Bash` and, since 3.2.1, codex's
# `Bash` (recorded payload, docs/specs/guard-declared-direct/PROGRESS.md).  Any other value falls back to
# the host default; every other host keeps the v3.1.0 behaviour (`classified`).  `strict` (3.3.0) needs the
# same events (edit tools plus main's shell calls), so it is selectable on the same hosts and is their default.
DECLARE_HOSTS = frozenset({"claude", "codex"})
# Hosts where "a write-level role was dispatched" unlocks only once the role has actually started (M11):
# the PreToolUse of the dispatch call records a pending write dispatch and the SubagentStart event of the
# same session releases it.  Claude's SubagentStart payload (session_id equal to main's, agent_id, agent_type,
# prompt_id) is recorded in tests/fixtures/claude_subagent_start_shape.json.  Every other host unlocks at the
# dispatch call itself, as before: no start event is recorded for it, and without one a pending dispatch
# would never be released.  The registration (plugin hooks.json, install_hooks.py) and this script ship
# together; a Claude install whose registration lacks SubagentStart has no start event and would stay locked.
START_UNLOCK_HOSTS = frozenset({"claude"})
# `#direct` as an instruction the user typed: a standalone token that follows the start of the text or
# whitespace and is followed by the end, whitespace or sentence punctuation (ASCII or CJK).  Anything
# else (`x#direct`, `(#direct)`, `#directly`, a URL fragment) is not.  Code the user quoted does not
# count: fenced blocks and inline spans are masked with NUL (never whitespace) before matching.
DIRECT_TOKEN_RE = re.compile(r"(?<!\S)#direct(?![^\s.,;:!?\u3002\uff0c\u3001\uff1b\uff1a\uff01\uff1f])")
FENCE_OPEN_RE = re.compile(r" {0,3}`{3,}")
FENCE_CLOSE_RE = re.compile(r" {0,3}`{3,}\s*$")
INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)(?:(?!\n[ \t\r]*\n).)+?(?<!`)\1(?!`)", re.DOTALL)


def has_direct_token(prompt: Any) -> bool:
    """True when the user's prompt carries `#direct` as typed instruction, outside any code."""
    if not isinstance(prompt, str):
        return False
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
    text = INLINE_CODE_RE.sub("\0", "\n".join(lines))
    return DIRECT_TOKEN_RE.search(text) is not None
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

CLASSIFIED_ROLE = {"judgment": "executor", "mechanical": "applier"}
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
        "VERIFY_EDIT": "Shoal dispatch guard：verify 等級的 role 不可用編輯工具改檔，請把發現回報給上層。",
        "R1": (
            "Shoal dispatch guard：本輪已被分類為實作工作，且尚未派出 write role。"
            "請派給 executor 或 applier，或在 prompt 加上 #direct 以直接修改。"
        ),
        "G4": (
            "Shoal dispatch guard：main session 不自己開背景 shell。"
            "請改在背景派出 watcher，或在 prompt 加上 #direct。"
        ),
        "STRICT": (
            "Shoal dispatch guard：main session 不自己改檔。"
            "請派出可寫的 role（executor 或 applier），或請使用者在 prompt 加上 #direct。"
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
    raw = env.get("SHOAL_GUARD") or ""
    if not raw:
        mode = HOST_DEFAULT_MODE.get(host, "shadow")
    else:
        mode = raw if raw in ("enforce", "shadow", "off") else "shadow"
    if mode == "enforce" and host in FORCED_SHADOW_HOSTS:
        mode = "shadow"
    return mode


def resolve_r1(host: str, env: Dict[str, str]) -> str:
    """SHOAL_GUARD_R1: `classified` and `off` as given; `strict` and `declare` where the host can gate.

    Unset, unrecognized, or `strict` / `declare` on a host that cannot gate -> the host default
    (`strict` on claude and codex, `classified` elsewhere)."""
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
_DOUBLE_BRACKET_END_RE = re.compile(r"(?:^|\s)\]\](?=$|[\s;&|)])")
# Words after which the next word is still a command (`FOO=1 tee f`, `then tee f`).
_COMMAND_KEEP = frozenset(("then", "do", "else", "elif", "if", "while", "until", "!", "{"))
# Wrappers: the next word is the real command, after any options.  `-exec` / `-execdir` work
# anywhere on a `find` line, so they are matched at argument position too.
_COMMAND_WRAPPERS = frozenset(("sudo", "command", "exec", "env", "time", "nohup", "builtin", "xargs"))
_FIND_EXEC = frozenset(("-exec", "-execdir"))
# sed flags that take no value; the first other letter ends a short-option cluster.
_SED_FLAG_LETTERS = "Enrsuzb"


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


def shell_write_targets(command: str) -> List[str]:
    """File targets that `command` writes by a literal reading of its text (G5).

    Counts `>`, `>>`, `>|`, `&>` redirects to a word, `tee [-a] file...` and `sed -i` /
    `--in-place`, each at command position (after `;`, `|`, `&&`, newline, `(`, `then`, `do`, or
    wrappers such as `sudo`, `env`, `xargs`, `find -exec`).  Never counts: `>&2` / `2>&1`
    duplications, `<` input, here-document bodies, quoted text, `[[ ]]`, `(( ))`, `$(( ))`,
    comments and `>(...)`.  Targets are returned as written (quotes removed); a target holding
    `$` or a backtick has no known value and is the caller's call.  Writes through an
    interpreter or another command (python, node, cp, mv, patch, git apply, dd, ...) are not
    detected.  The TypeScript port (guard/shell-writes.ts) must return the same list.
    """
    if ">" not in command and "tee" not in command and "sed" not in command:
        return []
    targets: List[str] = []
    n = len(command)
    i = 0
    cmd_pos, wrapped = True, False
    name: Optional[str] = None
    args: List[str] = []
    heredocs: List[Tuple[str, bool]] = []

    def flush() -> None:
        nonlocal name, args, cmd_pos, wrapped
        if name == "tee":
            targets.extend(_tee_files(args))
        elif name == "sed":
            targets.extend(_sed_in_place_files(args))
        name, args, cmd_pos, wrapped = None, [], True, False

    while i < n:
        c = command[i]
        nxt = command[i + 1] if i + 1 < n else ""
        if c in " \t\r":
            i += 1
        elif c == "\n":
            flush()
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
            flush()
            i += 1
            if i < n and command[i] in ";|&":
                i += 1
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
                targets.append(word)
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
                i += 1
        elif c == ")":
            flush()
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
            elif _ASSIGNMENT_RE.match(word) or word in _COMMAND_KEEP:
                pass
            elif wrapped and word.startswith("-"):
                pass
            elif word in _COMMAND_WRAPPERS:
                wrapped = True
            else:
                name, args, cmd_pos, wrapped = word.rsplit("/", 1)[-1], [], False, False
    flush()
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
        self.r1 = resolve_r1(self.host, env)
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
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        if decision in ("skip", "deny", "would_deny", "advise", "allow", "state"):
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
        if kind == "subagent_start":
            return self.subagent_start()
        sid, tid = event.get("session_id"), event.get("turn_id")
        is_boundary = kind in ("prompt", "turn_boundary")
        tool_kind = event.get("tool_kind")
        if kind == "tool" and tool_kind == "background_shell" and self.host not in DENY_MAIN_HOSTS:
            tool_kind = None  # G4 exists on claude only
        if kind == "tool" and tool_kind == "shell":
            # A foreground shell call that is neither a declaration nor a file write has no opinion,
            # and touches no state or log.  `declare` reads declarations and judges writes (G5);
            # `strict` only judges writes (a declaration is an ordinary no-op there); `classified` judges
            # writes on claude only (v3.1.0); `off` has no G5.
            if self.r1 == "declare":
                if parse_declaration(event.get("command")) is None and self.shell_write_target() is None:
                    tool_kind = None
            elif self.r1 == "strict":
                if self.shell_write_target() is None:
                    tool_kind = None
            elif (
                self.r1 != "classified"
                or self.host not in DENY_MAIN_HOSTS
                or self.shell_write_target() is None
            ):
                tool_kind = None
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
                         "dispatched": False, "advised": False, "edited": edited,
                         "direct": event.get("direct") is True, "declared": False, "pending": 0}
            else:
                state = {"turn_id": tid, "dispatched": False, "advised": False, "edited": [],
                         "direct": event.get("direct") is True, "declared": False, "pending": 0}
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
            "direct": state.get("direct") is True,  # this turn's prompt carried #direct
            "declared": state.get("declared") is True,  # main declared direct work this turn (M3)
            "pending": _pending(state),  # write dispatches whose role has not started yet (M11)
        }

        if event.get("tool_kind") == "dispatch":
            if role_access(event.get("dispatched_role")) == "write":
                if self.host in START_UNLOCK_HOSTS:
                    state["pending"] += 1  # released by the role's SubagentStart; the call itself is allowed
                    _write_json(state_path, state)
                    return self.result("allow", "dispatch_pending")
                state["dispatched"] = True
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
        log line says so (skip_reason prompt_id_mismatch).  Bad ids fail open with a skip record."""
        event = self.event
        if self.host not in START_UNLOCK_HOSTS or role_access(event.get("role")) != "write":
            return {"decision": "none", "rule": None, "skip_reason": None, "reason": None, "mode": self.mode}
        sid, tid = event.get("session_id"), event.get("turn_id")
        if sid is None:
            return self.result("skip", skip="missing_id")
        if not valid_id(sid):
            return self.result("skip", skip="invalid_id")
        guard = self.guard_dir
        if guard is None:
            return self.result("skip", skip="state_unavailable")
        state_path = guard / "state" / (sid + ".json")
        with _state_lock(guard / "state" / (sid + ".lock")) as lock_skip:
            if lock_skip is not None:
                return self.result("skip", skip=lock_skip)
            state = _read_json(state_path)
            if _pending(state) < 1:
                return self.result("skip", skip="start_without_pending")
            mismatch = isinstance(tid, str) and state.get("turn_id") != tid
            state["pending"] = _pending(state) - 1
            state["dispatched"] = True
            if not _write_json(state_path, state):
                return self.result("skip", skip="state_write_failed")
            return self.result("state", "dispatch_started", skip="prompt_id_mismatch" if mismatch else None)

    def background_shell(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """G4: main starting a background shell.  Reads state only; nothing is recorded."""
        if self.env.get("SHOAL_GUARD_DIRECT") == "1" or state["direct"]:
            return self.result("allow", "direct")
        return self.result(
            "deny" if self.mode == "enforce" else "would_deny", "G4", reason=_text(self.env, "G4")
        )

    def shell_write_target(self) -> Optional[str]:
        """G5: the first non-exempt file that main's shell command writes (UNKNOWN_TARGET or the
        raw text when its value is not known), or None.  `/dev/...`, exempt paths and nothing
        else are skipped; the check reads no state."""
        command = self.event.get("command")
        if not isinstance(command, str) or not command:
            return None
        cwd = self.event.get("cwd") or os.getcwd()
        for raw in shell_write_targets(command):
            target = self._expand_target(raw)
            if target is None:
                return raw  # `$var`, `$(...)`, backticks: a redirect to a non-/dev target
            if target == "/dev" or target.startswith("/dev/"):
                continue
            if is_exempt(resolve_path(target, cwd), self.host, self.env, self.home):
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
            return self.result("allow", "direct", file=target)
        if state["dispatched"]:
            return self.result("allow", "dispatched", file=target)
        if self.r1 == "strict":
            return self.result(
                "deny" if self.mode == "enforce" else "would_deny", "R1",
                reason=_text(self.env, "STRICT"), file=target
            )
        if self.r1 == "declare":
            if self._declared(state, guard):
                return self.result("allow", "declared", file=target)
            return self.result(
                "deny" if self.mode == "enforce" else "would_deny", "R1",
                reason=_text(self.env, "DECLARE"), file=target
            )
        if self._classified(state, guard) is None:
            return self.result("allow", "uncounted", file=target)
        return self.result(
            "deny" if self.mode == "enforce" else "would_deny", "R1", reason=_text(self.env, "R1"), file=target
        )

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
                "deny", "R1", reason=_text(self.env, "STRICT" if strict else "DECLARE" if declare else "R1"),
                file=raw_paths[0],
            )
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
    direct: bool = False,
    command: Any = None,
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
        "direct": direct,
        "command": command if isinstance(command, str) else None,
    }


def adapt_claude(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if (
        "hookEventName" in payload
    ):  # grok running Claude-compat hooks: grok's own entry handles it
        return None
    name = payload.get("hook_event_name")
    if name == "SubagentStart":
        # Its agent_id/agent_type name the NEW subagent; the event belongs to the main session's session
        # (payload keys recorded in tests/fixtures/claude_subagent_start_shape.json), so it is not a subagent call.
        return _event("claude", "subagent_start", payload.get("session_id"), payload.get("prompt_id"),
                      payload.get("cwd"), False, payload.get("agent_type"))
    sub = bool(payload.get("agent_id"))
    base = (
        payload.get("session_id"),
        payload.get("prompt_id"),
        payload.get("cwd"),
        sub,
        payload.get("agent_type"),
    )
    if name == "UserPromptSubmit":
        prompt = payload.get("prompt")  # read for the #direct token only; never stored or logged
        has_direct = has_direct_token(prompt)
        return _event("claude", "prompt", *base, direct=has_direct)
    if name != "PreToolUse":
        return None
    tool, tin = payload.get("tool_name"), _dict(payload.get("tool_input"))
    if tool == "Bash" and tin.get("run_in_background") is True:  # G4 first: one deny, not two
        return _event("claude", "tool", *base, tool=tool, tool_kind="background_shell")
    if tool == "Bash":
        return _event("claude", "tool", *base, tool=tool, tool_kind="shell", command=tin.get("command"))
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
        # The payload's `prompt` field is what shoal_autoroute_gate.py reads on Codex too.
        return _event("codex", "prompt", *base, direct=has_direct_token(payload.get("prompt")))
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
    if tool == "Bash" and isinstance(tin.get("command"), str):
        # Codex's shell tool: tool_input is exactly {"command": str}; there is no run_in_background.
        return _event("codex", "tool", *base, tool=tool, tool_kind="shell", command=tin["command"])
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
        if name == "PreToolUse" and not _matcher_covers(group.get("matcher"), tool if isinstance(tool, str) else None):
            continue
        handlers = group.get("hooks")
        for handler in handlers if isinstance(handlers, list) else []:
            if _runs_global_guard(_dict(handler).get("command"), str(script), host, home, data_dir):
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
