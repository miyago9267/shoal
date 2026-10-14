/**
 * Guard chain: external members attached by configuration only (mirror of the chain section of
 * hooks/shoal_guard.py; docs/specs/modular-install S2).
 *
 * Config: the `chain` array of the installed module manifest, `${XDG_DATA_HOME:-~/.local/share}/shoal/modules.json`
 * (SHOAL_GUARD_CHAIN_FILE overrides the path).  Entry: `{name, command (argv), hosts, order}`.  After shoal's own
 * decision, each entry whose `hosts` holds this host runs in ascending `order`: argv exec without a shell, the raw
 * hook payload on stdin, cwd and env unchanged.  A member denies only by printing
 * `{"decision":"deny","reason":"..."}`; `{"decision":"allow"}` or no output allows.  A non-zero exit, a timeout
 * (5 s, SHOAL_GUARD_CHAIN_TIMEOUT_MS), unparseable or unknown output is fail-open with a chain_error /
 * chain_timeout log line.  The first deny wins and later members are not run; shoal's own deny/block skips the
 * chain.
 *
 * Unlike the core `evaluate`, this is async: `tool.execute.before` awaits it, so every member call adds its
 * latency to the tool call (no member configured: one failed file open).
 */
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { isAbsolute, join } from "node:path";
import { appendLog, guardDir, resolveMode, shortHash, type Env, type GuardEvent, type GuardResult } from "./core.js";

export const CHAIN_TIMEOUT_MS = 5000;
const CHAIN_MAX_TIMEOUT_MS = 60000;
const CHAIN_MAX_OUTPUT = 65536;
const MAX_MANIFEST_BYTES = 1024 * 1024;

export type ChainMember = { name: string; command: string[]; order: number };
type Outcome = "allow" | "deny" | "chain_error" | "chain_timeout";

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
    const { name, command, hosts, order = 0 } = entry as Record<string, unknown>;
    if (
      typeof name === "string" &&
      name !== "" &&
      Array.isArray(command) &&
      command.length > 0 &&
      command.every((a) => typeof a === "string" && a !== "") &&
      Array.isArray(hosts) &&
      hosts.includes(host) &&
      typeof order === "number" &&
      Number.isFinite(order)
    ) {
      members.push({ name, command: command as string[], order });
    }
  }
  return members.sort((a, b) => a.order - b.order); // Array.sort is stable
}

function callMember(command: string[], raw: Buffer, env: Env, timeoutMs: number): Promise<{ outcome: Outcome; reason: string }> {
  return new Promise((resolve) => {
    let settled = false;
    const chunks: Buffer[] = [];
    let size = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let child: ReturnType<typeof spawn> | undefined;
    const done = (outcome: Outcome, reason = "") => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ outcome, reason });
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
      if (body.decision === "allow") return done("allow");
      if (body.decision === "deny") {
        const reason = typeof body.reason === "string" ? body.reason.trim() : "";
        return done("deny", reason || "denied");
      }
      return done("chain_error");
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
    if (result.mode === "off" || result.decision === "deny" || result.decision === "block") return result;
    const host = event.host;
    const dir = guardDir(env, home);
    const mode = resolveMode(host, env);
    const log = (decision: string, member: string, ms?: number) =>
      appendLog(dir, {
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
      });
    const members = chainMembers(host, env, home);
    if (members === null) {
      log("chain_error", "manifest");
      return result;
    }
    if (members.length === 0) return result;
    const raw = Buffer.from(rawPayload ?? JSON.stringify(event), "utf8");
    const timeoutMs = chainTimeoutMs(env);
    for (const member of members) {
      const started = performance.now();
      const { outcome, reason } = await callMember(member.command, raw, env, timeoutMs);
      const ms = Math.floor(performance.now() - started);
      log(outcome.startsWith("chain_") ? outcome : `chain_${outcome}`, member.name, ms);
      if (outcome !== "deny") continue;
      if (event.kind !== "tool" && event.kind !== "stop") continue; // nothing to refuse on prompt/start events
      const base = event.kind === "tool" ? "deny" : "block";
      return {
        decision: mode === "enforce" ? base : `would_${base}`,
        rule: "chain",
        skip_reason: null,
        reason: `${member.name}: ${reason}`,
        mode,
      };
    }
    return result;
  } catch {
    return result;
  }
}
