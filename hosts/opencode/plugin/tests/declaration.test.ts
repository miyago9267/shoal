// Replays tests/fixtures/declaration_cases.json (shared with hooks/shoal_guard.py) against the
// TypeScript declaration parser used by guard rule R1 in `declare` mode.
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { logReason, parseDeclaration } from "../src/guard/declaration.ts";
import { resolveR1 } from "../src/guard/core.ts";

const REPO_ROOT = resolve(import.meta.dir, "..", "..", "..", "..");
const doc = JSON.parse(readFileSync(join(REPO_ROOT, "tests", "fixtures", "declaration_cases.json"), "utf8")) as {
  cases: Array<{ command: string; reason: string | null }>;
};

describe("parseDeclaration", () => {
  test("fixture is large enough and has unique commands", () => {
    expect(doc.cases.length).toBeGreaterThanOrEqual(100);
    expect(new Set(doc.cases.map((c) => c.command)).size).toBe(doc.cases.length);
    expect(doc.cases.some((c) => c.reason !== null)).toBe(true);
  });

  for (const { command, reason } of doc.cases) {
    test(JSON.stringify(command), () => {
      expect(parseDeclaration(command)).toBe(reason);
    });
  }

  test("non-strings are not declarations", () => {
    for (const value of [null, undefined, 7, [": shoal-direct x"]]) expect(parseDeclaration(value)).toBeNull();
  });

  test("logReason removes controls and cuts at 200 characters", () => {
    expect(logReason("a\tb\x01c\x7fd\x85e\nf")).toBe("abcdef");
    expect(logReason("x".repeat(250))).toBe("x".repeat(200));
    expect(logReason("改".repeat(250))).toBe("改".repeat(200));
  });
});

describe("resolveR1", () => {
  test("claude and codex are strict by default; declare, classified and off are selectable", () => {
    for (const host of ["claude", "codex"]) {
      expect(resolveR1(host, {})).toBe("strict");
      for (const value of ["", "bogus", "STRICT", "strict"]) expect(resolveR1(host, { SHOAL_GUARD_R1: value })).toBe("strict");
      expect(resolveR1(host, { SHOAL_GUARD_R1: "declare" })).toBe("declare");
      expect(resolveR1(host, { SHOAL_GUARD_R1: "classified" })).toBe("classified");
      expect(resolveR1(host, { SHOAL_GUARD_R1: "off" })).toBe("off");
    }
  });

  test("hosts that cannot declare keep the v3.1.0 rule", () => {
    for (const host of ["grok", "agy", "opencode"]) {
      for (const value of ["", "declare", "strict", "bogus", "classified"]) {
        expect(resolveR1(host, { SHOAL_GUARD_R1: value })).toBe("classified");
      }
      expect(resolveR1(host, { SHOAL_GUARD_R1: "off" })).toBe("off");
    }
  });
});
