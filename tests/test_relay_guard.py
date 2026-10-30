"""cross-vendor-relay T1.4: the guard's SHOAL_RELAY_ROLE adoption (S1.11, Security review F4/F5).

A session is the relayed named role only on codex, for executor / applier, with the runner's
`<guard dir>/relay-<nonce>` file ({"role", "pid"}, regular, ours, not a symlink, live pid).  Anything less leaves
the guard exactly as before: every shared vector is replayed with the relay env and must not change.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import guard_vectors_helper as helper  # noqa: E402
import shoal_guard as guard  # noqa: E402
import shoal_relay  # noqa: E402

NONCE = "0123456789abcdef0123456789abcdef"
RELAY_ENV = {"SHOAL_RELAY_ROLE": "executor", "SHOAL_RELAY_NONCE": NONCE}
SPAWN_PAYLOAD = {  # tests/fixtures/codex_subagent_tool_shapes.json main_spawn_pre; T1.4 probe, codex-cli 0.160.1
    "hook_event_name": "PreToolUse",
    "session_id": "relay-s1",
    "turn_id": "relay-t1",
    "cwd": None,
    "model": "m",
    "permission_mode": "default",
    "transcript_path": None,
    "tool_name": "collaborationspawn_agent",
    "tool_use_id": "u1",
    "tool_input": {"agent_type": "scout", "message": "hi", "task_name": "t"},
}


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


@unittest.skipIf(os.name == "nt", "shoal guard is POSIX-only; it is a no-op on Windows")
class RelayVectorRegressionTests(unittest.TestCase):
    """S0.4 + S1.11: the relay env without a trusted nonce, or on another host, changes no vector result."""

    def setUp(self) -> None:
        self.data = helper.load_vectors()

    def replay(
        self, vector: Dict[str, Any], extra_env: Dict[str, Optional[str]]
    ) -> list:
        vec = dict(vector, env={**(vector.get("env") or {}), **extra_env})
        return helper.run_vector(
            vec, self.data["log_whitelist"], guard, self.data.get("env_defaults")
        )

    def test_env_only_without_nonce_file_is_unchanged_on_every_host(self) -> None:
        for vector in self.data["vectors"]:
            with self.subTest(vector["name"]):
                self.assertEqual(self.replay(vector, RELAY_ENV), [])

    def test_other_hosts_with_env_and_valid_nonce_are_unchanged(self) -> None:
        real = guard.evaluate

        def with_nonce(
            event: Dict[str, Any], env: Dict[str, str], home: Path
        ) -> Dict[str, Any]:
            gdir = Path(guard._state_base(env, home)) / "shoal" / "guard"
            if gdir.is_dir() and not gdir.is_symlink():
                path = gdir / ("relay-" + NONCE)
                if not path.exists():
                    path.write_text(
                        json.dumps({"role": "executor", "pid": os.getpid()}),
                        encoding="utf-8",
                    )
                    os.chmod(path, 0o600)
            return real(event, env, home)

        with mock.patch.object(guard, "evaluate", with_nonce):
            for vector in self.data["vectors"]:
                if vector.get("host", "claude") == "codex":
                    continue
                with self.subTest(vector["name"]):
                    self.assertEqual(self.replay(vector, RELAY_ENV), [])


@unittest.skipIf(os.name == "nt", "shoal guard is POSIX-only; it is a no-op on Windows")
class RelayAdoptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.box = helper.Sandbox()
        self.addCleanup(self.box.close)
        self.home = Path(self.box.home)
        self.base_env = self.box.env({})
        self.gdir = guard._guard_dir(self.base_env, self.home)
        assert self.gdir is not None
        self.nonce_path = self.gdir / ("relay-" + NONCE)

    def env(self, **extra: str) -> Dict[str, str]:
        return {**self.base_env, **RELAY_ENV, **extra}

    def write_nonce(self, body: Any = None, path: Optional[Path] = None) -> Path:
        path = path or self.nonce_path
        text = (
            body
            if isinstance(body, str)
            else json.dumps(body or {"role": "executor", "pid": os.getpid()})
        )
        path.write_text(text, encoding="utf-8")
        os.chmod(path, 0o600)
        return path

    def event(self, host: str = "codex", **fields: Any) -> Dict[str, Any]:
        return helper.normalize_event(fields, host, self.box)

    def spawn(self, host: str = "codex") -> Dict[str, Any]:
        name = "collaborationspawn_agent" if host == "codex" else None
        return self.event(
            host,
            kind="tool",
            tool_kind="dispatch",
            tool_name=name,
            dispatched_role="scout",
        )

    def edit(self, host: str = "codex") -> Dict[str, Any]:
        name = "apply_patch" if host == "codex" else None
        return self.event(
            host, kind="tool", tool_kind="edit", tool_name=name, paths=["$WORK/a.py"]
        )

    def log(self) -> str:
        path = self.gdir / "guard.jsonl"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def assert_unchanged(self, events: list, env: Dict[str, str], reason: str) -> None:
        """Same decisions as without any relay env, and the rejection is logged."""
        for ev in events:
            plain = guard.evaluate(
                dict(ev), self.base_env, self.home
            )
            got = guard.evaluate(dict(ev), env, self.home)
            self.assertEqual(got, plain, ev)
        self.assertIn('"skip_reason":"%s"' % reason, self.log())
        self.assertNotIn("relay_adopt", self.log())

    # -- adopted ----------------------------------------------------------------
    def test_adopted_session_denies_spawn_agent_and_collaboration_tools(self) -> None:
        self.write_nonce()
        result = guard.evaluate(self.spawn(), self.env(), self.home)
        self.assertEqual((result["decision"], result["rule"]), ("deny", "RELAY"))
        self.assertIn("`executor`", result["reason"])
        other = self.event(
            kind="tool", tool_kind="other", tool_name="collaborationwait_agent"
        )
        self.assertEqual(
            guard.evaluate(other, self.env(), self.home)["decision"], "deny"
        )
        self.assertEqual(
            guard.evaluate(
                self.event(kind="tool", tool_kind="other", tool_name="Read"),
                self.env(),
                self.home,
            )["decision"],
            "none",
        )

    def test_adopted_spawn_is_denied_in_every_mode(self) -> None:
        self.write_nonce()
        for mode in ("enforce", "shadow", "off"):
            with self.subTest(mode):
                self.assertEqual(
                    guard.evaluate(self.spawn(), self.env(SHOAL_GUARD=mode), self.home)[
                        "decision"
                    ],
                    "deny",
                )

    def test_adopted_session_edits_without_a_dispatch_and_stop_does_not_block(
        self,
    ) -> None:
        self.write_nonce()
        env = self.env()
        main_edit = guard.evaluate(self.edit(), self.base_env, self.home)
        self.assertEqual(
            main_edit["decision"], "deny"
        )  # control: codex main must dispatch first (R1)
        for ev in (
            self.event(kind="prompt"),
            self.edit(),
            self.event(
                kind="tool",
                tool_kind="shell",
                tool_name="Bash",
                command="echo x > $WORK/b.py",
            ),
            self.event(kind="stop", stop_hook_active=False),
        ):
            with self.subTest(ev["kind"]):
                self.assertEqual(guard.evaluate(ev, env, self.home)["decision"], "none")
        log = self.log()
        self.assertIn('"decision":"relay_adopt"', log)
        self.assertIn('"agent_type":"executor"', log)
        self.assertNotIn(NONCE, log)

    def test_applier_role_is_adopted_too(self) -> None:
        self.write_nonce({"role": "applier", "pid": os.getpid()})
        result = guard.evaluate(
            self.spawn(), self.env(SHOAL_RELAY_ROLE="applier"), self.home
        )
        self.assertEqual((result["decision"], result["rule"]), ("deny", "RELAY"))

    def test_cli_denies_a_real_codex_spawn_payload(self) -> None:
        self.write_nonce()
        payload = dict(SPAWN_PAYLOAD, cwd=self.box.work)
        out = guard.run("codex", json.dumps(payload).encode(), self.env())
        body = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(
            (body["hookEventName"], body["permissionDecision"]), ("PreToolUse", "deny")
        )
        patch = dict(
            payload,
            tool_name="apply_patch",
            tool_input={
                "command": "*** Begin Patch\n*** Add File: a.py\n+x\n*** End Patch\n"
            },
        )
        self.assertIsNone(guard.run("codex", json.dumps(patch).encode(), self.env()))

    def test_nonce_written_by_the_runner_is_adopted(self) -> None:
        env = self.env()
        path = shoal_relay._create_nonce(env, "executor")
        self.addCleanup(lambda: path.exists() and path.unlink())
        self.assertEqual(path, self.nonce_path)
        self.assertEqual(guard.evaluate(self.spawn(), env, self.home)["rule"], "RELAY")

    # -- rejected: identical to no relay env ------------------------------------
    def test_env_only_without_nonce_file(self) -> None:
        self.assert_unchanged(
            [self.spawn(), self.edit()], self.env(), "relay_nonce_file"
        )

    def test_host_claude_with_env_and_valid_nonce(self) -> None:
        self.write_nonce()
        self.assert_unchanged(
            [self.spawn("claude"), self.edit("claude")], self.env(), "relay_host"
        )

    def test_stale_pid(self) -> None:
        self.write_nonce({"role": "executor", "pid": _dead_pid()})
        self.assert_unchanged([self.spawn(), self.edit()], self.env(), "relay_pid_dead")

    def test_symlinked_nonce(self) -> None:
        target = self.write_nonce(path=self.gdir / "state" / "elsewhere.json")
        os.symlink(target, self.nonce_path)
        self.assert_unchanged(
            [self.spawn(), self.edit()], self.env(), "relay_nonce_file"
        )

    def test_fifo_nonce_does_not_block(self) -> None:
        os.mkfifo(self.nonce_path, 0o600)
        self.assert_unchanged([self.spawn()], self.env(), "relay_nonce_file")

    def test_foreign_owner_nonce(self) -> None:
        self.write_nonce()
        with helper.foreign_owner(guard, [str(self.nonce_path)]):
            self.assert_unchanged([self.spawn()], self.env(), "relay_nonce_file")

    def test_role_mismatch(self) -> None:
        self.write_nonce({"role": "applier", "pid": os.getpid()})
        self.assert_unchanged([self.spawn()], self.env(), "relay_role_mismatch")

    def test_role_outside_executor_applier(self) -> None:
        self.write_nonce({"role": "security-executor", "pid": os.getpid()})
        self.assert_unchanged(
            [self.spawn()], self.env(SHOAL_RELAY_ROLE="security-executor"), "relay_role"
        )

    def test_bad_nonce_format(self) -> None:
        self.write_nonce()
        for nonce in ("../relay-" + NONCE, NONCE.upper(), NONCE + "\n", NONCE[:-1], ""):
            with self.subTest(nonce=nonce):
                self.assert_unchanged(
                    [self.spawn()],
                    self.env(SHOAL_RELAY_NONCE=nonce),
                    "relay_nonce_format",
                )

    def test_bad_nonce_content(self) -> None:
        for body in (
            "not json",
            "[]",
            {"role": "executor"},
            {"role": "executor", "pid": os.getpid(), "x": 1},
            {"role": "executor", "pid": True},
            {"role": "executor", "pid": 0},
            {"role": "executor", "pid": -1},
            {"role": "executor", "pid": str(os.getpid())},
        ):
            with self.subTest(body=body):
                self.write_nonce(body)
                self.assert_unchanged([self.spawn()], self.env(), "relay_nonce_content")

    def test_off_guard_logs_no_rejection(self) -> None:
        guard.evaluate(self.edit(), self.env(SHOAL_GUARD="off"), self.home)
        self.assertNotIn("relay_ignore", self.log())


if __name__ == "__main__":
    unittest.main()
