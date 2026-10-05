// Replays tests/fixtures/guard_vectors.json (shared with the Python guard, hooks/shoal_guard.py)
// against the TypeScript core.  Mirrors tests/guard_vectors_helper.py.  Every vector applies to
// the core and is replayed; none is skipped.
import { afterEach, describe, expect, test } from "bun:test";
import {
  chmodSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import {
  evaluate,
  guardDir,
  ROLE_ACCESS,
  setOwnerResolverForTests,
  type GuardEvent,
} from "../src/guard/core.ts";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const PLUGIN_ROOT = resolve(import.meta.dir, "..");
const REPO_ROOT = resolve(PLUGIN_ROOT, "..", "..", "..");
const VECTORS_PATH = join(REPO_ROOT, "tests", "fixtures", "guard_vectors.json");
const TOOL_NAME_BY_KIND: Record<string, string> = { edit: "Edit", dispatch: "Agent", other: "Read" };

const doc = JSON.parse(readFileSync(VECTORS_PATH, "utf8")) as Json;

/** A directory for temp HOMEs that is not itself under an exempt /tmp root. */
function scratchBase(): string {
  const base = realpathSync(tmpdir());
  return base === "/tmp" || base.startsWith("/tmp/") || base.startsWith("/private/tmp")
    ? PLUGIN_ROOT
    : base;
}

class Sandbox {
  readonly root = realpathSync(mkdtempSync(join(scratchBase(), ".guard-vec-")));
  readonly home = join(this.root, "home");
  readonly work = join(this.home, "work");
  readonly tmpdir = join(this.home, "tmpdir");

  constructor() {
    for (const path of [this.home, this.work, this.tmpdir]) mkdirSync(path, { mode: 0o700 });
  }

  close(): void {
    rmSync(this.root, { recursive: true, force: true });
  }

  env(extra: Record<string, string | null> | undefined): Record<string, string> {
    const env: Record<string, string> = {
      HOME: this.home,
      XDG_STATE_HOME: join(this.home, "xdg-state"),
      TMPDIR: "$TMPDIR",
    };
    for (const [key, value] of Object.entries(extra ?? {})) {
      if (value === null) delete env[key];
      else env[key] = value;
    }
    return this.sub(env) as Record<string, string>;
  }

  stateBase(env: Record<string, string>): string {
    const xdg = env.XDG_STATE_HOME ?? "";
    return xdg && isAbsolute(xdg) ? xdg : join(this.home, ".local", "state");
  }

  sub(value: unknown, state?: string): unknown {
    if (typeof value === "string") {
      const out = value
        .replaceAll("$HOME", this.home)
        .replaceAll("$WORK", this.work)
        .replaceAll("$TMPDIR", this.tmpdir);
      return state ? out.replaceAll("$STATE", state) : out;
    }
    if (Array.isArray(value)) return value.map((item) => this.sub(item, state));
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value).map(([k, v]) => [this.sub(k, state) as string, this.sub(v, state)]),
      );
    }
    return value;
  }
}

function lexists(path: string): boolean {
  try {
    lstatSync(path);
    return true;
  } catch {
    return false;
  }
}

/** makedirs with 0700 for every component created. */
function mkdirs(path: string): void {
  const missing: string[] = [];
  let cursor = path;
  while (cursor && !lexists(cursor) && dirname(cursor) !== cursor) {
    missing.push(cursor);
    cursor = dirname(cursor);
  }
  for (const item of missing.reverse()) mkdirSync(item, { mode: 0o700 });
}

function normalizeEvent(stepEvent: Json, vectorHost: string, sandbox: Sandbox): GuardEvent {
  const event: Json = {
    host: vectorHost,
    kind: null,
    session_id: "s1",
    turn_id: "t1",
    cwd: "$WORK",
    is_subagent: false,
    role: null,
    tool_name: null,
    tool_kind: null,
    paths: [],
    dispatched_role: null,
    ...stepEvent,
  };
  if (event.tool_name === null && event.kind === "tool") {
    event.tool_name = TOOL_NAME_BY_KIND[event.tool_kind] ?? null;
  }
  return sandbox.sub(event) as GuardEvent;
}

function applySetup(setup: Json, sandbox: Sandbox, env: Record<string, string>, state: string): void {
  const sub = (value: unknown) => sandbox.sub(value, state) as any; // eslint-disable-line @typescript-eslint/no-explicit-any
  for (const path of sub(setup.dirs ?? []) as string[]) mkdirs(path);
  for (const [link, target] of Object.entries(sub(setup.symlinks ?? {}) as Record<string, string>)) {
    mkdirs(dirname(link));
    symlinkSync(target, link);
  }
  for (const [path, content] of Object.entries(sub(setup.write ?? {}) as Record<string, string>)) {
    mkdirs(dirname(path));
    writeFileSync(path, content);
  }
  for (const [path, mode] of Object.entries(sub(setup.chmod ?? {}) as Record<string, string>)) {
    chmodSync(path, Number.parseInt(mode, 8));
  }
  const needsGuard = ["turn", "turn_legacy_prompt_id", "state_file", "turn_file", "log_prefill_bytes"].some(
    (key) => key in setup,
  );
  if (!needsGuard) return;
  const guard = guardDir(env, sandbox.home);
  if (guard === null) throw new Error("guard dir unavailable during setup");
  for (const [key, idKey] of [
    ["turn", "turn_id"],
    ["turn_legacy_prompt_id", "prompt_id"],
  ] as const) {
    if (key in setup) {
      const turn = setup[key] as Json;
      writeFileSync(
        join(guard, "turns", `${turn.session}.json`),
        JSON.stringify({ [idKey]: turn.turn_id, role: turn.role }),
      );
    }
  }
  for (const [key, subDir] of [
    ["state_file", "state"],
    ["turn_file", "turns"],
  ] as const) {
    if (key in setup) {
      writeFileSync(join(guard, subDir, `${setup[key].session}.json`), setup[key].content as string);
    }
  }
  if ("log_prefill_bytes" in setup) {
    writeFileSync(join(guard, "guard.jsonl"), "x".repeat(Number(setup.log_prefill_bytes)));
  }
}

