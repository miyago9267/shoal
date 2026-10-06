"""Dispatch guard: shared vectors, role table, per-host adapters, CLI behavior."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "tests"))

import guard_vectors_helper as helper  # noqa: E402
import shoal_guard as guard  # noqa: E402

GUARD = ROOT / "hooks" / "shoal_guard.py"


@unittest.skipIf(os.name == "nt", "shoal guard is POSIX-only; it is a no-op on Windows")
class VectorTests(unittest.TestCase):
    def test_shared_vectors(self) -> None:
        data = helper.load_vectors()
        self.assertGreaterEqual(len(data["vectors"]), 90)
        names = [v["name"] for v in data["vectors"]]
        self.assertEqual(len(names), len(set(names)))
        for vector in data["vectors"]:
            with self.subTest(vector["name"]):
                self.assertEqual(helper.run_vector(vector, data["log_whitelist"], guard), [])

    def test_vectors_cover_the_spec_r8_list(self) -> None:
        names = " ".join(v["name"] for v in helper.load_vectors()["vectors"])
        for needle in ("dotdot", "symlink", "dispatch_scout", "dispatch_executor", "skip_missing", "log_whitelist",
                       "xdg_unset", "xdg_relative", "symlinked", "foreign_owner", "r1_", "direct_env", "exempt",
                       "leaf", "verify_edit", "mode_shadow", "agy_forced_shadow"):
            self.assertIn(needle, names)

    def test_log_whitelist_constant_matches_vectors(self) -> None:
        self.assertEqual(list(guard.LOG_FIELDS), helper.load_vectors()["log_whitelist"])


class WindowsNoOpTests(unittest.TestCase):
    def test_run_is_a_silent_no_op_when_os_name_is_nt(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            with mock.patch.object(guard.os, "name", "nt"):
                out = guard.run("claude", b"x" * (guard.MAX_INPUT_BYTES + 1), {"HOME": home})
            self.assertIsNone(out)
            self.assertEqual(list(Path(home).iterdir()), [])


class RoleTableTests(unittest.TestCase):
    def test_role_access_matches_core_and_host_bindings(self) -> None:
        expected = {}
        roles = tomllib.loads((ROOT / "core" / "roles.toml").read_text(encoding="utf-8"))["roles"]
        expected.update({name: spec["access"] for name, spec in roles.items()})
        for binding in sorted((ROOT / "hosts").glob("*/binding.toml")):
            extra = tomllib.loads(binding.read_text(encoding="utf-8")).get("extra_roles", {})
            for name, spec in extra.items():
                self.assertNotIn(name, expected, "%s redefines %s" % (binding, name))
                expected[name] = spec["access"]
        self.assertEqual(guard.ROLE_ACCESS, expected)


class RoleNameTests(unittest.TestCase):
    """K3: only a bare name or the `shoal:` prefix names a known role."""

    def test_normalize_role_uses_an_explicit_allowlist(self) -> None:
        for name, want in (("executor", "executor"), ("shoal:executor", "executor"), ("shoal:verifier", "verifier"),
                           ("x:executor", "x:executor"), ("shoal:shoal:executor", "shoal:executor"),
                           ("SHOAL:executor", "SHOAL:executor"), ("", ""), ("shoal:", "")):
            self.assertEqual(guard.normalize_role(name), want, name)
        self.assertIsNone(guard.normalize_role(None))
        self.assertIsNone(guard.normalize_role(7))

    def test_role_access_sees_through_the_shoal_namespace_only(self) -> None:
        self.assertEqual(guard.role_access("shoal:executor"), "write")
        self.assertEqual(guard.role_access("shoal:verifier"), "verify")
        for bad in ("x:executor", "shoal:shoal:executor", "SHOAL:verifier", "shoal:", None):
            self.assertIsNone(guard.role_access(bad), bad)


class SyntaxTests(unittest.TestCase):
    def test_guard_parses_as_python_39(self) -> None:
        ast.parse(GUARD.read_text(encoding="utf-8"), feature_version=(3, 9))

    def test_default_mode_table(self) -> None:
        self.assertEqual(guard.HOST_DEFAULT_MODE, {"claude": "enforce", "codex": "shadow", "grok": "shadow", "agy": "shadow"})

    def test_valid_id(self) -> None:
        self.assertTrue(guard.valid_id("ses_ab-1"))
        self.assertTrue(guard.valid_id("x" * 128))
        for bad in ("", "x" * 129, "a b", "a/b", "a:b", "..", None, 7):
            self.assertFalse(guard.valid_id(bad), bad)
        self.assertTrue(guard.valid_id("conv_1:2", composed=True))
        self.assertFalse(guard.valid_id("conv/1:2", composed=True))


@unittest.skipIf(os.name == "nt", "shoal guard is POSIX-only; it is a no-op on Windows")
class CliCase(unittest.TestCase):
    """Runs the real script with a temp HOME and XDG_STATE_HOME."""

    def setUp(self) -> None:
        self.sandbox = helper.Sandbox()
        self.addCleanup(self.sandbox.close)
        self.home = self.sandbox.home
        self.work = self.sandbox.work
        self.state = os.path.join(self.home, "xdg-state")
        self.guard_dir = os.path.join(self.state, "shoal", "guard")

    def env(self, **extra: str) -> dict:
        env = {"HOME": self.home, "XDG_STATE_HOME": self.state, "TMPDIR": self.sandbox.tmpdir,
               "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        env.update(extra)
        return env

    def run_guard(self, host: str, payload, **env_extra: str) -> str:
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        proc = subprocess.run([sys.executable, str(GUARD), "--host", host], input=raw, capture_output=True,
                              env=self.env(**env_extra), timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.decode()

    def log_records(self) -> list:
        path = os.path.join(self.guard_dir, "guard.jsonl")
        if not os.path.exists(path):
            return []
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]

    def write_turn(self, session: str, turn: str, role: str) -> None:
        turns = Path(self.guard_dir) / "turns"
        turns.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(turns, 0o700)
        (turns / (session + ".json")).write_text(json.dumps({"turn_id": turn, "role": role}), encoding="utf-8")

    def path(self, name: str) -> str:
        return os.path.join(self.work, name)


def claude_prompt(**kw):
    return {"session_id": "sess-1", "prompt_id": "p-1", "cwd": "WORK", "hook_event_name": "UserPromptSubmit",
            "prompt": "SECRET-PROMPT-TEXT please edit", "transcript_path": "/x/y.jsonl", **kw}


def claude_tool(tool, tool_input, **kw):
    return {"session_id": "sess-1", "prompt_id": "p-1", "cwd": "WORK", "hook_event_name": "PreToolUse",
            "tool_name": tool, "tool_input": tool_input, "tool_use_id": "tu-1", **kw}


class ClaudeAdapterTests(CliCase):
    def test_normalizes_main_edit_and_dispatch(self) -> None:
        event = guard.adapt_claude(claude_tool("MultiEdit", {"file_path": "/r/a.py", "edits": []}))
        self.assertEqual((event["kind"], event["tool_kind"], event["paths"], event["is_subagent"]),
                         ("tool", "edit", ["/r/a.py"], False))
        self.assertEqual((event["session_id"], event["turn_id"]), ("sess-1", "p-1"))
        notebook = guard.adapt_claude(claude_tool("NotebookEdit", {"notebook_path": "/r/n.ipynb"}))
        self.assertEqual(notebook["paths"], ["/r/n.ipynb"])
        for tool in ("Edit", "Write"):
            self.assertEqual(guard.adapt_claude(claude_tool(tool, {"file_path": "/r/a"}))["tool_kind"], "edit")
        agent = guard.adapt_claude(claude_tool("Agent", {"subagent_type": "executor", "prompt": "x"}))
        self.assertEqual((agent["tool_kind"], agent["dispatched_role"]), ("dispatch", "executor"))
        workflow = guard.adapt_claude(claude_tool("Workflow", {"script": "x"}))
        self.assertEqual((workflow["tool_kind"], workflow["dispatched_role"]), ("dispatch", None))
        self.assertEqual(guard.adapt_claude(claude_tool("Bash", {"command": "ls"}))["tool_kind"], "other")

    def test_subagent_identified_by_agent_id(self) -> None:
        event = guard.adapt_claude(claude_tool("Edit", {"file_path": "/r/a"}, agent_id="ag-1", agent_type="verifier"))
        self.assertTrue(event["is_subagent"])
        self.assertEqual(event["role"], "verifier")

    def test_grok_camel_case_payload_is_noop(self) -> None:
        payload = {"hookEventName": "pre_tool_use", "sessionId": "s", "promptId": "p", "toolName": "search_replace",
                   "toolInput": {"file_path": "/r/a"}, "session_id": "s", "prompt_id": "p"}
        self.assertIsNone(guard.adapt_claude(payload))
        for index in range(3):
            self.assertEqual(self.run_guard("claude", {**payload, "toolInput": {"file_path": self.path("f%d" % index)}}), "")
        self.assertFalse(os.path.exists(self.guard_dir))

    def test_other_events_are_noop(self) -> None:
        self.assertIsNone(guard.adapt_claude({"hook_event_name": "Stop", "session_id": "s"}))

    def test_end_to_end_enforce_then_dispatch_unlocks(self) -> None:
        cwd = self.work
        self.run_guard("claude", claude_prompt(cwd=cwd))
        self.write_turn("sess-1", "p-1", "judgment")
        out = self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=cwd))
        body = json.loads(out)["hookSpecificOutput"]
        self.assertEqual((body["hookEventName"], body["permissionDecision"]), ("PreToolUse", "deny"))
        self.assertIn("SHOAL_GUARD_DIRECT", body["permissionDecisionReason"])
        self.assertNotIn("#direct", body["permissionDecisionReason"])
        self.assertEqual(self.run_guard("claude", claude_tool("Agent", {"subagent_type": "scout"}, cwd=cwd)), "")
        self.assertIn("deny", self.run_guard("claude", claude_tool("Write", {"file_path": "a.py"}, cwd=cwd)))
        self.assertEqual(self.run_guard("claude", claude_tool("Agent", {"subagent_type": "executor"}, cwd=cwd)), "")
        self.assertEqual(self.run_guard("claude", claude_tool("Write", {"file_path": "a.py"}, cwd=cwd)), "")
        decisions = [(r.get("decision"), r.get("rule")) for r in self.log_records()]
        self.assertEqual(decisions, [("state", None), ("deny", "R1"), ("allow", "dispatch"), ("deny", "R1"),
                                     ("allow", "dispatch"), ("allow", "dispatched")])

    def test_prompt_direct_marker_is_not_honored(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt="#direct fix it"))
        self.write_turn("sess-1", "p-1", "mechanical")
        self.assertIn("deny", self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work)))

    def test_zh_tw_message(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work))
        self.write_turn("sess-1", "p-1", "mechanical")
        out = self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work), SHOAL_GUARD_LANG="zh-TW")
        reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("不直接改檔", reason)
        self.assertIn("SHOAL_GUARD_DIRECT=1", reason)
        self.assertIn("mech-executor", reason)

    def test_r2_message_counts_files(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work))
        for name in ("a", "b"):
            self.assertEqual(self.run_guard("claude", claude_tool("Edit", {"file_path": name}, cwd=self.work)), "")
        reason = json.loads(self.run_guard("claude", claude_tool("Edit", {"file_path": "c"}, cwd=self.work)))[
            "hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("2 files", reason)

    def test_shadow_outputs_nothing_and_logs_would_deny(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work), SHOAL_GUARD="shadow")
        self.write_turn("sess-1", "p-1", "judgment")
        out = self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work), SHOAL_GUARD="shadow")
        self.assertEqual(out, "")
        self.assertEqual(self.log_records()[-1]["decision"], "would_deny")

    def test_subagent_leaf_and_verify_edit(self) -> None:
        out = self.run_guard("claude", claude_tool("Agent", {"subagent_type": "scout"}, agent_id="a1", agent_type="executor"))
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        out = self.run_guard("claude", claude_tool("MultiEdit", {"file_path": self.path("a")}, agent_id="a1", agent_type="verifier"))
        self.assertIn("deny", out)
        self.assertEqual(self.run_guard("claude", claude_tool("Edit", {"file_path": self.path("a")}, agent_id="a1", agent_type="executor")), "")
        self.assertEqual([r["rule"] for r in self.log_records()], ["LEAF", "VERIFY_EDIT"])

    def test_missing_ids_record_skip_reason(self) -> None:
        payload = claude_tool("Edit", {"file_path": "a"}, cwd=self.work)
        del payload["session_id"]
        self.assertEqual(self.run_guard("claude", payload), "")
        bad = claude_tool("Edit", {"file_path": "a"}, cwd=self.work, session_id="../../etc")
        self.assertEqual(self.run_guard("claude", bad), "")
        self.assertEqual([r["skip_reason"] for r in self.log_records()], ["missing_id", "invalid_id"])

    def test_prompt_id_is_optional_for_claude_tools_and_prompts(self) -> None:
        """M1: after `/login` both UserPromptSubmit and PreToolUse arrive without prompt_id."""
        def no_id(payload):
            del payload["prompt_id"]
            return payload

        def edit(name):
            return no_id(claude_tool("Edit", {"file_path": self.path(name)}, cwd=self.work))

        self.run_guard("claude", claude_prompt(cwd=self.work))
        self.run_guard("claude", edit("a"))
        self.run_guard("claude", edit("b"))
        agent = claude_tool("Agent", {"subagent_type": "executor"}, cwd=self.work)
        self.assertEqual(self.run_guard("claude", agent), "")
        self.assertEqual(self.run_guard("claude", no_id(claude_prompt(cwd=self.work))), "")
        self.assertIn("already edited 2 files", self.run_guard("claude", edit("c")))
        state = json.loads(Path(self.guard_dir, "state", "sess-1.json").read_text(encoding="utf-8"))
        self.assertEqual(state["turn_id"], "p-1")
        self.assertFalse(state["dispatched"])
        self.assertEqual(len(state["edited"]), 2)

    def test_prompt_without_id_and_no_state_writes_nothing(self) -> None:
        payload = claude_prompt(cwd=self.work)
        del payload["prompt_id"]
        self.assertEqual(self.run_guard("claude", payload), "")
        self.assertFalse(os.path.exists(os.path.join(self.guard_dir, "state", "sess-1.json")))
        self.assertEqual([r["skip_reason"] for r in self.log_records()], ["missing_id"])

    def test_log_and_state_never_contain_prompt_or_tool_input(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work))
        secret_input = {"file_path": self.path("deep/name.py"), "new_string": "SECRET-TOOL-BODY", "content": "SECRET-TOOL-BODY"}
        self.run_guard("claude", claude_tool("Write", secret_input, cwd=self.work))
        blob = ""
        for dirpath, _, names in os.walk(self.guard_dir):
            for name in names:
                blob += Path(dirpath, name).read_text(encoding="utf-8")
        self.assertNotIn("SECRET-PROMPT-TEXT", blob)
        self.assertNotIn("SECRET-TOOL-BODY", blob)
        self.assertNotIn("transcript", blob)
        self.assertIn('"file":"name.py"', blob)


class StateLockTests(CliCase):
    """K4: the per-session state read-modify-write is serialized by flock."""

    def test_parallel_guards_keep_every_edited_entry(self) -> None:
        # Limit 40 so R2 never fires; every process edits a distinct file of one session.
        self.run_guard("claude", claude_prompt(cwd=self.work), SHOAL_GUARD_MAX_FILES="40")
        count = 16
        procs = []
        for index in range(count):
            raw = json.dumps(claude_tool("Edit", {"file_path": self.path("f%d.py" % index)}, cwd=self.work)).encode()
            proc = subprocess.Popen([sys.executable, str(GUARD), "--host", "claude"], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env=self.env(SHOAL_GUARD_MAX_FILES="40"))
            proc.stdin.write(raw)
            proc.stdin.close()
            procs.append(proc)
        for proc in procs:
            self.assertEqual(proc.wait(timeout=60), 0, proc.stderr.read())
            proc.stdout.close()
            proc.stderr.close()
        state = json.loads(Path(self.guard_dir, "state", "sess-1.json").read_text(encoding="utf-8"))
        self.assertEqual(len(state["edited"]), count)
        self.assertEqual(len(set(state["edited"])), count)

    def test_lock_file_is_private_and_a_held_lock_fails_open(self) -> None:
        import fcntl
        self.run_guard("claude", claude_prompt(cwd=self.work))
        lock = Path(self.guard_dir, "state", "sess-1.lock")
        self.assertEqual(lock.stat().st_mode & 0o777, 0o600)
        fd = os.open(str(lock), os.O_RDWR)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        event = guard.adapt_claude(claude_tool("Edit", {"file_path": self.path("a")}, cwd=self.work))
        with mock.patch.object(guard, "LOCK_WAIT_SECONDS", 0.05):
            result = guard.evaluate(event, self.env(), Path(self.home))
        self.assertEqual((result["decision"], result["skip_reason"]), ("skip", "lock_timeout"))

    def test_symlinked_lock_file_is_refused(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work))
        lock = Path(self.guard_dir, "state", "sess-1.lock")
        lock.unlink()
        lock.symlink_to(self.path("elsewhere"))
        event = guard.adapt_claude(claude_tool("Edit", {"file_path": self.path("a")}, cwd=self.work))
        result = guard.evaluate(event, self.env(), Path(self.home))
        self.assertEqual((result["decision"], result["skip_reason"]), ("skip", "state_unavailable"))
        self.assertFalse(os.path.exists(self.path("elsewhere")))


class CodexAdapterTests(CliCase):
    PATCH = ("*** Begin Patch\n*** Add File: new/a.py\n+x\n*** Update File: src/b.py\n@@\n-a\n+b\n"
             "*** Delete File: old.py\n*** Update File: src/c.py\n*** Move to: src/d.py\n@@\n-q\n+r\n*** End Patch")

    @staticmethod
    def prompt(**kw):
        return {"session_id": "019f-s", "turn_id": "019f-t", "cwd": "WORK", "hook_event_name": "UserPromptSubmit",
                "model": "gpt", "permission_mode": "never", "prompt": "hello", **kw}

    @staticmethod
    def tool(name, tool_input, **kw):
        return {"session_id": "019f-s", "turn_id": "019f-t", "cwd": "WORK", "hook_event_name": "PreToolUse",
                "tool_name": name, "tool_input": tool_input, "tool_use_id": "c1", **kw}

    def test_patch_headers_parsed(self) -> None:
        self.assertEqual(guard.patch_paths(self.PATCH), ["new/a.py", "src/b.py", "old.py", "src/c.py", "src/d.py"])
        self.assertEqual(guard.patch_paths(None), [])
        self.assertEqual(guard.patch_paths("no headers"), [])
        self.assertEqual(guard.patch_paths(["*** Add File: x", "+y"]), ["x"])

    def test_normalizes(self) -> None:
        event = guard.adapt_codex(self.tool("apply_patch", {"command": self.PATCH}))
        self.assertEqual((event["tool_kind"], event["turn_id"], event["is_subagent"]), ("edit", "019f-t", False))
        self.assertEqual(len(event["paths"]), 5)
        for name in ("collaborationspawn_agent", "spawn_agent"):
            spawn = guard.adapt_codex(self.tool(name, {"agent_type": "sol-executor", "message": "x"}))
            self.assertEqual((spawn["tool_kind"], spawn["dispatched_role"]), ("dispatch", "sol-executor"))
        sub = guard.adapt_codex(self.tool("apply_patch", {"command": self.PATCH}, agent_id="a1", agent_type="verifier"))
        self.assertEqual((sub["is_subagent"], sub["role"]), (True, "verifier"))
        self.assertEqual(guard.adapt_codex(self.tool("shell", {"command": "ls"}))["tool_kind"], "other")

    def test_default_shadow_then_enforce_denies_third_file(self) -> None:
        self.run_guard("codex", self.prompt(cwd=self.work))
        for name in ("a", "b"):
            patch = "*** Begin Patch\n*** Add File: %s\n+x\n*** End Patch" % name
            self.assertEqual(self.run_guard("codex", self.tool("apply_patch", {"command": patch}, cwd=self.work)), "")
        patch = "*** Begin Patch\n*** Add File: c\n+x\n*** End Patch"
        self.assertEqual(self.run_guard("codex", self.tool("apply_patch", {"command": patch}, cwd=self.work)), "")
        self.assertEqual(self.log_records()[-1]["decision"], "would_deny")
        out = self.run_guard("codex", self.tool("apply_patch", {"command": patch}, cwd=self.work), SHOAL_GUARD="enforce")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("spawn_agent", json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_multi_file_patch_denied_in_one_call(self) -> None:
        self.run_guard("codex", self.prompt(cwd=self.work), SHOAL_GUARD="enforce")
        out = self.run_guard("codex", self.tool("apply_patch", {"command": self.PATCH}, cwd=self.work), SHOAL_GUARD="enforce")
        self.assertIn("deny", out)

    def test_dispatch_write_role_unlocks(self) -> None:
        env = {"SHOAL_GUARD": "enforce"}
        self.run_guard("codex", self.prompt(cwd=self.work), **env)
        self.assertEqual(self.run_guard("codex", self.tool("collaborationspawn_agent", {"agent_type": "executor"}, cwd=self.work), **env), "")
        self.assertEqual(self.run_guard("codex", self.tool("apply_patch", {"command": self.PATCH}, cwd=self.work), **env), "")

    def test_verifier_subagent_apply_patch_denied(self) -> None:
        payload = self.tool("apply_patch", {"command": self.PATCH}, cwd=self.work, agent_id="a1", agent_type="verifier")
        out = self.run_guard("codex", payload, SHOAL_GUARD="enforce")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(self.log_records()[-1]["rule"], "VERIFY_EDIT")

    def test_missing_turn_id_is_skipped(self) -> None:
        payload = self.tool("apply_patch", {"command": self.PATCH}, cwd=self.work)
        del payload["turn_id"]
        self.assertEqual(self.run_guard("codex", payload, SHOAL_GUARD="enforce"), "")
        self.assertEqual(self.log_records()[-1]["skip_reason"], "missing_id")


class GrokAdapterTests(CliCase):
    @staticmethod
    def prompt(**kw):
        return {"hookEventName": "user_prompt_submit", "sessionId": "gs-1", "promptId": "gp-1", "cwd": "WORK",
                "permissionMode": "default", "prompt": "hello", **kw}

    @staticmethod
    def tool(name, tool_input, **kw):
        return {"hookEventName": "pre_tool_use", "sessionId": "gs-1", "promptId": "gp-1", "cwd": "WORK",
                "toolName": name, "toolInput": tool_input, "permissionMode": "default", **kw}

    def test_normalizes(self) -> None:
        edit = guard.adapt_grok(self.tool("search_replace", {"file_path": "/r/a", "old_string": "x"}))
        self.assertEqual((edit["kind"], edit["tool_kind"], edit["paths"], edit["session_id"], edit["turn_id"]),
                         ("tool", "edit", ["/r/a"], "gs-1", "gp-1"))
        spawn = guard.adapt_grok(self.tool("spawn_subagent", {"subagent_type": "executor"}))
        self.assertEqual((spawn["tool_kind"], spawn["dispatched_role"]), ("dispatch", "executor"))
        sub = guard.adapt_grok(self.tool("search_replace", {"file_path": "/r/a"}, subagentType="verifier"))
        self.assertEqual((sub["is_subagent"], sub["role"]), (True, "verifier"))
        self.assertEqual(guard.adapt_grok(self.prompt())["kind"], "prompt")
        self.assertIsNone(guard.adapt_grok({"hookEventName": "subagent_stop"}))

    def test_deny_output_shape_and_flow(self) -> None:
        env = {"SHOAL_GUARD": "enforce"}
        self.run_guard("grok", self.prompt(cwd=self.work), **env)
        self.write_turn("gs-1", "gp-1", "judgment")
        out = json.loads(self.run_guard("grok", self.tool("search_replace", {"file_path": "a.py"}, cwd=self.work), **env))
        self.assertEqual(set(out), {"decision", "reason"})
        self.assertEqual(out["decision"], "deny")
        self.assertIn("spawn_subagent", out["reason"])
        self.assertEqual(self.run_guard("grok", self.tool("spawn_subagent", {"subagent_type": "mech-executor"}, cwd=self.work), **env), "")
        self.assertEqual(self.run_guard("grok", self.tool("search_replace", {"file_path": "a.py"}, cwd=self.work), **env), "")

    def test_default_is_shadow(self) -> None:
        self.run_guard("grok", self.prompt(cwd=self.work))
        self.write_turn("gs-1", "gp-1", "judgment")
        self.assertEqual(self.run_guard("grok", self.tool("search_replace", {"file_path": "a.py"}, cwd=self.work)), "")
        self.assertEqual(self.log_records()[-1]["decision"], "would_deny")

    def test_tool_without_prompt_id_uses_state_turn(self) -> None:
        def e0(name):
            payload = self.tool("search_replace", {"file_path": "src/" + name + ".py"}, cwd=self.work)
            del payload["promptId"]
            return payload
        self.run_guard("grok", self.prompt(cwd=self.work))
        self.assertEqual(self.run_guard("grok", e0("a")), "")
        self.assertEqual(self.run_guard("grok", e0("b")), "")
        self.assertEqual(self.run_guard("grok", e0("c")), "")
        self.assertEqual(self.log_records()[-1]["decision"], "would_deny")
        out = json.loads(self.run_guard("grok", e0("d"), SHOAL_GUARD="enforce"))
        self.assertEqual(out["decision"], "deny")

    def test_write_file_counts_toward_r2(self) -> None:
        self.assertEqual(guard.adapt_grok(self.tool("write_file", {"path": "/r/n"}))["paths"], ["/r/n"])
        self.run_guard("grok", self.prompt(cwd=self.work))
        for key, name in (("path", "a"), ("file_path", "b"), ("file_path", "c")):
            payload = self.tool("write_file", {key: "src/" + name + ".py"}, cwd=self.work)
            del payload["promptId"]
            out = self.run_guard("grok", payload)
            self.assertEqual(out, "")

    def test_write_tool_counts_toward_r2(self) -> None:
        self.run_guard("grok", self.prompt(cwd=self.work))
        for name in ("a", "b", "c"):
            payload = self.tool("write", {"content": "x", "file_path": "src/" + name + ".py"}, cwd=self.work)
            del payload["promptId"]
            self.assertEqual(self.run_guard("grok", payload), "")
        self.assertEqual(self.log_records()[-1]["decision"], "would_deny")

    def test_subagent_leaf_denied(self) -> None:
        payload = self.tool("spawn_subagent", {"subagent_type": "scout"}, subagentType="executor")
        out = json.loads(self.run_guard("grok", payload, SHOAL_GUARD="enforce"))
        self.assertEqual(out["decision"], "deny")

    def test_host_from_env_when_argv_has_no_host(self) -> None:
        # grok execs the hook path directly and passes the host through the hook's env map
        payload = self.tool("spawn_subagent", {"subagent_type": "scout"}, subagentType="executor")
        proc = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload).encode(),
                              capture_output=True, timeout=30,
                              env=self.env(SHOAL_GUARD="enforce", SHOAL_GUARD_HOST="grok"))
        self.assertEqual(json.loads(proc.stdout)["decision"], "deny")
        proc = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload).encode(),
                              capture_output=True, timeout=30, env=self.env(SHOAL_GUARD="enforce"))
        self.assertEqual((proc.returncode, proc.stdout), (0, b""))


class AgyAdapterTests(CliCase):
    @staticmethod
    def pre_invocation(n=0, steps=0, **kw):
        return {"conversationId": "conv-1", "invocationNum": n, "initialNumSteps": steps, **kw}

    @staticmethod
    def tool(name, args, **kw):
        return {"conversationId": "conv-1", "toolCall": {"name": name, "args": args}, **kw}

    @staticmethod
    def subagents(*roles):
        return {"Subagents": [{"Model": "inherit", "Prompt": "p", "Role": r, "TypeName": r} for r in roles]}

    def test_normalizes(self) -> None:
        boundary = guard.adapt_agy(self.pre_invocation(0, 12))
        self.assertEqual((boundary["kind"], boundary["session_id"], boundary["turn_id"]), ("turn_boundary", "conv-1", "conv-1:12"))
        for n in (1, 2, 7):  # later model calls inside the same turn are not boundaries
            self.assertIsNone(guard.adapt_agy(self.pre_invocation(n, 12)))
        self.assertIsNone(guard.adapt_agy({"conversationId": "c", "invocationNum": True}))
        self.assertEqual(guard.adapt_agy({"conversationId": "c", "invocationNum": 0, "initialNumSteps": 0})["turn_id"], "c:0")
        self.assertIsNone(guard.adapt_agy({"conversationId": "c", "invocationNum": 0})["turn_id"])
        write = guard.adapt_agy(self.tool("write_to_file", {"TargetFile": "/r/a", "CodeContent": "x"}))
        self.assertEqual((write["kind"], write["tool_kind"], write["paths"], write["turn_id"]), ("tool", "edit", ["/r/a"], None))
        replace = guard.adapt_agy(self.tool("multi_replace_file_content", {"TargetFile": "/r/b"}))
        self.assertEqual((replace["tool_kind"], replace["paths"]), ("edit", ["/r/b"]))
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", self.subagents("mech-executor")))["dispatched_role"], "mech-executor")
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", {"Subagents": [{"Role": "executor"}]}))["dispatched_role"], "executor")
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", self.subagents("executor", "scout")))["dispatched_role"], "scout")
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", self.subagents("executor", "mech-executor")))["dispatched_role"], "executor")
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", {}))["dispatched_role"], None)
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", {"Subagents": []}))["dispatched_role"], None)
        self.assertEqual(guard.adapt_agy(self.tool("run_command", {}))["tool_kind"], "other")
        self.assertFalse(guard.adapt_agy(self.tool("write_to_file", {"TargetFile": "/r/a"}))["is_subagent"])
        self.assertIsNone(guard.adapt_agy({"conversationId": "c"}))

    def test_always_shadow_even_with_enforce(self) -> None:
        env = {"SHOAL_GUARD": "enforce"}
        self.run_guard("agy", self.pre_invocation(0, cwd=self.work), **env)
        self.write_turn("conv-1", "conv-1:0", "judgment")
        out = self.run_guard("agy", self.tool("write_to_file", {"TargetFile": self.path("a.py")}), **env)
        self.assertEqual(out, "")
        record = self.log_records()[-1]
        self.assertEqual((record["decision"], record["rule"], record["mode"], record["host"]), ("would_deny", "R1", "shadow", "agy"))

    def test_deny_output_shape(self) -> None:
        self.assertEqual(json.loads(guard.deny_output("agy", "why")), {"decision": "deny", "reason": "why"})
        self.assertEqual(json.loads(guard.deny_output("grok", "why")), {"decision": "deny", "reason": "why"})
        claude = json.loads(guard.deny_output("claude", "why"))["hookSpecificOutput"]
        self.assertEqual(claude, {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "why"})
        self.assertEqual(json.loads(guard.deny_output("codex", "why")), json.loads(guard.deny_output("claude", "why")))

    def test_dispatch_unlocks_within_invocation(self) -> None:
        self.run_guard("agy", self.pre_invocation(0))
        self.run_guard("agy", self.tool("invoke_subagent", self.subagents("executor", "mech-executor")))
        self.run_guard("agy", self.pre_invocation(1))  # next model call in the turn: state kept
        self.run_guard("agy", self.tool("write_to_file", {"TargetFile": self.path("a")}, cwd=self.work))
        self.assertEqual(self.log_records()[-1]["rule"], "dispatched")

    def test_mixed_subagents_do_not_unlock(self) -> None:
        self.run_guard("agy", self.pre_invocation(0))
        self.run_guard("agy", self.tool("invoke_subagent", self.subagents("executor", "scout")))
        self.run_guard("agy", self.tool("write_to_file", {"TargetFile": self.path("a")}, cwd=self.work))
        self.assertEqual(self.log_records()[-1]["rule"], "count")


class RobustnessTests(CliCase):
    def test_bad_input_exits_zero_silently(self) -> None:
        for raw in (b"", b"not json", b"[1,2]", b"null", b"\xff\xfe"):
            self.assertEqual(self.run_guard("claude", raw), "")

    def test_oversize_payload_skipped_with_reason(self) -> None:
        raw = json.dumps(claude_tool("Edit", {"file_path": "a", "new_string": "x" * (guard.MAX_INPUT_BYTES + 10)})).encode()
        self.assertEqual(self.run_guard("claude", raw), "")
        self.assertEqual(self.log_records()[-1]["skip_reason"], "oversize_payload")

    def test_non_object_payload_logs_bad_payload(self) -> None:
        self.run_guard("claude", b"[1,2]")
        self.assertEqual(self.log_records()[-1]["skip_reason"], "bad_payload")

    def test_unknown_or_missing_host_exits_zero(self) -> None:
        for argv in ([], ["--host", "nope"], ["--host"]):
            proc = subprocess.run([sys.executable, str(GUARD), *argv], input=b"{}", capture_output=True, env=self.env(), timeout=30)
            self.assertEqual((proc.returncode, proc.stdout), (0, b""))

    def test_exception_fails_open_and_logs_skip_reason(self) -> None:
        env = self.env()
        raw = json.dumps(claude_tool("Edit", {"file_path": "a"}, cwd=self.work)).encode()
        with mock.patch.object(guard, "evaluate", side_effect=RuntimeError("boom")):
            self.assertIsNone(guard.run("claude", raw, env))
        self.assertEqual(self.log_records()[-1]["skip_reason"], "exception")

    def test_nul_byte_path_fails_open(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work))
        out = self.run_guard("claude", claude_tool("Edit", {"file_path": "a\u0000b"}, cwd=self.work))
        self.assertEqual(out, "")
        self.assertEqual(self.log_records()[-1]["skip_reason"], "exception")

    def test_log_stops_at_one_mib(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work))
        path = Path(self.guard_dir) / "guard.jsonl"
        path.write_text("x" * (guard.MAX_LOG_BYTES + 1), encoding="utf-8")
        before = path.stat().st_size
        self.run_guard("claude", claude_tool("Edit", {"file_path": "a"}, cwd=self.work))
        self.assertEqual(path.stat().st_size, before)

    def test_off_mode_creates_nothing(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work), SHOAL_GUARD="off")
        self.assertFalse(os.path.exists(self.state))

    def test_resolve_mode(self) -> None:
        self.assertEqual(guard.resolve_mode("claude", {}), "enforce")
        self.assertEqual(guard.resolve_mode("codex", {}), "shadow")
        self.assertEqual(guard.resolve_mode("agy", {"SHOAL_GUARD": "enforce"}), "shadow")
        self.assertEqual(guard.resolve_mode("agy", {"SHOAL_GUARD": "off"}), "off")
        self.assertEqual(guard.resolve_mode("claude", {"PILOTFISH_GUARD": "shadow"}), "shadow")
        self.assertEqual(guard.resolve_mode("claude", {"SHOAL_GUARD": "shadow", "PILOTFISH_GUARD": "off"}), "shadow")


if __name__ == "__main__":
    unittest.main()
