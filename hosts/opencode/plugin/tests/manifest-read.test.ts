// Issue #26: the module manifest is read only when it is a regular file owned by the current user.
// Mirrors ChainCliTests.test_fifo_manifest_* / test_foreign_owned_manifest_* in tests/test_shoal_guard.py.
import { afterEach, describe, expect, spyOn, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chainMembers } from "../src/guard/chain.ts";
import { dispatchGuardSelected } from "../src/guard/core.ts";

const posix = process.platform !== "win32";
const dirs: string[] = [];

function sandbox(): string {
  const dir = mkdtempSync(join(tmpdir(), "shoal-manifest-"));
  dirs.push(dir);
  return dir;
}

afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("module manifest read (#26)", () => {
  test.skipIf(!posix)("a FIFO manifest returns at once and keeps the guard on", () => {
    const home = sandbox();
    const fifo = join(home, "chain.fifo");
    expect(spawnSync("mkfifo", [fifo]).status).toBe(0);
    const env = { SHOAL_GUARD_CHAIN_FILE: fifo };
    const started = performance.now();
    expect(chainMembers("claude", env, home)).toEqual([]);
    expect(dispatchGuardSelected("claude", env, home)).toBe(true);
    expect(performance.now() - started).toBeLessThan(1000);
  });

  test.skipIf(!posix)("a manifest owned by another uid supplies no chain and does not switch the guard off", () => {
    const home = sandbox();
    const manifest = join(home, "chain.json");
    writeFileSync(
      manifest,
      JSON.stringify({
        chain: [{ name: "m0", command: ["true"], hosts: ["claude"], order: 0 }],
        claude: { modules: ["core"], version: "3.8.0" },
      }),
    );
    const env = { SHOAL_GUARD_CHAIN_FILE: manifest };
    expect(chainMembers("claude", env, home)).toHaveLength(1);
    expect(dispatchGuardSelected("claude", env, home)).toBe(false);
    const uid = process.getuid!();
    const spy = spyOn(process, "getuid").mockReturnValue(uid + 1);
    try {
      expect(chainMembers("claude", env, home)).toEqual([]);
      expect(dispatchGuardSelected("claude", env, home)).toBe(true);
    } finally {
      spy.mockRestore();
    }
  });
});
