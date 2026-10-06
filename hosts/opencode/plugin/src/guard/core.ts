/**
 * Shoal dispatch guard core (TypeScript port of hooks/shoal_guard.py).
 *
 * Decides on a normalized event only; the OpenCode adapter lives in ./opencode.ts.
 * Behaviour must stay identical to the Python core: both replay
 * tests/fixtures/guard_vectors.json.  The guard is a policy nudge, not a security
 * boundary (docs/specs/dispatch-enforcement/SPEC.md).
 *
 * `evaluate` throws only on programming or OS errors; callers fail open.
 */
import {
  closeSync,
  constants,
  fchmodSync,
  fstatSync,
  lstatSync,
  mkdirSync,
  openSync,
  readSync,
  readlinkSync,
  statSync,
  unlinkSync,
  writeSync,
} from "node:fs";
import { basename, dirname, isAbsolute, join, relative } from "node:path";

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
  kind: "prompt" | "turn_boundary" | "tool";
  session_id: string | null;
  turn_id: string | null;
  cwd: string | null;
  is_subagent: boolean;
  role: string | null;
  tool_name: string | null;
  tool_kind: "edit" | "dispatch" | "other" | null;
  paths: string[];
  dispatched_role: string | null;
};

export type GuardResult = {
  decision: string;
  rule: string | null;
  skip_reason: string | null;
  reason: string | null;
  mode: string;
};

type StateFile = { turn_id: string | null; dispatched: boolean; edited: string[] };
type LogRecord = Record<string, unknown>;

// Default mode per host.  E6: opencode is enforce (shadow evidence met); codex/grok stay shadow, agy is forced shadow.
const HOST_DEFAULT_MODE: Record<string, string> = {
  claude: "enforce",
  codex: "shadow",
  grok: "shadow",
  agy: "shadow",
  opencode: "enforce",
};
// Hosts that cannot tell main from subagent: enforce is never allowed (spec R5).
const FORCED_SHADOW_HOSTS = new Set(["agy"]);
// Hosts whose payload identifies the calling role: LEAF / VERIFY_EDIT apply (spec R6).
const ROLE_AWARE_HOSTS = new Set(["claude", "codex", "grok", "opencode"]);
// agy turn ids are composed `conversation:invocation`; its tool payload may not carry one.
const COMPOSED_TURN_HOSTS = new Set(["agy"]);
// Hosts whose tool hooks carry no turn id: the turn recorded at the prompt boundary is used
// (claude: after `/login` a resumed session has no prompt_id).
const STATE_TURN_HOSTS = new Set(["agy", "grok", "opencode", "claude"]);
// Hosts whose prompt event may lack a turn id: it clears `dispatched` and keeps turn and edits (M1).
const PROMPT_KEEP_HOSTS = new Set(["claude"]);
// Role-name namespaces accepted as the same role (K3).  Explicit allowlist only: any other
// `x:name` stays unknown, so it neither unlocks nor counts as a leaf/verify role.
const ROLE_NAMESPACES = ["shoal:"];

