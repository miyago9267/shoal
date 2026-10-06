// K4 (state lock) and K3 (role namespace) for the TypeScript guard core.
import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, utimesSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { evaluate, guardDir, normalizeRole, setLockWaitForTests, type GuardEvent } from "../src/guard/core.ts";

const CORE = resolve(import.meta.dir, "..", "src", "guard", "core.ts");

let root = "";
let work = "";
let env: Record<string, string> = {};

beforeEach(() => {
  const base = realpathSync(tmpdir()).startsWith("/tmp") ? resolve(import.meta.dir, "..") : realpathSync(tmpdir());
  root = realpathSync(mkdtempSync(join(base, ".guard-lock-")));
  work = join(root, "work");
  mkdirSync(work, { mode: 0o700 });
  env = {
    HOME: root,
    XDG_STATE_HOME: join(root, "xdg-state"),
    TMPDIR: join(root, "tmpdir"),
    SHOAL_GUARD_MAX_FILES: "40",
  };
});

afterEach(() => {
  setLockWaitForTests(null);
  rmSync(root, { recursive: true, force: true });
});

function editEvent(name: string): GuardEvent {
  return {
    host: "claude",
    kind: "tool",
    session_id: "s1",
    turn_id: null,
    cwd: work,
    is_subagent: false,
    role: null,
    tool_name: "Edit",
    tool_kind: "edit",
    paths: [join(work, name)],
    dispatched_role: null,
  };
}

describe("state lock (K4)", () => {
  test("parallel guard processes keep every edited entry", async () => {
    const count = 12;
    const code = `
      import { evaluate } from ${JSON.stringify(CORE)};
      const [name, home, xdg, tmp, wd] = process.argv.slice(1);
      const env = { HOME: home, XDG_STATE_HOME: xdg, TMPDIR: tmp, SHOAL_GUARD_MAX_FILES: "40" };
      const r = evaluate({ host: "claude", kind: "tool", session_id: "s1", turn_id: null, cwd: wd,
        is_subagent: false, role: null, tool_name: "Edit", tool_kind: "edit", paths: [wd + "/" + name],
        dispatched_role: null }, env, home);
      if (r.decision !== "allow") { console.error(JSON.stringify(r)); process.exit(1); }
    `;
    const procs = Array.from({ length: count }, (_, i) =>
      Bun.spawn(["bun", "-e", code, `f${i}.ts`, root, env.XDG_STATE_HOME, env.TMPDIR, work], {
        stdout: "pipe",
        stderr: "pipe",
      }),
    );
    const codes = await Promise.all(procs.map((p) => p.exited));
    expect(codes).toEqual(Array.from({ length: count }, () => 0));
    const dir = guardDir(env, root) as string;
    const state = JSON.parse(readFileSync(join(dir, "state", "s1.json"), "utf8")) as { edited: string[] };
    expect(new Set(state.edited).size).toBe(count);
    expect(existsSync(join(dir, "state", "s1.tslock"))).toBe(false);
  }, 60000);

  test("a fresh lock held by someone else fails open with lock_timeout", () => {
    const dir = guardDir(env, root) as string;
    const lock = join(dir, "state", "s1.tslock");
    writeFileSync(lock, "", { mode: 0o600 });
    setLockWaitForTests(50);
    const result = evaluate(editEvent("a.ts"), env, root);
    expect([result.decision, result.skip_reason]).toEqual(["skip", "lock_timeout"]);
    expect(existsSync(lock)).toBe(true);
  });

  test("a stale lock from a dead process is removed", () => {
    const dir = guardDir(env, root) as string;
    const lock = join(dir, "state", "s1.tslock");
    writeFileSync(lock, "", { mode: 0o600 });
    const old = new Date(Date.now() - 60_000);
    utimesSync(lock, old, old);
    const result = evaluate(editEvent("a.ts"), env, root);
    expect([result.decision, result.rule]).toEqual(["allow", "count"]);
    expect(existsSync(lock)).toBe(false);
  });
});

describe("role namespace (K3)", () => {
  test("only the bare name and the shoal: prefix are recognised", () => {
    expect(normalizeRole("executor")).toBe("executor");
    expect(normalizeRole("shoal:executor")).toBe("executor");
    expect(normalizeRole("x:executor")).toBe("x:executor");
    expect(normalizeRole("shoal:shoal:executor")).toBe("shoal:executor");
    expect(normalizeRole("SHOAL:executor")).toBe("SHOAL:executor");
    expect(normalizeRole(null)).toBeNull();
  });
});

describe("advise reminder (R1/R2 never deny)", () => {
  const advEnv = () => ({ ...env, SHOAL_GUARD: "enforce", SHOAL_GUARD_MAX_FILES: "1" });
  const turnEvent = (name: string, turn: string, host = "claude"): GuardEvent => ({
    ...editEvent(name),
    host,
    turn_id: turn,
  });
  const prompt = (turn: string, host = "claude"): GuardEvent => ({
    ...editEvent("x"),
    host,
    kind: "prompt",
    turn_id: turn,
    tool_name: null,
    tool_kind: null,
    paths: [],
  });

  test("first advise per turn carries the message, later ones and other hosts do not, new turn re-arms", () => {
    const e = advEnv();
    evaluate(prompt("t1"), e, root);
    expect(evaluate(turnEvent("a", "t1"), e, root).decision).toBe("allow");
    const first = evaluate(turnEvent("b", "t1"), e, root);
    expect([first.decision, first.rule, first.notify]).toEqual(["advise", "R2", true]);
    expect(first.reason).toContain("edited 2 files directly");
    const second = evaluate(turnEvent("c", "t1"), e, root);
    expect([second.decision, second.notify, second.reason]).toEqual(["advise", false, null]);
    evaluate(prompt("t2"), e, root);
    evaluate(turnEvent("a", "t2"), e, root);
    expect(evaluate(turnEvent("b", "t2"), e, root).notify).toBe(true);
  });

  test("zh-TW message and non-output hosts", () => {
    const e = { ...advEnv(), SHOAL_GUARD_LANG: "zh-TW" };
    evaluate(prompt("t1"), e, root);
    evaluate(turnEvent("a", "t1"), e, root);
    expect(evaluate(turnEvent("b", "t1"), e, root).reason).toContain("提醒");
    const grok = { ...e, SHOAL_GUARD: "enforce" };
    evaluate(prompt("g1", "grok"), grok, root);
    evaluate(turnEvent("a", "g1", "grok"), grok, root);
    const result = evaluate(turnEvent("b", "g1", "grok"), grok, root);
    expect([result.decision, result.notify, result.reason]).toEqual(["advise", false, null]);
  });
});
