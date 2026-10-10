// Replays tests/fixtures/direct_token_vectors.json (shared with hooks/shoal_guard.py has_direct_token).
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { hasDirectToken } from "../src/guard/core.ts";

const REPO_ROOT = resolve(import.meta.dir, "..", "..", "..", "..");
const doc = JSON.parse(
  readFileSync(join(REPO_ROOT, "tests", "fixtures", "direct_token_vectors.json"), "utf8"),
) as { vectors: { name: string; prompt: string; direct: boolean }[] };

describe("hasDirectToken", () => {
  test("the shared vector file is not empty", () => {
    expect(doc.vectors.length).toBeGreaterThanOrEqual(30);
  });
  for (const vector of doc.vectors) {
    test(vector.name, () => {
      expect(hasDirectToken(vector.prompt)).toBe(vector.direct);
    });
  }
  test("non-string prompts never count", () => {
    expect(hasDirectToken(null)).toBe(false);
    expect(hasDirectToken(7)).toBe(false);
    expect(hasDirectToken(undefined)).toBe(false);
  });
});
