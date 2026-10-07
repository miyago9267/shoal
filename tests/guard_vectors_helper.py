"""Replay tests/fixtures/guard_vectors.json against hooks/shoal_guard.py.

Shared by tests/test_shoal_guard.py.  The vectors are at the
normalized-event level so another implementation (OpenCode TypeScript) can replay them.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

ROOT = Path(__file__).resolve().parents[1]
VECTORS_PATH = ROOT / "tests" / "fixtures" / "guard_vectors.json"
TOOL_NAME_BY_KIND = {"edit": "Edit", "dispatch": "Agent", "other": "Read"}


def load_vectors() -> Dict[str, Any]:
    return json.loads(VECTORS_PATH.read_text(encoding="utf-8"))


def scratch_base() -> str:
    """A directory for temp HOMEs that is not itself under an exempt /tmp root."""
    base = os.path.realpath(tempfile.gettempdir())
    if base == "/tmp" or base.startswith("/tmp/") or base.startswith("/private/tmp"):
        return str(ROOT)
    return base


class Sandbox:
    """Temp HOME with $WORK and $TMPDIR beneath it."""

    def __init__(self) -> None:
        self.root = os.path.realpath(tempfile.mkdtemp(prefix=".guard-vec-", dir=scratch_base()))
        self.home = os.path.join(self.root, "home")
        self.work = os.path.join(self.home, "work")
        self.tmpdir = os.path.join(self.home, "tmpdir")
        for path in (self.home, self.work, self.tmpdir):
            os.mkdir(path, 0o700)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def env(self, extra: Optional[Dict[str, Optional[str]]]) -> Dict[str, str]:
        env = {"HOME": self.home, "XDG_STATE_HOME": os.path.join(self.home, "xdg-state"), "TMPDIR": "$TMPDIR"}
        for key, value in (extra or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return {k: self.sub(v) for k, v in env.items()}

    def state_base(self, env: Dict[str, str]) -> str:
        xdg = env.get("XDG_STATE_HOME", "")
        return xdg if xdg and os.path.isabs(xdg) else os.path.join(self.home, ".local", "state")

    def sub(self, value: Any, state: Optional[str] = None) -> Any:
        if isinstance(value, str):
            value = value.replace("$HOME", self.home).replace("$WORK", self.work).replace("$TMPDIR", self.tmpdir)
            return value.replace("$STATE", state) if state else value
        if isinstance(value, list):
            return [self.sub(v, state) for v in value]
        if isinstance(value, dict):
            return {self.sub(k, state): self.sub(v, state) for k, v in value.items()}
        return value


def mkdirs(path: str, home: str) -> None:
    """makedirs with 0700 for every component created below HOME."""
    missing: List[str] = []
    cursor = path
    while cursor and not os.path.lexists(cursor):
        missing.append(cursor)
        cursor = os.path.dirname(cursor)
    for item in reversed(missing):
        os.mkdir(item, 0o700)


def normalize_event(step_event: Dict[str, Any], vector_host: str, sandbox: Sandbox) -> Dict[str, Any]:
    event: Dict[str, Any] = {
        "host": vector_host,
        "kind": None,
        "session_id": "s1",
        "turn_id": "t1",
        "cwd": "$WORK",
        "is_subagent": False,
        "role": None,
        "tool_name": None,
        "tool_kind": None,
        "paths": [],
        "dispatched_role": None,
    }
    event.update(step_event)
    if event["tool_name"] is None and event["kind"] == "tool":
        event["tool_name"] = TOOL_NAME_BY_KIND.get(event["tool_kind"])
    return sandbox.sub(event)


def apply_setup(setup: Dict[str, Any], sandbox: Sandbox, env: Dict[str, str], module: Any, state: str) -> None:
    sub = lambda v: sandbox.sub(v, state)  # noqa: E731
    for path in sub(setup.get("dirs", [])):
        mkdirs(path, sandbox.home)
    for link, target in sub(setup.get("symlinks", {})).items():
        mkdirs(os.path.dirname(link), sandbox.home)
        os.symlink(target, link)
    for path, text in sub(setup.get("write", {})).items():
        mkdirs(os.path.dirname(path), sandbox.home)
        Path(path).write_text(text, encoding="utf-8")
    for path, mode in sub(setup.get("chmod", {})).items():
        os.chmod(path, int(mode, 8))
    needs_guard = any(k in setup for k in ("turn", "turn_legacy_prompt_id", "state_file", "turn_file", "log_prefill_bytes"))
    if not needs_guard:
        return
    guard = module._guard_dir(env, Path(sandbox.home))
    if guard is None:
        raise RuntimeError("guard dir unavailable during setup")
    for key, id_key in (("turn", "turn_id"), ("turn_legacy_prompt_id", "prompt_id")):
        if key in setup:
            turn = setup[key]
            (guard / "turns" / (turn["session"] + ".json")).write_text(
                json.dumps({id_key: turn["turn_id"], "role": turn["role"]}), encoding="utf-8")
    for key, sub_dir in (("state_file", "state"), ("turn_file", "turns")):
        if key in setup:
            (guard / sub_dir / (setup[key]["session"] + ".json")).write_text(setup[key]["content"], encoding="utf-8")
    if "log_prefill_bytes" in setup:
        (guard / "guard.jsonl").write_text("x" * int(setup["log_prefill_bytes"]), encoding="utf-8")


@contextlib.contextmanager
def foreign_owner(module: Any, targets: List[str]) -> Iterator[None]:
    """Make _open_private see the given files as owned by another uid."""
    original, real_uid = module._open_private, module._uid
    wanted = set(targets)

    def wrapped(path: Any, flags: int) -> Optional[int]:
        if str(path) not in wanted:
            return original(path, flags)
        module._uid = lambda: real_uid() + 1
        try:
            return original(path, flags)
        finally:
            module._uid = real_uid

    module._open_private = wrapped
    try:
        yield
    finally:
        module._open_private = original


def run_vector(vector: Dict[str, Any], whitelist: List[str], module: Any) -> List[str]:
    """Replay one vector; returns a list of failure descriptions (empty = pass)."""
    failures: List[str] = []
    sandbox = Sandbox()
    try:
        env = sandbox.env(vector.get("env"))
        state = sandbox.state_base(env)
        home = Path(sandbox.home)
        apply_setup(vector.get("setup", {}), sandbox, env, module, state)
        guard_dir = os.path.join(state, "shoal", "guard")
        targets = [os.path.join(guard_dir, rel) for rel in vector.get("foreign_owner", [])]
        host = vector.get("host", "claude")
        with foreign_owner(module, targets):
            for index, step in enumerate(vector["steps"]):
                event = normalize_event(step["event"], host, sandbox)
                result = module.evaluate(event, env, home)
                for key, want in step["expect"].items():
                    if result.get(key) != want:
                        failures.append("%s step %d: %s expected %r got %r" % (vector["name"], index, key, want, result.get(key)))
        failures.extend(check_post(vector, sandbox, state, whitelist))
    except Exception as exc:  # noqa: BLE001 - report as a failed vector
        failures.append("%s: raised %r" % (vector["name"], exc))
    finally:
        sandbox.close()
    return failures


def check_post(vector: Dict[str, Any], sandbox: Sandbox, state: str, whitelist: List[str]) -> List[str]:
    failures: List[str] = []
    sub = lambda v: sandbox.sub(v, state)  # noqa: E731
    name = vector["name"]
    for path in sub(vector.get("files_exist", [])):
        if not os.path.lexists(path):
            failures.append("%s: expected %s to exist" % (name, path))
    for path in sub(vector.get("files_absent", [])):
        if os.path.lexists(path):
            failures.append("%s: expected %s to be absent" % (name, path))
    for path, mode in sub(vector.get("modes", {})).items():
        try:
            got = stat.S_IMODE(os.lstat(path).st_mode)
        except OSError:
            failures.append("%s: %s missing for mode check" % (name, path))
            continue
        if got != int(mode, 8):
            failures.append("%s: %s mode %o != %s" % (name, path, got, mode))
    for path, text in sub(vector.get("file_contents", {})).items():
        if Path(path).read_text(encoding="utf-8") != text:
            failures.append("%s: %s content changed" % (name, path))
    log_path = os.path.join(state, "shoal", "guard", "guard.jsonl")
    log_text = Path(log_path).read_text(encoding="utf-8") if os.path.isfile(log_path) else ""
    if "log_prefill_bytes" not in vector.get("setup", {}):
        for line in log_text.splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                failures.append("%s: non-JSON log line" % name)
                continue
            extra = set(record) - set(whitelist)
            if extra:
                failures.append("%s: log fields outside whitelist: %s" % (name, sorted(extra)))
    for needle in sub(vector.get("log_contains", [])):
        if needle not in log_text:
            failures.append("%s: log lacks %r" % (name, needle))
    for needle in sub(vector.get("log_lacks", [])):
        if needle in log_text:
            failures.append("%s: log must not contain %r" % (name, needle))
    if "log_size_max" in vector and len(log_text.encode()) > vector["log_size_max"]:
        failures.append("%s: log grew past cap" % name)
    return failures
