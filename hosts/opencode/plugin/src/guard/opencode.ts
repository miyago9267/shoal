/**
 * OpenCode adapter for the Shoal dispatch guard.
 *
 * Hooks (evidence: tests/fixtures/opencode_guard_event_shapes.json, opencode 1.18.x):
 * - `chat.message` is the prompt/turn boundary (turn id = `output.message.id`); a standalone `#direct` in the
 *   main session's prompt text is the turn's direct flag.
 * - `event` `session.created` announces a child session (`parentID` = main session, `agent` = role).  That is
 *   the "role really started" signal (E3): a write-capable child releases the main session's pending write
 *   dispatch.  A failed dispatch creates no session and so never unlocks.  `client.session.get` is the fallback
 *   for a tool call from a session this adapter has not been told about.
 * - `tool.execute.before` throws an Error with the deny message to block a call.  `bash` is judged as a shell
 *   call, `write`/`edit`/`multiedit`/`apply_patch` as edits, `task` as a dispatch.
 *
 * Fail-open: an exception, a missing id, or a session lookup that fails or hangs (unknown session) means
 * "no opinion"; a content-free skip record is logged.
 *
 * Not attached: the turn-end completion check (E6).  The `event` hook returns void and cannot block, so
 * `session.idle` cannot hold a turn open (INSTALL.md, OpenCode section).
 */
import type { Hooks, PluginInput } from "@opencode-ai/plugin";
import { homedir } from "node:os";
import { evaluate, hasDirectToken, logSkip, patchPaths, type Env, type GuardEvent } from "./core.js";

const HOST = "opencode";
const SESSION_LOOKUP_TIMEOUT_MS = 3000;
const EDIT_TOOLS = new Set(["write", "edit", "multiedit"]);

type SessionInfo = {
  subagent: boolean;
  role: string | null;
  /** child sessions: the main session. */
  parentID: string | null;
  /** child sessions: the main turn that was current when the child was created. */
  turn: string | null;
};
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

export function createOpenCodeGuard(
  input: PluginInput,
): Pick<Hooks, "chat.message" | "tool.execute.before" | "event"> {
  const directory = str(record(input).directory) ?? process.cwd();
  const client = record(input).client as SessionClient | undefined;
  const sessions = new Map<string, SessionInfo>();
  // chat.message of a child session names its agent before any tool call: a lookup fallback.
  const messageAgent = new Map<string, string>();
  // main session -> id of its current turn (its latest chat.message)
  const mainTurn = new Map<string, string>();
  // child sessions whose start has already been reported to the core
  const started = new Set<string>();

  function startChild(childID: string, parentID: string, role: string | null, env: Env): void {
    const turn = mainTurn.get(parentID) ?? null;
    sessions.set(childID, { subagent: true, role, parentID, turn });
    if (started.has(childID)) return;
    started.add(childID);
    evaluate(
      {
        host: HOST,
        kind: "subagent_start",
        session_id: parentID,
        turn_id: null,
        cwd: directory,
        is_subagent: false,
        role,
        tool_name: null,
        tool_kind: null,
        paths: [],
        dispatched_role: null,
      },
      env,
      homeOf(env),
    );
  }

  async function lookup(sessionID: string): Promise<SessionInfo> {
    const cached = sessions.get(sessionID);
    if (cached) return cached;
    if (!client?.session?.get) throw new Error("no session client");
    const response = record(await withTimeout(client.session.get({ path: { id: sessionID } }), SESSION_LOOKUP_TIMEOUT_MS));
    const session = record("data" in response ? response.data : response);
    if (str(session.id) === null) throw new Error("unexpected session payload");
    const parentID = str(session.parentID);
    const role = str(session.agent) ?? messageAgent.get(sessionID) ?? null;
    if (parentID === null) {
      const info = { subagent: false, role, parentID: null, turn: null };
      sessions.set(sessionID, info);
      return info;
    }
    const info = { subagent: true, role, parentID, turn: mainTurn.get(parentID) ?? null };
    // a subagent without a known role is looked up again on the next call
    if (role !== null) {
      // the session exists, so its role has started (session.created may not have been delivered yet)
      startChild(sessionID, parentID, role, currentEnv());
    }
    return info;
  }

  function event(
    kind: GuardEvent["kind"],
    sessionID: string,
    turnID: string | null,
    info: SessionInfo,
    extra: Partial<GuardEvent> = {},
  ): GuardEvent {
    // a subagent is reported under its main session and the main turn current when the child was created, so the
    // user's `#direct` of that turn can release it (core: SUBAGENT_DIRECT_HOSTS)
    const asChild = info.subagent && info.parentID !== null;
    return {
      host: HOST,
      kind,
      session_id: asChild ? info.parentID : sessionID,
      turn_id: asChild ? info.turn : turnID,
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
        if (info.subagent) return; // a child's prompt is the task prompt: no turn boundary, no #direct
        if (turnID !== null) mainTurn.set(sessionID, turnID);
        const text = (Array.isArray(output?.parts) ? output.parts : [])
          .map((part) => (record(part).type === "text" ? str(record(part).text) : null))
          .filter((t): t is string => t !== null)
          .join("\n");
        evaluate(event("prompt", sessionID, turnID, info, { direct: hasDirectToken(text) }), env, homeOf(env));
      } catch {
        logSkip(HOST, env, homeOf(env), "exception");
      }
    },

    event: async ({ event: incoming }) => {
      const env = currentEnv();
      try {
        const e = record(incoming);
        if (e.type !== "session.created") return;
        const properties = record(e.properties);
        const info = record(properties.info);
        const id = str(info.id) ?? str(properties.sessionID);
        if (id === null) return;
        const parentID = str(info.parentID);
        if (parentID === null) {
          sessions.set(id, { subagent: false, role: null, parentID: null, turn: null });
          return;
        }
        startChild(id, parentID, str(info.agent) ?? messageAgent.get(id) ?? null, env);
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
        if (!isEdit && tool !== "task" && tool !== "bash") return; // other tools never reach the guard
        if (sessionID === null) return logSkip(HOST, env, homeOf(env), "missing_id");
        const info = await lookup(sessionID);
        const turnID = null; // tool hooks carry no message id; the prompt boundary state is used
        const args = record(output?.args);
        // R1 for main: strict (unset); the user may still choose classified or off
        const evalEnv: Env = env.SHOAL_GUARD_R1 ? env : { ...env, SHOAL_GUARD_R1: "strict" };
        let guardEvent: GuardEvent;
        if (isEdit) {
          guardEvent = event("tool", sessionID, turnID, info, {
            tool_name: tool,
            tool_kind: "edit",
            paths: editPaths(tool, args),
          });
        } else if (tool === "bash") {
          guardEvent = event("tool", sessionID, turnID, info, {
            tool_name: tool,
            tool_kind: "shell",
            command: str(args.command),
            cwd: str(args.workdir) ?? directory,
          });
        } else {
          guardEvent = event("tool", sessionID, turnID, info, {
            tool_name: tool,
            tool_kind: "dispatch",
            dispatched_role: str(args.subagent_type),
          });
        }
        const result = evaluate(guardEvent, evalEnv, homeOf(env));
        if (result.decision === "deny") reason = result.reason;
      } catch {
        logSkip(HOST, env, homeOf(env), "exception");
      }
      if (reason !== null) throw new Error(reason);
    },
  };
}
