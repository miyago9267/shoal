// OpenCode treats every export of a plugin's entry module as a plugin function and fails the
// whole plugin with "Plugin export is not a function" otherwise (seen live on 1.18.31).
import { afterAll, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const entry = resolve(import.meta.dir, "..", "src", "plugin", "pilotfish-opencode.ts");
const workDir = mkdtempSync(join(tmpdir(), "pilotfish-entry-"));
afterAll(() => rmSync(workDir, { recursive: true, force: true }));

function assertAllFunctions(mod: Record<string, unknown>): void {
  const names = Object.keys(mod);
  expect(names.length).toBeGreaterThan(0);
  for (const name of names) expect([name, typeof mod[name]]).toEqual([name, "function"]);
}

describe("plugin entry exports", () => {
  test("the entry source exports only functions", async () => {
    assertAllFunctions((await import(entry)) as Record<string, unknown>);
  });

  test("the bundled entry exports only functions, as the installers build it", async () => {
    const built = await Bun.build({
      entrypoints: [entry],
      outdir: workDir,
      target: "bun",
      format: "esm",
      naming: "pilotfish-opencode.js",
    });
    expect(built.success).toBe(true);
    const bundle = join(workDir, "pilotfish-opencode.js");
    const mod = (await import(bundle)) as Record<string, unknown>;
    assertAllFunctions(mod);
    expect(typeof mod.default).toBe("function");
  });
});
