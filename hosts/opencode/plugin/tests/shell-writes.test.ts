// Replays tests/fixtures/shell_write_cases.json (shared with hooks/shoal_guard.py) against the
// TypeScript shell-write detector used by guard rule G5.
import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { shellWriteTargets } from "../src/guard/shell-writes.ts";

const REPO_ROOT = resolve(import.meta.dir, "..", "..", "..", "..");
const doc = JSON.parse(readFileSync(join(REPO_ROOT, "tests", "fixtures", "shell_write_cases.json"), "utf8")) as {
  cases: Array<{ command: string; targets: string[] }>;
};

describe("shellWriteTargets", () => {
  test("fixture is large enough and has unique commands", () => {
    expect(doc.cases.length).toBeGreaterThanOrEqual(60);
    expect(new Set(doc.cases.map((c) => c.command)).size).toBe(doc.cases.length);
  });

  for (const { command, targets } of doc.cases) {
    test(JSON.stringify(command), () => {
      expect(shellWriteTargets(command)).toEqual(targets);
    });
  }

  test("interpreter and copy writes are out of scope", () => {
    for (const command of ["python3 write_it.py", "python3 -c \"import subprocess; subprocess.run(['cp', 'a', 'b'])\"", "cp a b", "mv a b", "git apply x.patch", "dd if=a of=b"]) {
      expect(shellWriteTargets(command)).toEqual([]);
    }
  });

  test("malformed input terminates", () => {
    for (const command of ["cat > ", ">", "echo '", "echo $(", "echo ${", "(( a", "[[ a", "cat <<", "cat <<EOF\nbody", "\\", "echo >(", "tee", "sed -i", "2>", "&>", "(".repeat(400)]) {
      expect(Array.isArray(shellWriteTargets(command))).toBe(true);
    }
  });
});
