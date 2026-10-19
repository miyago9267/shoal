#!/usr/bin/env python3
"""Hook latency baseline (docs/specs/code-restructure T0.1): p50 / p95 of the registered claude entry
`run.sh shoal_guard.py --host claude --plugin` for SessionStart, PreToolUse(Bash) and PreToolUse(Edit).

Not a unit test.  Run it with the working directory under a real (non-/tmp) directory, because the guard exempts /tmp:
    cd ~/shoal-live-360 && python3 <repo>/tests/bench_hook_latency.py [-n 200] [--json]
State and cache go to a throwaway HOME-like directory, so the user's guard state is untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "plugins" / "claude-guard" / "hooks"


def payloads(cwd: str) -> dict:
    base = {"session_id": "bench-s1", "prompt_id": "bench-p1", "cwd": cwd}
    return {
        "SessionStart": {**base, "hook_event_name": "SessionStart", "source": "startup"},
        "PreToolUse(Bash)": {**base, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                             "tool_input": {"command": "ls -l"}},
        "PreToolUse(Edit)": {**base, "hook_event_name": "PreToolUse", "tool_name": "Edit",
                             "tool_input": {"file_path": os.path.join(cwd, "bench-target.txt")}},
    }


def percentile(sorted_ms: list[float], q: float) -> float:
    return sorted_ms[min(len(sorted_ms) - 1, int(round(q * (len(sorted_ms) - 1))))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=200, help="runs per event")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    cwd = os.path.realpath(os.getcwd())
    if cwd == "/tmp" or cwd.startswith(("/tmp/", "/private/tmp")):
        print("cwd is under /tmp, which the guard exempts: run from another directory", file=sys.stderr)
        return 2
    results = {}
    with tempfile.TemporaryDirectory(prefix=".bench-hook-", dir=os.path.expanduser("~")) as scratch:
        env = {**os.environ, "HOME": scratch, "XDG_STATE_HOME": os.path.join(scratch, "state"),
               "XDG_CACHE_HOME": os.path.join(scratch, "cache"), "XDG_DATA_HOME": os.path.join(scratch, "data")}
        cmd = ["/bin/sh", str(HOOKS / "run.sh"), str(HOOKS / "shoal_guard.py"), "--host", "claude", "--plugin"]
        for name, payload in payloads(cwd).items():
            data = json.dumps(payload)
            subprocess.run(cmd, input=data, text=True, capture_output=True, env=env, cwd=cwd)  # warm the bytecode cache
            samples = []
            for _ in range(args.n):
                start = time.perf_counter()
                subprocess.run(cmd, input=data, text=True, capture_output=True, env=env, cwd=cwd)
                samples.append((time.perf_counter() - start) * 1000)
            samples.sort()
            results[name] = {"n": args.n, "p50_ms": round(statistics.median(samples), 2),
                             "p95_ms": round(percentile(samples, 0.95), 2)}
    if args.json:
        print(json.dumps(results, indent=1))
    else:
        for name, r in results.items():
            print("%-18s n=%-4d p50=%7.2f ms  p95=%7.2f ms" % (name, r["n"], r["p50_ms"], r["p95_ms"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
