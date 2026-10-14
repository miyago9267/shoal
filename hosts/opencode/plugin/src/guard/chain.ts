/**
 * Guard chain: external members attached by configuration only (mirror of the chain section of
 * hooks/shoal_guard.py; docs/specs/modular-install S2).
 *
 * Config: the `chain` array of the installed module manifest, `${XDG_DATA_HOME:-~/.local/share}/shoal/modules.json`
 * (SHOAL_GUARD_CHAIN_FILE overrides the path).  Entry: `{name, command (argv), hosts, order, events}`; `events`
 * (default ["PreToolUse"]) picks the events the member gets.  OpenCode forwards only PreToolUse (tool.execute.before)
 * today; the other events follow with shoal-guard M3.  After shoal's own decision, each subscribed entry whose
 * `hosts` holds this host runs in ascending `order`: argv exec without a shell, the raw hook payload on stdin, env
 * inherited plus SHOAL_GUARD_HOST and SHOAL_GUARD_EVENT.  A member denies only by printing
 * `{"decision":"deny","reason":"..."}`; `{"decision":"allow"}` or no output allows; an optional `context` string is
 * advisory (joined into the result, logged, never sent to the model on OpenCode); `member`/`version` are only
 * logged.  A non-zero exit, a timeout (5 s, SHOAL_GUARD_CHAIN_TIMEOUT_MS), unparseable or unknown output is
 * fail-open with a chain_error / chain_timeout log line.  The whole chain gets CHAIN_BUDGET_MS; a member that finds
 * it used up is skipped with chain_budget.  The first deny wins and later members are not run; shoal's own
 * deny/block skips the chain.  With the dispatch guard deselected in the manifest but members present, the chain
 * runs alone (chain-only).
 *
 * Unlike the core `evaluate`, this is async: `tool.execute.before` awaits it, so every member call adds its
 * latency to the tool call (no member configured: one failed file open).
 */
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { isAbsolute, join } from "node:path";
import { appendLog, guardDir, resolveMode, shortHash, type Env, type GuardEvent, type GuardResult } from "./core.js";

export const CHAIN_TIMEOUT_MS = 5000;
// The hosts' hook timeout is 10 s; the chain ends before it (margin 2 s).  Mirror of the Python constants.
export const CHAIN_BUDGET_MS = 10000 - 2000;
const CHAIN_MAX_TIMEOUT_MS = CHAIN_BUDGET_MS;
const CHAIN_MIN_SLICE_MS = 100;
const CHAIN_MAX_OUTPUT = 65536;
const CHAIN_MAX_CONTEXT = 8192;
export const CHAIN_EVENTS = ["PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionEnd", "Stop"];
const KIND_EVENT: Record<string, string> = {
  tool: "PreToolUse",
  post_shell: "PostToolUse",
  post_tool: "PostToolUse",
  prompt: "UserPromptSubmit",
  session_end: "SessionEnd",
  stop: "Stop",
};
const MAX_MANIFEST_BYTES = 1024 * 1024;

export type ChainMember = { name: string; command: string[]; order: number; events: string[] };
type Outcome = "allow" | "deny" | "chain_error" | "chain_timeout";
type Called = { outcome: Outcome; reason: string; context: string | null; report: string | null };

export function chainManifestPath(env: Env, home: string): string {
  const override = env.SHOAL_GUARD_CHAIN_FILE ?? "";
  if (override && isAbsolute(override)) return override;
  const xdg = env.XDG_DATA_HOME ?? "";
  const data = xdg && isAbsolute(xdg) ? xdg : join(home, ".local", "share");
  return join(data, "shoal", "modules.json");
}

export function chainTimeoutMs(env: Env): number {
  const value = Number.parseInt(env.SHOAL_GUARD_CHAIN_TIMEOUT_MS ?? "", 10);
  return Number.isInteger(value) && value > 0 && value <= CHAIN_MAX_TIMEOUT_MS ? value : CHAIN_TIMEOUT_MS;
}

