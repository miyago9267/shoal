// OpenCode adapter: hooks, subagent detection through client.session.get, edit tool paths,
// fail-open behaviour.  The core rules themselves are covered by guard-vectors.test.ts.
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createOpenCodeGuard, editPaths } from "../src/guard/opencode.ts";

const PLUGIN_ROOT = resolve(import.meta.dir, "..");
const ENV_KEYS = ["HOME", "XDG_STATE_HOME", "TMPDIR", "SHOAL_GUARD", "SHOAL_GUARD_DIRECT", "SHOAL_GUARD_LANG", "SHOAL_GUARD_MAX_FILES", "SHOAL_GUARD_R1", "SHOAL_GUARD_WRITE_AGENTS", "SHOAL_GUARD_SUBAGENT_WRITE", "SHOAL_GUARD_CHAIN_FILE", "SHOAL_GUARD_CHAIN_TIMEOUT_MS", "PATH"];

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

async function prompt(guard: ReturnType<typeof makeGuard>, sessionID: string, messageID = "msg_001", text = "") {
  await guard["chat.message"]!(
    { sessionID } as never,
    { message: { id: messageID }, parts: [{ type: "text", text }] } as never,
  );
}
async function created(guard: ReturnType<typeof makeGuard>, id: string, parentID: string | null, agent?: string) {
  const info = parentID === null ? { id } : { id, parentID, agent };
  await guard.event!({ event: { type: "session.created", properties: { sessionID: id, info } } } as never);
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
  test("defaults to enforce: a main edit is denied (strict) until a write role has started", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await expect(call(guard, "write", MAIN, edit("a"))).rejects.toThrow(/does not edit files itself/);
    expect(logLines().at(-1)).toMatchObject({ decision: "deny", rule: "R1", mode: "enforce", host: "opencode", tool: "write", file: "a" });
  });

  test("SHOAL_GUARD=shadow logs would_deny without throwing", async () => {
    process.env.SHOAL_GUARD = "shadow";
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    for (const name of ["a", "b", "c"]) await call(guard, "write", MAIN, edit(name));
    expect(logLines().at(-1)).toMatchObject({ decision: "would_deny", rule: "R1", mode: "shadow", host: "opencode", file: "c" });
  });

  test("SHOAL_GUARD=off never throws", async () => {
    process.env.SHOAL_GUARD = "off";
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    for (const name of ["a", "b", "c", "d"]) await call(guard, "write", MAIN, edit(name));
    await call(guard, "bash", MAIN, { command: "echo x > out.txt" });
  });

  test("a write-role task call alone does not unlock; the child session.created does (E3)", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await call(guard, "task", MAIN, { subagent_type: "executor", prompt: "x" });
    expect(logLines().at(-1)).toMatchObject({ decision: "allow", rule: "dispatch_pending" });
    await expect(call(guard, "write", MAIN, edit("d"))).rejects.toThrow(/does not edit files itself/);
    await created(guard, CHILD, MAIN, "executor");
    expect(logLines().at(-1)).toMatchObject({ decision: "state", rule: "dispatch_started" });
    await call(guard, "write", MAIN, edit("d"));
    expect(logLines().at(-1)).toMatchObject({ decision: "allow", rule: "dispatched" });
  });

  test("a failed dispatch (task before, no session.created) never unlocks", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await call(guard, "task", MAIN, { subagent_type: "no-such-role-xyz", prompt: "x" });
    await call(guard, "task", MAIN, { subagent_type: "executor", prompt: "x" }); // announced, then the host fails it
    await expect(call(guard, "write", MAIN, edit("a"))).rejects.toThrow(/does not edit files itself/);
    await expect(call(guard, "bash", MAIN, { command: "echo x > out.txt" })).rejects.toThrow(/does not edit files itself/);
  });

  test("a read-only dispatch does not unlock, even when its session starts", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await call(guard, "task", MAIN, { subagent_type: "scout" });
    await created(guard, CHILD, MAIN, "scout");
    await expect(call(guard, "write", MAIN, edit("a"))).rejects.toThrow(/does not edit files itself/);
  });

  test("a new chat.message (messageID) starts a new turn and locks again", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN, "msg_001");
    await call(guard, "task", MAIN, { subagent_type: "applier" });
    await created(guard, CHILD, MAIN, "applier");
    await call(guard, "write", MAIN, edit("a"));
    await prompt(guard, MAIN, "msg_002");
    await expect(call(guard, "write", MAIN, edit("a"))).rejects.toThrow(/does not edit files itself/);
  });

  test("main bash: a write is denied, a read passes", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await call(guard, "bash", MAIN, { command: "ls -la && git status" });
    await call(guard, "bash", MAIN, { command: "cat a.txt | grep x" });
    await expect(call(guard, "bash", MAIN, { command: "echo hi > notes.txt", workdir: work })).rejects.toThrow(/does not edit files itself/);
    expect(logLines().at(-1)).toMatchObject({ decision: "deny", rule: "R1", tool: "bash" });
    await call(guard, "bash", MAIN, { command: "echo hi > /tmp/scratch.txt" }); // exempt path
  });

  test("main bash write passes after a write role started", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await call(guard, "task", MAIN, { subagent_type: "executor" });
    await created(guard, CHILD, MAIN, "executor");
    await call(guard, "bash", MAIN, { command: "echo hi > notes.txt" });
  });

  test("apply_patch from main is denied and takes its paths from the patch headers", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    const patchText = ["*** Begin Patch", `*** Add File: ${join(work, "a.txt")}`, "+x", "*** End Patch"].join("\n");
    await expect(call(guard, "apply_patch", MAIN, { patchText })).rejects.toThrow(/does not edit files itself/);
    expect(logLines().at(-1)).toMatchObject({ decision: "deny", rule: "R1", file: "a.txt" });
  });

  test("#direct in the main chat.message releases the main edit and shell write; the next turn does not", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN, "msg_001", "please fix it #direct");
    await call(guard, "write", MAIN, edit("a"));
    await call(guard, "bash", MAIN, { command: "echo hi > notes.txt" });
    await prompt(guard, MAIN, "msg_002", "now something else");
    await expect(call(guard, "write", MAIN, edit("a"))).rejects.toThrow(/does not edit files itself/);
  });

  test("#fast typed in a raw chat.message persists the session fast flag; #strict clears it; code spans do not count", async () => {
    const guard = makeGuard(defaultSessions());
    const fastFlag = () => {
      try {
        return JSON.parse(readFileSync(join(root, "home", "xdg-state", "shoal", "guard", "state", MAIN + ".json"), "utf8")).fast === true;
      } catch {
        return false;
      }
    };
    await prompt(guard, MAIN, "msg_001", "what does `#fast` do?");
    expect(fastFlag()).toBe(false);
    await prompt(guard, MAIN, "msg_002", "please go #fast, thanks");
    expect(fastFlag()).toBe(true);
    await prompt(guard, MAIN, "msg_003", "carry on");
    expect(fastFlag()).toBe(true);
    await prompt(guard, MAIN, "msg_004", "#fast and #strict");
    expect(fastFlag()).toBe(false);
  });

  test("#direct inside inline code or glued to text is not a directive", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN, "msg_001", "what does `#direct` do? also foo#direct");
    await expect(call(guard, "write", MAIN, edit("a"))).rejects.toThrow(/does not edit files itself/);
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

  test("SHOAL_GUARD_R1=classified keeps the old advise-only behaviour", async () => {
    process.env.SHOAL_GUARD_R1 = "classified";
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    for (const name of ["a", "b", "c"]) await call(guard, "write", MAIN, edit(name));
    expect(logLines().at(-1)).toMatchObject({ decision: "advise", rule: "R2", mode: "enforce" });
  });

  test("tools outside the guarded set never look up the session", async () => {
    const guard = makeGuard(defaultSessions());
    await call(guard, "read", MAIN, { filePath: "x" });
    await call(guard, "grep", MAIN, { pattern: "x" });
    expect(lookups).toEqual([]);
  });

  test("ses_ ids with underscores are accepted and the session lookup is cached", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await expect(call(guard, "write", MAIN, edit("a"))).rejects.toThrow();
    await expect(call(guard, "write", MAIN, edit("b"))).rejects.toThrow();
    expect(lookups).toEqual([MAIN]);
    expect(logLines().some((line) => line.skip_reason === "invalid_id")).toBe(false);
  });

  test("accepts a bare session payload as well as { data }", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const guard = makeGuard(defaultSessions(), "bare");
    await prompt(guard, MAIN);
    await expect(call(guard, "write", MAIN, edit("a"))).rejects.toThrow();
    expect(lookups).toEqual([MAIN]);
  });
});

