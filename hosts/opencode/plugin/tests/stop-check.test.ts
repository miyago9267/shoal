// The completion check (docs/specs/shared-rules B2-B4) is replayed through tests/fixtures/guard_vectors.json
// (guard-vectors.test.ts).  These cases pin the switch and the host table, which the vectors only exercise
// through events.
import { describe, expect, test } from "bun:test";
import { stopEnabled } from "../src/guard/core.ts";

describe("SHOAL_GUARD_STOP", () => {
  test("is on by default and off only for the exact value `off`, on claude and codex", () => {
    for (const host of ["claude", "codex"]) {
      expect(stopEnabled(host, {})).toBe(true);
      expect(stopEnabled(host, { SHOAL_GUARD_STOP: "on" })).toBe(true);
      expect(stopEnabled(host, { SHOAL_GUARD_STOP: "maybe" })).toBe(true);
      expect(stopEnabled(host, { SHOAL_GUARD_STOP: "" })).toBe(true);
      expect(stopEnabled(host, { SHOAL_GUARD_STOP: "off" })).toBe(false);
    }
  });

  test("has no effect on a host that never blocks", () => {
    for (const host of ["grok", "agy", "opencode", ""]) {
      expect(stopEnabled(host, {})).toBe(false);
      expect(stopEnabled(host, { SHOAL_GUARD_STOP: "on" })).toBe(false);
    }
  });
});