/** The whole chain's time; SHOAL_GUARD_CHAIN_BUDGET_MS can only shorten it. */
export function chainBudgetMs(env: Env): number {
  const value = Number.parseInt(env.SHOAL_GUARD_CHAIN_BUDGET_MS ?? "", 10);
  return Number.isInteger(value) && value > 0 && value <= CHAIN_BUDGET_MS ? value : CHAIN_BUDGET_MS;
}

/** The canonical hook event a normalized event came from (null: not one a member can subscribe to). */
export function chainEventName(event: GuardEvent): string | null {
  const name = event.hook_event ?? KIND_EVENT[event.kind];
  return name !== undefined && CHAIN_EVENTS.includes(name) ? name : null;
}

/** Members for `host` in run order; [] when none; null when the manifest exists but cannot be read. */
export function chainMembers(host: string, env: Env, home: string): ChainMember[] | null {
  let doc: unknown;
  try {
    const text = readFileSync(chainManifestPath(env, home));
    doc = JSON.parse(text.subarray(0, MAX_MANIFEST_BYTES).toString("utf8"));
  } catch (error) {
    return (error as NodeJS.ErrnoException)?.code === "ENOENT" ? [] : null;
  }
  const entries = typeof doc === "object" && doc !== null ? (doc as Record<string, unknown>).chain : undefined;
  const members: ChainMember[] = [];
  for (const entry of Array.isArray(entries) ? entries : []) {
    if (typeof entry !== "object" || entry === null) continue;
    const { name, command, hosts, order = 0, events = ["PreToolUse"] } = entry as Record<string, unknown>;
    if (
      typeof name === "string" &&
      name !== "" &&
      Array.isArray(command) &&
      command.length > 0 &&
      command.every((a) => typeof a === "string" && a !== "") &&
      Array.isArray(hosts) &&
      hosts.includes(host) &&
      typeof order === "number" &&
      Number.isFinite(order) &&
      Array.isArray(events) &&
      events.every((e) => typeof e === "string")
    ) {
      members.push({ name, command: command as string[], order, events: (events as string[]).filter((e) => CHAIN_EVENTS.includes(e)) });
    }
  }
  return members.sort((a, b) => a.order - b.order); // Array.sort is stable
}

function callMember(command: string[], raw: Buffer, env: Env, timeoutMs: number): Promise<Called> {
  return new Promise((resolve) => {
    let settled = false;
    const chunks: Buffer[] = [];
    let size = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let child: ReturnType<typeof spawn> | undefined;
    const done = (outcome: Outcome, reason = "", context: string | null = null, report: string | null = null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ outcome, reason, context, report });
    };
    try {
      child = spawn(command[0], command.slice(1), { env: env as NodeJS.ProcessEnv, stdio: ["pipe", "pipe", "ignore"] });
    } catch {
      return done("chain_error");
    }
    timer = setTimeout(() => {
      child?.kill("SIGKILL");
      done("chain_timeout");
    }, timeoutMs);
    child.on("error", () => done("chain_error"));
    child.stdin?.on("error", () => undefined); // a member that never reads stdin
    child.stdout?.on("data", (chunk: Buffer) => {
      if (size < CHAIN_MAX_OUTPUT) chunks.push(chunk);
      size += chunk.length;
    });
    child.on("close", (code) => {
      if (code !== 0) return done("chain_error");
      const out = Buffer.concat(chunks).subarray(0, CHAIN_MAX_OUTPUT).toString("utf8").trim();
      if (out === "") return done("allow");
      let obj: unknown;
      try {
        obj = JSON.parse(out);
      } catch {
        return done("chain_error");
      }
      const body = typeof obj === "object" && obj !== null ? (obj as Record<string, unknown>) : {};
      if (body.decision !== "allow" && body.decision !== "deny") return done("chain_error");
      const context =
        typeof body.context === "string" && body.context.trim() !== "" ? body.context.trim().slice(0, CHAIN_MAX_CONTEXT) : null;
      const reported = [
        ["id", body.member],
        ["version", body.version],
      ]
        .filter(([, v]) => typeof v === "string" && v !== "")
        .map(([k, v]) => `${k}=${(v as string).slice(0, 60)}`)
        .join(" ");
      const report = reported === "" ? null : reported;
      if (body.decision === "allow") return done("allow", "", context, report);
      const reason = typeof body.reason === "string" ? body.reason.trim() : "";
      return done("deny", reason || "denied", context, report);
    });
    child.stdin?.end(raw);
  });
}

