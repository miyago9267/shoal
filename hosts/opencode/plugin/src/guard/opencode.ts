/**
 * OpenCode adapter for the Shoal dispatch guard.
 *
 * Hooks: `chat.message` is the prompt/turn boundary (turn id = messageID), and
 * `tool.execute.before` throws an Error with the deny message to block a call (E0
 * verified).  Session ids are `ses_...` (underscores allowed).  A session whose
 * `parentID` is set is a subagent; its role is the session's `agent`.
 *
 * Every failure path is fail-open: an exception, a missing id, or a session lookup
 * that fails or hangs means "no opinion".
 */
import type { Hooks, PluginInput } from "@opencode-ai/plugin";
import { homedir } from "node:os";
import { evaluate, logSkip, patchPaths, type Env, type GuardEvent } from "./core.js";

const HOST = "opencode";
const SESSION_LOOKUP_TIMEOUT_MS = 3000;
const EDIT_TOOLS = new Set(["write", "edit", "multiedit"]);

type SessionInfo = { subagent: boolean; role: string | null };
type SessionClient = {
  session: { get(options: { path: { id: string } }): Promise<unknown> };
};

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function str(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function currentEnv(): Env {
  return process.env as Env;
}

function homeOf(env: Env): string {
  return env.HOME || homedir();
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("session lookup timed out")), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

/** apply_patch carries `patchText`; write/edit/multiedit carry `filePath`. */
export function editPaths(tool: string, args: unknown): string[] {
  const input = record(args);
  if (tool === "apply_patch") return patchPaths(input.patchText);
  const path = str(input.filePath);
  return path ? [path] : [];
}

export function createOpenCodeGuard(input: PluginInput): Pick<Hooks, "chat.message" | "tool.execute.before"> {
  const directory = str(record(input).directory) ?? process.cwd();
  const client = record(input).client as SessionClient | undefined;
  const sessions = new Map<string, SessionInfo>();
  // chat.message of a child session names its agent before any tool call: a lookup fallback.
  const messageAgent = new Map<string, string>();

  async function lookup(sessionID: string): Promise<SessionInfo> {
    const cached = sessions.get(sessionID);
    if (cached) return cached;
    if (!client?.session?.get) throw new Error("no session client");
    const response = record(await withTimeout(client.session.get({ path: { id: sessionID } }), SESSION_LOOKUP_TIMEOUT_MS));
    const session = record("data" in response ? response.data : response);
    if (str(session.id) === null) throw new Error("unexpected session payload");
    const subagent = str(session.parentID) !== null;
    const role = str(session.agent) ?? messageAgent.get(sessionID) ?? null;
    const info = { subagent, role };
    // a subagent without a known role is looked up again on the next call
    if (!subagent || role !== null) sessions.set(sessionID, info);
    return info;
  }

  function event(
    kind: GuardEvent["kind"],
    sessionID: string,
    turnID: string | null,
    info: SessionInfo,
    extra: Partial<GuardEvent> = {},
  ): GuardEvent {
    return {
      host: HOST,
      kind,
      session_id: sessionID,
      turn_id: turnID,
      cwd: directory,
      is_subagent: info.subagent,
      role: info.role,
      tool_name: null,
      tool_kind: null,
      paths: [],
      dispatched_role: null,
      ...extra,
    };
  }

  return {
    "chat.message": async (hookInput, output) => {
      const env = currentEnv();
      try {
        const sessionID = str(hookInput?.sessionID);
        if (sessionID === null) return logSkip(HOST, env, homeOf(env), "missing_id");
        const agent = str(hookInput?.agent);
        if (agent !== null) messageAgent.set(sessionID, agent);
        const info = await lookup(sessionID);
        const turnID = str(hookInput?.messageID) ?? str(record(output?.message).id);
        evaluate(event("prompt", sessionID, turnID, info), env, homeOf(env));
      } catch {
        logSkip(HOST, env, homeOf(env), "exception");
      }
    },

    "tool.execute.before": async (hookInput, output) => {
      const env = currentEnv();
      let reason: string | null = null;
      try {
        const tool = str(hookInput?.tool) ?? "";
        const sessionID = str(hookInput?.sessionID);
        const isEdit = tool === "apply_patch" || EDIT_TOOLS.has(tool);
        if (!isEdit && tool !== "task") return; // other tools never reach the guard
        if (sessionID === null) return logSkip(HOST, env, homeOf(env), "missing_id");
        const info = await lookup(sessionID);
        const turnID = null; // tool hooks carry no message id; the prompt boundary state is used
        const guardEvent = isEdit
          ? event("tool", sessionID, turnID, info, {
              tool_name: tool,
              tool_kind: "edit",
              paths: editPaths(tool, output?.args),
            })
          : event("tool", sessionID, turnID, info, {
              tool_name: tool,
              tool_kind: "dispatch",
              dispatched_role: str(record(output?.args).subagent_type),
            });
        const result = evaluate(guardEvent, env, homeOf(env));
        if (result.decision === "deny") reason = result.reason;
      } catch {
        logSkip(HOST, env, homeOf(env), "exception");
      }
      if (reason !== null) throw new Error(reason);
    },
  };
}
