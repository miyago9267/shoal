// E1 (docs/specs/guard-every-gate) on the opencode host.  The shared vectors cover claude and codex (the
// Python guard does not evaluate opencode subagents), so the opencode edit-tool cases live here.
import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { evaluate, type GuardEvent } from "../src/guard/core.ts";

function event(role: string | null, path = "/work/src/a"): GuardEvent {
  return {
    host: "opencode",
    kind: "tool",
    session_id: "ses_1",
    turn_id: "t1",
    cwd: "/work",
    is_subagent: true,
    role,
    tool_name: "edit",
    tool_kind: "edit",
    paths: [path],
    dispatched_role: null,
    direct: false,
    command: null,
  } as GuardEvent;
}

describe("E1 subagent write rule (opencode edit tools)", () => {
  const home = mkdtempSync(join(tmpdir(), "e1-"));
  const base = { HOME: home, XDG_STATE_HOME: join(home, "state") };
  const run = (e: GuardEvent, env: Record<string, string>) => evaluate(e, { ...base, ...env }, home);

  test("switch off: non-shoal subagent edit is allowed", () => {
    // opencode defaults to on (S3); an explicit off still disables the rule
    expect(run(event("build"), { SHOAL_GUARD: "enforce", SHOAL_GUARD_SUBAGENT_WRITE: "off" }).decision).toBe("none");
    expect(run(event("build"), { SHOAL_GUARD: "enforce" })).toMatchObject({ decision: "deny", rule: "E1" });
  });
  test("on + enforce: denied; write role, allowlist, DIRECT and exempt path pass", () => {
    const on = { SHOAL_GUARD: "enforce", SHOAL_GUARD_SUBAGENT_WRITE: "on" };
    expect(run(event("build"), on)).toMatchObject({ decision: "deny", rule: "E1" });
    expect(run(event(null), on)).toMatchObject({ decision: "deny", rule: "E1" });
    expect(run(event("executor"), on).decision).toBe("none");
    expect(run(event("verifier"), on)).toMatchObject({ decision: "deny", rule: "VERIFY_EDIT" });
    expect(run(event("build"), { ...on, SHOAL_GUARD_WRITE_AGENTS: "x, build" }).decision).toBe("none");
    expect(run(event("build"), { ...on, SHOAL_GUARD_DIRECT: "1" }).decision).toBe("none");
    expect(run(event("build", "/tmp/x"), on).decision).toBe("none");
  });
  test("on + shadow: would_deny", () => {
    const env = { SHOAL_GUARD: "shadow", SHOAL_GUARD_SUBAGENT_WRITE: "on" };
    expect(run(event("build"), env)).toMatchObject({ decision: "would_deny", rule: "E1" });
  });
  test("cleanup", () => rmSync(home, { recursive: true, force: true }));
});