/**
 * Run the chain after shoal's own decision.  `rawPayload` is what members get on stdin (default: the event as
 * JSON).  Never throws: any failure leaves `result` unchanged.
 */
export async function applyChain(
  event: GuardEvent,
  result: GuardResult,
  env: Env,
  home: string,
  rawPayload?: string,
): Promise<GuardResult> {
  try {
    const started = performance.now();
    if (result.decision === "deny" || result.decision === "block") return result;
    const host = event.host;
    let mode = resolveMode(host, env, home);
    const members = chainMembers(host, env, home);
    const log = (decision: string, member: string, ms?: number, reason?: string) =>
      appendLog(guardDir(env, home), {
        host,
        event: event.kind,
        tool: event.tool_name,
        decision,
        rule: "chain",
        mode,
        session: shortHash(event.session_id),
        turn: shortHash(event.turn_id),
        member,
        ms: ms === undefined ? undefined : String(ms),
        reason,
      });
    if (result.mode === "off") {
      // Chain-only: the manifest switched the dispatch guard off for this host, but it has chain members; an
      // explicit SHOAL_GUARD=off still turns everything off.  The chain denies in the host's own mode.
      const own = resolveMode(host, env);
      if (own === "off" || members === null || members.length === 0) return result;
      mode = own;
      result = { ...result, mode };
    }
    if (members === null) {
      log("chain_error", "manifest");
      return result;
    }
    const name = chainEventName(event);
    const subscribed = members.filter((m) => name !== null && m.events.includes(name));
    if (subscribed.length === 0) return result;
    const raw = Buffer.from(rawPayload ?? JSON.stringify(event), "utf8");
    const memberEnv = { ...env, SHOAL_GUARD_HOST: host, SHOAL_GUARD_EVENT: name as string };
    const timeoutMs = chainTimeoutMs(env);
    const deadline = started + chainBudgetMs(env);
    const contexts: string[] = [];
    for (const member of subscribed) {
      const remaining = Math.floor(deadline - performance.now());
      if (remaining < CHAIN_MIN_SLICE_MS) {
        log("chain_budget", member.name, 0);
        continue;
      }
      const t0 = performance.now();
      const called = await callMember(member.command, raw, memberEnv, Math.min(timeoutMs, remaining));
      const ms = Math.floor(performance.now() - t0);
      const { outcome } = called;
      log(outcome.startsWith("chain_") ? outcome : `chain_${outcome}`, member.name, ms);
      if (called.report !== null) log("chain_report", member.name, undefined, called.report);
      if (called.context !== null) {
        log("chain_context", member.name);
        contexts.push(called.context);
      }
      if (outcome !== "deny") continue;
      // only a PreToolUse deny blocks (and a Stop block, as before); elsewhere it is logged only
      if ((name !== "PreToolUse" && name !== "Stop") || (event.kind !== "tool" && event.kind !== "stop")) continue;
      const base = event.kind === "tool" ? "deny" : "block";
      return {
        decision: mode === "enforce" ? base : `would_${base}`,
        rule: "chain",
        skip_reason: null,
        reason: `${member.name}: ${called.reason}`,
        mode,
        context: null,
      };
    }
    return { ...result, context: contexts.length > 0 ? contexts.join("\n") : null };
  } catch {
    return result;
  }
}