function checkPost(vector: Json, sandbox: Sandbox, state: string, whitelist: string[]): string[] {
  const failures: string[] = [];
  const sub = (value: unknown) => sandbox.sub(value, state) as any; // eslint-disable-line @typescript-eslint/no-explicit-any
  const name = vector.name as string;
  for (const path of sub(vector.files_exist ?? []) as string[]) {
    if (!lexists(path)) failures.push(`${name}: expected ${path} to exist`);
  }
  for (const path of sub(vector.files_absent ?? []) as string[]) {
    if (lexists(path)) failures.push(`${name}: expected ${path} to be absent`);
  }
  for (const [path, mode] of Object.entries(sub(vector.modes ?? {}) as Record<string, string>)) {
    if (!lexists(path)) {
      failures.push(`${name}: ${path} missing for mode check`);
      continue;
    }
    const got = lstatSync(path).mode & 0o7777;
    if (got !== Number.parseInt(mode, 8)) failures.push(`${name}: ${path} mode ${got.toString(8)} != ${mode}`);
  }
  for (const [path, content] of Object.entries(sub(vector.file_contents ?? {}) as Record<string, string>)) {
    if (readFileSync(path, "utf8") !== content) failures.push(`${name}: ${path} content changed`);
  }
  const logPath = join(state, "shoal", "guard", "guard.jsonl");
  const logText = existsSync(logPath) ? readFileSync(logPath, "utf8") : "";
  if (!("log_prefill_bytes" in (vector.setup ?? {}))) {
    for (const line of logText.split("\n").filter(Boolean)) {
      let record: Json;
      try {
        record = JSON.parse(line) as Json;
      } catch {
        failures.push(`${name}: non-JSON log line`);
        continue;
      }
      const extra = Object.keys(record).filter((key) => !whitelist.includes(key));
      if (extra.length > 0) failures.push(`${name}: log fields outside whitelist: ${extra.sort()}`);
    }
  }
  for (const needle of sub(vector.log_contains ?? []) as string[]) {
    if (!logText.includes(needle)) failures.push(`${name}: log lacks ${JSON.stringify(needle)}`);
  }
  for (const needle of sub(vector.log_lacks ?? []) as string[]) {
    if (logText.includes(needle)) failures.push(`${name}: log must not contain ${JSON.stringify(needle)}`);
  }
  if ("log_size_max" in vector && Buffer.byteLength(logText) > vector.log_size_max) {
    failures.push(`${name}: log grew past cap`);
  }
  return failures;
}

function runVector(vector: Json, whitelist: string[]): string[] {
  const failures: string[] = [];
  const sandbox = new Sandbox();
  try {
    const env = sandbox.env(vector.env);
    const state = sandbox.stateBase(env);
    applySetup(vector.setup ?? {}, sandbox, env, state);
    const guardPath = join(state, "shoal", "guard");
    const foreign = new Set((vector.foreign_owner ?? []).map((rel: string) => join(guardPath, rel)));
    const realUid = process.getuid!();
    setOwnerResolverForTests((path) => (foreign.has(path) ? realUid + 1 : realUid));
    const host = (vector.host as string | undefined) ?? "claude";
    for (const [index, step] of (vector.steps as Json[]).entries()) {
      const result = evaluate(normalizeEvent(step.event, host, sandbox), env, sandbox.home) as Json;
      for (const [key, want] of Object.entries(step.expect)) {
        if (result[key] !== want) {
          failures.push(
            `${vector.name} step ${index}: ${key} expected ${JSON.stringify(want)} got ${JSON.stringify(result[key])}`,
          );
        }
      }
    }
    failures.push(...checkPost(vector, sandbox, state, whitelist));
  } catch (error) {
    failures.push(`${vector.name}: raised ${String(error)}`);
  } finally {
    setOwnerResolverForTests(null);
    sandbox.close();
  }
  return failures;
}

afterEach(() => setOwnerResolverForTests(null));

describe("guard vectors (shared with hooks/shoal_guard.py)", () => {
  test("vector file is the expected shape", () => {
    expect(doc.vectors.length).toBeGreaterThanOrEqual(95);
    expect(doc.log_whitelist).toContain("skip_reason");
  });

  for (const vector of doc.vectors as Json[]) {
    test(vector.name, () => {
      expect(runVector(vector, doc.log_whitelist as string[])).toEqual([]);
    });
  }
});

describe("role table parity with hooks/shoal_guard.py", () => {
  test("ROLE_ACCESS matches the Python table", () => {
    const source = readFileSync(join(REPO_ROOT, "hooks", "shoal_guard.py"), "utf8");
    const block = /ROLE_ACCESS = \{([^}]*)\}/.exec(source)?.[1] ?? "";
    const python = Object.fromEntries(
      Array.from(block.matchAll(/"([^"]+)":\s*"([^"]+)"/g), (m) => [m[1], m[2]]),
    );
    expect(Object.keys(python).length).toBeGreaterThan(5);
    expect(ROLE_ACCESS).toEqual(python);
  });
});
