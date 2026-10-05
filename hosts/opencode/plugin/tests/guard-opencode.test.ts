// OpenCode adapter: hooks, subagent detection through client.session.get, edit tool paths,
// fail-open behaviour.  The core rules themselves are covered by guard-vectors.test.ts.
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createOpenCodeGuard, editPaths } from "../src/guard/opencode.ts";

const PLUGIN_ROOT = resolve(import.meta.dir, "..");
const ENV_KEYS = ["HOME", "XDG_STATE_HOME", "TMPDIR", "SHOAL_GUARD", "PILOTFISH_GUARD", "SHOAL_GUARD_DIRECT", "SHOAL_GUARD_LANG", "SHOAL_GUARD_MAX_FILES", "PILOTFISH_GUARD_MAX_FILES"];

type Sessions = Record<string, { id: string; parentID?: string | null; agent?: string }>;

let root: string;
let work: string;
let saved: Record<string, string | undefined>;
let lookups: string[];

function scratchBase(): string {
  const base = realpathSync(tmpdir());
  return base === "/tmp" || base.startsWith("/tmp/") || base.startsWith("/private/tmp") ? PLUGIN_ROOT : base;
}

function makeGuard(sessions: Sessions, shape: "data" | "bare" = "data") {
  const client = {
    session: {
      async get(options: { path: { id: string } }) {
        lookups.push(options.path.id);
        const session = sessions[options.path.id];
        if (!session) throw new Error("not found");
        return shape === "data" ? { data: session } : session;
      },
    },
  };
  return createOpenCodeGuard({ client, directory: work } as never);
}

const MAIN = "ses_main_01";
const CHILD = "ses_child_02";
const defaultSessions = (): Sessions => ({
  [MAIN]: { id: MAIN, parentID: null },
  [CHILD]: { id: CHILD, parentID: MAIN, agent: "executor" },
});

async function prompt(guard: ReturnType<typeof makeGuard>, sessionID: string, messageID = "msg_001") {
  await guard["chat.message"]!({ sessionID, messageID } as never, { message: {}, parts: [] } as never);
}
async function call(guard: ReturnType<typeof makeGuard>, tool: string, sessionID: string, args: unknown) {
  await guard["tool.execute.before"]!({ tool, sessionID, callID: "call_1" } as never, { args } as never);
}
const edit = (name: string) => ({ filePath: join(work, name) });
const logLines = () => {
  try {
    return readFileSync(join(root, "home", "xdg-state", "shoal", "guard", "guard.jsonl"), "utf8")
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Record<string, string>);
  } catch {
    return [];
  }
};

beforeEach(() => {
  saved = Object.fromEntries(ENV_KEYS.map((key) => [key, process.env[key]]));
  root = realpathSync(mkdtempSync(join(scratchBase(), ".guard-oc-")));
  const home = join(root, "home");
  work = join(home, "work");
  mkdirSync(work, { recursive: true, mode: 0o700 });
  mkdirSync(join(home, "tmpdir"), { mode: 0o700 });
  for (const key of ENV_KEYS) delete process.env[key];
  process.env.HOME = home;
  process.env.XDG_STATE_HOME = join(home, "xdg-state");
  process.env.TMPDIR = join(home, "tmpdir");
  lookups = [];
});

afterEach(() => {
  for (const key of ENV_KEYS) {
    if (saved[key] === undefined) delete process.env[key];
    else process.env[key] = saved[key];
  }
  rmSync(root, { recursive: true, force: true });
});

describe("OpenCode guard: main session", () => {
  test("defaults to shadow: the third file is logged as would_deny, not thrown", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    for (const name of ["a", "b", "c"]) await call(guard, "write", MAIN, edit(name));
    const last = logLines().at(-1)!;
    expect(last).toMatchObject({ decision: "would_deny", rule: "R2", mode: "shadow", host: "opencode", tool: "write", file: "c" });
  });

  test("enforce throws the deny message on the third file and allows after a write-level dispatch", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await call(guard, "write", MAIN, edit("a"));
    await call(guard, "edit", MAIN, edit("b"));
    await expect(call(guard, "multiedit", MAIN, edit("c"))).rejects.toThrow(/Shoal dispatch guard.*edited 2 files.*with task;/);
    await call(guard, "task", MAIN, { subagent_type: "executor", prompt: "x" });
    await call(guard, "write", MAIN, edit("c"));
  });

  test("a read-only dispatch does not unlock", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await call(guard, "task", MAIN, { subagent_type: "scout" });
    await call(guard, "write", MAIN, edit("a"));
    await call(guard, "write", MAIN, edit("b"));
    await expect(call(guard, "write", MAIN, edit("c"))).rejects.toThrow();
  });

  test("a new chat.message (messageID) starts a new turn", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN, "msg_001");
    await call(guard, "write", MAIN, edit("a"));
    await call(guard, "write", MAIN, edit("b"));
    await expect(call(guard, "write", MAIN, edit("c"))).rejects.toThrow();
    await prompt(guard, MAIN, "msg_002");
    await call(guard, "write", MAIN, edit("c"));
  });

  test("apply_patch paths come from the patch headers", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    const patchText = [
      "*** Begin Patch",
      `*** Add File: ${join(work, "a.txt")}`,
      "+x",
      `*** Update File: ${join(work, "b.txt")}`,
      "@@",
      `*** Update File: ${join(work, "c.txt")}`,
      "*** End Patch",
    ].join("\n");
    await expect(call(guard, "apply_patch", MAIN, { patchText })).rejects.toThrow(/edited 2 files/);
  });

  test("SHOAL_GUARD_DIRECT=1 and SHOAL_GUARD=off let everything through", async () => {
    process.env.SHOAL_GUARD = "enforce";
    process.env.SHOAL_GUARD_DIRECT = "1";
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    for (const name of ["a", "b", "c", "d"]) await call(guard, "write", MAIN, edit(name));
    process.env.SHOAL_GUARD_DIRECT = "0";
    process.env.SHOAL_GUARD = "off";
    await call(guard, "write", MAIN, edit("e"));
  });

  test("zh-TW message with SHOAL_GUARD_LANG", async () => {
    process.env.SHOAL_GUARD = "enforce";
    process.env.SHOAL_GUARD_LANG = "zh-TW";
    process.env.SHOAL_GUARD_MAX_FILES = "0";
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await expect(call(guard, "write", MAIN, edit("a"))).rejects.toThrow(/main session/);
  });

  test("non-edit tools never look up the session", async () => {
    const guard = makeGuard(defaultSessions());
    await call(guard, "bash", MAIN, { command: "ls" });
    await call(guard, "read", MAIN, { filePath: "x" });
    expect(lookups).toEqual([]);
  });

  test("ses_ ids with underscores are accepted and the session lookup is cached", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await call(guard, "write", MAIN, edit("a"));
    await call(guard, "write", MAIN, edit("b"));
    expect(lookups).toEqual([MAIN]);
    expect(logLines().some((line) => line.skip_reason === "invalid_id")).toBe(false);
  });

  test("accepts a bare session payload as well as { data }", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const guard = makeGuard(defaultSessions(), "bare");
    await prompt(guard, MAIN);
    await call(guard, "write", MAIN, edit("a"));
    expect(lookups).toEqual([MAIN]);
  });
});