describe("OpenCode guard: subagents", () => {
  test("a subagent dispatching `task` hits LEAF: thrown by default, only logged in shadow", async () => {
    const guard = makeGuard(defaultSessions());
    await expect(call(guard, "task", CHILD, { subagent_type: "scout" })).rejects.toThrow(/leaf workers/);
    process.env.SHOAL_GUARD = "shadow";
    await call(guard, "task", CHILD, { subagent_type: "scout" });
    expect(logLines().at(-1)).toMatchObject({ decision: "would_deny", rule: "LEAF", mode: "shadow" });
  });

  test("a verifier subagent cannot use editing tools", async () => {
    process.env.SHOAL_GUARD = "enforce";
    const sessions = defaultSessions();
    sessions[CHILD].agent = "verifier";
    const guard = makeGuard(sessions);
    await expect(call(guard, "edit", CHILD, edit("a"))).rejects.toThrow(/verify-level/);
  });

  test("executor and applier subagents may edit and shell-write, and never touch main state", async () => {
    for (const role of ["executor", "applier"]) {
      const sessions = defaultSessions();
      sessions[CHILD].agent = role;
      const guard = makeGuard(sessions);
      for (const name of ["a", "b", "c", "d"]) await call(guard, "write", CHILD, edit(name));
      await call(guard, "bash", CHILD, { command: "echo hi > notes.txt" });
      await call(guard, "apply_patch", CHILD, { patchText: `*** Update File: ${join(work, "z.ts")}` });
      await prompt(guard, MAIN);
      await expect(call(guard, "write", MAIN, edit("a"))).rejects.toThrow(/does not edit files itself/);
    }
  });

  test("a non-shoal child (general, explore, unknown) is denied edit, shell write and apply_patch (E1)", async () => {
    for (const role of ["general", "explore", "my-own-agent"]) {
      const sessions = defaultSessions();
      sessions[CHILD].agent = role;
      const guard = makeGuard(sessions);
      await expect(call(guard, "write", CHILD, edit("a"))).rejects.toThrow(/not a shoal write-capable role/);
      await expect(call(guard, "edit", CHILD, edit("a"))).rejects.toThrow(/not a shoal/);
      await expect(call(guard, "bash", CHILD, { command: "echo hi > notes.txt" })).rejects.toThrow(/not a shoal/);
      await expect(call(guard, "apply_patch", CHILD, { patchText: `*** Add File: ${join(work, "z.ts")}` })).rejects.toThrow(/not a shoal/);
      expect(logLines().at(-1)).toMatchObject({ decision: "deny", rule: "E1" });
      await call(guard, "bash", CHILD, { command: "ls && cat a.txt" }); // reads are fine
      await call(guard, "write", CHILD, { filePath: "/tmp/x.txt" }); // exempt path
    }
  });

  test("SHOAL_GUARD_WRITE_AGENTS and SHOAL_GUARD_DIRECT=1 release a non-shoal child", async () => {
    const sessions = defaultSessions();
    sessions[CHILD].agent = "general";
    process.env.SHOAL_GUARD_WRITE_AGENTS = "foo, general";
    await call(makeGuard(sessions), "write", CHILD, edit("a"));
    delete process.env.SHOAL_GUARD_WRITE_AGENTS;
    await expect(call(makeGuard(sessions), "write", CHILD, edit("a"))).rejects.toThrow();
    process.env.SHOAL_GUARD_DIRECT = "1";
    await call(makeGuard(sessions), "bash", CHILD, { command: "echo hi > notes.txt" });
  });

  test("shadow mode logs the E1 would_deny and does not throw", async () => {
    process.env.SHOAL_GUARD = "shadow";
    const sessions = defaultSessions();
    sessions[CHILD].agent = "general";
    await call(makeGuard(sessions), "write", CHILD, edit("a"));
    expect(logLines().at(-1)).toMatchObject({ decision: "would_deny", rule: "E1", mode: "shadow" });
  });

  test("SHOAL_GUARD_SUBAGENT_WRITE=off turns E1 off", async () => {
    process.env.SHOAL_GUARD_SUBAGENT_WRITE = "off";
    const sessions = defaultSessions();
    sessions[CHILD].agent = "general";
    await call(makeGuard(sessions), "write", CHILD, edit("a"));
  });

  test("a child session announced by session.created needs no session.get", async () => {
    const guard = makeGuard({});
    await created(guard, MAIN, null);
    await prompt(guard, MAIN, "msg_001", "x");
    await created(guard, CHILD, MAIN, "general");
    await expect(call(guard, "write", CHILD, edit("a"))).rejects.toThrow(/not a shoal/);
    expect(lookups).toEqual([]);
  });

  test("a child of an unknown session is resolved through the session.get fallback", async () => {
    const sessions = defaultSessions();
    sessions[CHILD].agent = "general";
    const g2 = makeGuard(sessions);
    await expect(call(g2, "write", CHILD, edit("a"))).rejects.toThrow(/not a shoal/);
    expect(lookups).toContain(CHILD);
  });

  test("the fallback lookup of a write-role child also counts as its start", async () => {
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN);
    await call(guard, "task", MAIN, { subagent_type: "executor" });
    await call(guard, "write", CHILD, edit("a")); // child's first tool call, session.created never seen
    await call(guard, "write", MAIN, edit("m"));
    expect(logLines().at(-1)).toMatchObject({ decision: "allow", rule: "dispatched" });
  });

  test("#direct of the turn that created the child releases it; a later turn does not", async () => {
    const sessions = defaultSessions();
    sessions[CHILD].agent = "general";
    const guard = makeGuard(sessions);
    await prompt(guard, MAIN, "msg_001", "do it #direct");
    await created(guard, CHILD, MAIN, "general");
    await call(guard, "write", CHILD, edit("a"));
    await call(guard, "bash", CHILD, { command: "echo hi > notes.txt" });
    // next turn without #direct: a new general child is denied
    const CHILD2 = "ses_child_03";
    await prompt(guard, MAIN, "msg_002", "now plain");
    await created(guard, CHILD2, MAIN, "general");
    await expect(call(guard, "write", CHILD2, edit("a"))).rejects.toThrow(/#direct/);
    // the first child keeps the release recorded for its own turn
    await call(guard, "write", CHILD, edit("b"));
  });

  test("a child without #direct in its turn is denied, and the message offers #direct", async () => {
    const sessions = defaultSessions();
    sessions[CHILD].agent = "general";
    const guard = makeGuard(sessions);
    await prompt(guard, MAIN, "msg_001", "plain");
    await created(guard, CHILD, MAIN, "general");
    await expect(call(guard, "write", CHILD, edit("a"))).rejects.toThrow(/#direct/);
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
    await call(guard, "write", MAIN, { filePath: join(work, "secret-name.txt"), content: "TOPSECRET" }).catch(() => {});
    const raw = readFileSync(join(root, "home", "xdg-state", "shoal", "guard", "guard.jsonl"), "utf8");
    expect(raw).not.toContain("TOPSECRET");
    expect(raw).not.toContain(work);
  });
});

describe("OpenCode guard: event hook", () => {
  test("malformed events are ignored without throwing", async () => {
    const guard = makeGuard(defaultSessions());
    for (const event of [null, {}, { type: "session.created" }, { type: "session.created", properties: { info: {} } }, { type: "session.idle", properties: { sessionID: MAIN } }]) {
      await guard.event!({ event } as never);
    }
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

describe("OpenCode guard: chain", () => {
  const member = join(PLUGIN_ROOT, "..", "..", "..", "tests", "fixtures", "chain", "member.py");

  function configure(...args: string[][]) {
    const file = join(root, "chain.json");
    writeFileSync(
      file,
      JSON.stringify({ chain: args.map((a, i) => ({ name: `m${i}`, command: ["python3", member, ...a], hosts: ["opencode"], order: i })) }),
    );
    process.env.SHOAL_GUARD_CHAIN_FILE = file;
    process.env.SHOAL_GUARD_CHAIN_TIMEOUT_MS = "1500";
    process.env.PATH ??= "/usr/bin:/bin";
  }

  test("a member deny blocks the call with a name-prefixed reason; the payload carries the tool args", async () => {
    configure(["deny_if", "needle-in-args"]);
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN, "msg_001", "#direct");
    await call(guard, "bash", MAIN, { command: "ls" });
    await expect(call(guard, "bash", MAIN, { command: "echo needle-in-args" })).rejects.toThrow("m0: saw needle-in-args");
    expect(logLines().filter((l) => l.rule === "chain").map((l) => l.decision)).toEqual(["chain_allow", "chain_deny"]);
  });

  test("a failing member never blocks", async () => {
    configure(["exit1"], ["garbage"]);
    const guard = makeGuard(defaultSessions());
    await prompt(guard, MAIN, "msg_001", "#direct");
    await call(guard, "bash", MAIN, { command: "ls" });
    expect(logLines().filter((l) => l.rule === "chain").map((l) => l.decision)).toEqual(["chain_error", "chain_error"]);
  });
});
