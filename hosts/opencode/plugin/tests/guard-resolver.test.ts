// Unit tests for lenientRealpath: mirrors Python os.path.realpath(strict=False).
import { afterEach, describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { lenientRealpath } from "../src/guard/core.ts";

const dirs: string[] = [];
function tmp(): string {
  const d = mkdtempSync(join(tmpdir(), "resolver-"));
  dirs.push(d);
  return realpathSync(d);
}
afterEach(() => {
  while (dirs.length) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe("lenientRealpath", () => {
  test("missing file under symlinked root resolves the existing prefix", () => {
    const base = tmp();
    mkdirSync(join(base, "real"));
    symlinkSync(join(base, "real"), join(base, "lnk"));
    expect(lenientRealpath(join(base, "lnk", "new.txt"))).toBe(join(base, "real", "new.txt"));
  });

  test("missing nested tail is kept and .. collapsed lexically", () => {
    const base = tmp();
    mkdirSync(join(base, "real"));
    symlinkSync(join(base, "real"), join(base, "lnk"));
    expect(lenientRealpath(join(base, "lnk", "a", "b", "..", "c.txt"))).toBe(join(base, "real", "a", "c.txt"));
  });

  test("/tmp new file matches realpath of /tmp", () => {
    expect(lenientRealpath("/tmp/shoal-new-file.txt")).toBe(join(realpathSync("/tmp"), "shoal-new-file.txt"));
  });
});