describe("OpenCode guard: subagents", () => {
  test("a subagent dispatching `task` hits LEAF (enforce) and is only logged in shadow", async () => {
    const guard = makeGuard(defaultSessions());
    await call(guard, "task", CHILD, { subagent_type: "scout" });
    expect(logLines().at(-1)).toMatchObject({ decision: "would_deny", rule: "LEAF", mode: "shadow" });
    process.env.SHOAL_GUARD = "enforce";
    await expect(call(guard, "task", CHILD, { subagent_type: "scout" })).rejects.toThrow(/leaf workers/);
  });

  test("a verifier subagent cannot use editing tools", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const sessions = defaultSessions();
    sessions[CHILD].agent = "verifier";
    const guard = makeGuard(sessions);
    await expect(call(guard, "edit", CHILD, edit("a"))).rejects.toThrow(/verify-level/);
  });

  test("an executor subagent may edit any number of files and never touches main state", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const guard = makeGuard(defaultSessions());
    for (const name of ["a", "b", "c", "d"]) await call(guard, "write", CHILD, edit(name));
    await prompt(guard, MAIN);
    await call(guard, "write", MAIN, edit("a"));
  });

  test("the subagent role falls back to the agent named by its first chat.message", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const sessions = defaultSessions();
    delete sessions[CHILD].agent;
    const guard = makeGuard(sessions);
    await guard["chat.message"]!({ sessionID: CHILD, agent: "verifier", messageID: "msg_9" } as never, { message: {}, parts: [] } as never);
    await expect(call(guard, "write", CHILD, edit("a"))).rejects.toThrow(/verify-level/);
  });
});

describe("OpenCode guard: fail-open", () => {
  test("a failing session lookup never blocks or throws", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const guard = makeGuard({});
    await prompt(guard, "ses_unknown");
    for (const name of ["a", "b", "c", "d"]) await call(guard, "write", "ses_unknown", edit(name));
    expect(logLines().some((line) => line.skip_reason === "exception")).toBe(true);
  });

  test("missing client, missing session id and malformed args do not throw", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const guard = createOpenCodeGuard({ directory: work } as never);
    await call(guard, "write", MAIN, edit("a"));
    await guard["tool.execute.before"]!({ tool: "write", callID: "c" } as never, { args: edit("a") } as never);
    const ok = makeGuard(defaultSessions());
    await call(ok, "write", MAIN, null);
    await call(ok, "apply_patch", MAIN, { patchText: 5 });
    await call(ok, "task", MAIN, undefined);
  });

  test("the log carries only whitelisted fields and no tool args", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await call(guard, "write", MAIN, { filePath: join(work, "secret-name.txt"), content: "TOPSECRET" });
    const raw = readFileSync(join(root, "home", "xdg-state", "shoal", "guard", "guard.jsonl"), "utf8");
    expect(raw).not.toContain("TOPSECRET");
    expect(raw).not.toContain(work);
  });
});

describe("editPaths", () => {
  test("covers each OpenCode editing tool", () => {
    expect(editPaths("write", { filePath: "/a" })).toEqual(["/a"]);
    expect(editPaths("edit", { filePath: "/b", oldString: "x" })).toEqual(["/b"]);
    expect(editPaths("multiedit", { filePath: "/c", edits: [] })).toEqual(["/c"]);
    expect(editPaths("apply_patch", { patchText: "*** Update File: x/y.ts\n*** Move to: x/z.ts\n*** Delete File: q" })).toEqual(["x/y.ts", "x/z.ts", "q"]);
    expect(editPaths("write", {})).toEqual([]);
    expect(editPaths("apply_patch", null)).toEqual([]);
  });
});
