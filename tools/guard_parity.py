#!/usr/bin/env python3
"""One-off parity check: replay the Claude guard vectors through the shoal guard and the dotfile guard.

Not run in CI.  Both guards get the same raw Claude payloads in a temp HOME; the script prints
every step whose allow/deny outcome differs and tags it with the R2 change that explains it
(spec docs/specs/dispatch-enforcement/SPEC.md R2): realpath, read-only dispatch no longer
unlocks, `#direct` replaced by SHOAL_GUARD_DIRECT.  Exit 1 when a difference has no tag.

    python3 tools/guard_parity.py [--old PATH_TO_pilotfish-dispatch-guard.py]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "tests"))

import guard_vectors_helper as helper  # noqa: E402
import shoal_guard  # noqa: E402

DEFAULT_OLD = Path.home() / "dotfile/config/ai/claude/hooks/pilotfish-dispatch-guard.py"
ENV_ALIASES = {"SHOAL_GUARD": "PILOTFISH_GUARD", "SHOAL_GUARD_MAX_FILES": "PILOTFISH_GUARD_MAX_FILES"}
WRITE_ROLES = {"executor", "mech-executor", "security-executor", "sol-executor"}


def raw_payload(event: dict) -> dict:
    """Normalized event -> Claude hook payload."""
    payload: dict = {"cwd": event["cwd"]}
    if event["session_id"] is not None:
        payload["session_id"] = event["session_id"]
    if event["turn_id"] is not None:
        payload["prompt_id"] = event["turn_id"]
    if event["kind"] == "prompt":
        return {**payload, "hook_event_name": "UserPromptSubmit", "prompt": event.get("prompt_text", "work on it")}
    payload.update({"hook_event_name": "PreToolUse", "tool_name": event["tool_name"], "tool_input": {}})
    if event["tool_kind"] == "edit" and event["paths"]:
        payload["tool_input"] = {"file_path": event["paths"][0]}
    if event["tool_kind"] == "dispatch" and event["dispatched_role"]:
        payload["tool_input"] = {"subagent_type": event["dispatched_role"]}
    return payload


def call(script: Path, args: list, payload: dict, env: dict) -> str:
    proc = subprocess.run([sys.executable, str(script), *args], input=json.dumps(payload).encode(),
                          capture_output=True, env=env, timeout=30)
    return "deny" if b'"permissionDecision": "deny"' in proc.stdout or b'"permissionDecision":"deny"' in proc.stdout else "allow"


def old_turn_file(home: str, setup: dict) -> None:
    for key in ("turn", "turn_legacy_prompt_id"):
        if key in setup:
            turns = Path(home, ".local/state/miyago/jev/turns")
            for part in (Path(home, ".local"), Path(home, ".local/state"), Path(home, ".local/state/miyago"),
                         Path(home, ".local/state/miyago/jev"), turns):
                part.mkdir(mode=0o700, exist_ok=True)
            (turns / (setup[key]["session"] + ".json")).write_text(
                json.dumps({"prompt_id": setup[key]["turn_id"], "role": setup[key]["role"]}), encoding="utf-8")


def tags_for(vector: dict, index: int, sandbox: helper.Sandbox, direct_prompt: bool) -> list:
    """Which R2 change can explain a difference at this step (looks at the whole history, since the
    old guard's count depends on earlier paths)."""
    tags = []
    history = [helper.normalize_event(s["event"], "claude", sandbox) for s in vector["steps"][: index + 1]]
    for event in history:
        for raw in event["paths"]:
            full = raw if os.path.isabs(raw) else os.path.join(event["cwd"], raw)
            if os.path.realpath(full) != os.path.normpath(full) or ".." in raw.split("/") or not os.path.isabs(raw):
                tags.append("R2 realpath")
    if any(e["tool_kind"] == "dispatch" and e["dispatched_role"] not in WRITE_ROLES for e in history[:-1]):
        tags.append("R2 read-only dispatch no longer unlocks")
    if (vector.get("env") or {}).get("SHOAL_GUARD_DIRECT") == "1" or direct_prompt:
        tags.append("R2 #direct replaced by SHOAL_GUARD_DIRECT")
    return sorted(set(tags))


def replay(vector: dict, old_script: Path, direct_prompt: bool = False) -> list:
    sandbox = helper.Sandbox()
    rows = []
    try:
        env = sandbox.env(vector.get("env"))
        state = sandbox.state_base(env)
        helper.apply_setup(vector.get("setup", {}), sandbox, env, shoal_guard, state)
        old_turn_file(sandbox.home, vector.get("setup", {}))
        old_env = {k: v for k, v in env.items() if k not in ENV_ALIASES and k != "SHOAL_GUARD_DIRECT"}
        old_env.update({ENV_ALIASES[k]: v for k, v in env.items() if k in ENV_ALIASES})
        old_env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
        new_env = {**env, "PATH": old_env["PATH"]}
        for index, step in enumerate(vector["steps"]):
            event = helper.normalize_event(step["event"], "claude", sandbox)
            if direct_prompt and event["kind"] == "prompt":
                event["prompt_text"] = "#direct quick fix"
            payload = raw_payload(event)
            new = call(ROOT / "hooks/shoal_guard.py", ["--host", "claude"], payload, new_env)
            old = call(old_script, [], payload, old_env)
            rows.append((vector["name"], index, old, new, event, tags_for(vector, index, sandbox, direct_prompt)))
    finally:
        sandbox.close()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--old", type=Path, default=DEFAULT_OLD)
    args = parser.parse_args()
    if not args.old.is_file():
        print("old guard not found: %s" % args.old)
        return 2
    vectors = [v for v in helper.load_vectors()["vectors"]
               if v.get("host", "claude") == "claude" and v.get("parity", True) is not False
               and not any(s["event"].get("is_subagent") for s in v["steps"])]
    rows = []
    for vector in vectors:
        rows.extend(replay(vector, args.old))
    # `#direct` in the prompt: the old guard honors it, the new one does not (R2).
    direct = {"name": "extra_prompt_direct_marker", "env": {"SHOAL_GUARD": "enforce"}, "steps": [
        {"event": {"kind": "prompt", "turn_id": "t1"}},
        *[{"event": {"kind": "tool", "tool_kind": "edit", "turn_id": "t1", "paths": ["$WORK/src/f%d" % i]}} for i in range(4)]]}
    rows.extend(replay(direct, args.old, direct_prompt=True))

    diffs = [r for r in rows if r[2] != r[3]]
    unmapped = [r for r in diffs if not r[5]]
    print("vectors replayed: %d (+1 extra #direct scenario)" % len(vectors))
    print("steps compared: %d  identical: %d  different: %d  unmapped: %d" % (len(rows), len(rows) - len(diffs), len(diffs), len(unmapped)))
    counts = Counter(tag for r in diffs for tag in (r[5] or ["UNMAPPED"]))
    for tag, count in sorted(counts.items()):
        print("  %-45s %d" % (tag, count))
    by_vector = Counter(r[0] for r in diffs)
    for name, count in sorted(by_vector.items()):
        first = next(r for r in diffs if r[0] == name)
        print("  - %s (%d step%s): old=%s new=%s [%s]" % (name, count, "" if count == 1 else "s", first[2], first[3], "; ".join(first[5]) or "UNMAPPED"))
    return 1 if unmapped else 0


if __name__ == "__main__":
    raise SystemExit(main())