// role -> access level.  Keep in sync with ROLE_ACCESS in hooks/shoal_guard.py
// (tests/guard-vectors.test.ts compares the two tables).
export const ROLE_ACCESS: Record<string, string> = {
  scout: "read-only",
  "plan-verifier": "read-only",
  "security-reviewer": "read-only",
  Explore: "read-only",
  "mech-executor": "write",
  executor: "write",
  "security-executor": "write",
  "sol-executor": "write",
  verifier: "verify",
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

const CLASSIFIED_ROLE: Record<string, string> = {
  judgment: "executor",
  mechanical: "mech-executor",
};
const DISPATCH_NAME: Record<string, string> = {
  claude: "Agent",
  codex: "spawn_agent",
  grok: "spawn_subagent",
  agy: "invoke_subagent",
  opencode: "task",
};
const LOG_FIELDS = ["host", "event", "tool", "rule", "decision", "file", "skip_reason", "mode"];

const MESSAGES: Record<string, Record<string, string>> = {
  en: {
    R1:
      "Shoal dispatch guard: this turn was classified as work for `{role}`, so the main " +
      "session must not edit files directly. Dispatch `{role}` with {tool} (brief: scope, " +
      "stop condition, output cap); main only integrates and verifies. Once a write-level " +
      "role is dispatched, main edits for the rest of this turn are allowed. For a genuine " +
      "1-2 line fix, the user can restart the session with SHOAL_GUARD_DIRECT=1.",
    R2:
      "Shoal dispatch guard: the main session already edited {n} files this turn without " +
      "dispatching any agent. Hand multi-file changes to `executor` (needs judgment) or " +
      "`mech-executor` (fully specified mechanical change) with {tool}; once a write-level " +
      "role is dispatched, main edits for the rest of this turn are allowed. If the user " +
      "wants you to do it directly, they can restart the session with SHOAL_GUARD_DIRECT=1.",
    LEAF:
      "Shoal dispatch guard: subagents are leaf workers and must not dispatch other " +
      "agents. Finish the task yourself and report back to the parent.",
    VERIFY_EDIT:
      "Shoal dispatch guard: verify-level roles must not edit files with editing tools. " +
      "Report findings to the parent instead.",
  },
  "zh-TW": {
    R1:
      "Shoal dispatch guard：本輪被分類為 `{role}` 的工作，main session 不直接改檔。" +
      "請用 {tool} 派出 `{role}`（brief 寫清楚 scope、stop condition、output cap），" +
      "main 只負責整合與驗收；派出 write 等級 role 後，本輪 main 的編輯會自動放行。" +
      "若確實只是 1-2 行的小修，請使用者以 SHOAL_GUARD_DIRECT=1 重新啟動 session。",
    R2:
      "Shoal dispatch guard：main session 這一輪已經直接改了 {n} 個檔案，而且沒有派任何 agent。" +
      "多檔修改請用 {tool} 交給 `executor`（需要判斷）或 `mech-executor`" +
      "（規格完整的機械性修改）；派出 write 等級 role 後，本輪 main 的編輯會自動放行。" +
      "若使用者要你直接做，請他以 SHOAL_GUARD_DIRECT=1 重新啟動 session。",
    LEAF: "Shoal dispatch guard：subagent 是 leaf worker，不可再派其他 agent。請自己完成並回報給上層。",
    VERIFY_EDIT: "Shoal dispatch guard：verify 等級的 role 不可用編輯工具改檔，請把發現回報給上層。",
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeText(value: unknown): string | null {
  return typeof value === "string" ? value.slice(0, 200) : null;
}

/** Append one whitelisted record to guard.jsonl (1 MiB cap).  Never throws. */
export function appendLog(dir: string | null, record: LogRecord): void {
  if (dir === null) return;
  const line: Record<string, string> = { ts: new Date().toISOString() };
  for (const key of LOG_FIELDS) {
    let value = record[key];
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

/** Unset -> host default; an unrecognized value -> shadow (as the legacy guard did). */
export function resolveMode(host: string, env: Env): string {
  const raw = env.SHOAL_GUARD || env.PILOTFISH_GUARD || "";
  let mode: string;
  if (!raw) mode = HOST_DEFAULT_MODE[host] ?? "shadow";
  else mode = raw === "enforce" || raw === "shadow" || raw === "off" ? raw : "shadow";
  if (mode === "enforce" && FORCED_SHADOW_HOSTS.has(host)) mode = "shadow";
  return mode;
}

/** null when the configured value is not an integer (the guard then fails open). */
function maxFiles(env: Env): number | null {
  const raw = env.SHOAL_GUARD_MAX_FILES || env.PILOTFISH_GUARD_MAX_FILES || "2";
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

function none(mode: string): GuardResult {
  return { decision: "none", rule: null, skip_reason: null, reason: null, mode };
}

class Guard {
  readonly host: string;
  readonly mode: string;
  private dir: string | null = null;
  private dirTried = false;

  constructor(
    private readonly event: GuardEvent,
    private readonly env: Env,
    private readonly home: string,
  ) {
    this.host = String(event.host || "");
    this.mode = resolveMode(this.host, env);
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
    opts: { rule?: string; skip?: string; reason?: string; file?: string } = {},
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
    });
    return {
      decision,
      rule: opts.rule ?? null,
      skip_reason: opts.skip ?? null,
      reason: opts.reason ?? null,
      mode: this.mode,
    };
  }

  // -- subagent backstop (spec R6) ------------------------------------------
  subagent(): GuardResult {
    const { role, tool_kind: toolKind } = this.event;
    let rule: string | null = null;
    if (toolKind === "dispatch") rule = "LEAF";
    else if (toolKind === "edit" && roleAccess(role) === "verify") rule = "VERIFY_EDIT";
    if (rule === null) return none(this.mode);
    const first = this.event.paths?.[0];
    return this.result(this.mode === "enforce" ? "deny" : "would_deny", {
      rule,
      reason: text(this.env, rule),
      file: first,
    });
  }

  // -- main session ---------------------------------------------------------
  main(): GuardResult {
    const event = this.event;
    const isBoundary = event.kind === "prompt" || event.kind === "turn_boundary";
    if (event.kind === "tool" && event.tool_kind !== "edit" && event.tool_kind !== "dispatch") {
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

  /** The state read-modify-write; the caller holds the per-session lock. */
  private locked(isBoundary: boolean, keep: boolean, tid: string | null, statePath: string, dir: string): GuardResult {
    const event = this.event;
    if (isBoundary) {
      let next: StateFile;
      if (keep) {
        // M1: id-less prompt.  Clear the unlock, keep turn and edits; no state, nothing to do.
        const prior = readJson(statePath);
        if (Object.keys(prior).length === 0) return this.result("skip", { skip: "missing_id" });
        next = {
          turn_id: typeof prior.turn_id === "string" ? prior.turn_id : null,
          dispatched: false,
          edited: Array.isArray(prior.edited) ? (prior.edited as string[]) : [],
        };
      } else next = { turn_id: tid, dispatched: false, edited: [] };
      if (!writeJson(statePath, next)) return this.result("skip", { skip: "state_write_failed" });
      return this.result("state");
    }

    let prior = readJson(statePath);
    if (tid != null && prior.turn_id !== tid) prior = {};
    const edited = Array.isArray(prior.edited) ? (prior.edited as string[]) : [];
    const state: StateFile = {
      turn_id: tid != null ? tid : ((prior.turn_id as string | undefined) ?? null),
      dispatched: prior.dispatched === true,
      edited,
    };

    if (event.tool_kind === "dispatch") {
      if (roleAccess(event.dispatched_role) === "write") {
        state.dispatched = true;
        writeJson(statePath, state);
      }
      return this.result("allow", { rule: "dispatch" });
    }
    return this.edit(state, statePath, dir);
  }

  private edit(state: StateFile, statePath: string, dir: string): GuardResult {
    const rawPaths = (this.event.paths ?? []).filter((p) => typeof p === "string" && p !== "");
    if (rawPaths.length === 0) return this.result("skip", { skip: "no_path" });
    const cwd = this.event.cwd || process.cwd();
    const resolved = rawPaths.map((p) => resolvePath(p, cwd));
    const edited: string[] = [...state.edited];
    const direct = this.env.SHOAL_GUARD_DIRECT === "1";
    const limit = maxFiles(this.env);
    let classified: string | null = null;
    const tid = state.turn_id; // effective turn (agy tool events may omit it)
    if (!direct && !state.dispatched && tid !== null) {
      const turn = readJson(join(dir, "turns", String(this.event.session_id) + ".json"));
      const turnId = "turn_id" in turn ? turn.turn_id : turn.prompt_id;
      const role = turnId === tid ? turn.role : null;
      classified = typeof role === "string" && Object.hasOwn(CLASSIFIED_ROLE, role) ? role : null;
    }

    let firstRule = "exempt";
    for (const [index, path] of resolved.entries()) {
      if (isExempt(path, this.host, this.env, this.home)) continue;
      let rule: string;
      if (direct) rule = "direct";
      else if (state.dispatched) rule = "dispatched";
      else if (classified) {
        return this.deny("R1", rawPaths[index], edited.length, CLASSIFIED_ROLE[classified]);
      } else if (!edited.includes(path) && (limit === null || edited.length >= limit)) {
        if (limit === null) return this.result("skip", { skip: "invalid_config" });
        return this.deny("R2", rawPaths[index], edited.length, null);
      } else rule = "count";
      if (firstRule === "exempt") firstRule = rule;
      if (!edited.includes(path)) edited.push(path);
    }
    if (firstRule !== "exempt") {
      state.edited = edited;
      writeJson(statePath, state);
    }
    return this.result("allow", { rule: firstRule, file: rawPaths[0] });
  }

  private deny(rule: string, path: string, count: number, role: string | null): GuardResult {
    return this.result(this.mode === "enforce" ? "deny" : "would_deny", {
      rule,
      reason: text(this.env, rule, {
        n: count,
        role,
        tool: DISPATCH_NAME[this.host] ?? "the dispatch tool",
      }),
      file: path,
    });
  }
}

/** Decide on a normalized event.  Throws only on programming/OS errors (caller fails open). */
export function evaluate(event: GuardEvent, env: Env, home: string): GuardResult {
  const guard = new Guard(event, env, home);
  if (guard.mode === "off") return none("off");
  if (event.is_subagent) {
    if (ROLE_AWARE_HOSTS.has(guard.host) && event.kind === "tool") return guard.subagent();
    return none(guard.mode);
  }
  return guard.main();
}

/** Log a content-free skip record (fail-open paths in adapters).  Never throws. */
export function logSkip(host: string, env: Env, home: string, reason: string): void {
  try {
    const mode = resolveMode(host, env);
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
