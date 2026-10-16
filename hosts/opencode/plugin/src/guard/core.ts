/**
 * Shoal dispatch guard core (TypeScript port of hooks/shoal_guard.py).
 *
 * Decides on a normalized event only; the OpenCode adapter lives in ./opencode.ts.
 * Behaviour must stay identical to the Python core: both replay
 * tests/fixtures/guard_vectors.json.  The guard is a policy nudge, not a security
 * boundary (docs/specs/dispatch-enforcement/SPEC.md; R1 deny, G4 and G5 on claude:
 * docs/specs/delegation-default/SPEC.md).
 *
 * `evaluate` throws only on programming or OS errors; callers fail open.
 */
import {
  closeSync,
  constants,
  existsSync,
  fchmodSync,
  fstatSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readSync,
  readlinkSync,
  statSync,
  unlinkSync,
  writeSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { basename, dirname, isAbsolute, join, relative } from "node:path";
import { logReason, parseDeclaration } from "./declaration.js";
import { shellWriteTargets } from "./shell-writes.js";

export const MAX_LOG_BYTES = 1024 * 1024;
export const MAX_STATE_BYTES = 64 * 1024;
const ID_RE = /^[A-Za-z0-9_-]{1,128}$/;
const LOCK_STALE_MS = 5000;
let lockWaitMs = 2000;

/** Tests shorten the lock wait to exercise lock_timeout quickly. */
export function setLockWaitForTests(ms: number | null): void {
  lockWaitMs = ms ?? 2000;
}

export type Env = Record<string, string | undefined>;

export type GuardEvent = {
  host: string;
  kind: "prompt" | "turn_boundary" | "tool" | "subagent_start" | "stop" | "session_start" | "post_shell" | "post_tool" | "session_end";
  session_id: string | null;
  turn_id: string | null;
  cwd: string | null;
  is_subagent: boolean;
  role: string | null;
  tool_name: string | null;
  tool_kind: "edit" | "dispatch" | "background_shell" | "shell" | "other" | null;
  paths: string[];
  dispatched_role: string | null;
  /** shell events (claude `Bash`, G5): the command text; null otherwise. */
  command?: string | null;
  /** prompt events (claude): the user's prompt carried a standalone `#direct` token. */
  direct?: boolean;
  /** prompt events: "on" for a standalone `#fast`, "off" for `#strict`; absent when neither was typed. */
  fast?: "on" | "off" | null;
  /** stop events: the host's raw `stop_hook_active` value; only exactly `false` lets the guard block. */
  stop_hook_active?: unknown;
  /** codex: the subagent's id on its events and on `subagent_start` (its own turn_id differs from main's). */
  agent_id?: string | null;
  /** agy: the conversation's workspace paths, joined; every listed subagent's role name on `invoke_subagent`; the host's raw `fullyIdle`. */
  workspace?: string | null;
  dispatched_roles?: string[] | null;
  /** dispatch events: the short description the lane label is read from (agy: `dispatch_descs`, each Subagents[] entry's Role field). */
  dispatch_desc?: string | null;
  dispatch_descs?: Array<string | null> | null;
  fully_idle?: unknown;
  /** agy, set by the guard: the access class of the subagent conversation the event belongs to. */
  conv_class?: string | null;
  /** the canonical hook event name when it differs from what `kind` implies (guard chain). */
  hook_event?: string | null;
};

export type GuardResult = {
  decision: string;
  rule: string | null;
  skip_reason: string | null;
  reason: string | null;
  mode: string;
  /** advise only: true when this call is the first of the turn and the host should print `reason`. */
  notify?: boolean;
  /** guard chain: the members' advisory `context`, joined by a newline (null when none); logged, never sent on opencode. */
  context?: string | null;
};

type StateFile = {
  turn_id: string | null;
  dispatched: boolean;
  advised: boolean;
  edited: string[];
  direct: boolean;
  /** fast mode is on for this session (set by `#fast`, cleared by `#strict`; omitted when off). */
  fast?: boolean;
  /** write dispatches whose role has not started yet (M11; START_UNLOCK_HOSTS only). */
  pending: number;
  /** main declared direct work this turn (`: shoal-direct <reason>`, M3). */
  declared: boolean;
  /** B2: an allowed, non-exempt change happened this turn (see markChanged). */
  changed: boolean;
  /** B2: after the latest change a verify-level role was dispatched or started, or main ran a plain foreground shell call. */
  checked: boolean;
  post_seen?: boolean; // claude, codex: this session has seen a PostToolUse of a main-session shell call
  /** B3: this turn's one completion block has been spent. */
  stop_blocked: boolean;
  /** E1: the last DIRECT_TURNS_MAX turn ids whose prompt carried `#direct` (omitted when empty). */
  direct_turns?: string[];
  /** codex: agent ids released from E1 by a `#direct` turn at their start (the last AGENTS_MAX). */
  direct_agents?: string[];
  /** codex: agent ids that already released a pending dispatch (the last AGENTS_MAX). */
  started_agents?: string[];
};
type LogRecord = Record<string, unknown>;

// Default mode per host.  E6: opencode is enforce (shadow evidence met); codex, grok and agy are enforce.
const HOST_DEFAULT_MODE: Record<string, string> = {
  claude: "enforce",
  codex: "enforce",
  grok: "enforce",
  agy: "enforce",
  opencode: "enforce",
};
// Hosts whose payload identifies the calling role: LEAF / VERIFY_EDIT apply (spec R6).
const ROLE_AWARE_HOSTS = new Set(["claude", "codex", "grok", "opencode"]);
// Hosts whose `Stop` payload is recorded (tests/fixtures/stop_payload_shapes.json) and whose hook accepts
// {"decision": "block", "reason": ...}: only they block an unverified completion (B4).  opencode has no
// recorded end-of-turn payload for the main session, so it never blocks.  SHOAL_GUARD_STOP switches the check off
// on these hosts and has no effect elsewhere.  Grok and agy have the payload but their block output is not yet
// exercised: their default is shadow (`would_block` only) until SHOAL_GUARD_STOP=enforce.
const STOP_HOSTS = new Set(["claude", "codex", "grok", "agy"]);
// Hosts whose registration carries PostToolUse for the shell tool: there `checked` is set by a shell call that really
// ran (kind `post_shell`); PreToolUse counts only until the session has seen its first PostToolUse (state `post_seen`).
const POST_HOSTS = new Set(["claude", "codex"]);
const STOP_SHADOW_DEFAULT_HOSTS = new Set(["grok", "agy"]);
// agy (tests/fixtures/agy_guard_event_shapes.json): the payload names no role and no parent, but a subagent runs in its
// OWN conversation (announced by a `SessionStart`).  The guard infers main vs subagent from the order of events and keeps
// it in `state/agy.conversations.json`.  Not exact: two sessions dispatching at once in one workspace can be confused.
const CONVERSATION_HOSTS = new Set(["agy"]);
const AGY_RECORD_FILE = "agy.conversations";
const AGY_RECORD_MAX = 64;
const AGY_PENDING_TTL_MS = 600_000;
// Hosts whose prompt event carries the user's text, so that `#direct` exists.  agy's PreInvocation carries none.
const PROMPT_DIRECT_HOSTS = new Set(["claude", "codex", "grok", "opencode"]);
type AgyConversation = { id: string; kind: "main" | "sub"; role: string; cls: string; dispatcher: string };
type AgyPending = { dispatcher: string; role: string; workspace: string; ts: number };
// agy turn ids are composed `conversation:invocation`; its tool payload may not carry one.
const COMPOSED_TURN_HOSTS = new Set(["agy"]);
// Hosts whose tool hooks carry no turn id: the turn recorded at the prompt boundary is used
// (claude: after `/login` a resumed session has no prompt_id).
const STATE_TURN_HOSTS = new Set(["agy", "grok", "opencode", "claude"]);
// Hosts whose PreToolUse accepts a non-blocking `additionalContext`: only they print the advise
// reminder.  The opencode adapter prints nothing (no verified equivalent): log only.
const ADVISE_OUTPUT_HOSTS = new Set(["claude", "codex"]);
// Hosts whose prompt event may lack a turn id: it clears `dispatched` and keeps turn and edits (M1).
const PROMPT_KEEP_HOSTS = new Set(["claude"]);
// Hosts where R1 denies (claude only, G1), where main's background shell is denied (G4) and where a
// shell command that writes a file is judged by R1 (G5).
// The OpenCode adapter never produces such an event; the vectors replay it at the core level.
const DENY_MAIN_HOSTS = new Set(["claude"]);
// SHOAL_GUARD_R1 (main-session edit rule; docs/specs/guard-declared-direct).  `declare` needs a way to
// declare, so it is selectable only on hosts whose adapter delivers main's shell calls to the guard
// (claude's and, since 3.2.1, codex's `Bash`; the OpenCode adapter's `bash`); every other host keeps the v3.1.0
// rule (`classified`).  `strict` (3.3.0) needs the same events and is selectable on the same hosts, where it is
// the default.
const DECLARE_HOSTS = new Set(["claude", "codex", "opencode", "grok", "agy"]);
// Hosts where "a write-level role was dispatched" unlocks only once the role has started (M11): the dispatch
// call records a pending write dispatch and the start event releases it (SubagentStart on claude and codex,
// `subagent_start` on grok, the new conversation's SessionStart on agy, `session.created` on opencode).  Every
// host the guard knows is in this set, so none unlocks at the dispatch call itself.  The registration and
// the guard script ship together; see hooks/shoal_guard.py.
const START_UNLOCK_HOSTS = new Set(["claude", "codex", "opencode", "grok", "agy"]);
// Codex: the first tool call of a write-level role's agent is start evidence as well (the SubagentStart hook may not be
// approved yet); each agent_id releases at most one pending dispatch (`started_agents`).  See hooks/shoal_guard.py.

// `#direct` as an instruction the user typed (mirrors hooks/shoal_guard.py has_direct_token): a
// standalone token after the start of the text or whitespace, followed by the end, whitespace or
// sentence punctuation (ASCII or CJK).  Fenced blocks and inline code spans are masked with NUL
// first, so quoted code never counts.  The OpenCode adapter does not read prompts; this exists so
// both implementations replay tests/fixtures/direct_token_vectors.json.
const tokenRe = (name: string): RegExp =>
  new RegExp("(?<!\\S)#" + name + "(?![^\\s.,;:!?\\u3002\\uff0c\\u3001\\uff1b\\uff1a\\uff01\\uff1f])");
const DIRECT_TOKEN_RE = tokenRe("direct");
const FAST_TOKEN_RE = tokenRe("fast");
const STRICT_TOKEN_RE = tokenRe("strict");
const FENCE_OPEN_RE = /^ {0,3}`{3,}/;
const FENCE_CLOSE_RE = /^ {0,3}`{3,}\s*$/;
const INLINE_CODE_RE = /(?<!`)(`+)(?!`)(?:(?!\n[ \t\r]*\n)[\s\S])+?(?<!`)\1(?!`)/g;

/** The prompt text with fenced blocks and inline code masked, or null when it is not a string. */
function unquoted(prompt: unknown): string | null {
  if (typeof prompt !== "string") return null;
  const lines: string[] = [];
  let inFence = false;
  for (const line of prompt.split("\n")) {
    if (inFence) {
      inFence = !FENCE_CLOSE_RE.test(line);
      lines.push("\0");
    } else if (FENCE_OPEN_RE.test(line)) {
      inFence = true;
      lines.push("\0");
    } else lines.push(line);
  }
  return lines.join("\n").replace(INLINE_CODE_RE, "\0");
}

export function hasDirectToken(prompt: unknown): boolean {
  const text = unquoted(prompt);
  return text !== null && DIRECT_TOKEN_RE.test(text);
}

/** Fast mode switch typed in the prompt: "off" for `#strict` (wins when both appear), "on" for `#fast`, else null. */
export function fastSwitch(prompt: unknown): "on" | "off" | null {
  const text = unquoted(prompt);
  if (text === null) return null;
  if (STRICT_TOKEN_RE.test(text)) return "off";
  return FAST_TOKEN_RE.test(text) ? "on" : null;
}
// Role-name namespaces accepted as the same role (K3).  Explicit allowlist only: any other
// `x:name` stays unknown, so it neither unlocks nor counts as a leaf/verify role.
const ROLE_NAMESPACES = ["shoal:"];

// role -> access level.  Keep in sync with ROLE_ACCESS in hooks/shoal_guard.py
// (tests/guard-vectors.test.ts compares the two tables).
export const ROLE_ACCESS: Record<string, string> = {
  scout: "read-only",
  "plan-critic": "read-only",
  "security-reviewer": "read-only",
  researcher: "read-only",
  Explore: "read-only",
  "applier": "write",
  executor: "write",
  "security-executor": "write",
  "sol-executor": "write",
  verifier: "verify",
  watcher: "verify",
};

/** Bare role name; a leading allowlisted namespace (`shoal:`) is removed once (K3). */
export function normalizeRole(role: string | null | undefined): string | null {
  if (typeof role !== "string") return null;
  for (const prefix of ROLE_NAMESPACES) {
    if (role.startsWith(prefix)) return role.slice(prefix.length);
  }
  return role;
}

function roleAccess(role: string | null | undefined): string | null {
  const name = normalizeRole(role);
  return name !== null && Object.hasOwn(ROLE_ACCESS, name) ? ROLE_ACCESS[name] : null;
}

// Dispatch lanes (SHOAL_GUARD_LANES, default on): keep in sync with LANE_ROLES in hooks/shoal_guard.py.
const LANE_ROLES: Record<string, string[]> = {
  fast: ["applier"],
  complex: ["executor", "sol-executor"],
  rigorous: ["security-executor"],
};
const LANE_RE = /^\s*\[(fast|complex|rigorous)\]/;

const CLASSIFIED_ROLE: Record<string, string> = {
  judgment: "executor",
  mechanical: "applier",
};
const DISPATCH_NAME: Record<string, string> = {
  claude: "Agent",
  codex: "spawn_agent",
  grok: "spawn_subagent",
  agy: "invoke_subagent",
  opencode: "task",
};
const LOG_FIELDS = ["host", "event", "tool", "rule", "decision", "file", "skip_reason", "mode", "reason", "agent_type", "agent_id", "session", "turn", "fast", "member", "ms"];

const MESSAGES: Record<string, Record<string, string>> = {
  en: {
    ADVISE:
      "Shoal dispatch brake (a reminder, nothing was blocked): this turn has edited {n} " +
      "files directly. If the work is stable same-shape repetition, or bounded judgment " +
      "with a stable contract, consider handing it to `applier` / `executor` with " +
      "{tool}; otherwise continuing directly is fine.",
    LEAF:
      "Shoal dispatch guard: subagents are leaf workers and must not dispatch other " +
      "agents. Finish the task yourself and report back to the parent.",
    VERIFY_EDIT:
      "Shoal dispatch guard: verify-level roles must not edit files with editing tools. " +
      "Report findings to the parent instead.",
    R1:
      "Shoal dispatch guard: this turn is classified as implementation work and no write " +
      "role has been dispatched. Dispatch executor or applier, or add #direct to your " +
      "prompt to edit directly.",
    G4:
      "Shoal dispatch guard: the main session does not start background shells. Dispatch " +
      "watcher in the background instead, or add #direct to your prompt.",
    STRICT:
      "Shoal dispatch guard: the main session does not edit files itself. Dispatch a " +
      "write-capable role (executor or applier), or ask the user to add #direct to the prompt.",
    STRICT_ND:
      "Shoal dispatch guard: the main session does not edit files itself. Dispatch a " +
      "write-capable role (executor or applier) and wait until it has started, add the role to " +
      "SHOAL_GUARD_WRITE_AGENTS, or set SHOAL_GUARD_DIRECT=1 (this host has no prompt marker for it).",
    DECLARE_ND:
      "Shoal dispatch guard: the main session delegates edits by default. Dispatch a " +
      "write-capable role (executor or applier), or declare direct work first by running " +
      'exactly : shoal-direct "<reason>" as its own shell command, or set SHOAL_GUARD_DIRECT=1 ' +
      "(this host has no prompt marker for it).",
    LANE_MISSING:
      "Shoal dispatch guard: a write-role dispatch ({role}) must start its description with a lane label: " +
      "[fast] -> applier, [complex] -> executor, [rigorous] -> security-executor " +
      "(e.g. `[complex] fix: ...`). Add the label, or set SHOAL_GUARD_LANES=off.",
    LANE_MISMATCH:
      "Shoal dispatch guard: lane label [{label}] does not match role {role}. " +
      "[fast] -> applier, [complex] -> executor, [rigorous] -> security-executor. " +
      "Dispatch {expected} for [{label}], or change the label to match {role}.",
    E1:
      "Shoal dispatch guard: a subagent that is not a shoal write-capable role does not edit files. " +
      "Dispatch a shoal write-capable role (executor or applier), add this agent type to " +
      "SHOAL_GUARD_WRITE_AGENTS, or set SHOAL_GUARD_DIRECT=1.",
    E1D:
      "Shoal dispatch guard: a subagent that is not a shoal write-capable role does not edit files. " +
      "Dispatch a shoal write-capable role (executor or applier), add #direct to the user prompt that " +
      "started this work, add this agent type to SHOAL_GUARD_WRITE_AGENTS, or set SHOAL_GUARD_DIRECT=1.",
    STOP:
      "Shoal completion check: this turn changed files and no check ran afterwards. Run a " +
      "verification now (tests, a verifier or watcher role), or say explicitly in your report " +
      "that the change is unverified.",
    DECLARE:
      "Shoal dispatch guard: the main session delegates edits by default. Dispatch a " +
      "write-capable role (executor or applier), or declare direct work first by running " +
      'exactly : shoal-direct "<reason>" as its own shell command, or ask the user to add ' +
      "#direct to the prompt.",
  },
  "zh-TW": {
    ADVISE:
      "Shoal dispatch brake（提醒，沒有擋任何操作）：本輪 main session 已直接改了 {n} 個檔案。" +
      "若這是穩定的同形重複，或契約穩定、範圍有界的判斷工作，可考慮用 {tool} 交給 " +
      "`applier` / `executor`；否則直接做下去也可以。",
    LEAF: "Shoal dispatch guard：subagent 是 leaf worker，不可再派其他 agent。請自己完成並回報給上層。",
    VERIFY_EDIT: "Shoal dispatch guard：verify 等級的 role 不可用編輯工具改檔，請把發現回報給上層。",
    R1:
      "Shoal dispatch guard：本輪已被分類為實作工作，且尚未派出 write role。" +
      "請派給 executor 或 applier，或在 prompt 加上 #direct以直接修改。",
    G4:
      "Shoal dispatch guard：main session 不自己開背景 shell。" +
      "請改在背景派出 watcher，或在 prompt 加上 #direct。",
    STRICT:
      "Shoal dispatch guard：main session 不自己改檔。" +
      "請派出可寫的 role（executor 或 applier），或請使用者在 prompt 加上 #direct。",
    STRICT_ND:
      "Shoal dispatch guard：main session 不自己改檔。請派出可寫的 role（executor 或 applier）並等它啟動、" +
      "把 role 加進 SHOAL_GUARD_WRITE_AGENTS，或設定 SHOAL_GUARD_DIRECT=1（這個 host 沒有 prompt 標記可用）。",
    DECLARE_ND:
      "Shoal dispatch guard：main session 預設把改檔交給別的 role。" +
      "請派出可寫的 role（executor 或 applier），或先宣告直接做：把 " +
      ': shoal-direct "<理由>" 當成單獨一次 shell 指令執行，或設定 SHOAL_GUARD_DIRECT=1（這個 host 沒有 prompt 標記可用）。',
    E1:
      "Shoal dispatch guard：不是 shoal 可寫 role 的 subagent 不改檔。" +
      "請派出 shoal 可寫的 role（executor 或 applier）、把這個 agent type 加進 " +
      "SHOAL_GUARD_WRITE_AGENTS，或設定 SHOAL_GUARD_DIRECT=1。",
    E1D:
      "Shoal dispatch guard：不是 shoal 可寫 role 的 subagent 不改檔。" +
      "請派出 shoal 可寫的 role（executor 或 applier）、請使用者在啟動這項工作的 prompt 加上 #direct、" +
      "把這個 agent type 加進 SHOAL_GUARD_WRITE_AGENTS，或設定 SHOAL_GUARD_DIRECT=1。",
    LANE_MISSING:
      "Shoal dispatch guard：派 write role（{role}）時，description 開頭必須有 lane 標籤：" +
      "[fast] -> applier、[complex] -> executor、[rigorous] -> security-executor" +
      "（例如 `[complex] fix: ...`）。請補上標籤，或設定 SHOAL_GUARD_LANES=off。",
    LANE_MISMATCH:
      "Shoal dispatch guard：lane 標籤 [{label}] 與 role {role} 不符。" +
      "[fast] -> applier、[complex] -> executor、[rigorous] -> security-executor。" +
      "[{label}] 請改派 {expected}，或把標籤改成符合 {role}。",
    STOP:
      "Shoal completion check：本回合改過檔案，之後沒有跑過任何檢查。" +
      "請現在做一次驗證（測試、verifier 或 watcher role），或在回報中明確寫出這次修改尚未驗證。",
    DECLARE:
      "Shoal dispatch guard：main session 預設把改檔交給別的 role。" +
      "請派出可寫的 role（executor 或 applier），或先宣告直接做：把 " +
      ': shoal-direct "<理由>" 當成單獨一次 shell 指令執行，或請使用者在 prompt 加上 #direct。',
  },
};

// ---------------------------------------------------------------------------
// State and log files (spec R4)
// ---------------------------------------------------------------------------

// Tests simulate a file owned by another uid through this seam (see guard-vectors.test.ts).
let ownerResolver: ((path: string) => number) | null = null;
export function setOwnerResolverForTests(resolver: ((path: string) => number) | null): void {
  ownerResolver = resolver;
}

function currentUid(path: string): number {
  if (ownerResolver) return ownerResolver(path);
  return typeof process.getuid === "function" ? process.getuid() : -1;
}

function noSymlinkBelow(path: string, anchor: string): boolean {
  const rel = relative(anchor, path);
  if (rel === ".." || rel.startsWith("../") || isAbsolute(rel)) return false;
  let cursor = path;
  while (cursor !== anchor) {
    try {
      if (lstatSync(cursor).isSymbolicLink()) return false;
    } catch {
      // missing component: not a symlink
    }
    const parent = dirname(cursor);
    if (parent === cursor) break;
    cursor = parent;
  }
  return true;
}

/** Open a regular file owned by us with O_NOFOLLOW; force mode 0600.  null when untrusted. */
function openPrivate(path: string, flags: number): number | null {
  let fd: number;
  try {
    fd = openSync(path, flags | (constants.O_NOFOLLOW ?? 0), 0o600);
  } catch {
    return null;
  }
  try {
    const info = fstatSync(fd);
    if (!info.isFile() || info.uid !== currentUid(path)) {
      closeSync(fd);
      return null;
    }
    fchmodSync(fd, 0o600);
  } catch {
    try {
      closeSync(fd);
    } catch {
      // already closed
    }
    return null;
  }
  return fd;
}

function stateBase(env: Env, home: string): string {
  const xdg = env.XDG_STATE_HOME ?? "";
  if (xdg && isAbsolute(xdg)) return xdg;
  return join(home, ".local", "state");
}

/** ${state}/shoal/guard with state/ and turns/ beneath it; null if it cannot be trusted. */
export function guardDir(env: Env, home: string): string | null {
  const base = stateBase(env, home);
  const rel = relative(home, base);
  const insideHome = !(rel === ".." || rel.startsWith("../") || isAbsolute(rel));
  const anchor = insideHome ? home : base; // XDG outside HOME: only dirs below it are checked
  try {
    if (!noSymlinkBelow(base, anchor)) return null;
    mkdirSync(base, { recursive: true });
    const levels: Array<[string, boolean]> = [
      ["shoal", false],
      ["shoal/guard", true],
      ["shoal/guard/state", true],
      ["shoal/guard/turns", true],
    ];
    for (const [sub, strict] of levels) {
      const cursor = join(base, sub);
      try {
        mkdirSync(cursor, { mode: 0o700 });
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      }
      const info = lstatSync(cursor);
      if (!info.isDirectory() || info.uid !== currentUid(cursor)) return null;
      if (strict && (info.mode & 0o077) !== 0) return null;
    }
  } catch {
    return null;
  }
  return join(base, "shoal", "guard");
}

function sleepMs(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

/**
 * Run `body` holding an exclusive-create `.tslock` file (0600, O_NOFOLLOW) beside the state.
 * Returns the skip reason instead when the lock cannot be taken within lockWaitMs; a lock
 * older than LOCK_STALE_MS belongs to a dead process and is removed.
 */
function withStateLock(path: string, body: () => GuardResult, skip: (reason: string) => GuardResult): GuardResult {
  const flags = constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW ?? 0);
  const deadline = Date.now() + lockWaitMs;
  let fd: number | null = null;
  for (;;) {
    try {
      fd = openSync(path, flags, 0o600);
      break;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") return skip("state_unavailable");
    }
    try {
      if (Date.now() - lstatSync(path).mtimeMs > LOCK_STALE_MS) unlinkSync(path);
    } catch {
      // vanished or not removable: retry below
    }
    if (Date.now() >= deadline) return skip("lock_timeout");
    sleepMs(10);
  }
  try {
    return body();
  } finally {
    try {
      closeSync(fd);
      unlinkSync(path);
    } catch {
      // already gone
    }
  }
}

function readJson(path: string): Record<string, unknown> {
  const fd = openPrivate(path, constants.O_RDONLY);
  if (fd === null) return {};
  try {
    const buffer = Buffer.alloc(MAX_STATE_BYTES);
    const bytes = readSync(fd, buffer, 0, MAX_STATE_BYTES, null);
    const data: unknown = JSON.parse(buffer.subarray(0, bytes).toString("utf8"));
    return isRecord(data) ? data : {};
  } catch {
    return {};
  } finally {
    closeSync(fd);
  }
}

function writeJson(path: string, value: unknown): boolean {
  const fd = openPrivate(path, constants.O_WRONLY | constants.O_CREAT | constants.O_TRUNC);
  if (fd === null) return false;
  try {
    writeSync(fd, JSON.stringify(value));
  } finally {
    closeSync(fd);
  }
  return true;
}

function pendingCount(state: Record<string, unknown>): number {
  const value = state.pending;
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : 0;
}

/** B2: a change after a check puts the turn back to "unchecked". */
function markChanged(state: StateFile): void {
  state.changed = true;
  state.checked = false;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeText(value: unknown): string | null {
  return typeof value === "string" ? value.slice(0, 200) : null;
}

/** Non-reversible 8-hex tag of a session or turn id, for the log (undefined when there is no id). */
export function shortHash(value: unknown): string | undefined {
  if (typeof value !== "string" || value === "") return undefined;
  return createHash("sha256").update(value, "utf8").digest("hex").slice(0, 8);
}

/** Append one whitelisted record to guard.jsonl (1 MiB cap).  Never throws. */
export function appendLog(dir: string | null, record: LogRecord): void {
  if (dir === null) return;
  const line: Record<string, string | boolean> = { ts: new Date().toISOString() };
  for (const key of LOG_FIELDS) {
    let value = record[key];
    if (key === "fast") {
      if (value === true) line.fast = true; // the only boolean field: present only when fast mode was on
      continue;
    }
    if (key === "file" && typeof value === "string") value = basename(value);
    const text = safeText(value);
    if (text !== null) line[key] = text;
  }
  const path = join(dir, "guard.jsonl");
  try {
    try {
      if (statSync(path).size > MAX_LOG_BYTES) return;
    } catch {
      // not created yet
    }
    const fd = openPrivate(path, constants.O_WRONLY | constants.O_APPEND | constants.O_CREAT);
    if (fd === null) return;
    try {
      writeSync(fd, JSON.stringify(line) + "\n");
    } finally {
      closeSync(fd);
    }
  } catch {
    // logging must never affect the decision
  }
}

// ---------------------------------------------------------------------------
// Rules
// ---------------------------------------------------------------------------

/** Session and turn ids; composed (agy `conversation:invocation`) ids map ':' to '_'. */
export function validId(value: unknown, composed = false): boolean {
  if (typeof value !== "string") return false;
  return ID_RE.test(composed ? value.replaceAll(":", "_") : value);
}

/**
 * False only when the installed module manifest has a record for `host` whose modules lack `dispatch-guard`
 * (modular-install S3, `--without dispatch-guard`).  No manifest, an unreadable one, or no record: true.
 * Mirror of dispatch_guard_selected in hooks/shoal_guard.py; SHOAL_GUARD_CHAIN_FILE overrides the path.
 */
export function dispatchGuardSelected(host: string, env: Env, home: string): boolean {
  try {
    const override = env.SHOAL_GUARD_CHAIN_FILE ?? "";
    const xdg = env.XDG_DATA_HOME ?? "";
    const data = xdg && isAbsolute(xdg) ? xdg : join(home, ".local", "share");
    const path = override && isAbsolute(override) ? override : join(data, "shoal", "modules.json");
    const doc: unknown = JSON.parse(readFileSync(path).subarray(0, 1024 * 1024).toString("utf8"));
    const entry = typeof doc === "object" && doc !== null ? (doc as Record<string, unknown>)[host] : undefined;
    const modules = typeof entry === "object" && entry !== null ? (entry as Record<string, unknown>).modules : undefined;
    return !(Array.isArray(modules) && !modules.includes("dispatch-guard"));
  } catch {
    return true;
  }
}

/** Unset -> host default; an unrecognized value -> shadow (as the legacy guard did). */
export function resolveMode(host: string, env: Env, home?: string): string {
  if (home !== undefined && !dispatchGuardSelected(host, env, home)) return "off";
  const raw = env.SHOAL_GUARD || "";
  let mode: string;
  if (!raw) mode = HOST_DEFAULT_MODE[host] ?? "shadow";
  else mode = raw === "enforce" || raw === "shadow" || raw === "off" ? raw : "shadow";
  return mode;
}

/**
 * E1 (docs/specs/guard-every-gate): hosts where SHOAL_GUARD_SUBAGENT_WRITE defaults to `on`, and hosts whose
 * subagent PreToolUse carries the main session's session_id and the prompt_id of the turn that started it, so the
 * user's `#direct` can release a subagent.
 */
const SUBAGENT_WRITE_DEFAULT_ON_HOSTS = new Set(["claude", "codex", "opencode", "grok", "agy"]);
// opencode: the adapter reports a subagent under its main session id and the main turn that was current when the
// child session was created (hosts/opencode/plugin/src/guard/opencode.ts).
const SUBAGENT_DIRECT_HOSTS = new Set(["claude", "codex", "opencode", "grok"]);
/**
 * Grok: a subagent's tool events carry its OWN session id (= the subagentId of `subagent_start`, which is sent under
 * main's session id).  `subagent_start` records subagent id -> {main session, role, direct flag} in
 * `state/grok.agents.json` (the last GROK_AGENTS_MAX); a tool event under a recorded id is that subagent's call.
 */
const MAPPED_HOSTS = new Set(["grok"]);
const GROK_AGENTS_MAX = 64;
const GROK_AGENTS_FILE = "grok.agents";
type AgentEntry = { id: string; session: string; role: string; direct: boolean };

/** The valid entries of a grok agent-map file's content, the last GROK_AGENTS_MAX. */
function agentEntries(raw: Record<string, unknown>): AgentEntry[] {
  const items = raw.agents;
  if (!Array.isArray(items)) return [];
  const kept = items.filter(
    (e): e is AgentEntry =>
      e !== null &&
      typeof e === "object" &&
      validId((e as AgentEntry).id) &&
      validId((e as AgentEntry).session) &&
      typeof (e as AgentEntry).role === "string" &&
      typeof (e as AgentEntry).direct === "boolean",
  );
  return kept.slice(-GROK_AGENTS_MAX);
}
/**
 * Codex: a subagent runs in its own turn, so `#direct` is looked up by agent_id: a SubagentStart while main's current
 * turn carried `#direct` records the id in `direct_agents`.
 */
const AGENT_KEYED_HOSTS = new Set(["codex"]);
const AGENTS_MAX = 32;
/** The state file remembers this many most recent turn ids that carried `#direct`. */
const DIRECT_TURNS_MAX = 16;

/** SHOAL_GUARD_LANES: `off` disables the dispatch-lane rule only; any other value (or none) leaves it on. */
export function lanesEnabled(env: Env): boolean {
  return env.SHOAL_GUARD_LANES !== "off";
}

/** The lane label a dispatch description starts with, else null. */
export function laneLabel(desc: unknown): string | null {
  return typeof desc === "string" ? (LANE_RE.exec(desc)?.[1] ?? null) : null;
}

/** [message key, format args] when dispatching `role` with `desc` breaks the lane rule; null otherwise. */
function laneViolation(role: string | null | undefined, desc: unknown): [string, Record<string, string>] | null {
  const bare = normalizeRole(role);
  if (bare === null || roleAccess(role) !== "write") return null;
  const label = laneLabel(desc);
  if (label === null) return ["LANE_MISSING", { role: bare }];
  if (LANE_ROLES[label].includes(bare)) return null;
  return ["LANE_MISMATCH", { label, role: bare, expected: LANE_ROLES[label][0] }];
}

/** SHOAL_GUARD_SUBAGENT_WRITE: `on` enables E1, `off` disables it; unset (or any other value) follows the host default. */
export function subagentWriteEnabled(host: string, env: Env): boolean {
  const raw = env.SHOAL_GUARD_SUBAGENT_WRITE;
  if (raw === "on" || raw === "off") return raw === "on";
  return SUBAGENT_WRITE_DEFAULT_ON_HOSTS.has(host);
}

function directTurns(state: Record<string, unknown>): string[] {
  const raw = state.direct_turns;
  if (!Array.isArray(raw)) return [];
  return raw.filter((t): t is string => typeof t === "string").slice(-DIRECT_TURNS_MAX);
}

/** `direct_agents` / `started_agents` of a state file: ids that pass validId, the last AGENTS_MAX. */
function agentList(state: Record<string, unknown>, key: string): string[] {
  const raw = state[key];
  if (!Array.isArray(raw)) return [];
  return raw.filter((a): a is string => validId(a)).slice(-AGENTS_MAX);
}

/** Keep the two agent lists of `prior` in `state` (they live across turns, like `direct_turns`). */
function carryAgents(state: StateFile, prior: Record<string, unknown>): void {
  if (prior.post_seen === true) state.post_seen = true;
  const direct = agentList(prior, "direct_agents");
  if (direct.length > 0) state.direct_agents = direct;
  const started = agentList(prior, "started_agents");
  if (started.length > 0) state.started_agents = started;
}

/** SHOAL_GUARD_WRITE_AGENTS: the raw agent type, or the type without a `shoal:` prefix, is in the list. */
export function writeAgentAllowed(role: string | null | undefined, env: Env): boolean {
  if (typeof role !== "string" || role === "") return false;
  const wanted = new Set((env.SHOAL_GUARD_WRITE_AGENTS ?? "").split(",").map((item) => item.trim()));
  wanted.delete("");
  return wanted.has(role) || wanted.has(normalizeRole(role) ?? "");
}

/**
 * SHOAL_GUARD_STOP: `off` disables the completion check on claude, codex, grok and agy; any other value (or none)
 * keeps it on (grok and agy: logging only, see stopBlocks).  No effect on a host outside STOP_HOSTS.
 */
export function stopEnabled(host: string, env: Env): boolean {
  return STOP_HOSTS.has(host) && env.SHOAL_GUARD_STOP !== "off";
}

/** False on a host whose block output is unverified (STOP_SHADOW_DEFAULT_HOSTS) unless SHOAL_GUARD_STOP=enforce. */
export function stopBlocks(host: string, env: Env): boolean {
  return !STOP_SHADOW_DEFAULT_HOSTS.has(host) || env.SHOAL_GUARD_STOP === "enforce";
}

/**
 * SHOAL_GUARD_R1: `classified` and `off` as given; `strict` and `declare` where the host can gate.
 * Unset, unrecognized, or `strict` / `declare` on a host outside DECLARE_HOSTS -> `classified`.  Every host the
 * guard knows (claude, codex, opencode, grok, agy) is in DECLARE_HOSTS, so `strict` is the default there.
 */
export function resolveR1(host: string, env: Env): string {
  const raw = env.SHOAL_GUARD_R1 || "";
  if (raw === "classified" || raw === "off") return raw;
  if (!DECLARE_HOSTS.has(host)) return "classified";
  return raw === "declare" ? "declare" : "strict";
}

/** null when the configured value is not an integer (the guard then fails open). */
function maxFiles(env: Env): number | null {
  const raw = env.SHOAL_GUARD_MAX_FILES || "2";
  if (!/^\s*[+-]?\d+\s*$/.test(raw)) return null;
  return Math.max(0, Number.parseInt(raw, 10));
}

/** realpath that tolerates missing tails and dangling symlinks, like Python's non-strict one. */
export function lenientRealpath(input: string): string {
  const queue = input.split("/").reverse(); // stack: next component at the end
  let resolved = "/";
  let links = 0;
  while (queue.length > 0) {
    const name = queue.pop() as string;
    if (name === "" || name === ".") continue;
    if (name === "..") {
      resolved = dirname(resolved);
      continue;
    }
    const next = join(resolved, name);
    let isLink = false;
    try {
      isLink = lstatSync(next).isSymbolicLink();
    } catch {
      // missing: keep the remaining components as written
    }
    if (!isLink || ++links > 40) {
      resolved = next;
      continue;
    }
    let target: string;
    try {
      target = readlinkSync(next);
    } catch {
      resolved = next;
      continue;
    }
    if (isAbsolute(target)) resolved = "/";
    for (const part of target.split("/").reverse()) queue.push(part);
  }
  return resolved;
}

/** Absolute, symlink-resolved path (`..` collapsed); non-existent tails are kept. */
export function resolvePath(path: string, cwd: string): string {
  return lenientRealpath(isAbsolute(path) ? path : join(cwd || process.cwd(), path));
}

function under(path: string, root: string): boolean {
  const trimmed = root.replace(/\/+$/, "");
  return trimmed !== "" && (path === trimmed || path.startsWith(trimmed + "/"));
}

/**
 * Root of the repository under test: the nearest ancestor of `cwd` holding `.git` (a directory or a worktree
 * file); `cwd` itself (resolved) when there is none.
 */
export function repoUnderTest(cwd: string): string {
  const start = lenientRealpath(cwd || process.cwd());
  let cursor = start;
  for (;;) {
    if (existsSync(join(cursor, ".git"))) return cursor;
    const parent = dirname(cursor);
    if (parent === cursor) return start;
    cursor = parent;
  }
}

/** `path` is already resolved.  Exempt: /tmp, $TMPDIR, any `.ai` directory, claude transcripts. */
export function isExempt(path: string, host: string, env: Env, home: string): boolean {
  if (path.split("/").slice(0, -1).includes(".ai")) return true;
  const roots = ["/tmp", "/private/tmp", lenientRealpath("/tmp")];
  const tmpdir = env.TMPDIR ?? "";
  if (tmpdir && isAbsolute(tmpdir) && lenientRealpath(tmpdir) !== "/") {
    roots.push(lenientRealpath(tmpdir));
  }
  if (host === "claude") {
    roots.push(lenientRealpath(join(home, ".claude", "projects")));
    const config = env.CLAUDE_CONFIG_DIR ?? "";
    if (config && isAbsolute(config)) roots.push(lenientRealpath(join(config, "projects")));
  }
  return roots.some((root) => under(path, root));
}

function text(env: Env, key: string, fmt: Record<string, unknown> = {}): string {
  const lang = env.SHOAL_GUARD_LANG === "zh-TW" ? "zh-TW" : "en";
  return MESSAGES[lang][key].replace(/\{(\w+)\}/g, (_m, name: string) => String(fmt[name]));
}

/** STRICT / DECLARE, or their variant without the `#direct` exit on a host whose prompt event carries no text. */
function exitText(env: Env, host: string, key: "STRICT" | "DECLARE"): string {
  return text(env, PROMPT_DIRECT_HOSTS.has(host) ? key : key + "_ND");
}

function none(mode: string): GuardResult {
  return { decision: "none", rule: null, skip_reason: null, reason: null, mode };
}

/** The valid content of the agy conversation record, each list the last AGY_RECORD_MAX. */
function agyRecord(raw: Record<string, unknown>): { conversations: AgyConversation[]; pending: AgyPending[] } {
  const convs = Array.isArray(raw.conversations) ? raw.conversations : [];
  const pend = Array.isArray(raw.pending) ? raw.pending : [];
  const conversations = convs.filter(
    (c): c is AgyConversation =>
      c !== null &&
      typeof c === "object" &&
      validId((c as AgyConversation).id) &&
      ((c as AgyConversation).kind === "main" || (c as AgyConversation).kind === "sub") &&
      typeof (c as AgyConversation).role === "string" &&
      ["write", "nonwrite", "unknown", ""].includes((c as AgyConversation).cls) &&
      ((c as AgyConversation).dispatcher === "" || validId((c as AgyConversation).dispatcher)),
  );
  const pending = pend.filter(
    (e): e is AgyPending =>
      e !== null &&
      typeof e === "object" &&
      validId((e as AgyPending).dispatcher) &&
      typeof (e as AgyPending).role === "string" &&
      typeof (e as AgyPending).workspace === "string" &&
      typeof (e as AgyPending).ts === "number",
  );
  return { conversations: conversations.slice(-AGY_RECORD_MAX), pending: pending.slice(-AGY_RECORD_MAX) };
}

class Guard {
  readonly host: string;
  readonly mode: string;
  readonly r1: string;
  private dir: string | null = null;
  private dirTried = false;
  private fast: boolean;
  private fastState = false; // the session's fast flag as persisted by this prompt event
  /** State file of an allowed write not yet counted as a change (see commitChange). */
  pendingChange: string | null = null;
  private readonly env: Env;

  constructor(
    public event: GuardEvent,
    env: Env,
    private readonly home: string,
  ) {
    // Fast mode (SHOAL_GUARD_FAST=1) marks the light lane only; it does not release main edits.
    this.fast = env.SHOAL_GUARD_FAST === "1";
    this.env = env;
    this.host = String(event.host || "");
    this.mode = resolveMode(this.host, env, home);
    this.r1 = resolveR1(this.host, env);
  }

  get guardDirectory(): string | null {
    if (!this.dirTried) {
      this.dirTried = true;
      this.dir = guardDir(this.env, this.home);
    }
    return this.dir;
  }

  private result(
    decision: string,
    opts: { rule?: string; skip?: string; reason?: string; file?: string; notify?: boolean; note?: string } = {},
  ): GuardResult {
    appendLog(this.guardDirectory, {
      host: this.host,
      event: this.event.kind,
      tool: this.event.tool_name,
      decision,
      mode: this.mode,
      rule: opts.rule,
      skip_reason: opts.skip,
      file: opts.file,
      reason: opts.note,
      session: shortHash(this.event.session_id),
      turn: shortHash(this.event.turn_id),
      fast: this.fast,
      ...(this.event.is_subagent || this.event.kind === "subagent_start"
        ? { agent_type: this.event.role, agent_id: this.event.agent_id }
        : {}),
    });
    return {
      decision,
      rule: opts.rule ?? null,
      skip_reason: opts.skip ?? null,
      reason: opts.reason ?? null,
      mode: this.mode,
      notify: opts.notify ?? false,
    };
  }

  // -- subagent backstop (spec R6) ------------------------------------------
  /** Lane rule for a main session's dispatch: a deny / would_deny result when it breaks the rule, else null. */
  laneRule(): GuardResult | null {
    const event = this.event;
    const listed = CONVERSATION_HOSTS.has(this.host) ? event.dispatched_roles : null;
    const descs = event.dispatch_descs ?? [];
    const pairs: Array<[string | null | undefined, unknown]> = listed
      ? listed.map((r, i): [string, unknown] => [r, descs[i]])
      : [[event.dispatched_role, event.dispatch_desc]];
    for (const [role, desc] of pairs) {
      const violation = laneViolation(role, desc);
      if (violation !== null) {
        return this.result(this.mode === "enforce" ? "deny" : "would_deny", {
          rule: "LANE",
          reason: text(this.env, violation[0], violation[1]),
        });
      }
    }
    return null;
  }

  subagent(): GuardResult {
    const { role, tool_kind: toolKind } = this.event;
    if (AGENT_KEYED_HOSTS.has(this.host) && roleAccess(role) === "write" && (toolKind === "edit" || toolKind === "shell")) {
      this.noteStartedByTool(); // logs its own record; the call itself is judged below as before
    }
    let rule: string | null = null;
    if (toolKind === "dispatch") rule = "LEAF";
    else if (toolKind === "edit" && roleAccess(role) === "verify") rule = "VERIFY_EDIT";
    if (rule === null && subagentWriteEnabled(this.host, this.env)) rule = this.subagentWriteRule(role, toolKind);
    if (rule === null) return none(this.mode);
    let file: string | undefined = this.event.paths?.[0];
    if ((rule === "E1" || rule === "E1_UNKNOWN") && toolKind === "shell") file = this.shellWriteTarget(roleAccess(role) === "verify") ?? undefined;
    if (rule === "E1_UNKNOWN") return this.result("skip", { rule: "E1", skip: "would_deny_unknown_class", file }); // role not established: only logged
    return this.result(this.mode === "enforce" ? "deny" : "would_deny", {
      rule,
      reason: text(this.env, rule === "E1" && SUBAGENT_DIRECT_HOSTS.has(this.host) ? "E1D" : rule),
      file,
    });
  }

  /** E1: "E1" when this subagent call writes a non-exempt file and nothing releases it, else null. */
  private subagentWriteRule(role: string | null | undefined, toolKind: string | null | undefined): string | null {
    const convClass = CONVERSATION_HOSTS.has(this.host) ? this.event.conv_class : undefined;
    if (convClass === "write" || ((convClass === undefined || convClass === null) && roleAccess(role) === "write")) return null;
    let writes: boolean;
    if (toolKind === "edit") {
      const cwd = this.event.cwd || process.cwd();
      writes = (this.event.paths ?? []).some((p) => !isExempt(resolvePath(p, cwd), this.host, this.env, this.home));
    } else if (toolKind === "shell") {
      writes = this.shellWriteTarget(roleAccess(role) === "verify") !== null;
    } else {
      return null;
    }
    if (!writes) return null;
    if (writeAgentAllowed(role, this.env) || this.env.SHOAL_GUARD_DIRECT === "1") return null;
    if (this.subagentDirectReleased()) return null;
    return convClass === "unknown" ? "E1_UNKNOWN" : "E1";
  }

  /**
   * The user's `#direct` releases a subagent when the turn named by the subagent event's (session_id, turn_id) is
   * in the main session's `direct_turns`.  Read-only; any problem (host without the payload evidence, bad ids, no
   * state dir, unreadable or corrupt state) means "not released", never an exception.
   */
  subagentDirectReleased(): boolean {
    try {
      if (!SUBAGENT_DIRECT_HOSTS.has(this.host)) return false;
      if (MAPPED_HOSTS.has(this.host)) {
        return this.agentEntry(this.event.session_id)?.direct === true;
      }
      if (AGENT_KEYED_HOSTS.has(this.host)) {
        const agent = this.event.agent_id;
        const asid = this.event.session_id;
        const adir = this.guardDirectory;
        if (!validId(asid) || !validId(agent) || adir === null) return false;
        return agentList(readJson(join(adir, "state", asid + ".json")), "direct_agents").includes(agent as string);
      }
      const sid = this.event.session_id;
      const tid = this.event.turn_id;
      if (!validId(sid) || !validId(tid)) return false;
      const dir = this.guardDirectory;
      if (dir === null) return false;
      const state = readJson(join(dir, "state", sid + ".json"));
      return directTurns(state).includes(tid as string);
    } catch {
      return false;
    }
  }

  /**
   * Grok: the recorded `subagent_start` of the subagent whose own session id is `agent`, or null.  Read-only; any
   * problem (bad id, no state dir, unreadable file) means "no record".
   */
  agentEntry(agent: unknown): AgentEntry | null {
    try {
      const dir = this.guardDirectory;
      if (dir === null || !validId(agent)) return null;
      const entries = agentEntries(readJson(join(dir, "state", GROK_AGENTS_FILE + ".json")));
      for (let i = entries.length - 1; i >= 0; i--) if (entries[i].id === agent) return entries[i];
    } catch {
      return null;
    }
    return null;
  }

  /**
   * Grok: a tool event under a recorded subagent's session id is that subagent's call, whatever its own payload says
   * (a generic subagent may carry no `subagentType`).  Fills `is_subagent` and a missing role.
   */
  resolveMappedAgent(): void {
    const entry = this.agentEntry(this.event.session_id);
    if (entry === null) return;
    this.event = { ...this.event, is_subagent: true };
    if (!this.event.role) this.event.role = entry.role || null;
  }

  /**
   * Grok `subagent_start`: record subagent id -> {main session, role, direct flag of main's current turn}.  Silent and
   * best effort: without a record the subagent is judged by its own payload and `#direct` is not available.
   */
  private registerAgent(): void {
    try {
      const sid = this.event.session_id;
      const agent = this.event.agent_id;
      const dir = this.guardDirectory;
      if (!validId(sid) || !validId(agent) || dir === null) return;
      const direct = readJson(join(dir, "state", sid + ".json")).direct === true;
      const path = join(dir, "state", GROK_AGENTS_FILE + ".json");
      withStateLock(
        join(dir, "state", GROK_AGENTS_FILE + ".tslock"),
        () => {
          const entries = agentEntries(readJson(path)).filter((e) => e.id !== agent);
          entries.push({ id: agent as string, session: sid as string, role: this.event.role || "", direct });
          writeJson(path, { agents: entries.slice(-GROK_AGENTS_MAX) });
          return none(this.mode);
        },
        () => none(this.mode),
      );
    } catch {
      /* best effort */
    }
  }

  // -- agy: main vs subagent by conversation order ---------------------------
  private agyPaths(): { record: string; lock: string } | null {
    const dir = this.guardDirectory;
    if (dir === null) return null;
    return { record: join(dir, "state", AGY_RECORD_FILE + ".json"), lock: join(dir, "state", AGY_RECORD_FILE + ".tslock") };
  }

  /** The recorded conversation `cid`, or null (no record, bad id, no state dir: all mean "main").  Read-only. */
  agyConversation(cid: unknown): AgyConversation | null {
    try {
      const paths = this.agyPaths();
      if (paths === null || !validId(cid)) return null;
      const { conversations } = agyRecord(readJson(paths.record));
      for (let i = conversations.length - 1; i >= 0; i--) if (conversations[i].id === cid) return conversations[i];
    } catch {
      return null;
    }
    return null;
  }

  /** PreToolUse of invoke_subagent: one pending entry per listed subagent.  Silent, best effort. */
  private agyPushPending(): void {
    try {
      const cid = this.event.session_id;
      const paths = this.agyPaths();
      if (paths === null || !validId(cid)) return;
      const roles = this.event.dispatched_roles && this.event.dispatched_roles.length > 0 ? this.event.dispatched_roles : [""];
      withStateLock(
        paths.lock,
        () => {
          const record = agyRecord(readJson(paths.record));
          const now = Date.now();
          const pending = record.pending.filter((e) => now - e.ts <= AGY_PENDING_TTL_MS);
          for (const role of roles) {
            pending.push({ dispatcher: cid as string, role: typeof role === "string" ? role : "", workspace: this.event.workspace || "", ts: now });
          }
          writeJson(paths.record, { conversations: record.conversations, pending: pending.slice(-AGY_RECORD_MAX) });
          return none(this.mode);
        },
        () => none(this.mode),
      );
    } catch {
      /* best effort */
    }
  }

  /** write for a shoal write role or an allowlisted type, unknown for no role name, else nonwrite. */
  private agyClass(role: string): string {
    if (!role) return "unknown";
    return roleAccess(role) === "write" || writeAgentAllowed(role, this.env) ? "write" : "nonwrite";
  }

  /**
   * SessionStart of an unseen conversation: a subagent when a dispatch is pending (oldest first, preferring the same
   * workspace), else a main conversation.  The role is known only when every candidate names the same one; otherwise the
   * class is recorded when all candidates share it, else "unknown".  A write class releases the dispatcher's pending
   * write dispatch; a verify role counts as a check.
   */
  private agySessionStart(): GuardResult {
    const cid = this.event.session_id;
    const paths = this.agyPaths();
    if (!validId(cid)) return this.result("skip", { skip: "invalid_id" });
    if (paths === null) return this.result("skip", { skip: "state_unavailable" });
    let entry: AgyConversation | null = null;
    let known = false;
    const outcome = withStateLock(
      paths.lock,
      () => {
        const record = agyRecord(readJson(paths.record));
        if (record.conversations.some((c) => c.id === cid)) {
          known = true;
          return none(this.mode);
        }
        const now = Date.now();
        const pending = record.pending.filter((e) => now - e.ts <= AGY_PENDING_TTL_MS);
        const ws = this.event.workspace || "";
        const sameWs = pending.filter((e) => ws !== "" && e.workspace === ws);
        const cands = sameWs.length > 0 ? sameWs : pending;
        if (cands.length > 0) {
          const roles = cands.map((e) => e.role);
          const role = new Set(roles).size === 1 ? roles[0] : "";
          const classes = new Set(roles.map((r) => this.agyClass(r)));
          const cls = classes.size === 1 ? [...classes][0] : "unknown";
          const taken = cands[0];
          pending.splice(pending.indexOf(taken), 1);
          entry = { id: cid as string, kind: "sub", role, cls, dispatcher: taken.dispatcher };
        } else {
          entry = { id: cid as string, kind: "main", role: "", cls: "", dispatcher: "" };
        }
        const ok = writeJson(paths.record, { conversations: [...record.conversations, entry].slice(-AGY_RECORD_MAX), pending });
        return ok ? none(this.mode) : this.result("skip", { skip: "state_write_failed" });
      },
      (reason) => this.result("skip", { skip: reason }),
    );
    if (known) return none(this.mode);
    if (entry === null || outcome.decision === "skip") return outcome;
    const made = entry as AgyConversation;
    if (made.kind === "main") return this.result("state", { rule: "conversation_main" });
    if (made.cls === "write") {
      this.event = { ...this.event, session_id: made.dispatcher };
      return this.releasePending(made.dispatcher, null, null);
    }
    if (roleAccess(made.role) === "verify") {
      this.event = { ...this.event, session_id: made.dispatcher };
      this.noteVerifyStarted();
    }
    return this.result("state", { rule: "conversation_sub", note: "class_" + made.cls });
  }

  /**
   * agy: the result for SessionStart and for a subagent conversation's events; null = judge as main (a conversation
   * without a record is main).  The adapter's own `is_subagent` is never used on this host.
   */
  agyRoute(): GuardResult | null {
    const { kind, tool_kind: toolKind } = this.event;
    if (kind === "session_start") return this.agySessionStart();
    if (kind === "tool" && toolKind === "dispatch") this.agyPushPending();
    const rec = this.agyConversation(this.event.session_id);
    if (rec === null || rec.kind !== "sub") {
      this.event = { ...this.event, is_subagent: false };
      return null;
    }
    if (kind !== "tool") return none(this.mode); // a subagent's invocation boundary or stop is not main's
    if (toolKind === "dispatch") return this.result("skip", { rule: "LEAF", skip: "leaf_dispatch_not_enforced" });
    this.event = { ...this.event, is_subagent: true, role: rec.role || null, conv_class: rec.cls };
    return this.subagent();
  }

  // -- completion check (B2, B3) --------------------------------------------
  /** State and lock file of this event's session for a silent state update, or null. */
  private checkPaths(wantedTurn: string | null): { statePath: string; lockPath: string } | null {
    const sid = this.event.session_id;
    if (!validId(sid) || (wantedTurn != null && !validId(wantedTurn))) return null;
    const dir = this.guardDirectory;
    if (dir === null) return null;
    return { statePath: join(dir, "state", sid + ".json"), lockPath: join(dir, "state", sid + ".tslock") };
  }

  /**
   * B2: main ran a plain foreground shell call.  When the turn is changed and unchecked, mark it checked.
   * Cheap by construction: hosts outside STOP_HOSTS, SHOAL_GUARD_STOP=off and a missing or invalid id return at
   * once; otherwise one unlocked read of the state file, and the lock and the write only happen when the turn is
   * changed and not yet checked.  Never logs.
   */
  private noteCheck(ran = false, counts = true): void {
    if (!stopEnabled(this.host, this.env)) return;
    const tid = this.event.turn_id;
    const paths = this.checkPaths(tid);
    if (paths === null) return;
    // `ran`: the PostToolUse of that call; it also records `post_seen`, which turns the PreToolUse path off.
    const pendingCheck = (state: Record<string, unknown>): boolean => {
      if (!counts) return false; // a write or declaration: not a check itself, but its PostToolUse still proves the hook fires
      if (!ran && POST_HOSTS.has(this.host) && state.post_seen === true) return false;
      return state.changed === true && state.checked !== true && (tid == null || state.turn_id === tid);
    };
    const needsWrite = (state: Record<string, unknown>): boolean =>
      pendingCheck(state) || (ran && Object.keys(state).length > 0 && state.post_seen !== true);
    if (!needsWrite(readJson(paths.statePath))) return;
    withStateLock(
      paths.lockPath,
      () => {
        const state = readJson(paths.statePath);
        if (needsWrite(state)) {
          if (ran) state.post_seen = true;
          if (pendingCheck(state)) state.checked = true;
          writeJson(paths.statePath, state);
        }
        return none(this.mode);
      },
      () => none(this.mode),
    );
  }

  /** B2 on claude: the SubagentStart of a verify-level role counts as a check, like its dispatch call. */
  private noteVerifyStarted(): void {
    if (!stopEnabled(this.host, this.env)) return;
    const paths = this.checkPaths(null);
    if (paths === null) return;
    withStateLock(
      paths.lockPath,
      () => {
        const state = readJson(paths.statePath);
        if (state.changed === true && state.checked !== true) {
          state.checked = true;
          writeJson(paths.statePath, state);
        }
        return none(this.mode);
      },
      () => none(this.mode),
    );
  }

  /**
   * B3: the main session is about to end its turn.  Blocks once per turn when files changed and nothing checked
   * them (see hooks/shoal_guard.py); every other path has no opinion (fail open).
   */
  private stop(): GuardResult {
    const event = this.event;
    if (!stopEnabled(this.host, this.env)) return none(this.mode);
    const flag = event.stop_hook_active;
    if (flag === true) return none(this.mode); // the host says this stop is the retry after a block
    const conv = CONVERSATION_HOSTS.has(this.host);
    if (conv && event.fully_idle !== true) return none(this.mode); // agy: only the stop that leaves the whole session idle ends main's turn
    const sid = event.session_id;
    const tid = event.turn_id;
    if (sid == null || (tid == null && !conv)) return this.result("skip", { skip: "missing_id" }); // agy's Stop carries no turn: the state's turn is used
    if (!validId(sid) || (tid != null && !validId(tid))) return this.result("skip", { skip: "invalid_id" });
    if (flag !== false) return this.result("skip", { skip: "bad_payload" });
    const dir = this.guardDirectory;
    if (dir === null) return this.result("skip", { skip: "state_unavailable" });
    const statePath = join(dir, "state", sid + ".json");
    const due = (state: Record<string, unknown>): boolean =>
      (tid == null || state.turn_id === tid) && (!conv || typeof state.turn_id === "string") && state.changed === true && state.checked !== true && state.stop_blocked !== true;
    if (!due(readJson(statePath))) return none(this.mode); // other turn, no change, checked or already blocked
    return withStateLock(
      join(dir, "state", sid + ".tslock"),
      () => {
        const state = readJson(statePath);
        if (!due(state)) return none(this.mode);
        if (this.mode !== "enforce" || !stopBlocks(this.host, this.env)) {
          return this.result("would_block", { rule: "STOP", note: "unverified_change" });
        }
        state.stop_blocked = true;
        // without the flag a block could repeat: do not block
        if (!writeJson(statePath, state)) return this.result("skip", { skip: "state_write_failed" });
        return this.result("block", { rule: "STOP", reason: text(this.env, "STOP"), note: "unverified_change" });
      },
      (reason) => this.result("skip", { skip: reason }),
    );
  }

  /**
   * B2 on claude and codex: PostToolUse of a main-session shell call, i.e. the call really ran.  A plain foreground
   * call (neither a declaration nor a file write) marks the turn checked; any such event records `post_seen`.
   * It never decides anything.
   */
  private postShell(): GuardResult {
    if (POST_HOSTS.has(this.host)) {
      const plain = parseDeclaration(this.event.command) === null && this.shellWriteTarget() === null;
      this.noteCheck(true, plain);
    }
    return none(this.mode);
  }

  // -- main session ---------------------------------------------------------
  main(): GuardResult {
    const event = this.event;
    if (event.kind === "subagent_start") return this.subagentStart();
    if (event.kind === "stop") return this.stop();
    if (event.kind === "post_shell") return this.postShell();
    const isBoundary = event.kind === "prompt" || event.kind === "turn_boundary";
    let toolKind = event.tool_kind;
    if (event.kind === "tool" && toolKind === "background_shell" && !DENY_MAIN_HOSTS.has(this.host)) {
      toolKind = null; // G4 exists on claude only
    }
    if (event.kind === "tool" && toolKind === "shell") {
      // A foreground shell call that is neither a declaration nor a file write has no opinion, and
      // touches no log.  `declare` hosts read declarations and judge writes (G5);
      // `strict` only judges writes (a declaration is an ordinary no-op there); `classified` judges
      // writes on claude only (v3.1.0); `off` has no G5.
      const declaration = parseDeclaration(event.command) !== null;
      const writeTarget = this.shellWriteTarget();
      if (this.r1 === "declare") {
        if (!declaration && writeTarget === null) toolKind = null;
      } else if (this.r1 === "strict") {
        if (writeTarget === null) toolKind = null;
      } else if (this.r1 !== "classified" || !DENY_MAIN_HOSTS.has(this.host) || writeTarget === null) {
        toolKind = null;
      }
      // B2: a plain foreground call after a change counts as a check.
      if (toolKind === null && writeTarget === null && !declaration) this.noteCheck();
    }
    if (
      event.kind === "tool" &&
      toolKind !== "edit" &&
      toolKind !== "dispatch" &&
      toolKind !== "background_shell" &&
      toolKind !== "shell"
    ) {
      return none(this.mode);
    }
    const sid = event.session_id;
    const tid = event.turn_id;
    if (sid == null) return this.result("skip", { skip: "missing_id" });
    if (!validId(sid)) return this.result("skip", { skip: "invalid_id" });
    const composed = COMPOSED_TURN_HOSTS.has(this.host);
    const turnOptional = event.kind === "tool" && STATE_TURN_HOSTS.has(this.host);
    const keepTurn = event.kind === "prompt" && PROMPT_KEEP_HOSTS.has(this.host);
    if (tid == null && !turnOptional && !keepTurn) return this.result("skip", { skip: "missing_id" });
    if (tid != null && !validId(tid, composed)) return this.result("skip", { skip: "invalid_id" });
    const dir = this.guardDirectory;
    if (dir === null) return this.result("skip", { skip: "state_unavailable" });
    const statePath = join(dir, "state", sid + ".json");

    return withStateLock(
      join(dir, "state", sid + ".tslock"),
      () => this.locked(isBoundary, keepTurn && tid == null, tid, statePath, dir),
      (reason) => this.result("skip", { skip: reason }),
    );
  }

  /**
   * Prompt event: update the session's fast flag (`#fast` on, `#strict` off, otherwise unchanged) and return whether
   * this turn counts as `#direct` (its own token only; fast mode does not release edits).
   */
  private promptDirect(prior: Record<string, unknown>): boolean {
    const sw = this.event.fast;
    this.fastState = sw === "on" || (prior.fast === true && sw !== "off");
    if (this.fastState) this.fast = true;
    return this.event.direct === true;
  }

  /** The state read-modify-write; the caller holds the per-session lock. */
  private locked(isBoundary: boolean, keep: boolean, tid: string | null, statePath: string, dir: string): GuardResult {
    const event = this.event;
    if (isBoundary) {
      let next: StateFile;
      if (keep) {
        // M1: id-less prompt.  Clear the unlock, keep turn and edits; no state, nothing to do.
        const prior = readJson(statePath);
        if (Object.keys(prior).length === 0) return this.result("skip", { skip: "missing_id" });
        let turns = directTurns(prior);
        const direct = this.promptDirect(prior);
        if (direct && typeof prior.turn_id === "string") {
          turns = [...turns, prior.turn_id].slice(-DIRECT_TURNS_MAX);
        }
        next = {
          turn_id: typeof prior.turn_id === "string" ? prior.turn_id : null,
          dispatched: false,
          advised: false,
          edited: Array.isArray(prior.edited) ? (prior.edited as string[]) : [],
          direct,
          declared: false,
          pending: 0,
          changed: false,
          checked: false,
          stop_blocked: false,
        };
        if (turns.length > 0) next.direct_turns = turns;
        if (this.fastState) next.fast = true;
        carryAgents(next, prior);
      } else {
        const priorState = readJson(statePath);
        let turns = directTurns(priorState);
        const direct = this.promptDirect(priorState);
        if (direct && typeof tid === "string") turns = [...turns, tid].slice(-DIRECT_TURNS_MAX);
        next = {
          turn_id: tid,
          dispatched: false,
          advised: false,
          edited: [],
          direct,
          declared: false,
          pending: 0,
          changed: false,
          checked: false,
          stop_blocked: false,
        };
        if (turns.length > 0) next.direct_turns = turns;
        if (this.fastState) next.fast = true;
        carryAgents(next, priorState);
      }
      if (!writeJson(statePath, next)) return this.result("skip", { skip: "state_write_failed" });
      return this.result("state");
    }

    let prior = readJson(statePath);
    const keptTurns = directTurns(prior);
    const priorState = prior;
    if (tid != null && prior.turn_id !== tid) prior = {};
    const edited = Array.isArray(prior.edited) ? (prior.edited as string[]) : [];
    const state: StateFile = {
      turn_id: tid != null ? tid : ((prior.turn_id as string | undefined) ?? null),
      dispatched: prior.dispatched === true,
      advised: prior.advised === true,
      edited,
      direct: prior.direct === true, // this turn's prompt carried #direct
      declared: prior.declared === true, // main declared direct work this turn (M3)
      pending: pendingCount(prior), // write dispatches whose role has not started yet (M11)
      changed: prior.changed === true, // B2: a change this turn (see markChanged)
      checked: prior.checked === true, // B2: a check after the latest change
      stop_blocked: prior.stop_blocked === true, // B3: this turn's one block is spent
    };
    if (keptTurns.length > 0) state.direct_turns = keptTurns; // E1: turns that carried #direct
    if (priorState.fast === true) {
      state.fast = true; // fast mode lasts for the session (set by #fast, cleared by #strict)
      this.fast = true;
    }
    carryAgents(state, priorState); // codex: agents released by #direct / already counted as started

    if (event.tool_kind === "dispatch") {
      const listed = CONVERSATION_HOSTS.has(this.host) ? event.dispatched_roles : null;
      let writes = 1;
      let access: string | null;
      if (listed != null) { // agy: one pending start per listed write role
        writes = listed.filter((r) => roleAccess(r) === "write").length;
        access = writes > 0 ? "write" : listed.some((r) => roleAccess(r) === "verify") ? "verify" : null;
      } else {
        access = roleAccess(event.dispatched_role);
      }
      if (access === "write") {
        if (START_UNLOCK_HOSTS.has(this.host)) {
          state.pending += writes; // released by the role's SubagentStart; the call itself is allowed
          writeJson(statePath, state);
          return this.result("allow", { rule: "dispatch_pending" });
        }
        state.dispatched = true;
        markChanged(state);
        writeJson(statePath, state);
      } else if (access === "verify") {
        state.checked = true; // B2: a verify-level role was dispatched
        writeJson(statePath, state);
      }
      return this.result("allow", { rule: "dispatch" });
    }
    if (event.tool_kind === "background_shell") return this.backgroundShell(state);
    if (event.tool_kind === "shell") return this.shell(state, statePath, dir);
    return this.edit(state, statePath, dir);
  }

  /**
   * M11: a role has started.  A write-level role of the main session's session releases one pending write
   * dispatch and unlocks the turn; any other start changes nothing.  The event is tied to the main session by
   * session id; a `prompt_id` that differs from the guard's current turn still releases and the log line says
   * so (skip_reason prompt_id_mismatch).  Bad ids fail open with a skip record.
   *
   * Codex (AGENT_KEYED_HOSTS): the started agent's own turn_id says nothing about main's turn, so it is not
   * compared; the agent is released from E1 when main's current turn carried `#direct` (`direct_agents`), and a write
   * role counts once per agent_id (`started_agents`).
   */
  private subagentStart(): GuardResult {
    const event = this.event;
    const access = roleAccess(event.role);
    if (MAPPED_HOSTS.has(this.host)) this.registerAgent();
    if (AGENT_KEYED_HOSTS.has(this.host)) this.noteDirectAgent();
    if (!START_UNLOCK_HOSTS.has(this.host) || (access !== "write" && access !== "verify")) return none(this.mode);
    if (access === "verify") {
      this.noteVerifyStarted();
      return none(this.mode);
    }
    return this.releasePending(event.session_id, event.turn_id, event.agent_id);
  }

  /** A write role has started: one pending dispatch of session `sid` is released, once per codex agent_id. */
  private releasePending(sid: string | null | undefined, tid: string | null | undefined, agent: string | null | undefined): GuardResult {
    const keyed = AGENT_KEYED_HOSTS.has(this.host);
    if (sid == null) return this.result("skip", { skip: "missing_id" });
    if (!validId(sid)) return this.result("skip", { skip: "invalid_id" });
    if (keyed && !validId(agent)) return this.result("skip", { skip: "missing_id" });
    const dir = this.guardDirectory;
    if (dir === null) return this.result("skip", { skip: "state_unavailable" });
    const statePath = join(dir, "state", sid + ".json");
    return withStateLock(
      join(dir, "state", sid + ".tslock"),
      () => {
        const state = readJson(statePath);
        const started = agentList(state, "started_agents");
        if (keyed && started.includes(agent as string)) return this.result("skip", { skip: "agent_already_started" });
        if (pendingCount(state) < 1) return this.result("skip", { skip: "start_without_pending" });
        const mismatch = typeof tid === "string" && !keyed && state.turn_id !== tid;
        state.pending = pendingCount(state) - 1;
        state.dispatched = true;
        state.changed = true; // B2: the write role has started, so the turn counts as changed
        state.checked = false;
        if (keyed) state.started_agents = [...started, agent as string].slice(-AGENTS_MAX);
        if (!writeJson(statePath, state)) return this.result("skip", { skip: "state_write_failed" });
        return this.result("state", { rule: "dispatch_started", skip: mismatch ? "prompt_id_mismatch" : undefined });
      },
      (reason) => this.result("skip", { skip: reason }),
    );
  }

  /**
   * Codex SubagentStart: when main's current turn carried `#direct`, remember the new agent_id as released (E1; the
   * last AGENTS_MAX).  Silent and best effort: any problem leaves the agent unreleased.
   */
  private noteDirectAgent(): void {
    try {
      const sid = this.event.session_id;
      const agent = this.event.agent_id;
      const dir = this.guardDirectory;
      if (!validId(sid) || !validId(agent) || dir === null) return;
      const statePath = join(dir, "state", sid + ".json");
      if (readJson(statePath).direct !== true) return;
      withStateLock(
        join(dir, "state", sid + ".tslock"),
        () => {
          const state = readJson(statePath);
          if (state.direct !== true) return none(this.mode);
          state.direct_agents = [...agentList(state, "direct_agents"), agent as string].slice(-AGENTS_MAX);
          writeJson(statePath, state);
          return none(this.mode);
        },
        () => none(this.mode),
      );
    } catch {
      /* best effort */
    }
  }

  /**
   * Codex: the first tool call of a write-level role's agent releases one pending dispatch when its SubagentStart has
   * not (hook not approved yet).  Cheap: one unlocked read decides.
   */
  private noteStartedByTool(): void {
    try {
      const sid = this.event.session_id;
      const agent = this.event.agent_id;
      const dir = this.guardDirectory;
      if (!validId(sid) || !validId(agent) || dir === null) return;
      const state = readJson(join(dir, "state", sid + ".json"));
      if (pendingCount(state) < 1 || agentList(state, "started_agents").includes(agent as string)) return;
      this.releasePending(sid, null, agent);
    } catch {
      /* best effort */
    }
  }

  /** G4: main starting a background shell.  Reads state only; nothing is recorded. */
  private backgroundShell(state: StateFile): GuardResult {
    if (this.env.SHOAL_GUARD_DIRECT === "1" || state.direct) return this.result("allow", { rule: "direct" });
    return this.result(this.mode === "enforce" ? "deny" : "would_deny", {
      rule: "G4",
      reason: text(this.env, "G4"),
    });
  }

  /**
   * G5: the first non-exempt file that main's shell command writes (UNKNOWN_TARGET or the raw text
   * when its value is not known), or null.  `/dev/...`, exempt paths and nothing else are skipped;
   * the check reads no state.
   */
  private shellWriteTarget(outsideRepoOk = false): string | null {
    const command = this.event.command;
    if (typeof command !== "string" || command === "") return null;
    const cwd = this.event.cwd || process.cwd();
    const repo = outsideRepoOk ? repoUnderTest(cwd) : null; // verify roles (E1): a target outside the repo under test is free
    for (const raw of shellWriteTargets(command)) {
      const target = this.expandTarget(raw);
      if (target === null) return raw; // `$var`, `$(...)`, backticks: a redirect to a non-/dev target
      if (target === "/dev" || target.startsWith("/dev/")) continue;
      const resolved = resolvePath(target, cwd);
      if (isExempt(resolved, this.host, this.env, this.home)) continue;
      if (repo !== null && !under(resolved, repo)) continue;
      return raw;
    }
    return null;
  }

  /** Leading `~`, `$HOME`, `${HOME}`, `$TMPDIR`, `${TMPDIR}` expanded; null while unknown. */
  private expandTarget(raw: string): string | null {
    let target = raw;
    const tmp = this.env.TMPDIR ?? "";
    const bases: Array<[string, string]> = [
      ["~", this.home],
      ["$HOME", this.home],
      ["${HOME}", this.home],
      ["$TMPDIR", tmp],
      ["${TMPDIR}", tmp],
    ];
    for (const [prefix, base] of bases) {
      if (target === prefix || target.startsWith(prefix + "/")) {
        if (base === "" || !isAbsolute(base)) return null;
        target = base + target.slice(prefix.length);
        break;
      }
    }
    return target.includes("$") || target.includes("`") ? null : target;
  }

  /**
   * A main-session foreground shell call: a declaration (`declare` mode) or G5, R1 for a command that
   * writes a file.  A shell write is never recorded as an edit, so R2's count is unaffected; only a
   * declaration changes state.
   */
  private shell(state: StateFile, statePath: string, dir: string): GuardResult {
    if (this.r1 === "declare") {
      const reason = parseDeclaration(this.event.command);
      if (reason !== null) {
        state.declared = true;
        if (!writeJson(statePath, state)) return this.result("skip", { skip: "state_write_failed" });
        return this.result("state", { rule: "declare", note: logReason(reason) });
      }
    }
    const file = this.shellWriteTarget() ?? undefined;
    if (this.env.SHOAL_GUARD_DIRECT === "1" || state.direct) {
      this.shellWrote(statePath, file);
      return this.result("allow", { rule: "direct", file });
    }
    if (state.dispatched) {
      this.shellWrote(statePath, file);
      return this.result("allow", { rule: "dispatched", file });
    }
    if (this.r1 === "strict") return this.shellR1(state, statePath, file, exitText(this.env, this.host, "STRICT"));
    if (this.r1 === "declare") {
      if (this.declared(state, dir)) {
        this.shellWrote(statePath, file);
        return this.result("allow", { rule: "declared", file });
      }
      return this.shellR1(state, statePath, file, exitText(this.env, this.host, "DECLARE"));
    }
    if (this.classified(state, dir) === null) {
      this.shellWrote(statePath, file);
      return this.result("allow", { rule: "uncounted", file });
    }
    return this.shellR1(state, statePath, file, text(this.env, "R1"));
  }

  /** R1 on a shell write: enforce denies (nothing was written); shadow lets it through and logs it. */
  private shellR1(state: StateFile, statePath: string, file: string | undefined, reason: string): GuardResult {
    if (this.mode === "enforce") return this.result("deny", { rule: "R1", reason, file });
    this.shellWrote(statePath, file);
    return this.result("would_deny", { rule: "R1", reason, file });
  }

  /** B2: an allowed shell write counts as a change once the chain has allowed it too (commitChange). */
  private shellWrote(statePath: string, file: string | undefined): void {
    if (file !== undefined) this.pendingChange = statePath;
  }

  /** The role in this turn's classification file, or null (no, stale or unreadable file). */
  private turnRole(state: StateFile, dir: string): string | null {
    const tid = state.turn_id; // effective turn (agy tool events may omit it)
    if (tid === null) return null;
    const turn = readJson(join(dir, "turns", String(this.event.session_id) + ".json"));
    const turnId = "turn_id" in turn ? turn.turn_id : turn.prompt_id;
    const role = turnId === tid ? turn.role : null;
    return typeof role === "string" ? role : null;
  }

  /** The turn's `judgment` / `mechanical` classification, or null (no or stale classifier file). */
  private classified(state: StateFile, dir: string): string | null {
    const role = this.turnRole(state, dir);
    return role !== null && Object.hasOwn(CLASSIFIED_ROLE, role) ? role : null;
  }

  /**
   * `declare` mode: main declared direct work this turn, or the optional classification file says
   * `parent_local` (M5).  Any other role, or no file, changes nothing.
   */
  private declared(state: StateFile, dir: string): boolean {
    return state.declared || this.turnRole(state, dir) === "parent_local";
  }

  private edit(state: StateFile, statePath: string, dir: string): GuardResult {
    const rawPaths = (this.event.paths ?? []).filter((p) => typeof p === "string" && p !== "");
    if (rawPaths.length === 0) return this.result("skip", { skip: "no_path" });
    const cwd = this.event.cwd || process.cwd();
    const resolved = rawPaths.map((p) => resolvePath(p, cwd));
    const edited: string[] = [...state.edited];
    const direct = this.env.SHOAL_GUARD_DIRECT === "1" || state.direct;
    const limit = maxFiles(this.env);
    const declare = this.r1 === "declare";
    const strict = this.r1 === "strict";
    let classified: string | null = null;
    let declared = false;
    if (!direct && !state.dispatched) {
      if (declare) declared = this.declared(state, dir);
      else if (this.r1 === "classified") classified = this.classified(state, dir);
    }

    let firstRule = "exempt";
    let adviseRule: string | null = null;
    let denyR1 = false;
    for (const [index, path] of resolved.entries()) {
      if (isExempt(path, this.host, this.env, this.home)) continue;
      let rule: string;
      if (direct) rule = "direct";
      else if (state.dispatched) rule = "dispatched";
      else {
        rule = declared ? "declared" : "count";
        let fired: string | null = null;
        if (classified || strict || (declare && !declared)) fired = "R1";
        else if (!edited.includes(path) && (limit === null || edited.length >= limit)) {
          if (limit === null) return this.result("skip", { skip: "invalid_config" });
          fired = "R2";
        }
        // G1: R1 denies on claude; everywhere else R1 and R2 only remind and the edit goes ahead.
        if (fired === "R1" && (declare || strict || DENY_MAIN_HOSTS.has(this.host))) denyR1 = true;
        else if (fired !== null && adviseRule === null) adviseRule = fired;
      }
      if (firstRule === "exempt") firstRule = rule;
      if (!edited.includes(path)) edited.push(path);
    }
    if (firstRule === "exempt") return this.result("allow", { rule: firstRule, file: rawPaths[0] });
    if (denyR1 && this.mode === "enforce") {
      return this.result("deny", { rule: "R1", reason: strict || declare ? exitText(this.env, this.host, strict ? "STRICT" : "DECLARE") : text(this.env, "R1"), file: rawPaths[0] });
    }
    state.edited = edited;
    this.pendingChange = statePath; // B2: an allowed, non-exempt edit (shadow's would_deny included) is a change
    const notify =
      adviseRule !== null && !state.advised && this.mode === "enforce" && ADVISE_OUTPUT_HOSTS.has(this.host);
    if (notify) state.advised = true; // the one reminder of this turn is spent
    writeJson(statePath, state);
    // shadow: the edit goes ahead, the log says what enforce would have done
    if (denyR1) return this.result("would_deny", { rule: "R1", file: rawPaths[0] });
    if (adviseRule === null) return this.result("allow", { rule: firstRule, file: rawPaths[0] });
    return this.result("advise", {
      rule: adviseRule,
      reason: notify
        ? text(this.env, "ADVISE", { n: edited.length, tool: DISPATCH_NAME[this.host] ?? "the dispatch tool" })
        : undefined,
      file: rawPaths[0],
      notify,
    });
  }
}

/** Allowed writes whose "the turn changed" mark waits for the chain's verdict, keyed by shoal's own result. */
const pendingChanges = new WeakMap<GuardResult, string>();

/**
 * B2: count the write `result` allowed as a change.  applyChain calls it only when the final decision, chain
 * included, lets the write through (issue #6).  Best effort: a failed write only loses the record.
 */
export function commitChange(result: GuardResult): void {
  const statePath = pendingChanges.get(result);
  if (statePath === undefined) return;
  pendingChanges.delete(result);
  withStateLock(
    statePath.replace(/\.json$/, ".tslock"),
    () => {
      const state = readJson(statePath) as StateFile;
      markChanged(state);
      writeJson(statePath, state);
      return result;
    },
    () => result,
  );
}

/** Decide on a normalized event.  Throws only on programming/OS errors (caller fails open). */
export function evaluate(event: GuardEvent, env: Env, home: string): GuardResult {
  const guard = new Guard(event, env, home);
  const result = decide(guard, event, env);
  if (guard.pendingChange !== null) pendingChanges.set(result, guard.pendingChange);
  return result;
}

function decide(guard: Guard, event: GuardEvent, env: Env): GuardResult {
  if (guard.mode === "off") return none("off");
  if (event.kind === "post_tool" || event.kind === "session_end") return none(guard.mode); // chain-only events
  if (event.kind === "tool" && event.tool_kind === "dispatch" && !event.is_subagent && lanesEnabled(env)) {
    const lane = guard.laneRule();
    if (lane !== null) return lane;
  }
  if (CONVERSATION_HOSTS.has(guard.host)) {
    const routed = guard.agyRoute();
    if (routed !== null) return routed;
    event = guard.event;
  } else if (MAPPED_HOSTS.has(guard.host) && event.kind === "tool") {
    guard.resolveMappedAgent();
    event = guard.event;
  }
  if (event.is_subagent) {
    if (ROLE_AWARE_HOSTS.has(guard.host) && event.kind === "tool") return guard.subagent();
    return none(guard.mode);
  }
  return guard.main();
}

/** Log a content-free skip record (fail-open paths in adapters).  Never throws. */
export function logSkip(host: string, env: Env, home: string, reason: string): void {
  try {
    const mode = resolveMode(host, env, home);
    if (mode === "off") return;
    appendLog(guardDir(env, home), { host, decision: "skip", skip_reason: reason, mode });
  } catch {
    // best effort
  }
}

const PATCH_HEADER_RE = /^\*\*\* (?:Add File|Update File|Delete File|Move to):[ \t]*(.+?)[ \t]*$/gm;

/** File paths named by apply_patch headers (same rule as the Python codex adapter). */
export function patchPaths(command: unknown): string[] {
  if (Array.isArray(command)) command = command.map(String).join("\n");
  if (typeof command !== "string") return [];
  return Array.from(command.matchAll(PATCH_HEADER_RE), (match) => match[1]);
}
