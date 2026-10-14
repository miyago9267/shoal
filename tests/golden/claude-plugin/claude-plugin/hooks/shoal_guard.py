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
Fast mode (a standalone `#fast` in the prompt until `#strict`, or SHOAL_GUARD_FAST=1) counts every turn as `#direct`;
LEAF, VERIFY_EDIT and the completion check are unchanged.

The main-session edit rule (R1 for edit tools, G5 for a foreground `Bash` that literally writes a
file, see shell_write_targets) is chosen by SHOAL_GUARD_R1 (docs/specs/guard-declared-direct):
  strict      (default on claude, codex, grok and agy) deny unless this turn has a dispatched write role,
              `#direct` / SHOAL_GUARD_DIRECT=1, or the target is exempt.  A `: shoal-direct` command is an
              ordinary no-op here and a classification file has no effect (docs/specs/guard-declared-direct,
              M9).  The only exits are dispatch and the user's `#direct`.
  declare     (3.2.x default) deny unless this turn has a dispatched write role, `#direct` /
              SHOAL_GUARD_DIRECT=1, a declaration (a shell call that is exactly
              `: shoal-direct <reason>`, see parse_declaration) or a classification file whose role
              is `parent_local`.  No classification file, or any other role, has no effect.
  classified  the v3.1.0 rule: deny (claude) or advise (other hosts) only when the turn is
              classified judgment/mechanical by the optional classification file.  Selectable with
              SHOAL_GUARD_R1=classified; the default on no shipped host (an unknown host falls back to it).
  off         no R1/G5; the hard rules, G4 and R2 are untouched.

"A write-level role was dispatched" (the unlock in every mode) means, on claude, codex and grok, that the role has
started (M11, E3, E4): the dispatch call records a pending write dispatch and the start event releases it
(claude and codex: SubagentStart of the same session, codex once per agent_id and its subagent's first edit or shell
call also counts, see START_UNLOCK_HOSTS; grok: its `subagent_start`; agy: the SessionStart of the new subagent
conversation).  Every host this script serves is in START_UNLOCK_HOSTS, so none unlocks at the dispatch call itself.

Subagent write rule E1 (docs/specs/guard-every-gate), switch SHOAL_GUARD_SUBAGENT_WRITE: `off` leaves the subagent rules exactly as they were; `on` (the default on claude, codex, grok and agy) makes a subagent that is not a shoal write-capable role (an edit
tool or a literal shell write, as in G5, outside the exempt paths) get E1: deny in enforce, `would_deny` in shadow.
Exits: dispatch a shoal write role, put the agent type in SHOAL_GUARD_WRITE_AGENTS (comma-separated, exact match on the
raw type or the type without a `shoal:` prefix), or SHOAL_GUARD_DIRECT=1.  On claude a user's `#direct`
also releases it: the subagent event carries the main session's session_id and the prompt_id of the turn that started
it, and the prompt event keeps the last DIRECT_TURNS_MAX turn ids that carried `#direct` in the state file
(`direct_turns`), so a background Workflow child that edits after the main session moved on is still judged by the turn
that launched it.  Codex: a subagent has its own turn id, so the SubagentStart event of an agent records its agent_id when main's
current turn carried `#direct` (`direct_agents`, the last AGENTS_MAX) and that agent is released.  Other hosts have no
such payload evidence: not released (agy has no prompt text at all).  Grok: a subagent's events carry its own session id, so `subagent_start` (sent
under main's session id, with the subagent's id and type) records subagent id -> {main session, role, whether main's
turn carried `#direct`} in `state/grok.agents.json` (the last GROK_AGENTS_MAX); a tool event whose session id is in that
file is a subagent call of that role, and the recorded flag releases it.  A subagent event with a `subagentType` and no
record is still judged by its role, never released by `#direct`.  Verify-level roles keep VERIFY_EDIT.

