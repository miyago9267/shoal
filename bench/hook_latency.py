#!/usr/bin/env python3
"""Hook latency bench: wall time of each Claude guard hook event, as the host runs it.

Runs every command of plugins/claude-guard/hooks/hooks.json through `sh -c` (the way Claude Code runs hook
commands) N times with a synthetic payload, cwd a temp dir under ~/shoal-live-360, and prints p50/p90 in ms.
XDG_DATA_HOME / XDG_STATE_HOME point at a temp dir: the real chain manifest is copied in and the interpreter is
recorded there the way `shoal_install.py --update --apply` does, so the measured path matches an installed machine
without writing guard state into the real data dir.

Usage: python3 bench/hook_latency.py [-n 20] [--root plugins/claude-guard]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import shoal_install  # noqa: E402

TOOL_INPUT = {
    "Bash": {"command": "git status"},
    "Edit": {"file_path": "README.md", "old_string": "a", "new_string": "b"},
    "Agent": {
        "subagent_type": "shoal:executor",
        "description": "bench",
        "prompt": "bench",
    },
}


def _payload(event: str, matcher: str, cwd: str, sid: str) -> dict:
    tool = matcher.split("|")[0] if matcher else ""
    base = {
        "session_id": sid,
        "transcript_path": "",
        "cwd": cwd,
        "hook_event_name": event,
    }
    if event == "UserPromptSubmit":
        base["prompt"] = "fix the typo in README"
    elif event == "SubagentStart":
        base.update(agent_id="bench-agent", agent_type="shoal:executor")
    elif event == "Stop":
        base["stop_hook_active"] = False
    elif event == "SessionEnd":
        base["reason"] = "other"
    if tool:
        base.update(tool_name=tool, tool_input=TOOL_INPUT.get(tool, TOOL_INPUT["Edit"]))
        if event.startswith("PostToolUse"):
            base["tool_response"] = {"stdout": "", "stderr": "", "interrupted": False}
    return base


def _pct(values: list, q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=20)
    parser.add_argument("--root", default=str(REPO / "plugins" / "claude-guard"))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    hooks = json.loads((root / "hooks" / "hooks.json").read_text())["hooks"]
    live = Path.home() / "shoal-live-360"
    live.mkdir(exist_ok=True)
    real_data = (
        Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        / "shoal"
    )
    with (
        tempfile.TemporaryDirectory(dir=live, prefix="hook-latency-") as cwd,
        tempfile.TemporaryDirectory(prefix="hook-latency-xdg-") as xdg,
    ):
        data = Path(xdg) / "data" / "shoal"
        data.mkdir(parents=True)
        if (real_data / "modules.json").is_file():
            shutil.copy2(real_data / "modules.json", data / "modules.json")
        env = dict(
            os.environ,
            CLAUDE_PLUGIN_ROOT=str(root),
            XDG_DATA_HOME=str(Path(xdg) / "data"),
            XDG_STATE_HOME=str(Path(xdg) / "state"),
        )
        print("interpreter record:", shoal_install.record_interpreter(env))
        print("%-34s %8s %8s" % ("event", "p50 ms", "p90 ms"))
        for event, groups in hooks.items():
            for group in groups:
                matcher = group.get("matcher", "")
                for hook in group["hooks"]:
                    times = []
                    for i in range(args.n):
                        raw = json.dumps(
                            _payload(event, matcher, cwd, "bench-%d" % i)
                        ).encode()
                        started = time.perf_counter()
                        subprocess.run(
                            ["sh", "-c", hook["command"]],
                            input=raw,
                            cwd=cwd,
                            env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                        )
                        times.append((time.perf_counter() - started) * 1000)
                    label = event + ("(%s)" % matcher.split("|")[0] if matcher else "")
                    print(
                        "%-34s %8.0f %8.0f"
                        % (label, _pct(times, 0.5), _pct(times, 0.9))
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
