// Replays tests/fixtures/fast_switch_vectors.json (shared with hooks/shoal_guard.py fast_switch).
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fastSwitch } from "../src/guard/core.ts";

const REPO_ROOT = resolve(import.meta.dir, "..", "..", "..", "..");
const doc = JSON.parse(
  readFileSync(join(REPO_ROOT, "tests", "fixtures", "fast_switch_vectors.json"), "utf8"),
) as { vectors: { name: string; prompt: string; fast: "on" | "off" | "none" }[] };

describe("fastSwitch", () => {
  test("the shared vector file is not empty", () => {
    expect(doc.vectors.length).toBeGreaterThanOrEqual(30);
  });
  for (const vector of doc.vectors) {
    test(vector.name, () => {
      expect(fastSwitch(vector.prompt) ?? "none").toBe(vector.fast);
    });
  }
  test("non-string prompts never switch", () => {
    expect(fastSwitch(null)).toBeNull();
    expect(fastSwitch(7)).toBeNull();
  });
});