Completion check (docs/specs/shared-rules B2-B4).  Per turn the guard records `changed` (a main-session edit or
shell write was allowed and is not exempt, or a write-level role counts as dispatched by the rule above) and
`checked` (after the latest change, a verify-level role was dispatched or started, or main ran a foreground shell
call that is neither a file write nor a declaration; on claude and codex that call counts at its PostToolUse, i.e. when
it really ran, and its PreToolUse counts only until the session has seen its first PostToolUse, see POST_HOSTS).  On claude and codex the `Stop` event is blocked once per
turn when `changed` is set, `checked` is not, `stop_hook_active` is exactly false, the mode is enforce and
SHOAL_GUARD_STOP is not `off`; everything else (other turn, bad payload, unreadable state, shadow, off) fails
open.  Grok's `stop` event (only `reason == end_turn`) is attached, but its `{"decision": "block"}` output has not been
exercised on the real host: it logs `would_block` and blocks only with SHOAL_GUARD_STOP=enforce (in enforce mode).
Other hosts never block: their adapters receive no end-of-turn event that carries a verified payload.
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

# Default mode per host.  E6: claude/codex/grok enforce (grok: tests/fixtures/grok_guard_event_shapes.json shows deny is
# honoured for main and subagent writes); agy enforces too (tests/fixtures/agy_guard_event_shapes.json: deny is honoured
# for main and subagent writes, and a subagent runs in its own conversation, which the guard records, see CONVERSATION_HOSTS).
HOST_DEFAULT_MODE = {
    "claude": "enforce",
    "codex": "enforce",
    "grok": "enforce",
    "agy": "enforce",
}
# Hosts whose payload identifies the calling role: LEAF / VERIFY_EDIT apply (spec R6).
ROLE_AWARE_HOSTS = frozenset({"claude", "codex", "grok"})
# Hosts whose `Stop` payload is recorded (tests/fixtures/stop_payload_shapes.json) and whose hook accepts
# `{"decision": "block", "reason": ...}`: only they block an unverified completion (B4).  grok and agy record a
# `would_block` only (STOP_SHADOW_DEFAULT_HOSTS); opencode has no recorded end-of-turn payload for the main session, so
# it never blocks.  SHOAL_GUARD_STOP switches the check off on these hosts and has no effect elsewhere.  Grok has the payload (tests/fixtures/grok_guard_event_shapes.json)
# but its block output is not yet exercised: its default is shadow (`would_block` only) until SHOAL_GUARD_STOP=enforce.
STOP_HOSTS = frozenset({"claude", "codex", "grok", "agy"})
# Hosts whose registration carries PostToolUse for the shell tool (claude plugin / settings.json, codex shoal-guard-v5).
# There `checked` is set by a shell call that really ran (docs/specs/guard-every-gate E8); PreToolUse only counts as the
# fallback until the first PostToolUse of the session arrives (state `post_seen`), because the guard cannot read whether
# the user has approved the new hook (Codex) or restarted onto the new registration (Claude).
POST_HOSTS = frozenset({"claude", "codex"})
STOP_SHADOW_DEFAULT_HOSTS = frozenset({"grok", "agy"})
# agy (tests/fixtures/agy_guard_event_shapes.json): the payload names no role and no parent, but a subagent runs in its OWN
# conversation (new conversationId, announced by a `SessionStart`).  The guard infers main vs subagent from the order of
# events and keeps it in `state/agy.conversations.json`; see _Guard.agy_route.  Nothing here is exact: two sessions
# dispatching at the same moment in one workspace can be confused, and a mixed dispatch leaves the class unknown.
CONVERSATION_HOSTS = frozenset({"agy"})
AGY_RECORD_FILE = "agy.conversations"  # state/<this>.json; not a valid id (dot), so it never collides with a session
AGY_RECORD_MAX = 64
AGY_PENDING_TTL = 600.0  # seconds a dispatch waits for its subagent's SessionStart
AGY_EVENTS = frozenset({"SessionStart", "PreInvocation", "PreToolUse", "Stop"})
# Hosts whose prompt event carries the user's text, so that `#direct` exists.  agy's PreInvocation carries none.
PROMPT_DIRECT_HOSTS = frozenset({"claude", "codex", "grok", "opencode"})
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
# hosts whose adapter delivers main's shell calls to the guard: claude's `Bash`, since 3.2.1 codex's
# `Bash` (recorded payload, docs/specs/guard-declared-direct/PROGRESS.md) and the OpenCode adapter's `bash`
# (run by the TypeScript port; listed here so both implementations replay the same vectors).  Any other value falls back to
# the host default; every other host keeps the v3.1.0 behaviour (`classified`).  `strict` (3.3.0) needs the
# same events (edit tools plus main's shell calls), so it is selectable on the same hosts and is their default.
DECLARE_HOSTS = frozenset({"claude", "codex", "opencode", "grok", "agy"})
# Hosts where "a write-level role was dispatched" unlocks only once the role has actually started (M11):
# the PreToolUse of the dispatch call records a pending write dispatch and the SubagentStart event of the
# same session releases it.  Claude's SubagentStart payload (session_id equal to main's, agent_id, agent_type,
# prompt_id) is recorded in tests/fixtures/claude_subagent_start_shape.json.  Grok's `subagent_start` and agy's
# SessionStart of a new conversation are the start events there.  A host outside this set would unlock at the dispatch
# call itself (none ships); without a start event a pending dispatch would never be released.  The registration (plugin hooks.json, install_hooks.py) and this script ship
# together; a Claude install whose registration lacks SubagentStart has no start event and would stay locked.
START_UNLOCK_HOSTS = frozenset({"claude", "codex", "grok", "agy"})
# Codex (docs/specs/guard-every-gate E3; tests/fixtures/codex_subagent_tool_shapes.json): SubagentStart carries the new
# agent's agent_id and agent_type with the main session's session_id, and fires only when the role really started (a
# spawn of an unknown agent_type fires none).  The registration is a separate hook group that the user approves in
# `/hooks`; until then no start event arrives.  So the first tool call of a write-level role that carries an agent_id is
# start evidence as well (it needs only the PreToolUse registration that already exists): each agent_id releases at
# most one pending dispatch, whichever of the two arrives first (`started_agents`).
# E1 (docs/specs/guard-every-gate): hosts where SHOAL_GUARD_SUBAGENT_WRITE defaults to `on`, and hosts whose
# subagent PreToolUse carries the main session's session_id and the prompt_id of the turn that started it
# (claude: tests/fixtures/claude_subagent_tool_shapes.json), so the user's `#direct` can release a subagent.
SUBAGENT_WRITE_DEFAULT_ON_HOSTS = frozenset({"claude", "codex", "grok", "agy"})
SUBAGENT_DIRECT_HOSTS = frozenset({"claude", "codex", "grok"})
# Grok (tests/fixtures/grok_guard_event_shapes.json): a subagent's tool events carry its OWN session id (= the subagentId
# of the `subagent_start` event, which is sent under main's session id).  `subagent_start` records the mapping.
MAPPED_HOSTS = frozenset({"grok"})
GROK_AGENTS_MAX = 64
GROK_AGENTS_FILE = "grok.agents"  # state/<this>.json; not a valid id (no dots), so it never collides with a session
# Codex: a subagent runs in its own turn (turn_id differs from main's, constant for that agent), so `#direct` cannot be
# looked up by turn.  SubagentStart records the agent_id as released when main's current turn carried `#direct`
# (`direct_agents`); the subagent's later events are judged by their agent_id.
AGENT_KEYED_HOSTS = frozenset({"codex"})
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
    "agent_type",  # the subagent's type as the host sent it (raw); absent for main-session events
    "agent_id",
    "session",  # first 8 hex of sha256 of the session id / turn id: attributes lines, never reveals the id
    "turn",
    "fast",
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
            "prompt (or #fast for the whole session) to edit directly."
        ),
        "G4": (
            "Shoal dispatch guard: the main session does not start background shells. Dispatch "
            "watcher in the background instead, or add #direct to your prompt."
        ),
        "STRICT": (
            "Shoal dispatch guard: the main session does not edit files itself. Dispatch a "
            "write-capable role (executor or applier), or ask the user to add #direct (or #fast for the whole session) to the prompt."
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
        "E1": (
            "Shoal dispatch guard: a subagent that is not a shoal write-capable role does not edit files. "
            "Dispatch a shoal write-capable role (executor or applier), add this agent type to "
            "SHOAL_GUARD_WRITE_AGENTS, or set SHOAL_GUARD_DIRECT=1."
        ),
        "E1D": (
            "Shoal dispatch guard: a subagent that is not a shoal write-capable role does not edit files. "
            "Dispatch a shoal write-capable role (executor or applier), add #direct to the user prompt that "
            "started this work (or #fast for the whole session), add this agent type to SHOAL_GUARD_WRITE_AGENTS, or set SHOAL_GUARD_DIRECT=1."
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
            "#direct (or #fast for the whole session) to the prompt."
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
            "請派給 executor 或 applier，或在 prompt 加上 #direct（單輪）或 #fast（整個 session）以直接修改。"
        ),
        "G4": (
            "Shoal dispatch guard：main session 不自己開背景 shell。"
            "請改在背景派出 watcher，或在 prompt 加上 #direct。"
        ),
        "STRICT": (
            "Shoal dispatch guard：main session 不自己改檔。"
            "請派出可寫的 role（executor 或 applier），或請使用者在 prompt 加上 #direct 或 #fast。"
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
            "請派出 shoal 可寫的 role（executor 或 applier）、請使用者在啟動這項工作的 prompt 加上 #direct 或 #fast、"
            "把這個 agent type 加進 SHOAL_GUARD_WRITE_AGENTS，或設定 SHOAL_GUARD_DIRECT=1。"
        ),
        "STOP": (
            "Shoal completion check：本回合改過檔案，之後沒有跑過任何檢查。"
            "請現在做一次驗證（測試、verifier 或 watcher role），或在回報中明確寫出這次修改尚未驗證。"
        ),
        "DECLARE": (
            "Shoal dispatch guard：main session 預設把改檔交給別的 role。"
            "請派出可寫的 role（executor 或 applier），或先宣告直接做：把 "
            ': shoal-direct "<理由>" 當成單獨一次 shell 指令執行，或請使用者在 prompt 加上 #direct 或 #fast。'
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
    """Append one whitelisted record to guard.jsonl (1 MiB cap).  Never raises."""
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
    """
    if ">" not in command and "tee" not in command and "sed" not in command and "perl" not in command:
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
        elif name == "perl":
            targets.extend(_perl_in_place_files(args))
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


def _mark_changed(state: Dict[str, Any]) -> None:
    """B2: a change after a check puts the turn back to "unchecked"."""
    state["changed"] = True
    state["checked"] = False


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
        # Fast mode (SHOAL_GUARD_FAST=1) is `#direct` for every turn: reuse the SHOAL_GUARD_DIRECT release paths.
        self.fast = env.get("SHOAL_GUARD_FAST") == "1"
        self.env = dict(env, SHOAL_GUARD_DIRECT="1") if self.fast else env
        self.home = home
        self.host = str(event.get("host") or "")
        self.mode = resolve_mode(self.host, env)
        self.r1 = resolve_r1(self.host, env)
        self.fast_state = False  # the session's fast flag as persisted by this prompt event
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
            file = self.shell_write_target()
        if rule == "E1_UNKNOWN":  # the role cannot be established: never denied, only logged
            return self.result("skip", "E1", skip="would_deny_unknown_class", file=file)
        key = "E1D" if rule == "E1" and self.host in SUBAGENT_DIRECT_HOSTS else rule
        return self.result(decision, rule, reason=_text(self.env, key), file=file)

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
            writes = self.shell_write_target() is not None
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
            return tid in _direct_turns(state) or state.get("fast") is True
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

    def note_check(self, ran: bool = False, counts: bool = True) -> None:
        """B2: main ran a plain foreground shell call.  When the turn is changed and unchecked, mark it checked.

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
            self.note_check(ran=True, counts=plain)
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
        whether this turn counts as `#direct` (its own token, or fast mode on)."""
        switch = self.event.get("fast")
        self.fast_state = switch == "on" or (prior.get("fast") is True and switch != "off")
        if self.fast_state:
            self.fast = True
        return self.event.get("direct") is True or self.fast_state

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
                state = {"turn_id": prior_tid if isinstance(prior_tid, str) else None,
                         "dispatched": False, "advised": False, "edited": edited,
                         "direct": direct, "declared": False, "pending": 0,
                         "changed": False, "checked": False, "stop_blocked": False}
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
                state = {"turn_id": tid, "dispatched": False, "advised": False, "edited": [],
                         "direct": direct, "declared": False, "pending": 0,
                         "changed": False, "checked": False, "stop_blocked": False}
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
        state = {
            "turn_id": tid if tid is not None else state.get("turn_id"),
            "dispatched": state.get("dispatched") is True,
            "advised": state.get("advised") is True,
            "edited": edited,
            "direct": state.get("direct") is True,  # this turn's prompt carried #direct
            "declared": state.get("declared") is True,  # main declared direct work this turn (M3)
            "pending": _pending(state),  # write dispatches whose role has not started yet (M11)
            "changed": state.get("changed") is True,  # B2: a change this turn (see _mark_changed)
            "checked": state.get("checked") is True,  # B2: a check after the latest change
            "stop_blocked": state.get("stop_blocked") is True,  # B3: this turn's one block is spent
        }
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
            self._shell_wrote(state, state_path, target)
            return self.result("allow", "direct", file=target)
        if state["dispatched"]:
            self._shell_wrote(state, state_path, target)
            return self.result("allow", "dispatched", file=target)
        if self.r1 == "strict":
            return self._shell_r1(state, state_path, target, _exit_text(self.env, self.host, "STRICT"))
        if self.r1 == "declare":
            if self._declared(state, guard):
                self._shell_wrote(state, state_path, target)
                return self.result("allow", "declared", file=target)
            return self._shell_r1(state, state_path, target, _exit_text(self.env, self.host, "DECLARE"))
        if self._classified(state, guard) is None:
            self._shell_wrote(state, state_path, target)
            return self.result("allow", "uncounted", file=target)
        return self._shell_r1(state, state_path, target, _text(self.env, "R1"))

    def _shell_r1(self, state: Dict[str, Any], state_path: Path, target: Optional[str], reason: str) -> Dict[str, Any]:
        """R1 on a shell write: enforce denies (nothing was written); shadow lets it through and logs it."""
        if self.mode == "enforce":
            return self.result("deny", "R1", reason=reason, file=target)
        self._shell_wrote(state, state_path, target)
        return self.result("would_deny", "R1", reason=reason, file=target)

    def _shell_wrote(self, state: Dict[str, Any], state_path: Path, target: Optional[str]) -> None:
        """B2: an allowed shell write counts as a change.  Best effort: a failed write only loses the record."""
        if target is None:
            return
        _mark_changed(state)
        _write_json(state_path, state)

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
        _mark_changed(state)  # B2: an allowed, non-exempt edit (shadow's would_deny included) is a change
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
    stop_hook_active: Any = None,
    agent_id: Any = None,
    workspace: Any = None,
    dispatched_roles: Optional[List[str]] = None,
    fully_idle: Any = None,
    fast: Optional[str] = None,
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
    }


def adapt_claude(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    event = _adapt_claude(payload)
    if event is not None:
        event["agent_id"] = _str(payload.get("agent_id"))  # present on every subagent event; only logged on claude
    return event


def _adapt_claude(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
    if name == "Stop":
        # tests/fixtures/stop_payload_shapes.json: session_id, prompt_id, stop_hook_active (bool), ...
        return _event("claude", "stop", *base, stop_hook_active=payload.get("stop_hook_active"))
    if name == "UserPromptSubmit":
        prompt = payload.get("prompt")  # read for the #direct token only; never stored or logged
        has_direct = has_direct_token(prompt)
        return _event("claude", "prompt", *base, direct=has_direct, fast=fast_switch(prompt))
    if name in ("PostToolUse", "PostToolUseFailure"):
        # PostToolUseFailure (a Bash call that failed, e.g. a test run exiting non-zero) is a call that ran too.  Its
        # payload shape was not captured: only tool_name, tool_input, agent_id, session_id, prompt_id are relied on.
        # tests/fixtures/claude_subagent_tool_shapes.json: same keys as PreToolUse plus tool_response; a subagent's
        # call carries agent_id (sub).  Only a foreground Bash call matters: it ran, so it can count as a check.
        tool, tin = payload.get("tool_name"), _dict(payload.get("tool_input"))
        if tool != "Bash" or tin.get("run_in_background") is True:
            return None
        return _event("claude", "post_shell", *base, tool=tool, tool_kind="shell", command=tin.get("command"))
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
    event = _adapt_codex(payload)
    if event is not None:
        event["agent_id"] = _str(payload.get("agent_id"))  # present on every subagent event (and SubagentStart)
    return event


def _adapt_codex(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = payload.get("hook_event_name")
    sub = bool(payload.get("agent_id"))
    agent_id = payload.get("agent_id")
    if name == "SubagentStart":
        # tests/fixtures/codex_subagent_tool_shapes.json: agent_id/agent_type name the NEW subagent, session_id is
        # main's, turn_id is the subagent's own (not main's), so it is not passed on.  The event belongs to the
        # main session, so it is not a subagent call.
        return _event("codex", "subagent_start", payload.get("session_id"), None, payload.get("cwd"), False,
                      payload.get("agent_type"), agent_id=agent_id)
    base = (
        payload.get("session_id"),
        payload.get("turn_id"),
        payload.get("cwd"),
        sub,
        payload.get("agent_type"),
    )
    if name == "Stop":
        # tests/fixtures/stop_payload_shapes.json: session_id, turn_id, stop_hook_active (bool), ...
        return _event("codex", "stop", *base, stop_hook_active=payload.get("stop_hook_active"))
    if name == "UserPromptSubmit":
        # The payload's `prompt` field is what shoal_autoroute_gate.py reads on Codex too.
        return _event("codex", "prompt", *base, direct=has_direct_token(payload.get("prompt")),
                      fast=fast_switch(payload.get("prompt")))
    if name == "PostToolUse":
        # tests/fixtures/codex_subagent_tool_shapes.json: PostToolUse has tool_name, tool_input and tool_response; it
        # does not fire for a call that failed to start, and a subagent's call carries agent_id (sub).
        tool, tin = payload.get("tool_name"), _dict(payload.get("tool_input"))
        if tool != "Bash" or not isinstance(tin.get("command"), str):
            return None
        return _event("codex", "post_shell", *base, tool=tool, tool_kind="shell", command=tin["command"])
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
        return _event("grok", "prompt", *base, direct=has_direct_token(payload.get("prompt")),
                      fast=fast_switch(payload.get("prompt")))
    if name == "subagent_start":
        # tests/fixtures/grok_guard_event_shapes.json: sessionId is MAIN's; subagentId/subagentType name the NEW subagent,
        # whose own events carry sessionId == subagentId.
        return _event("grok", "subagent_start", payload.get("sessionId"), None, payload.get("cwd"), False,
                      payload.get("subagentType"), agent_id=payload.get("subagentId"))
    if name == "stop":
        # Two stops fire per run; only `reason == end_turn` ends a turn.  A subagent's own stop is not main's.
        if payload.get("reason") != "end_turn" or sub_type is not None:
            return None
        return _event("grok", "stop", *base, stop_hook_active=payload.get("stopHookActive"))
    if name != "pre_tool_use":
        return None
    tool, tin = payload.get("toolName"), _dict(payload.get("toolInput"))
    if tool == "run_terminal_command" and isinstance(tin.get("command"), str):
        return _event("grok", "tool", *base, tool=tool, tool_kind="shell", command=tin["command"])
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
                      dispatched_roles=_agy_dispatched_roles(args))
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
        if name in ("PreToolUse", "PostToolUse", "PostToolUseFailure") and not _matcher_covers(group.get("matcher"), tool if isinstance(tool, str) else None):
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
        event = (adapt_agy(payload, env.get("SHOAL_GUARD_EVENT")) if host == "agy" else ADAPTERS[host](payload))
        if event is None:
            return None
        result = evaluate(event, env, home)
        if result["decision"] == "deny":
            return deny_output(host, result["reason"])
        if result["decision"] == "block":
            return block_output(result["reason"])
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
