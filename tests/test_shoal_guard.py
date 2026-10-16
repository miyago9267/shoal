"""Dispatch guard: shared vectors, role table, per-host adapters, CLI behavior."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from pathlib import Path
from typing import Any
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
                self.assertEqual(helper.run_vector(vector, data["log_whitelist"], guard, data.get("env_defaults")), [])

    def test_vectors_cover_the_spec_r8_list(self) -> None:
        names = " ".join(v["name"] for v in helper.load_vectors()["vectors"])
        for needle in ("dotdot", "symlink", "dispatch_scout", "dispatch_executor", "skip_missing", "log_whitelist",
                       "xdg_unset", "xdg_relative", "symlinked", "foreign_owner", "r1_", "direct_env", "exempt",
                       "leaf", "verify_edit", "mode_shadow", "agy_mode_shadow_override"):
            self.assertIn(needle, names)

    def test_log_whitelist_constant_matches_vectors(self) -> None:
        self.assertEqual(list(guard.LOG_FIELDS), helper.load_vectors()["log_whitelist"])


@unittest.skipIf(os.name == "nt", "shoal guard is POSIX-only; it is a no-op on Windows")
class ShellWriteDetectorTests(unittest.TestCase):
    """G5: shell_write_targets is replayed from the fixture the TypeScript port also replays."""

    def test_shared_cases(self) -> None:
        data = json.loads((ROOT / "tests" / "fixtures" / "shell_write_cases.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["cases"]), 60)
        commands = [c["command"] for c in data["cases"]]
        self.assertEqual(len(commands), len(set(commands)))
        for case in data["cases"]:
            with self.subTest(case["command"]):
                self.assertEqual(guard.shell_write_targets(case["command"]), case["targets"])

    def test_interpreter_and_copy_writes_are_out_of_scope(self) -> None:
        for command in ("python3 -c \"open('f','w').write('x')\"", "node -e \"require('fs').writeFileSync('f','x')\"",
                        "cp a b", "mv a b", "git apply x.patch", "patch -p1 < x.patch", "dd if=a of=b", "install -m 644 a b"):
            self.assertEqual(guard.shell_write_targets(command), [], command)

    def test_scanner_terminates_on_malformed_input(self) -> None:
        for command in ("cat > ", ">", ">>", "echo '", 'echo "', "echo $(", "echo ${", "echo `", "(( a", "[[ a",
                        "cat <<", "cat <<EOF", "cat <<EOF\nbody", "\\", "echo >(", "tee", "sed -i", "2>", "&>",
                        "x" * 5000 + " > f", "(" * 400, "'" * 401):
            self.assertIsInstance(guard.shell_write_targets(command), list, command)


@unittest.skipIf(os.name == "nt", "shoal guard is POSIX-only; it is a no-op on Windows")
class DeclarationParserTests(unittest.TestCase):
    """M3: parse_declaration is replayed from the fixture the TypeScript port also replays."""

    def test_shared_cases(self) -> None:
        data = json.loads((ROOT / "tests" / "fixtures" / "declaration_cases.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["cases"]), 100)
        commands = [c["command"] for c in data["cases"]]
        self.assertEqual(len(commands), len(set(commands)))
        self.assertTrue(any(c["reason"] for c in data["cases"]))
        for case in data["cases"]:
            with self.subTest(case["command"]):
                self.assertEqual(guard.parse_declaration(case["command"]), case["reason"])

    def test_non_strings_are_not_declarations(self) -> None:
        for value in (None, 7, [": shoal-direct x"], b": shoal-direct x"):
            self.assertIsNone(guard.parse_declaration(value))

    def test_log_reason_is_clean_and_cut_at_200_characters(self) -> None:
        self.assertEqual(guard.log_reason("a\tb\x01c\x7fd\x85e\nf"), "abcdef")
        self.assertEqual(guard.log_reason("x" * 250), "x" * 200)
        self.assertEqual(guard.log_reason("\u6539" * 250), "\u6539" * 200)

    def test_resolve_r1(self) -> None:
        for host in ("claude", "codex", "opencode", "grok", "agy"):
            for env, want in (({}, "strict"), ({"SHOAL_GUARD_R1": ""}, "strict"), ({"SHOAL_GUARD_R1": "bogus"}, "strict"),
                              ({"SHOAL_GUARD_R1": "STRICT"}, "strict"), ({"SHOAL_GUARD_R1": "strict"}, "strict"),
                              ({"SHOAL_GUARD_R1": "declare"}, "declare"),
                              ({"SHOAL_GUARD_R1": "classified"}, "classified"), ({"SHOAL_GUARD_R1": "off"}, "off")):
                self.assertEqual(guard.resolve_r1(host, env), want, (host, env))
        # a host that cannot gate keeps v3.1.0, whatever is asked
        for host in ("",):
            for value in ("", "declare", "strict", "bogus", "classified"):
                self.assertEqual(guard.resolve_r1(host, {"SHOAL_GUARD_R1": value}), "classified", (host, value))
            self.assertEqual(guard.resolve_r1(host, {"SHOAL_GUARD_R1": "off"}), "off")

    def test_messages_carry_the_three_exits(self) -> None:
        for lang in ("en", "zh-TW"):
            text = guard.MESSAGES[lang]["DECLARE"]
            for needle in ("executor", "applier", ': shoal-direct "<', "#direct"):
                self.assertIn(needle, text, (lang, needle))
        self.assertEqual(
            guard.MESSAGES["en"]["DECLARE"],
            "Shoal dispatch guard: the main session delegates edits by default. Dispatch a write-capable role "
            '(executor or applier), or declare direct work first by running exactly : shoal-direct "<reason>" '
            "as its own shell command, or ask the user to add #direct to the prompt.")


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
        self.assertEqual(guard.HOST_DEFAULT_MODE, {"claude": "enforce", "codex": "enforce", "grok": "enforce", "agy": "enforce"})

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
        # The v3.1.0 tests run in `classified` mode; the declare tests pass SHOAL_GUARD_R1="declare", the strict tests "" (host default).
        env = {"HOME": self.home, "XDG_STATE_HOME": self.state, "TMPDIR": self.sandbox.tmpdir,
               "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "SHOAL_GUARD_R1": "classified",
               "SHOAL_GUARD_LANES": "off"}  # LaneAdapterTests switches the dispatch-lane rule on
        env.update(extra)
        return env

    def run_guard(self, host: str, payload, event: str = "", **env_extra: str) -> str:
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        argv = [sys.executable, str(GUARD), "--host", host] + (["--event", event] if event else [])
        proc = subprocess.run(argv, input=raw, capture_output=True,
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


def claude_start(role="shoal:executor", **kw):
    """The SubagentStart payload (tests/fixtures/claude_subagent_start_shape.json): the new subagent's id and type."""
    return {"session_id": "sess-1", "prompt_id": "p-1", "cwd": "WORK", "hook_event_name": "SubagentStart",
            "agent_id": "ag-1", "agent_type": role, "transcript_path": "/x/y.jsonl", **kw}


class LogAttributionTests(CliCase):
    """guard.jsonl says which agent and which session/turn made the call (short hashes, never raw ids)."""

    HEX8 = r"^[0-9a-f]{8}$"

    def test_claude_subagent_e1_deny_logs_agent_type_and_short_hashes(self) -> None:
        payload = claude_tool("Edit", {"file_path": self.path("a.py")}, cwd=self.work, agent_id="ag-9",
                              agent_type="general-purpose")
        out = self.run_guard("claude", payload, SHOAL_GUARD="enforce", SHOAL_GUARD_SUBAGENT_WRITE="on")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        record = self.log_records()[-1]
        self.assertEqual((record["rule"], record["agent_type"], record["agent_id"]), ("E1", "general-purpose", "ag-9"))
        self.assertRegex(record["session"], self.HEX8)
        self.assertRegex(record["turn"], self.HEX8)
        self.assertNotIn("sess-1", json.dumps(record))
        self.assertNotIn("p-1", json.dumps(record))
        self.run_guard("claude", payload, SHOAL_GUARD="enforce", SHOAL_GUARD_SUBAGENT_WRITE="on")
        first, second = self.log_records()[-2:]
        self.assertEqual((first["session"], first["turn"]), (second["session"], second["turn"]))  # stable

    def test_shadow_would_deny_keeps_the_fields(self) -> None:
        payload = claude_tool("Edit", {"file_path": self.path("a.py")}, cwd=self.work, agent_id="ag-9",
                              agent_type="shoal:scout")
        self.run_guard("claude", payload, SHOAL_GUARD="shadow", SHOAL_GUARD_SUBAGENT_WRITE="on")
        record = self.log_records()[-1]
        self.assertEqual((record["decision"], record["agent_type"]), ("would_deny", "shoal:scout"))

    def test_main_session_event_has_no_agent_fields(self) -> None:
        self.run_guard("claude", claude_tool("Edit", {"file_path": self.path("a.py")}, cwd=self.work),
                       SHOAL_GUARD="enforce")
        record = self.log_records()[-1]
        self.assertNotIn("agent_type", record)
        self.assertNotIn("agent_id", record)
        self.assertRegex(record["session"], self.HEX8)


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
        shell = guard.adapt_claude(claude_tool("Bash", {"command": "ls"}))
        self.assertEqual((shell["tool_kind"], shell["command"]), ("shell", "ls"))
        background = guard.adapt_claude(claude_tool("Bash", {"command": "ls > f", "run_in_background": True}))
        self.assertEqual((background["tool_kind"], background["command"]), ("background_shell", None))
        self.assertIsNone(guard.adapt_claude(claude_tool("Bash", {"command": 7}))["command"])

    def test_recorded_subagent_start_shape_is_accepted(self) -> None:
        shape = json.loads((ROOT / "tests" / "fixtures" / "claude_subagent_start_shape.json").read_text(encoding="utf-8"))
        make = {"str": "synthetic"}
        for agent_type in shape["agent_types"]:
            payload = {key: make[kind] for key, kind in shape["keys"].items()}
            payload["hook_event_name"] = shape["hook_event_name"]
            payload["agent_type"] = agent_type
            with self.subTest(agent_type):
                event = guard.adapt_claude(payload)
                # the payload's agent_id names the NEW subagent: the event is the main session's, not a subagent call
                self.assertEqual((event["kind"], event["is_subagent"], event["tool_kind"]), ("subagent_start", False, None))
                self.assertEqual((event["session_id"], event["turn_id"], event["role"]), ("synthetic", "synthetic", agent_type))
        self.assertEqual(guard.adapt_claude({"hook_event_name": "SubagentStart"})["role"], None)

    def test_malformed_subagent_start_payloads_fail_open(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work))
        for payload in ({"hook_event_name": "SubagentStart"}, claude_start(7), claude_start(None), claude_start(session_id=None),
                        claude_start(session_id="bad id/x"), claude_start(prompt_id=["x"]),
                        {"hook_event_name": "SubagentStart", "agent_type": "shoal:executor", "session_id": {}}):
            self.assertEqual(self.run_guard("claude", payload), "", payload)
        state = json.loads(Path(self.guard_dir, "state", "sess-1.json").read_text(encoding="utf-8"))
        self.assertEqual((state["dispatched"], state["pending"]), (False, 0))

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
        for name in ("SessionStart", "SubagentStop", "PostToolUse", "Notification"):
            self.assertIsNone(guard.adapt_claude({"hook_event_name": name, "session_id": "s"}), name)

    def test_end_to_end_enforce_then_dispatch_unlocks(self) -> None:
        cwd = self.work
        self.run_guard("claude", claude_prompt(cwd=cwd))
        self.write_turn("sess-1", "p-1", "judgment")
        out = self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=cwd))
        body = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(set(body), {"hookEventName", "permissionDecision", "permissionDecisionReason"})
        self.assertEqual((body["hookEventName"], body["permissionDecision"]), ("PreToolUse", "deny"))
        self.assertIn("classified as implementation work", body["permissionDecisionReason"])
        self.assertIn("#direct", body["permissionDecisionReason"])
        self.assertEqual(self.run_guard("claude", claude_tool("Agent", {"subagent_type": "scout"}, cwd=cwd)), "")
        self.assertIn("deny", self.run_guard("claude", claude_tool("Write", {"file_path": "a.py"}, cwd=cwd)))
        for role in ("watcher", "researcher"):
            self.assertEqual(self.run_guard("claude", claude_tool("Agent", {"subagent_type": role}, cwd=cwd)), "")
        self.assertIn("deny", self.run_guard("claude", claude_tool("Write", {"file_path": "a.py"}, cwd=cwd)))
        self.assertEqual(self.run_guard("claude", claude_tool("Agent", {"subagent_type": "executor"}, cwd=cwd)), "")
        self.assertIn("deny", self.run_guard("claude", claude_tool("Write", {"file_path": "a.py"}, cwd=cwd)))  # not started
        self.assertEqual(self.run_guard("claude", claude_start("scout", cwd=cwd)), "")
        self.assertIn("deny", self.run_guard("claude", claude_tool("Write", {"file_path": "a.py"}, cwd=cwd)))
        self.assertEqual(self.run_guard("claude", claude_start("shoal:executor", cwd=cwd)), "")
        self.assertEqual(self.run_guard("claude", claude_tool("Write", {"file_path": "a.py"}, cwd=cwd)), "")
        decisions = [(r.get("decision"), r.get("rule")) for r in self.log_records()]
        self.assertEqual(decisions, [("state", None), ("deny", "R1"), ("allow", "dispatch"), ("deny", "R1"),
                                     ("allow", "dispatch"), ("allow", "dispatch"), ("deny", "R1"),
                                     ("allow", "dispatch_pending"), ("deny", "R1"), ("deny", "R1"),
                                     ("state", "dispatch_started"), ("allow", "dispatched")])

    def test_r1_stays_advise_on_codex_and_never_prints_a_deny(self) -> None:
        payload = {"session_id": "sess-1", "turn_id": "t-1", "cwd": self.work, "hook_event_name": "UserPromptSubmit"}
        self.run_guard("codex", payload)
        self.write_turn("sess-1", "t-1", "judgment")
        edit = {"session_id": "sess-1", "turn_id": "t-1", "cwd": self.work, "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch", "tool_input": {"command": "*** Update File: a.py\n"}}
        out = self.run_guard("codex", edit)
        self.assertIn("additionalContext", out)
        self.assertNotIn("permissionDecision", out)
        self.assertEqual(self.log_records()[-1]["decision"], "advise")

    def test_prompt_direct_marker_releases_r1_for_that_turn_only(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt="please #direct fix it"))
        self.write_turn("sess-1", "p-1", "mechanical")
        self.assertEqual(self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work)), "")
        self.assertEqual(self.log_records()[-1]["rule"], "direct")
        state = json.loads(Path(self.guard_dir, "state", "sess-1.json").read_text(encoding="utf-8"))
        self.assertIs(state["direct"], True)
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt_id="p-2", prompt="next one"))
        self.write_turn("sess-1", "p-2", "mechanical")
        state = json.loads(Path(self.guard_dir, "state", "sess-1.json").read_text(encoding="utf-8"))
        self.assertIs(state["direct"], False)
        out = self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work, prompt_id="p-2"))
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_direct_token_must_stand_alone(self) -> None:
        def flag(prompt):
            return guard.adapt_claude(claude_prompt(prompt=prompt))["direct"]

        for text in ("#direct", "do it #direct", "#direct do it", "fix it, #direct.", "請 #direct 修",
                     "line one\n#direct", "請直接改 #direct。"):
            self.assertTrue(flag(text), text)
        for text in ("#directory", "x#direct", "##direct", "#direct-ly", "#direct_mode", "#directs", "# direct",
                     "direct", "#Direct", "", None, 7, "(#direct)", "修好#direct吧", "`#direct`",
                     "see docs/x#direct for details"):
            self.assertFalse(flag(text), text)
        self.assertFalse(guard.adapt_claude(claude_prompt())["direct"])  # no token in the default prompt

    def test_direct_token_vectors(self) -> None:
        """tests/fixtures/direct_token_vectors.json is shared with the TypeScript mirror."""
        vectors = json.loads((ROOT / "tests" / "fixtures" / "direct_token_vectors.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(vectors["vectors"]), 30)
        for vector in vectors["vectors"]:
            self.assertIs(guard.has_direct_token(vector["prompt"]), vector["direct"], vector["name"])
            self.assertIs(
                guard.adapt_claude(claude_prompt(prompt=vector["prompt"]))["direct"], vector["direct"], vector["name"]
            )

    def test_fast_switch_vectors(self) -> None:
        """tests/fixtures/fast_switch_vectors.json is shared with the TypeScript mirror (raw prompt -> on/off/none)."""
        doc = json.loads((ROOT / "tests" / "fixtures" / "fast_switch_vectors.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(doc["vectors"]), 30)
        codex = {"hook_event_name": "UserPromptSubmit", "session_id": "s", "turn_id": "t"}
        grok = {"hookEventName": "user_prompt_submit", "sessionId": "s", "promptId": "p"}
        for vector in doc["vectors"]:
            want = None if vector["fast"] == "none" else vector["fast"]
            prompt = vector["prompt"]
            self.assertEqual(guard.fast_switch(prompt), want, vector["name"])
            self.assertEqual(guard.adapt_claude(claude_prompt(prompt=prompt))["fast"], want, vector["name"])
            self.assertEqual(guard.adapt_codex({**codex, "prompt": prompt})["fast"], want, vector["name"])
            self.assertEqual(guard.adapt_grok({**grok, "prompt": prompt})["fast"], want, vector["name"])
        self.assertIsNone(guard.fast_switch(None))
        self.assertIsNone(guard.fast_switch(7))

    def test_fast_flag_from_raw_prompt_end_to_end(self) -> None:
        """Each host: a raw prompt payload -> adapter -> state file's fast flag (set by #fast, cleared by #strict)."""
        hosts = (
            ("claude", "sess-1", lambda text, n: claude_prompt(cwd=self.work, prompt_id="p-%d" % n, prompt=text)),
            ("codex", "019f-s", lambda text, n: CodexAdapterTests.prompt(cwd=self.work, turn_id="t-%d" % n, prompt=text)),
            ("grok", "gs-main", lambda text, n: {"hookEventName": "user_prompt_submit", "sessionId": "gs-main",
                                                 "cwd": self.work, "promptId": "gp-%d" % n, "prompt": text}),
        )
        for host, session, make in hosts:
            state_file = Path(self.guard_dir, "state", session + ".json")

            def fast() -> bool:
                return json.loads(state_file.read_text(encoding="utf-8")).get("fast") is True

            with self.subTest(host):
                self.run_guard(host, make("what does `#fast` do?", 1))
                self.assertFalse(fast())
                self.run_guard(host, make("go #fast, please", 2))
                self.assertTrue(fast())
                self.run_guard(host, make("carry on", 3))
                self.assertTrue(fast())
                self.run_guard(host, make("#fast and #strict", 4))
                self.assertFalse(fast())

    def test_quoted_direct_does_not_release_r1(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt="why does `#direct` exist?"))
        self.write_turn("sess-1", "p-1", "judgment")
        out = self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work))
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_direct_flag_is_recorded_but_the_prompt_text_never_is(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt="#direct SECRET-DIRECT-PROMPT"))
        blob = ""
        for dirpath, _, names in os.walk(self.guard_dir):
            for name in names:
                blob += Path(dirpath, name).read_text(encoding="utf-8")
        self.assertNotIn("SECRET-DIRECT-PROMPT", blob)
        self.assertIn('"direct": true', blob)

    def test_direct_marker_comes_from_claude_codex_and_grok_prompts(self) -> None:
        codex = {"hook_event_name": "UserPromptSubmit", "session_id": "s", "turn_id": "t"}
        self.assertTrue(guard.adapt_codex({**codex, "prompt": "do it #direct"})["direct"])
        self.assertFalse(guard.adapt_codex({**codex, "prompt": "do it `#direct`"})["direct"])
        self.assertFalse(guard.adapt_codex(codex)["direct"])
        grok = {"hookEventName": "user_prompt_submit", "sessionId": "s", "promptId": "p"}
        self.assertTrue(guard.adapt_grok({**grok, "prompt": "#direct"})["direct"])
        self.assertFalse(guard.adapt_grok({**grok, "prompt": "do it `#direct`"})["direct"])
        self.assertFalse(guard.adapt_grok(grok)["direct"])

    def test_direct_env_suppresses_advise(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work), SHOAL_GUARD_DIRECT="1")
        self.write_turn("sess-1", "p-1", "judgment")
        for name in ("a", "b", "c"):
            out = self.run_guard("claude", claude_tool("Edit", {"file_path": name}, cwd=self.work), SHOAL_GUARD_DIRECT="1")
            self.assertEqual(out, "")
        self.assertEqual([(r["decision"], r["rule"]) for r in self.log_records()[1:]], [("allow", "direct")] * 3)

    def test_advise_once_per_turn_and_rearms_on_new_turn(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work))
        for name in ("a", "b"):
            self.assertEqual(self.run_guard("claude", claude_tool("Edit", {"file_path": name}, cwd=self.work)), "")
        first = self.run_guard("claude", claude_tool("Edit", {"file_path": "c"}, cwd=self.work))
        self.assertIn("additionalContext", first)
        for name in ("d", "e"):
            self.assertEqual(self.run_guard("claude", claude_tool("Edit", {"file_path": name}, cwd=self.work)), "")
        advised = [r for r in self.log_records() if r["decision"] == "advise"]
        self.assertEqual(len(advised), 3)  # R2 fires on every new file past the limit; only the first one prints
        state = json.loads(Path(self.guard_dir, "state", "sess-1.json").read_text(encoding="utf-8"))
        self.assertTrue(state["advised"])
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt_id="p-2"))
        state = json.loads(Path(self.guard_dir, "state", "sess-1.json").read_text(encoding="utf-8"))
        self.assertFalse(state["advised"])
        for name in ("a", "b"):
            self.assertEqual(self.run_guard("claude", claude_tool("Edit", {"file_path": name}, cwd=self.work, prompt_id="p-2")), "")
        again = self.run_guard("claude", claude_tool("Edit", {"file_path": "c"}, cwd=self.work, prompt_id="p-2"))
        self.assertIn("additionalContext", again)

    def test_zh_tw_message(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work), SHOAL_GUARD_LANG="zh-TW")
        for name in ("a", "b"):
            self.run_guard("claude", claude_tool("Edit", {"file_path": name}, cwd=self.work), SHOAL_GUARD_LANG="zh-TW")
        out = self.run_guard("claude", claude_tool("Edit", {"file_path": "c"}, cwd=self.work), SHOAL_GUARD_LANG="zh-TW")
        reason = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("提醒", reason)
        self.assertIn("3 個檔案", reason)
        self.assertIn("applier", reason)

    def test_zh_tw_deny_messages(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work), SHOAL_GUARD_LANG="zh-TW")
        self.write_turn("sess-1", "p-1", "mechanical")
        out = self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work), SHOAL_GUARD_LANG="zh-TW")
        self.assertIn("已被分類為實作工作", json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"])
        out = self.run_guard("claude", claude_tool("Bash", {"command": "sleep 9", "run_in_background": True}, cwd=self.work),
                             SHOAL_GUARD_LANG="zh-TW")
        self.assertIn("watcher", json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIn("背景 shell", json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_r2_message_counts_files(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work))
        for name in ("a", "b"):
            self.assertEqual(self.run_guard("claude", claude_tool("Edit", {"file_path": name}, cwd=self.work)), "")
        reason = json.loads(self.run_guard("claude", claude_tool("Edit", {"file_path": "c"}, cwd=self.work)))[
            "hookSpecificOutput"]["additionalContext"]
        self.assertIn("edited 3 files", reason)

    def test_shadow_outputs_nothing_and_logs_would_deny(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work), SHOAL_GUARD="shadow")
        self.write_turn("sess-1", "p-1", "judgment")
        out = self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work), SHOAL_GUARD="shadow")
        self.assertEqual(out, "")
        self.assertEqual((self.log_records()[-1]["decision"], self.log_records()[-1]["rule"]), ("would_deny", "R1"))
        out = self.run_guard("claude", claude_tool("Bash", {"command": "x", "run_in_background": True}, cwd=self.work),
                             SHOAL_GUARD="shadow")
        self.assertEqual(out, "")
        self.assertEqual((self.log_records()[-1]["decision"], self.log_records()[-1]["rule"]), ("would_deny", "G4"))

    def test_g5_shell_write_is_denied_like_r1(self) -> None:
        heredoc = "cat > src/a.py <<'EOF'\nx\nEOF"
        self.run_guard("claude", claude_prompt(cwd=self.work))
        self.write_turn("sess-1", "p-1", "judgment")
        out = self.run_guard("claude", claude_tool("Bash", {"command": heredoc}, cwd=self.work))
        body = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(body["permissionDecision"], "deny")
        self.assertIn("#direct", body["permissionDecisionReason"])
        self.assertEqual((self.log_records()[-1]["decision"], self.log_records()[-1]["rule"]), ("deny", "R1"))
        before = len(self.log_records())
        self.assertEqual(self.run_guard("claude", claude_tool("Bash", {"command": "pytest -q 2>&1 | tail -5"}, cwd=self.work)), "")
        self.assertEqual(len(self.log_records()), before)
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt="#direct write it"))
        self.assertEqual(self.run_guard("claude", claude_tool("Bash", {"command": heredoc}, cwd=self.work)), "")
        self.assertEqual((self.log_records()[-1]["decision"], self.log_records()[-1]["rule"]), ("allow", "direct"))

    def test_g5_shadow_logs_would_deny_and_prints_nothing(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work), SHOAL_GUARD="shadow")
        self.write_turn("sess-1", "p-1", "mechanical")
        out = self.run_guard("claude", claude_tool("Bash", {"command": "echo x > out.txt"}, cwd=self.work), SHOAL_GUARD="shadow")
        self.assertEqual(out, "")
        self.assertEqual((self.log_records()[-1]["decision"], self.log_records()[-1]["rule"]), ("would_deny", "R1"))

    def test_g5_background_write_is_one_g4_deny(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work))
        self.write_turn("sess-1", "p-1", "judgment")
        payload = claude_tool("Bash", {"command": "cat > f <<EOF\nx\nEOF", "run_in_background": True}, cwd=self.work)
        out = self.run_guard("claude", payload)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("watcher", out)
        self.assertEqual([r["rule"] for r in self.log_records() if r.get("decision") == "deny"], ["G4"])

    def test_g5_leaves_other_hosts_and_subagents_alone(self) -> None:
        self.write_turn("sess-1", "p-1", "judgment")
        self.run_guard("claude", claude_prompt(cwd=self.work))
        self.assertEqual(self.run_guard("claude", claude_tool("Bash", {"command": "echo x > out.txt"}, cwd=self.work,
                                                              agent_id="a1", agent_type="executor")), "")
        codex = {"session_id": "sess-1", "turn_id": "p-1", "cwd": self.work, "hook_event_name": "PreToolUse",
                 "tool_name": "Bash", "tool_input": {"command": "echo x > out.txt"}}
        self.assertEqual(self.run_guard("codex", codex), "")

    def test_g5_an_allowed_shell_write_does_not_count_toward_r2(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work))
        for name in ("x1", "x2", "x3"):
            self.assertEqual(self.run_guard("claude", claude_tool("Bash", {"command": "echo 1 > " + name}, cwd=self.work)), "")
        for name in ("a", "b"):
            self.assertEqual(self.run_guard("claude", claude_tool("Edit", {"file_path": name}, cwd=self.work)), "")
        self.assertIn("edited 3 files", self.run_guard("claude", claude_tool("Edit", {"file_path": "c"}, cwd=self.work)))

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
        self.assertIn("edited 3 files", self.run_guard("claude", edit("c")))
        state = json.loads(Path(self.guard_dir, "state", "sess-1.json").read_text(encoding="utf-8"))
        self.assertEqual(state["turn_id"], "p-1")
        self.assertFalse(state["dispatched"])
        self.assertEqual(len(state["edited"]), 3)

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


class DeclareCliTests(CliCase):
    """`declare` mode through the real script (SHOAL_GUARD_R1=declare; no classification file anywhere)."""

    def guard_run(self, payload) -> str:
        return self.run_guard("claude", payload, SHOAL_GUARD_R1="declare")

    def edit(self, name="a.py", **kw) -> str:
        return self.guard_run(claude_tool("Edit", {"file_path": name}, cwd=self.work, **kw))

    def bash(self, command, **kw) -> str:
        return self.guard_run(claude_tool("Bash", {"command": command}, cwd=self.work, **kw))

    def start(self, **kw) -> None:
        self.guard_run(claude_prompt(cwd=self.work, **kw))

    def test_undeclared_edit_and_shell_write_are_denied_with_the_three_exits(self) -> None:
        self.start()
        for out in (self.edit(), self.bash("cat > a.py <<'EOF'\nx\nEOF")):
            body = json.loads(out)["hookSpecificOutput"]
            self.assertEqual((body["hookEventName"], body["permissionDecision"]), ("PreToolUse", "deny"))
            self.assertEqual(body["permissionDecisionReason"], guard.MESSAGES["en"]["DECLARE"])
        self.assertFalse(os.path.exists(os.path.join(self.guard_dir, "turns")) and
                         os.listdir(os.path.join(self.guard_dir, "turns")))

    def test_declaration_releases_edits_and_shell_writes_for_that_turn_only(self) -> None:
        self.start()
        self.assertIn("deny", self.edit())
        self.assertEqual(self.bash('  : shoal-direct "fix a typo"  '), "")
        self.assertEqual(self.edit(), "")
        self.assertEqual(self.bash("echo x > a.py"), "")
        self.guard_run(claude_prompt(cwd=self.work, prompt_id="p-2", prompt="next"))
        self.assertIn("deny", self.edit(prompt_id="p-2"))
        self.assertIn("deny", self.bash("echo x > a.py", prompt_id="p-2"))
        records = self.log_records()
        declared = [r for r in records if r.get("rule") == "declare"]
        self.assertEqual(len(declared), 1)
        self.assertEqual((declared[0]["decision"], declared[0]["reason"], declared[0]["tool"]), ("state", "fix a typo", "Bash"))

    def test_declaration_reason_is_logged_not_stored_in_state(self) -> None:
        self.start()
        self.bash(': shoal-direct "SECRET-REASON ' + "x" * 300 + '"')
        state = Path(self.guard_dir, "state", "sess-1.json").read_text(encoding="utf-8")
        self.assertNotIn("SECRET-REASON", state)
        self.assertIn('"declared": true', state)
        logged = [r for r in self.log_records() if r.get("rule") == "declare"][0]["reason"]
        self.assertEqual(len(logged), 200)
        self.assertTrue(logged.startswith("SECRET-REASON"))

    def test_chained_or_malformed_declarations_are_not_declarations(self) -> None:
        self.start()
        for command in (': shoal-direct "x"; rm -rf foo', 'ls; : shoal-direct "x"', ': shoal-direct ""',
                        ': shoal-direct "x" && ls', ': shoal-direct "x"\nls'):
            self.assertEqual(self.bash(command), "", command)
        self.assertIn("deny", self.edit())
        self.assertEqual([r for r in self.log_records() if r.get("rule") == "declare"], [])
        self.assertIn("deny", self.bash(': shoal-direct "x" > a.py'))

    def test_subagent_declaration_is_ignored(self) -> None:
        self.start()
        self.assertEqual(self.bash(': shoal-direct "x"', agent_id="ag-1", agent_type="executor"), "")
        self.assertIn("deny", self.edit())
        self.assertEqual(self.edit("b.py", agent_id="ag-1", agent_type="executor"), "")

    def test_declaration_does_not_unlock_the_background_shell_rule(self) -> None:
        self.start()
        self.bash(': shoal-direct "x"')
        out = self.guard_run(claude_tool("Bash", {"command": "sleep 1", "run_in_background": True}, cwd=self.work))
        self.assertIn(guard.MESSAGES["en"]["G4"], out)

    def test_dispatch_direct_and_parent_local_release_without_a_declaration(self) -> None:
        self.start(prompt="fix it #direct")
        self.assertEqual(self.edit(), "")
        self.start(prompt_id="p-2", prompt="plain")
        self.assertIn("deny", self.edit(prompt_id="p-2"))
        self.guard_run(claude_tool("Agent", {"subagent_type": "scout"}, cwd=self.work, prompt_id="p-2"))
        self.assertIn("deny", self.edit(prompt_id="p-2"))
        self.guard_run(claude_tool("Agent", {"subagent_type": "executor"}, cwd=self.work, prompt_id="p-2"))
        self.assertIn("deny", self.edit(prompt_id="p-2"))  # dispatched but not started
        self.guard_run(claude_start("shoal:executor", cwd=self.work, prompt_id="p-2"))
        self.assertEqual(self.edit(prompt_id="p-2"), "")
        self.start(prompt_id="p-3", prompt="plain")
        self.write_turn("sess-1", "p-3", "judgment")
        self.assertIn("deny", self.edit(prompt_id="p-3"))
        self.write_turn("sess-1", "p-3", "parent_local")
        self.assertEqual(self.edit(prompt_id="p-3"), "")
        self.assertEqual(self.run_guard("claude", claude_tool("Edit", {"file_path": "z.py"}, cwd=self.work, prompt_id="p-4"),
                                        SHOAL_GUARD_R1="declare", SHOAL_GUARD_DIRECT="1"), "")

    def test_off_and_classified_modes_do_not_deny_without_a_classification(self) -> None:
        self.start()
        for mode in ("off", "classified"):
            out = self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work), SHOAL_GUARD_R1=mode)
            self.assertEqual(out, "", mode)
            self.assertEqual(self.run_guard("claude", claude_tool("Bash", {"command": 'echo x > a.py'}, cwd=self.work),
                                            SHOAL_GUARD_R1=mode), "", mode)

    def test_zh_tw_message(self) -> None:
        self.start()
        out = self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work),
                             SHOAL_GUARD_R1="declare", SHOAL_GUARD_LANG="zh-TW")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"], guard.MESSAGES["zh-TW"]["DECLARE"])

    def test_codex_declare_end_to_end(self) -> None:
        patch = "*** Begin Patch\n*** Add File: a\n+x\n*** End Patch"

        def codex(payload) -> str:
            return self.run_guard("codex", payload, SHOAL_GUARD_R1="declare")

        codex(CodexAdapterTests.prompt(cwd=self.work))
        out = json.loads(codex(CodexAdapterTests.tool("apply_patch", {"command": patch}, cwd=self.work)))["hookSpecificOutput"]
        self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]),
                         ("deny", guard.MESSAGES["en"]["DECLARE"]))
        self.assertEqual(codex(CodexAdapterTests.tool("Bash", {"command": 'echo ok'}, cwd=self.work)), "")
        self.assertEqual([r.get("tool") for r in self.log_records()], [None, "apply_patch"])  # echo ok: no log line
        self.assertEqual(codex(CodexAdapterTests.tool("Bash", {"command": ' : shoal-direct "tiny fix" '}, cwd=self.work)), "")
        self.assertEqual(codex(CodexAdapterTests.tool("apply_patch", {"command": patch}, cwd=self.work)), "")
        self.assertEqual(self.log_records()[-1]["rule"], "declared")
        codex(CodexAdapterTests.prompt(cwd=self.work, turn_id="019f-t2"))
        heredoc = "cat > f.txt <<'EOF'\nhi\nEOF"
        out = json.loads(codex(CodexAdapterTests.tool("Bash", {"command": heredoc}, cwd=self.work, turn_id="019f-t2")))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        # a subagent's declaration is ignored
        self.assertEqual(codex(CodexAdapterTests.tool("Bash", {"command": ': shoal-direct "x"'}, cwd=self.work,
                                                      turn_id="019f-t2", agent_id="a1", agent_type="executor")), "")
        self.assertIn("deny", codex(CodexAdapterTests.tool("apply_patch", {"command": patch}, cwd=self.work, turn_id="019f-t2")))
        # classified on codex keeps the advise-only behaviour
        out = self.run_guard("codex", CodexAdapterTests.tool("apply_patch", {"command": patch}, cwd=self.work, turn_id="019f-t2"),
                             SHOAL_GUARD_R1="classified")
        self.assertNotIn("permissionDecision", out)


class StrictCliTests(CliCase):
    """`strict` (the claude and codex default since 3.3.0) through the real script, claude and codex payloads."""

    PATCH = "*** Begin Patch\n*** Add File: a\n+x\n*** End Patch"

    def claude(self, payload) -> str:
        return self.run_guard("claude", payload, SHOAL_GUARD_R1="")

    def codex(self, payload) -> str:
        return self.run_guard("codex", payload, SHOAL_GUARD_R1="")

    def deny_reason(self, out: str) -> str:
        body = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(body["permissionDecision"], "deny")
        return body["permissionDecisionReason"]

    def test_messages(self) -> None:
        self.assertEqual(
            guard.MESSAGES["en"]["STRICT"],
            "Shoal dispatch guard: the main session does not edit files itself. Dispatch a write-capable role "
            "(executor or applier), or ask the user to add #direct to the prompt.")
        for lang in ("en", "zh-TW"):
            text = guard.MESSAGES[lang]["STRICT"]
            for needle in ("executor", "applier", "#direct"):
                self.assertIn(needle, text)
            self.assertNotIn("shoal-direct", text)

    def test_claude_exits_are_dispatch_and_hash_direct_only(self) -> None:
        self.claude(claude_prompt(cwd=self.work))
        edit = claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work)
        self.assertEqual(self.deny_reason(self.claude(edit)), guard.MESSAGES["en"]["STRICT"])
        before = self.log_records()
        self.assertEqual(self.claude(claude_tool("Bash", {"command": ': shoal-direct "tiny fix"'}, cwd=self.work)), "")
        self.assertEqual(self.log_records(), before)  # a declaration is an ordinary no-op: no state, no log
        self.assertIn("deny", self.claude(edit))
        self.write_turn("sess-1", "p-1", "parent_local")
        self.assertIn("deny", self.claude(edit))
        self.assertIn("deny", self.claude(claude_tool("Bash", {"command": "echo x > a.py"}, cwd=self.work)))
        self.assertEqual(self.claude(claude_tool("Agent", {"subagent_type": "scout"}, cwd=self.work)), "")
        self.assertIn("deny", self.claude(edit))
        self.assertEqual(self.claude(claude_tool("Agent", {"subagent_type": "executor"}, cwd=self.work)), "")
        self.assertIn("deny", self.claude(edit))  # the role has not started yet
        self.assertEqual(self.claude(claude_start("shoal:executor", cwd=self.work)), "")
        self.assertEqual(self.claude(edit), "")
        self.claude(claude_prompt(cwd=self.work, prompt_id="p-2", prompt="fix it #direct"))
        self.assertEqual(self.claude(claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work, prompt_id="p-2")), "")
        self.assertEqual(self.run_guard("claude", claude_tool("Edit", {"file_path": "b.py"}, cwd=self.work, prompt_id="p-3"),
                                        SHOAL_GUARD_R1="", SHOAL_GUARD_DIRECT="1"), "")

    def test_codex_exits_are_dispatch_and_hash_direct_only(self) -> None:
        self.codex(CodexAdapterTests.prompt(cwd=self.work))
        patch = CodexAdapterTests.tool("apply_patch", {"command": self.PATCH}, cwd=self.work)
        self.assertEqual(self.deny_reason(self.codex(patch)), guard.MESSAGES["en"]["STRICT"])
        self.assertEqual(self.codex(CodexAdapterTests.tool("Bash", {"command": ': shoal-direct "x"'}, cwd=self.work)), "")
        self.assertIn("deny", self.codex(patch))
        self.assertIn("deny", self.codex(CodexAdapterTests.tool("Bash", {"command": "cat > f <<'EOF'\nhi\nEOF"}, cwd=self.work)))
        self.assertEqual(self.codex(CodexAdapterTests.tool("Bash", {"command": "echo ok"}, cwd=self.work)), "")
        self.assertEqual(self.codex(CodexAdapterTests.tool("spawn_agent", {"agent_type": "scout"}, cwd=self.work)), "")
        self.assertIn("deny", self.codex(patch))
        self.assertEqual(self.codex(CodexAdapterTests.tool("spawn_agent", {"agent_type": "executor"}, cwd=self.work)), "")
        self.assertIn("deny", self.codex(patch))  # a dispatched role unlocks once it has started (SubagentStart), not at the call
        self.assertEqual(self.codex(CodexAdapterTests.start("executor", cwd=self.work)), "")
        self.assertEqual(self.codex(patch), "")
        self.codex(CodexAdapterTests.prompt(cwd=self.work, turn_id="019f-t2", prompt="do it #direct"))
        self.assertEqual(self.codex(CodexAdapterTests.tool("apply_patch", {"command": self.PATCH}, cwd=self.work, turn_id="019f-t2")), "")

    def test_selectable_modes_keep_their_behavior(self) -> None:
        self.claude(claude_prompt(cwd=self.work))
        edit = claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work)
        self.assertEqual(self.run_guard("claude", edit, SHOAL_GUARD_R1="off"), "")
        self.assertEqual(self.run_guard("claude", edit, SHOAL_GUARD_R1="classified"), "")
        self.assertEqual(self.deny_reason(self.run_guard("claude", edit, SHOAL_GUARD_R1="declare")),
                         guard.MESSAGES["en"]["DECLARE"])


class StopCheckCliTests(CliCase):
    """B2-B4 (docs/specs/shared-rules): the completion check, run through the real script.  The vectors carry the
    rule table for both implementations; these tests cover the output format, the recorded payload shapes, the
    one-block-per-turn persistence and the fail-open paths that need a real process or a patched write."""

    SHAPES = json.loads((ROOT / "tests" / "fixtures" / "stop_payload_shapes.json").read_text(encoding="utf-8"))
    TEXT = ("Shoal completion check: this turn changed files and no check ran afterwards. Run a verification now "
            "(tests, a verifier or watcher role), or say explicitly in your report that the change is unverified.")

    def env(self, **extra: str) -> dict:
        return super().env(**{"SHOAL_GUARD_R1": "", **extra})  # the host default: strict

    def claude_stop(self, turn: str = "p-1", **kw) -> dict:
        return {"session_id": "sess-1", "prompt_id": turn, "cwd": self.work, "hook_event_name": "Stop",
                "stop_hook_active": False, "permission_mode": "default", **kw}

    def codex_stop(self, turn: str = "t-1", **kw) -> dict:
        return {"session_id": "019f-s", "turn_id": turn, "cwd": self.work, "hook_event_name": "Stop",
                "stop_hook_active": False, "model": "m", **kw}

    def test_recorded_stop_shapes_are_accepted(self) -> None:
        make = {"str": "synthetic", "bool": False, "dict": {}, "list": []}
        for host, adapt in (("claude", guard.adapt_claude), ("codex", guard.adapt_codex)):
            shape = self.SHAPES[host]
            payload = {key: make[kind] for key, kind in shape["keys"].items()}
            payload["hook_event_name"] = shape["hook_event_name"]
            with self.subTest(host):
                event = adapt(payload)
                self.assertEqual((event["kind"], event["is_subagent"], event["tool_kind"]), ("stop", False, None))
                self.assertEqual((event["session_id"], event["turn_id"]), ("synthetic", "synthetic"))
                self.assertIs(event["stop_hook_active"], False)
                self.assertIn(shape["turn_key"], payload)
                payload["stop_hook_active"] = True
                self.assertIs(adapt(payload)["stop_hook_active"], True)
                del payload["stop_hook_active"]
                self.assertIsNone(adapt(payload)["stop_hook_active"])

    def test_claude_flow_blocks_once_and_a_check_releases_it(self) -> None:
        def turn(turn_id: str, edit: bool, check: str = "") -> list:
            outs = [self.run_guard("claude", claude_prompt(cwd=self.work, prompt_id=turn_id, prompt="#direct do it"))]
            if edit:
                outs.append(self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work, prompt_id=turn_id)))
            if check:
                outs.append(self.run_guard("claude", claude_tool("Bash", {"command": check}, cwd=self.work, prompt_id=turn_id)))
            outs.append(self.run_guard("claude", self.claude_stop(turn_id)))
            return outs

        first = turn("p-1", edit=True)
        self.assertEqual(first[:-1], ["", ""])
        self.assertEqual(json.loads(first[-1]), {"decision": "block", "reason": self.TEXT})  # (a)
        self.assertEqual(self.run_guard("claude", self.claude_stop("p-1")), "")  # (b) one block per turn
        self.assertEqual(self.run_guard("claude", self.claude_stop("p-1", stop_hook_active=True)), "")
        self.assertEqual(turn("p-2", edit=True, check="python3 -m unittest")[-1], "")  # (c)
        self.assertEqual(turn("p-3", edit=False)[-1], "")  # (d)
        records = [r for r in self.log_records() if r.get("event") == "stop"]
        self.assertEqual([(r["decision"], r.get("rule")) for r in records if r["decision"] == "block"], [("block", "STOP")])

    def test_codex_flow_blocks_once_and_a_check_releases_it(self) -> None:
        patch = "*** Begin Patch\n*** Update File: a.py\n@@\n-a\n+b\n*** End Patch"

        def turn(turn_id: str, edit: bool, check: str = "") -> list:
            outs = [self.run_guard("codex", CodexAdapterTests.prompt(cwd=self.work, turn_id=turn_id, prompt="#direct do it"))]
            if edit:
                outs.append(self.run_guard("codex", CodexAdapterTests.tool("apply_patch", {"command": patch}, cwd=self.work, turn_id=turn_id)))
            if check:
                outs.append(self.run_guard("codex", CodexAdapterTests.tool("Bash", {"command": check}, cwd=self.work, turn_id=turn_id)))
            outs.append(self.run_guard("codex", self.codex_stop(turn_id)))
            return outs

        first = turn("t-1", edit=True)
        self.assertEqual(first[:-1], ["", ""])
        self.assertEqual(json.loads(first[-1]), {"decision": "block", "reason": self.TEXT})
        self.assertEqual(self.run_guard("codex", self.codex_stop("t-1")), "")
        self.assertEqual(turn("t-2", edit=True, check="python3 -m unittest")[-1], "")
        self.assertEqual(turn("t-3", edit=False)[-1], "")

    def test_posttoolusefailure_counts_as_a_check_on_claude(self) -> None:
        # E8: a Bash call that failed (non-zero exit) fires PostToolUseFailure instead of PostToolUse; it still ran.
        # The failure payload shape was not captured: only tool_name, tool_input, agent_id, session_id, prompt_id are read.
        def fail(command: str, turn: str, **kw) -> dict:
            return claude_tool("Bash", {"command": command}, cwd=self.work, prompt_id=turn,
                               hook_event_name="PostToolUseFailure", **kw)

        def prompt(t): return claude_prompt(cwd=self.work, prompt_id=t, prompt="#direct do it")
        def edit(t): return claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work, prompt_id=t)

        for payload in (prompt("f-1"), edit("f-1"), fail("make test", "f-1", error="exit 1")):
            self.assertEqual(self.run_guard("claude", payload), "")
        self.assertEqual(self.run_guard("claude", self.claude_stop("f-1")), "")
        # a subagent's failure does not count
        for payload in (prompt("f-2"), edit("f-2"), fail("make test", "f-2", agent_id="ag-1", agent_type="shoal:executor")):
            self.assertEqual(self.run_guard("claude", payload), "")
        self.assertEqual(json.loads(self.run_guard("claude", self.claude_stop("f-2")))["decision"], "block")
        # it sets post_seen: a later PreToolUse alone no longer counts
        pre = claude_tool("Bash", {"command": "make test"}, cwd=self.work, prompt_id="f-3")
        for payload in (prompt("f-3"), edit("f-3"), pre):
            self.assertEqual(self.run_guard("claude", payload), "")
        self.assertEqual(json.loads(self.run_guard("claude", self.claude_stop("f-3")))["decision"], "block")
        # background, non-Bash and malformed shapes: no event, no exception
        ev = fail("make test", "f-4")
        self.assertIsNotNone(guard.adapt_claude(ev))
        self.assertIsNone(guard.adapt_claude({**ev, "tool_input": {"command": "x", "run_in_background": True}}))
        self.assertIsNone(guard.adapt_claude({**ev, "tool_name": "Read"}))
        guard.adapt_claude({**ev, "tool_input": "oops"})  # any shape: fail-open, no exception
        self.assertIsNone(guard.adapt_claude({"hook_event_name": "PostToolUseFailure"}))

    def test_posttooluse_raw_payloads_set_the_check_on_claude_and_codex(self) -> None:
        # E8: PostToolUse (the call really ran) counts; PreToolUse only until the session has seen a PostToolUse.
        patch = "*** Begin Patch\n*** Update File: a.py\n@@\n-a\n+b\n*** End Patch"

        def claude_post(command: str, turn: str, **kw) -> dict:
            return claude_tool("Bash", {"command": command}, cwd=self.work, prompt_id=turn, hook_event_name="PostToolUse",
                               tool_response={"stdout": ""}, duration_ms=1, **kw)

        def codex_post(command: str, turn: str, **kw) -> dict:
            return CodexAdapterTests.tool("Bash", {"command": command}, cwd=self.work, turn_id=turn,
                                          hook_event_name="PostToolUse", tool_response="ok", **kw)

        flows = (
            ("claude", lambda t: claude_prompt(cwd=self.work, prompt_id=t, prompt="#direct do it"),
             lambda t: claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work, prompt_id=t),
             lambda c, t: claude_tool("Bash", {"command": c}, cwd=self.work, prompt_id=t),
             claude_post, self.claude_stop, {"agent_id": "ag-1", "agent_type": "shoal:executor"}),
            ("codex", lambda t: CodexAdapterTests.prompt(cwd=self.work, turn_id=t, prompt="#direct do it"),
             lambda t: CodexAdapterTests.tool("apply_patch", {"command": patch}, cwd=self.work, turn_id=t),
             lambda c, t: CodexAdapterTests.tool("Bash", {"command": c}, cwd=self.work, turn_id=t),
             codex_post, self.codex_stop, {"agent_id": "ag-1", "agent_type": "applier"}),
        )
        for host, prompt, edit, pre, post, stop, sub in flows:
            with self.subTest(host):
                self.setUp()  # a fresh sandbox per host
                # fresh session, PreToolUse only: the fallback counts it (old registration without PostToolUse)
                for payload in (prompt("a-1"), edit("a-1"), pre("make test", "a-1")):
                    self.assertEqual(self.run_guard(host, payload), "")
                self.assertEqual(self.run_guard(host, stop("a-1")), "")
                # a subagent's PostToolUse neither counts nor marks the session as post-capable
                for payload in (prompt("a-2"), edit("a-2"), post("make test", "a-2", **sub)):
                    self.assertEqual(self.run_guard(host, payload), "")
                self.assertEqual(json.loads(self.run_guard(host, stop("a-2")))["decision"], "block")
                # the main session's PostToolUse counts and switches the Pre fallback off for the session
                for payload in (prompt("a-3"), edit("a-3"), post("make test", "a-3")):
                    self.assertEqual(self.run_guard(host, payload), "")
                self.assertEqual(self.run_guard(host, stop("a-3")), "")
                for payload in (prompt("a-4"), edit("a-4"), pre("make test", "a-4")):
                    self.assertEqual(self.run_guard(host, payload), "")
                self.assertEqual(json.loads(self.run_guard(host, stop("a-4")))["decision"], "block")
        # a background Bash or a non-Bash PostToolUse is no event at all
        background = claude_tool("Bash", {"command": "make test", "run_in_background": True}, cwd=self.work,
                                 hook_event_name="PostToolUse", tool_response={})
        self.assertIsNone(guard.adapt_claude(background))
        self.assertIsNone(guard.adapt_claude({**background, "tool_name": "Read", "tool_input": {"file_path": "a"}}))
        self.assertIsNone(guard.adapt_codex(CodexAdapterTests.tool("apply_patch", {"command": patch}, hook_event_name="PostToolUse")))

    def test_nothing_is_printed_for_a_subagent_stop_or_another_session(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt="#direct"))
        self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work))
        self.assertEqual(self.run_guard("claude", self.claude_stop(agent_id="ag-1", agent_type="executor")), "")
        self.assertEqual(self.run_guard("claude", self.claude_stop(session_id="sess-2")), "")
        self.assertEqual(self.run_guard("claude", self.claude_stop(stop_hook_active="false")), "")
        self.assertEqual(json.loads(self.run_guard("claude", self.claude_stop()))["decision"], "block")

    def test_other_hosts_never_print_a_block(self) -> None:
        grok_prompt = {"hookEventName": "user_prompt_submit", "sessionId": "sess-1", "promptId": "p-1", "cwd": self.work}
        grok_edit = {"hookEventName": "pre_tool_use", "sessionId": "sess-1", "promptId": "p-1", "cwd": self.work,
                     "toolName": "write", "toolInput": {"file_path": "a.py"}}
        self.run_guard("grok", grok_prompt, SHOAL_GUARD="enforce", SHOAL_GUARD_R1="")
        self.run_guard("grok", grok_edit, SHOAL_GUARD="enforce", SHOAL_GUARD_R1="", SHOAL_GUARD_DIRECT="1")
        self.assertEqual(self.run_guard("grok", {"hookEventName": "stop", "sessionId": "sess-1", "promptId": "p-1",
                                                  "reason": "end_turn", "stopHookActive": False},
                                        SHOAL_GUARD="enforce", SHOAL_GUARD_R1=""), "")  # grok: shadow unless asked
        self.assertEqual(self.run_guard("agy", {"conversationId": "c", "invocationNum": 1}), "")

    def test_a_failed_state_write_does_not_block_and_does_not_spend_the_turn(self) -> None:
        env = self.env()
        for payload in (claude_prompt(cwd=self.work, prompt="#direct"),
                        claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work)):
            guard.run("claude", json.dumps(payload).encode(), env)
        raw = json.dumps(self.claude_stop()).encode()
        with mock.patch.object(guard, "_write_json", return_value=False):
            self.assertIsNone(guard.run("claude", raw, env))
        self.assertEqual(self.log_records()[-1]["skip_reason"], "state_write_failed")
        self.assertEqual(json.loads(guard.run("claude", raw, env))["decision"], "block")  # the failed write spent nothing
        self.assertIsNone(guard.run("claude", raw, env))

    def test_plain_shell_calls_touch_neither_state_nor_log_unless_a_check_is_due(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt="#direct"))
        state_file = Path(self.guard_dir, "state", "sess-1.json")
        before = (state_file.read_bytes(), len(self.log_records()), os.stat(state_file).st_mtime_ns)
        self.assertEqual(self.run_guard("claude", claude_tool("Bash", {"command": "ls"}, cwd=self.work)), "")
        self.assertEqual((state_file.read_bytes(), len(self.log_records()), os.stat(state_file).st_mtime_ns), before)
        self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work))
        changed = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual((changed["changed"], changed["checked"]), (True, False))
        logged = len(self.log_records())
        self.assertEqual(self.run_guard("claude", claude_tool("Bash", {"command": "ls"}, cwd=self.work)), "")
        checked = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual((checked["changed"], checked["checked"]), (True, True))
        self.assertEqual(len(self.log_records()), logged)  # the bookkeeping never logs

    def test_stop_switch_table(self) -> None:
        for host in ("claude", "codex"):
            for value, want in ((None, True), ("on", True), ("maybe", True), ("", True), ("off", False)):
                env = {} if value is None else {"SHOAL_GUARD_STOP": value}
                self.assertIs(guard.stop_enabled(host, env), want, (host, value))
        for host in ("grok", "agy"):
            for value, want in ((None, True), ("on", True), ("enforce", True), ("off", False)):
                env = {} if value is None else {"SHOAL_GUARD_STOP": value}
                self.assertIs(guard.stop_enabled(host, env), want, (host, value))
        for host in ("opencode", ""):
            self.assertIs(guard.stop_enabled(host, {}), False, host)
            self.assertIs(guard.stop_enabled(host, {"SHOAL_GUARD_STOP": "on"}), False, host)
        self.assertEqual(guard.STOP_HOSTS, frozenset({"claude", "codex", "grok", "agy"}))
        # grok's and agy's block output is unexercised: they block only when asked, the other hosts block unless switched off
        self.assertIs(guard.stop_blocks("agy", {}), False)
        self.assertIs(guard.stop_blocks("agy", {"SHOAL_GUARD_STOP": "enforce"}), True)
        self.assertIs(guard.stop_blocks("grok", {}), False)
        self.assertIs(guard.stop_blocks("grok", {"SHOAL_GUARD_STOP": "on"}), False)
        self.assertIs(guard.stop_blocks("grok", {"SHOAL_GUARD_STOP": "enforce"}), True)
        self.assertIs(guard.stop_blocks("claude", {}), True)

    def test_the_switch_and_the_guard_mode_silence_the_check(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt="#direct"))
        self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work))
        self.assertEqual(self.run_guard("claude", self.claude_stop(), SHOAL_GUARD_STOP="off"), "")
        self.assertEqual(self.run_guard("claude", self.claude_stop(), SHOAL_GUARD="shadow"), "")
        self.assertEqual(self.log_records()[-1]["decision"], "would_block")
        self.assertEqual(self.run_guard("claude", self.claude_stop(), SHOAL_GUARD="off"), "")
        self.assertEqual(json.loads(self.run_guard("claude", self.claude_stop()))["decision"], "block")

    def test_zh_tw_message_and_state_never_hold_the_last_message(self) -> None:
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt="#direct"))
        self.run_guard("claude", claude_tool("Edit", {"file_path": "a.py"}, cwd=self.work))
        out = json.loads(self.run_guard("claude", self.claude_stop(last_assistant_message="SECRET-LAST-MESSAGE"),
                                        SHOAL_GUARD_LANG="zh-TW"))
        self.assertIn("本回合改過檔案", out["reason"])
        blob = ""
        for dirpath, _, names in os.walk(self.guard_dir):
            for name in names:
                blob += Path(dirpath, name).read_text(encoding="utf-8")
        self.assertNotIn("SECRET-LAST-MESSAGE", blob)


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

    @staticmethod
    def start(agent_type, agent_id="019f-a1", **kw):
        """tests/fixtures/codex_subagent_tool_shapes.json: SubagentStart keys; turn_id is the subagent's own."""
        return {"session_id": "019f-s", "turn_id": "019f-sub", "cwd": "WORK", "hook_event_name": "SubagentStart",
                "agent_id": agent_id, "agent_type": agent_type, "model": "gpt", "permission_mode": "never",
                "transcript_path": "x", **kw}

    def test_recorded_subagent_start_shape_is_accepted(self) -> None:
        event = guard.adapt_codex(self.start("applier"))
        self.assertEqual((event["kind"], event["role"], event["agent_id"], event["session_id"], event["is_subagent"]),
                         ("subagent_start", "applier", "019f-a1", "019f-s", False))
        self.assertIsNone(event["turn_id"])  # the subagent's own turn says nothing about main's
        sub = guard.adapt_codex(self.tool("apply_patch", {"command": self.PATCH}, agent_id="019f-a1", agent_type="worker"))
        self.assertEqual((sub["is_subagent"], sub["role"], sub["agent_id"]), (True, "worker", "019f-a1"))
        self.assertIsNone(guard.adapt_codex(self.tool("Bash", {"command": "ls"}))["agent_id"])
        for bad in ({"hook_event_name": "SubagentStart"}, self.start(7, agent_id=None), self.start("applier", agent_id={})):
            self.assertEqual(guard.adapt_codex(bad)["kind"], "subagent_start")

    def test_worker_subagent_edit_is_denied_by_default_and_applier_is_not(self) -> None:
        env = {"SHOAL_GUARD": "enforce"}
        worker = self.tool("apply_patch", {"command": self.PATCH}, cwd=self.work, agent_id="019f-w1", agent_type="worker")
        out = self.run_guard("codex", worker, **env)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        record = self.log_records()[-1]
        self.assertEqual((record["rule"], record["agent_type"], record["agent_id"]), ("E1", "worker", "019f-w1"))
        applier = self.tool("apply_patch", {"command": self.PATCH}, cwd=self.work, agent_id="019f-a1", agent_type="applier")
        self.assertEqual(self.run_guard("codex", applier, **env), "")
        self.assertEqual(self.run_guard("codex", worker, SHOAL_GUARD_SUBAGENT_WRITE="off", **env), "")

    def test_direct_turn_releases_the_agent_started_in_it_through_the_real_script(self) -> None:
        env = {"SHOAL_GUARD": "enforce"}
        self.run_guard("codex", self.prompt(cwd=self.work, prompt="fix it #direct"), **env)
        self.assertEqual(self.run_guard("codex", self.start("worker", agent_id="019f-w1", cwd=self.work), **env), "")
        released = self.tool("apply_patch", {"command": self.PATCH}, cwd=self.work, agent_id="019f-w1", agent_type="worker",
                             turn_id="019f-sub")
        self.assertEqual(self.run_guard("codex", released, **env), "")
        other = self.tool("apply_patch", {"command": self.PATCH}, cwd=self.work, agent_id="019f-w2", agent_type="worker",
                          turn_id="019f-sub2")
        out = json.loads(self.run_guard("codex", other, **env))
        self.assertIn("#direct", out["hookSpecificOutput"]["permissionDecisionReason"])

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
        shell = guard.adapt_codex(self.tool("Bash", {"command": "echo ok"}))
        self.assertEqual((shell["tool_kind"], shell["command"], shell["turn_id"]), ("shell", "echo ok", "019f-t"))
        for bad in ({}, {"command": 7}, {"command": ["ls"]}, {"cmd": "ls"}):
            self.assertEqual(guard.adapt_codex(self.tool("Bash", bad))["tool_kind"], "other", bad)
        self.assertTrue(guard.adapt_codex(self.tool("Bash", {"command": "ls"}, agent_id="a1", agent_type="executor"))["is_subagent"])

    def test_recorded_payload_shape_is_accepted(self) -> None:
        # tests/fixtures/codex_payload_shapes.json: keys and types of a real codex-cli 0.160.0/0.160.1 run.
        shapes = json.loads((ROOT / "tests" / "fixtures" / "codex_payload_shapes.json").read_text(encoding="utf-8"))
        make = {"str": "synthetic", "dict": {"command": "echo synthetic"}, "NoneType": None}
        for name, shape in shapes["events"].items():
            payload = {key: make[kind] for key, kind in shape["keys"].items()}
            payload["cwd"] = self.work
            payload["hook_event_name"] = shape["hook_event_name"]
            if "tool_name" in payload:
                payload["tool_name"] = shape["tool_name"]
            if "tool_input" in payload:
                payload["tool_input"] = {k: make[t] for k, t in shape["tool_input"].items()}
            with self.subTest(name):
                event = guard.adapt_codex(payload)
                self.assertEqual(event["kind"], shape["expect_kind"])
                self.assertEqual(event["tool_kind"], shape["expect_tool_kind"])
                self.assertFalse(event["is_subagent"])
                self.assertEqual((event["session_id"], event["turn_id"]), ("synthetic", "synthetic"))
                self.assertEqual(event["command"], shape.get("expect_command"))

    def test_default_enforce_and_explicit_shadow_off(self) -> None:
        self.run_guard("codex", self.prompt(cwd=self.work))
        for name in ("a", "b"):
            patch = "*** Begin Patch\n*** Add File: %s\n+x\n*** End Patch" % name
            self.assertEqual(self.run_guard("codex", self.tool("apply_patch", {"command": patch}, cwd=self.work)), "")
        patch = "*** Begin Patch\n*** Add File: c\n+x\n*** End Patch"
        self.assertEqual(self.run_guard("codex", self.tool("apply_patch", {"command": patch}, cwd=self.work), SHOAL_GUARD="shadow"), "")
        self.assertEqual(self.log_records()[-1]["decision"], "advise")
        self.assertEqual(self.run_guard("codex", self.tool("apply_patch", {"command": patch}, cwd=self.work), SHOAL_GUARD="off"), "")
        patch = "*** Begin Patch\n*** Add File: d\n+x\n*** End Patch"
        out = self.run_guard("codex", self.tool("apply_patch", {"command": patch}, cwd=self.work))
        body = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(set(body), {"hookEventName", "additionalContext"})
        self.assertIn("spawn_agent", body["additionalContext"])

    def test_multi_file_patch_advises_in_one_call(self) -> None:
        self.run_guard("codex", self.prompt(cwd=self.work), SHOAL_GUARD="enforce")
        out = self.run_guard("codex", self.tool("apply_patch", {"command": self.PATCH}, cwd=self.work), SHOAL_GUARD="enforce")
        self.assertIn("edited 5 files", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("permissionDecision", out)

    def test_dispatch_write_role_unlocks(self) -> None:
        env = {"SHOAL_GUARD": "enforce", "SHOAL_GUARD_R1": "strict"}
        self.run_guard("codex", self.prompt(cwd=self.work), **env)
        self.assertEqual(self.run_guard("codex", self.tool("collaborationspawn_agent", {"agent_type": "executor"}, cwd=self.work), **env), "")
        patch = self.tool("apply_patch", {"command": self.PATCH}, cwd=self.work)
        self.assertIn("deny", self.run_guard("codex", patch, **env))  # the dispatch call alone no longer unlocks (E3)
        self.assertEqual(self.run_guard("codex", self.start("executor", cwd=self.work), **env), "")
        self.assertEqual(self.run_guard("codex", patch, **env), "")

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

    def test_enforce_advise_prints_nothing_and_logs(self) -> None:
        env = {"SHOAL_GUARD": "enforce"}
        self.run_guard("grok", self.prompt(cwd=self.work), **env)
        self.write_turn("gs-1", "gp-1", "judgment")
        self.assertEqual(self.run_guard("grok", self.tool("search_replace", {"file_path": "a.py"}, cwd=self.work), **env), "")
        self.assertEqual(self.log_records()[-1]["decision"], "advise")
        self.assertEqual(self.run_guard("grok", self.tool("spawn_subagent", {"subagent_type": "applier"}, cwd=self.work), **env), "")
        self.assertEqual(self.run_guard("grok", self.tool("search_replace", {"file_path": "a.py"}, cwd=self.work), **env), "")

    def test_default_mode_is_enforce_and_classified_only_advises(self) -> None:
        self.run_guard("grok", self.prompt(cwd=self.work))
        self.write_turn("gs-1", "gp-1", "judgment")
        self.assertEqual(self.run_guard("grok", self.tool("search_replace", {"file_path": "a.py"}, cwd=self.work)), "")
        self.assertEqual(self.log_records()[-1]["decision"], "advise")

    def test_tool_without_prompt_id_uses_state_turn(self) -> None:
        def e0(name):
            payload = self.tool("search_replace", {"file_path": "src/" + name + ".py"}, cwd=self.work)
            del payload["promptId"]
            return payload
        self.run_guard("grok", self.prompt(cwd=self.work))
        self.assertEqual(self.run_guard("grok", e0("a")), "")
        self.assertEqual(self.run_guard("grok", e0("b")), "")
        self.assertEqual(self.run_guard("grok", e0("c")), "")
        self.assertEqual(self.log_records()[-1]["decision"], "advise")
        self.assertEqual(self.run_guard("grok", e0("d"), SHOAL_GUARD="enforce"), "")

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
        self.assertEqual(self.log_records()[-1]["decision"], "advise")

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


class GrokGuardTests(CliCase):
    """guard-every-gate S4: shapes from tests/fixtures/grok_guard_event_shapes.json, run through the real script."""

    ENV = {"SHOAL_GUARD_R1": ""}  # the host default (strict); CliCase pins `classified`

    def common(self, name, **kw):
        return {"hookEventName": name, "sessionId": "gs-main", "cwd": self.work, "permissionMode": "default", **kw}

    def prompt(self, text="hello", prompt_id="gp-1"):
        return self.common("user_prompt_submit", promptId=prompt_id, prompt=text)

    def tool(self, name, tool_input, sid="gs-main", **kw):
        return self.common("pre_tool_use", toolName=name, toolInput=tool_input, toolUseId="u1", **{**kw, "sessionId": sid})

    def start(self, role, agent="gs-sub1"):
        return self.common("subagent_start", subagentId=agent, subagentType=role, description="d")

    def grok(self, payload, **env):
        return self.run_guard("grok", payload, **{**self.ENV, **env})

    def denied(self, out):
        return json.loads(out)["decision"] == "deny" if out else False

    def test_recorded_shapes_are_accepted(self) -> None:
        shell = guard.adapt_grok(self.tool("run_terminal_command", {"command": "echo x > a", "description": "d"}))
        self.assertEqual((shell["tool_kind"], shell["command"], shell["is_subagent"]), ("shell", "echo x > a", False))
        self.assertEqual(guard.adapt_grok(self.tool("run_terminal_command", {"description": "d"}))["tool_kind"], "other")
        start = guard.adapt_grok(self.start("applier"))
        self.assertEqual((start["kind"], start["session_id"], start["role"], start["agent_id"], start["is_subagent"], start["turn_id"]),
                         ("subagent_start", "gs-main", "applier", "gs-sub1", False, None))
        stop = guard.adapt_grok(self.common("stop", reason="end_turn", promptId="gp-1", stopHookActive=False))
        self.assertEqual((stop["kind"], stop["turn_id"], stop["stop_hook_active"]), ("stop", "gp-1", False))
        self.assertIsNone(guard.adapt_grok(self.common("stop", reason="shutdown", stopHookActive=False)))
        self.assertIsNone(guard.adapt_grok(self.common("stop", stopHookActive=False)))
        self.assertIsNone(guard.adapt_grok(self.common("stop", reason="end_turn", promptId="p", subagentType="applier")))
        self.assertIsNone(guard.adapt_grok(self.common("subagent_stop", subagentId="x")))

    def test_main_edit_and_shell_write_are_denied_by_default_and_a_started_write_role_unlocks(self) -> None:
        self.grok(self.prompt())
        write = self.tool("write", {"file_path": "src/a.py", "content": "x"})
        shell = self.tool("run_terminal_command", {"command": "echo x > src/a.py", "description": "d"})
        for payload in (write, self.tool("search_replace", {"file_path": "src/a.py"}), shell):
            self.assertTrue(self.denied(self.grok(payload)), payload["toolName"])
        self.assertEqual(self.grok(self.tool("run_terminal_command", {"command": "ls", "description": "d"})), "")
        self.assertEqual(self.grok(self.tool("spawn_subagent", {"subagent_type": "applier", "prompt": "p"})), "")
        self.assertTrue(self.denied(self.grok(write)))  # the dispatch call alone does not unlock
        self.assertEqual(self.grok(self.start("applier")), "")
        self.assertEqual(self.grok(write), "")
        self.assertEqual(self.grok(shell), "")

    def test_subagent_events_resolve_through_the_start_record(self) -> None:
        self.grok(self.prompt())
        self.grok(self.start("applier", "gs-sub1"))
        self.grok(self.start("general", "gs-sub2"))
        edit = {"file_path": "src/a.py", "content": "x"}
        self.assertEqual(self.grok(self.tool("write", edit, sid="gs-sub1", subagentType="applier")), "")
        self.assertTrue(self.denied(self.grok(self.tool("write", edit, sid="gs-sub2", subagentType="general"))))
        self.assertTrue(self.denied(self.grok(self.tool(
            "run_terminal_command", {"command": "echo x > src/a.py", "description": "d"}, sid="gs-sub2", subagentType="general"))))
        # a generic subagent whose own events carry no subagentType is still found by its session id
        self.assertTrue(self.denied(self.grok(self.tool("write", edit, sid="gs-sub2"))))
        self.assertEqual(self.grok(self.tool("write", {"file_path": "/tmp/x"}, sid="gs-sub2", subagentType="general")), "")
        self.assertEqual(self.grok(self.tool("write", edit, sid="gs-sub2", subagentType="general"), SHOAL_GUARD_WRITE_AGENTS="general"), "")
        # no record (the start event was missed): the role rules still apply, nothing releases it
        self.assertTrue(self.denied(self.grok(self.tool("write", edit, sid="gs-lost", subagentType="general"))))
        self.assertEqual(self.grok(self.tool("write", edit, sid="gs-lost", subagentType="applier")), "")
        self.assertTrue(self.denied(self.grok(self.tool("write", edit, sid="gs-lost", subagentType="verifier"))))
        self.assertTrue(self.denied(self.grok(self.tool("spawn_subagent", {"subagent_type": "scout"}, sid="gs-sub1", subagentType="applier"))))

    def test_direct_turn_releases_main_and_the_subagents_started_in_it(self) -> None:
        edit = {"file_path": "src/a.py", "content": "x"}
        self.grok(self.prompt("fix it #direct", "gp-1"))
        self.assertEqual(self.grok(self.tool("write", edit)), "")
        self.grok(self.start("general", "gs-sub1"))
        self.grok(self.prompt("next", "gp-2"))
        self.grok(self.start("general", "gs-sub2"))
        self.assertTrue(self.denied(self.grok(self.tool("write", edit))))
        self.assertEqual(self.grok(self.tool("write", edit, sid="gs-sub1", subagentType="general")), "")
        self.assertTrue(self.denied(self.grok(self.tool("write", edit, sid="gs-sub2", subagentType="general"))))
        self.assertTrue(self.denied(self.grok(self.tool("write", edit, sid="gs-sub3", subagentType="general"))))

    def test_agent_record_keeps_the_last_64(self) -> None:
        self.grok(self.prompt())
        for n in range(70):
            self.grok(self.start("general", "gs-a%d" % n))
        record = json.loads(Path(self.guard_dir, "state", "grok.agents.json").read_text(encoding="utf-8"))["agents"]
        self.assertEqual((len(record), record[0]["id"], record[-1]["id"]), (64, "gs-a6", "gs-a69"))
        self.assertEqual(record[-1], {"id": "gs-a69", "session": "gs-main", "role": "general", "direct": False})
        self.grok(self.start("applier", "gs-a69"))  # restarting an id replaces it
        record = json.loads(Path(self.guard_dir, "state", "grok.agents.json").read_text(encoding="utf-8"))["agents"]
        self.assertEqual((len(record), record[-1]["role"]), (64, "applier"))

    def test_stop_logs_would_block_by_default_and_blocks_only_when_asked(self) -> None:
        stop = self.common("stop", reason="end_turn", promptId="gp-1", stopHookActive=False)
        self.grok(self.prompt())
        self.grok(self.tool("spawn_subagent", {"subagent_type": "executor"}))
        self.grok(self.start("executor"))
        self.assertEqual(self.grok(stop), "")
        self.assertEqual((self.log_records()[-1]["decision"], self.log_records()[-1]["rule"]), ("would_block", "STOP"))
        self.assertEqual(self.grok(self.common("stop", reason="shutdown", stopHookActive=False)), "")
        out = json.loads(self.grok(stop, SHOAL_GUARD_STOP="enforce"))
        self.assertEqual(out["decision"], "block")
        self.assertEqual(self.grok(stop, SHOAL_GUARD_STOP="enforce"), "")  # one block per turn
        self.assertEqual(self.grok(self.common("stop", reason="end_turn", promptId="gp-1", stopHookActive=True),
                                   SHOAL_GUARD_STOP="enforce"), "")

    def test_mode_override_to_shadow_denies_nothing(self) -> None:
        self.grok(self.prompt(), SHOAL_GUARD="shadow")
        self.assertEqual(self.grok(self.tool("write", {"file_path": "src/a.py"}), SHOAL_GUARD="shadow"), "")
        self.assertEqual(self.log_records()[-1]["decision"], "would_deny")


class AgyAdapterTests(CliCase):
    def env(self, **extra: str) -> dict:
        return super().env(**{"SHOAL_GUARD_R1": "", **extra})  # the host default (strict)

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
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", self.subagents("applier")))["dispatched_role"], "applier")
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", {"Subagents": [{"Role": "executor"}]}))["dispatched_role"], "executor")
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", self.subagents("executor", "scout")))["dispatched_role"], "scout")
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", self.subagents("executor", "applier")))["dispatched_role"], "executor")
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", {}))["dispatched_role"], None)
        self.assertEqual(guard.adapt_agy(self.tool("invoke_subagent", {"Subagents": []}))["dispatched_role"], None)
        self.assertEqual(guard.adapt_agy(self.tool("run_command", {}))["tool_kind"], "other")
        self.assertFalse(guard.adapt_agy(self.tool("write_to_file", {"TargetFile": "/r/a"}))["is_subagent"])
        self.assertIsNone(guard.adapt_agy({"conversationId": "c"}))

    def test_default_enforce_denies_a_main_edit_and_shadow_only_logs(self) -> None:
        self.run_guard("agy", self.pre_invocation(0, cwd=self.work), event="PreInvocation")
        edit = self.tool("write_to_file", {"TargetFile": self.path("a.py")}, workspacePaths=[self.work])
        out = json.loads(self.run_guard("agy", edit, event="PreToolUse"))
        self.assertEqual(out["decision"], "deny")
        self.assertNotIn("#direct", out["reason"])  # agy's PreInvocation carries no prompt text
        self.assertIn("SHOAL_GUARD_DIRECT=1", out["reason"])
        record = self.log_records()[-1]
        self.assertEqual((record["decision"], record["rule"], record["mode"], record["host"]), ("deny", "R1", "enforce", "agy"))
        self.assertEqual(self.run_guard("agy", edit, event="PreToolUse", SHOAL_GUARD="shadow"), "")
        self.assertEqual(self.log_records()[-1]["decision"], "would_deny")

    def test_event_name_comes_from_the_registration(self) -> None:
        self.assertEqual(guard.adapt_agy({"conversationId": "c", "workspacePaths": ["/w"]}, "SessionStart")["kind"], "session_start")
        self.assertEqual(guard.adapt_agy({"conversationId": "c", "workspacePaths": ["/w"]}, "SessionStart")["workspace"], "/w")
        stop = guard.adapt_agy({"conversationId": "c", "fullyIdle": True, "executionNum": 1}, "Stop")
        self.assertEqual((stop["kind"], stop["fully_idle"], stop["stop_hook_active"]), ("stop", True, False))
        self.assertIsNone(guard.adapt_agy({"conversationId": "c", "invocationNum": 1, "initialNumSteps": 0}, "PreInvocation"))
        self.assertIsNone(guard.adapt_agy({"conversationId": "c"}, "PreToolUse"))  # named PreToolUse, but no toolCall
        self.assertIsNone(guard.adapt_agy(self.tool("write_to_file", {"TargetFile": "/r/a"}), "PostToolUse"))  # not an agy event we use
        self.assertEqual(guard.adapt_agy(self.tool("write_to_file", {"TargetFile": "/r/a"}), "PreToolUse")["tool_kind"], "edit")
        self.assertIsNone(guard.adapt_agy({"conversationId": "c"}))  # an old registration: no name, no shape
        shell = guard.adapt_agy(self.tool("run_command", {"CommandLine": "echo x > a", "Cwd": "/w"}), "PreToolUse")
        self.assertEqual((shell["tool_kind"], shell["command"], shell["cwd"]), ("shell", "echo x > a", "/w"))
        listed = guard.adapt_agy(self.tool("invoke_subagent", self.subagents("applier", "scout")), "PreToolUse")
        self.assertEqual(listed["dispatched_roles"], ["applier", "scout"])

    def test_old_registration_without_event_name_still_evaluated(self) -> None:
        self.run_guard("agy", self.pre_invocation(0, cwd=self.work))  # no --event
        edit = self.tool("write_to_file", {"TargetFile": self.path("a.py")}, cwd=self.work)
        self.assertEqual(json.loads(self.run_guard("agy", edit))["decision"], "deny")

    def test_env_event_name_is_accepted_too(self) -> None:
        self.run_guard("agy", {"conversationId": "conv-1", "workspacePaths": [self.work]}, SHOAL_GUARD_EVENT="SessionStart")
        self.assertEqual(self.log_records()[-1]["rule"], "conversation_main")

    def test_subagent_conversation_is_inferred_from_order_and_judged_by_role(self) -> None:
        wp = [self.work]
        self.run_guard("agy", {"conversationId": "m", "workspacePaths": wp}, event="SessionStart")
        self.run_guard("agy", self.pre_invocation(0, conversationId="m", workspacePaths=wp), event="PreInvocation")
        self.run_guard("agy", self.tool("invoke_subagent", self.subagents("scout"), conversationId="m", workspacePaths=wp),
                       event="PreToolUse")
        self.run_guard("agy", {"conversationId": "s", "workspacePaths": wp}, event="SessionStart")
        edit = self.tool("write_to_file", {"TargetFile": self.path("a.py")}, conversationId="s", workspacePaths=wp)
        out = json.loads(self.run_guard("agy", edit, event="PreToolUse"))
        self.assertEqual(out["decision"], "deny")
        self.assertEqual(self.log_records()[-1]["rule"], "E1")
        record = json.loads(Path(self.guard_dir, "state", "agy.conversations.json").read_text(encoding="utf-8"))
        self.assertEqual([(c["id"], c["kind"], c["role"]) for c in record["conversations"]], [("m", "main", ""), ("s", "sub", "scout")])
        self.assertEqual(record["pending"], [])

    def test_dispatch_alone_does_not_unlock_but_a_started_write_role_does(self) -> None:
        wp = [self.work]
        self.run_guard("agy", self.pre_invocation(0, conversationId="m"), event="PreInvocation")
        self.run_guard("agy", self.tool("invoke_subagent", self.subagents("executor"), conversationId="m", workspacePaths=wp),
                       event="PreToolUse")
        edit = self.tool("write_to_file", {"TargetFile": self.path("a.py")}, conversationId="m", cwd=self.work)
        self.assertEqual(json.loads(self.run_guard("agy", edit, event="PreToolUse"))["decision"], "deny")
        self.run_guard("agy", {"conversationId": "s", "workspacePaths": wp}, event="SessionStart")
        self.assertEqual(self.run_guard("agy", edit, event="PreToolUse"), "")
        self.assertEqual(self.log_records()[-1]["rule"], "dispatched")

    def test_deny_output_shape(self) -> None:
        self.assertEqual(json.loads(guard.deny_output("agy", "why")), {"decision": "deny", "reason": "why"})
        self.assertEqual(json.loads(guard.deny_output("grok", "why")), {"decision": "deny", "reason": "why"})
        claude = json.loads(guard.deny_output("claude", "why"))["hookSpecificOutput"]
        self.assertEqual(claude, {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "why"})
        self.assertEqual(json.loads(guard.deny_output("codex", "why")), json.loads(guard.deny_output("claude", "why")))

    def test_unlock_survives_later_model_calls_of_the_turn(self) -> None:
        self.run_guard("agy", self.pre_invocation(0, conversationId="m"), event="PreInvocation")
        self.run_guard("agy", self.tool("invoke_subagent", self.subagents("executor", "applier"), conversationId="m"),
                       event="PreToolUse")
        self.run_guard("agy", {"conversationId": "s1"}, event="SessionStart")
        self.run_guard("agy", self.pre_invocation(1, conversationId="m"), event="PreInvocation")  # state kept
        self.run_guard("agy", self.tool("write_to_file", {"TargetFile": self.path("a")}, conversationId="m", cwd=self.work),
                       event="PreToolUse")
        self.assertEqual(self.log_records()[-1]["rule"], "dispatched")
        self.run_guard("agy", self.pre_invocation(0, steps=9, conversationId="m"), event="PreInvocation")  # next turn
        out = self.run_guard("agy", self.tool("write_to_file", {"TargetFile": self.path("b")}, conversationId="m", cwd=self.work),
                             event="PreToolUse")
        self.assertEqual(json.loads(out)["decision"], "deny")

    def test_mixed_dispatch_leaves_the_class_unknown_and_is_not_denied(self) -> None:
        self.run_guard("agy", self.pre_invocation(0, conversationId="m"), event="PreInvocation")
        self.run_guard("agy", self.tool("invoke_subagent", self.subagents("applier", "scout"), conversationId="m"),
                       event="PreToolUse")
        self.run_guard("agy", {"conversationId": "s1"}, event="SessionStart")
        edit = self.tool("write_to_file", {"TargetFile": self.path("a")}, conversationId="s1", cwd=self.work)
        self.assertEqual(self.run_guard("agy", edit, event="PreToolUse"), "")
        self.assertEqual(self.log_records()[-1]["skip_reason"], "would_deny_unknown_class")

    def test_stop_logs_would_block_for_main_when_fully_idle_and_blocks_only_on_request(self) -> None:
        self.run_guard("agy", self.pre_invocation(0, conversationId="m"), event="PreInvocation")
        self.run_guard("agy", self.tool("write_to_file", {"TargetFile": self.path("a")}, conversationId="m", cwd=self.work),
                       event="PreToolUse", SHOAL_GUARD_DIRECT="1")
        stop = {"conversationId": "m", "executionNum": 1, "terminationReason": "NO_TOOL_CALL", "fullyIdle": True}
        self.assertEqual(self.run_guard("agy", dict(stop, fullyIdle=False), event="Stop"), "")
        self.assertEqual(self.run_guard("agy", stop, event="Stop"), "")
        self.assertEqual(self.log_records()[-1]["decision"], "would_block")
        out = json.loads(self.run_guard("agy", stop, event="Stop", SHOAL_GUARD_STOP="enforce"))
        self.assertEqual(out["decision"], "block")


class ChainCliTests(CliCase):
    """The guard chain through the real script: raw stdin to members, host-native deny output, fail-open."""

    MEMBER = str(ROOT / "tests" / "fixtures" / "chain" / "member.py")

    def configure(self, *modes: list) -> None:
        manifest = Path(self.home) / "chain.json"
        manifest.write_text(json.dumps({"chain": [
            {"name": "m%d" % i, "command": [sys.executable, self.MEMBER, *mode], "hosts": ["claude", "codex"], "order": i}
            for i, mode in enumerate(modes)]}), encoding="utf-8")
        self.chain_env = {"SHOAL_GUARD_CHAIN_FILE": str(manifest), "SHOAL_GUARD_CHAIN_TIMEOUT_MS": "1500"}

    def test_member_deny_uses_the_host_native_deny_output(self) -> None:
        self.configure(["deny", "stop right there"])
        out = json.loads(self.run_guard("claude", claude_tool("Read", {"file_path": "x"}, cwd=self.work), **self.chain_env))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecisionReason"], "m0: stop right there")

    def test_member_receives_the_raw_stdin_bytes(self) -> None:
        record = os.path.join(self.home, "seen.txt")
        self.configure(["record", record])
        raw = b'{"session_id": "sess-1",  "hook_event_name":"PreToolUse", "tool_name":"Read","tool_input":{},"cwd":"%s"}' % self.work.encode()
        self.assertEqual(self.run_guard("claude", raw, **self.chain_env), "")
        self.assertEqual(Path(record).read_bytes(), raw + b"\n")

    def test_member_failures_allow_and_log(self) -> None:
        self.configure(["exit1"], ["garbage"], ["sleep"])
        self.chain_env["SHOAL_GUARD_CHAIN_TIMEOUT_MS"] = "400"
        self.assertEqual(self.run_guard("claude", claude_tool("Read", {"file_path": "x"}, cwd=self.work), **self.chain_env), "")
        decisions = [r["decision"] for r in self.log_records() if r.get("rule") == "chain"]
        self.assertEqual(decisions, ["chain_error", "chain_error", "chain_timeout"])
        self.assertTrue(all("ms" in r and r["member"].startswith("m") for r in self.log_records() if r.get("rule") == "chain"))

    def test_manifest_record_without_dispatch_guard_runs_chain_only(self) -> None:
        # modular-install S3 switch + issue #3: members present -> chain-only; none for the host -> off
        self.configure(["deny", "stop right there"])
        manifest = Path(self.chain_env["SHOAL_GUARD_CHAIN_FILE"])
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        payload = claude_tool("Read", {"file_path": "x"}, cwd=self.work)
        for modules in (["core", "host-claude", "dispatch-guard"], ["core", "host-claude"]):
            manifest.write_text(json.dumps({**doc, "claude": {"modules": modules, "version": "3.8.0"}}), encoding="utf-8")
            self.assertTrue(self.run_guard("claude", payload, **self.chain_env), modules)
        manifest.write_text(json.dumps({"chain": [], "claude": {"modules": ["core"], "version": "3.8.0"}}), encoding="utf-8")
        self.assertEqual(self.run_guard("claude", payload, **self.chain_env), "")
        # a record for another host does not switch this host off
        manifest.write_text(json.dumps({**doc, "opencode": {"modules": ["core", "host-opencode"], "version": "3.8.0"}}), encoding="utf-8")
        self.assertTrue(self.run_guard("claude", payload, **self.chain_env))
        self.assertFalse(guard.dispatch_guard_selected("opencode", {"SHOAL_GUARD_CHAIN_FILE": str(manifest)}, Path(self.home)))

    def event_payload(self, name: str, **extra: Any) -> dict:
        return {"hook_event_name": name, "session_id": "sess-1", "cwd": self.work, **extra}

    def test_context_becomes_additional_context_on_claude_events_only(self) -> None:
        self.configure(["context", "mind the style"])
        manifest = Path(self.chain_env["SHOAL_GUARD_CHAIN_FILE"])
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        doc["chain"][0]["events"] = ["PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionEnd", "Stop"]
        manifest.write_text(json.dumps(doc), encoding="utf-8")
        cases = (("PreToolUse", {"tool_name": "Read", "tool_input": {}}), ("PostToolUse", {"tool_name": "Edit", "tool_input": {"file_path": "a"}}),
                 ("UserPromptSubmit", {"prompt": "hi", "prompt_id": "p1"}))
        for name, extra in cases:
            out = json.loads(self.run_guard("claude", self.event_payload(name, **extra), **self.chain_env))
            self.assertEqual(out, {"hookSpecificOutput": {"hookEventName": name, "additionalContext": "mind the style"}}, name)
        for name in ("SessionEnd", "Stop"):  # Claude has no additionalContext there: log only
            self.assertEqual(self.run_guard("claude", self.event_payload(name, stop_hook_active=True), **self.chain_env), "")
        self.assertIn("chain_context", [r["decision"] for r in self.log_records()])
        for host_name, extra in (("codex", {"tool_name": "Read", "tool_input": {}, "turn_id": "t"}),):
            doc["chain"][0]["hosts"] = ["codex"]
            manifest.write_text(json.dumps(doc), encoding="utf-8")
            self.assertEqual(self.run_guard(host_name, self.event_payload("PreToolUse", **extra), **self.chain_env), "")

    def test_post_tool_use_edit_and_session_end_reach_only_subscribers(self) -> None:
        record = os.path.join(self.home, "seen.txt")
        self.configure(["record", record])
        manifest = Path(self.chain_env["SHOAL_GUARD_CHAIN_FILE"])
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        post = self.event_payload("PostToolUse", tool_name="Edit", tool_input={"file_path": "a"})
        end = self.event_payload("SessionEnd")
        self.assertEqual(self.run_guard("claude", post, **self.chain_env), "")
        self.assertEqual(self.run_guard("claude", end, **self.chain_env), "")
        self.assertFalse(os.path.exists(record))
        doc["chain"][0]["events"] = ["PostToolUse", "SessionEnd"]
        manifest.write_text(json.dumps(doc), encoding="utf-8")
        self.run_guard("claude", post, **self.chain_env)
        self.run_guard("claude", end, **self.chain_env)
        self.assertEqual(len(Path(record).read_text(encoding="utf-8").splitlines()), 2)

    def test_event_nobody_needs_exits_fast_without_state_or_spawn(self) -> None:
        record = os.path.join(self.home, "seen.txt")
        self.configure(["record", record])  # a default (PreToolUse) member
        for payload in (self.event_payload("PostToolUse", tool_name="Edit", tool_input={}), self.event_payload("SessionEnd")):
            self.assertEqual(self.run_guard("claude", payload, **self.chain_env), "")
        self.assertFalse(os.path.exists(record))
        self.assertFalse(os.path.exists(self.state))
        raw = json.dumps(self.event_payload("PostToolUse", tool_name="Edit", tool_input={})).encode()
        env = self.env(**self.chain_env)
        started = time.monotonic()
        runs = 5
        for _ in range(runs):
            subprocess.run([sys.executable, str(GUARD), "--host", "claude"], input=raw, capture_output=True, env=env, timeout=30)
        guard_ms = (time.monotonic() - started) * 1000 / runs
        started = time.monotonic()
        for _ in range(runs):
            subprocess.run([sys.executable, "-c", "pass"], capture_output=True, env=env, timeout=30)
        base_ms = (time.monotonic() - started) * 1000 / runs
        print("\nfast-exit PostToolUse(Edit): %.1f ms per run, bare python %.1f ms" % (guard_ms, base_ms), file=sys.stderr)
        self.assertLess(guard_ms, base_ms + 250)

    def test_member_output_over_the_cap_is_chain_error_and_stops_the_member(self) -> None:
        env = dict(os.environ)
        called = guard._chain_call([sys.executable, self.MEMBER, "flood"], b"{}", env, 10000)
        self.assertEqual(called["outcome"], "chain_error")

    def test_first_deny_stops_later_members_even_on_log_only_events(self) -> None:
        record = os.path.join(self.home, "seen.txt")
        self.configure(["deny", "no"], ["record", record])
        manifest = Path(self.chain_env["SHOAL_GUARD_CHAIN_FILE"])
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        for m in doc["chain"]:
            m["events"] = ["PostToolUse"]
        manifest.write_text(json.dumps(doc), encoding="utf-8")
        post = self.event_payload("PostToolUse", tool_name="Edit", tool_input={"file_path": "a"})
        self.assertEqual(self.run_guard("claude", post, **self.chain_env), "")  # log only: no block
        self.assertFalse(os.path.exists(record))
        self.assertEqual([r["decision"] for r in self.log_records() if r.get("rule") == "chain"], ["chain_deny"])

    def test_numeric_version_is_reported_and_non_scalars_dropped(self) -> None:
        self.configure(["report_num"])
        self.run_guard("claude", claude_tool("Read", {"file_path": "x"}, cwd=self.work), **self.chain_env)
        reports = [r for r in self.log_records() if r.get("decision") == "chain_report"]
        self.assertEqual([r["reason"] for r in reports], ["id=fx-num version=1"])

    def test_no_manifest_changes_nothing(self) -> None:
        self.assertEqual(self.run_guard("claude", claude_tool("Read", {"file_path": "x"}, cwd=self.work)), "")
        self.assertEqual([r for r in self.log_records() if r.get("rule") == "chain"], [])


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
        self.assertEqual(guard.resolve_mode("codex", {}), "enforce")
        self.assertEqual(guard.resolve_mode("codex", {"SHOAL_GUARD": "shadow"}), "shadow")
        self.assertEqual(guard.resolve_mode("codex", {"SHOAL_GUARD": "off"}), "off")
        self.assertEqual(guard.resolve_mode("agy", {}), "enforce")
        self.assertEqual(guard.resolve_mode("agy", {"SHOAL_GUARD": "enforce"}), "enforce")
        self.assertEqual(guard.resolve_mode("agy", {"SHOAL_GUARD": "shadow"}), "shadow")
        self.assertEqual(guard.resolve_mode("agy", {"SHOAL_GUARD": "off"}), "off")
        self.assertEqual(guard.resolve_mode("claude", {"SHOAL_GUARD": "shadow"}), "shadow")


class LaneAdapterTests(CliCase):
    """Dispatch lanes: where each host's adapter reads the label, and the real script's deny, per host payload shape."""

    def test_adapters_read_the_label_text(self) -> None:
        claude = guard.adapt_claude(claude_tool("Agent", {"subagent_type": "executor", "description": "[complex] fix: x"}, cwd=self.work))
        self.assertEqual(claude["dispatch_desc"], "[complex] fix: x")
        self.assertIsNone(guard.adapt_claude(claude_tool("Workflow", {"description": "[fast] x"}, cwd=self.work))["dispatch_desc"])
        codex = guard.adapt_codex(CodexAdapterTests.tool("spawn_agent", {"agent_type": "executor", "task_name": "t", "message": "[complex] do"}))
        self.assertEqual(codex["dispatch_desc"], "[complex] do")  # task_name has no label: message is read
        codex = guard.adapt_codex(CodexAdapterTests.tool("spawn_agent", {"agent_type": "applier", "task_name": "[fast] t", "message": "m"}))
        self.assertEqual(codex["dispatch_desc"], "[fast] t")
        codex = guard.adapt_codex(CodexAdapterTests.tool("spawn_agent", {"agent_type": "applier", "task_name": "t", "message": "m"}))
        self.assertEqual(codex["dispatch_desc"], "t")
        grok = guard.adapt_grok(GrokAdapterTests.tool("spawn_subagent", {"subagent_type": "applier", "description": "[fast] x", "prompt": "p"}))
        self.assertEqual(grok["dispatch_desc"], "[fast] x")
        agy = guard.adapt_agy({"conversationId": "c1", "toolCall": {"name": "invoke_subagent", "args": {"Subagents": [
            {"TypeName": "executor", "Role": "[complex] a"}, {"TypeName": "applier"}]}}}, "PreToolUse")
        self.assertEqual((agy["dispatched_roles"], agy["dispatch_descs"]), (["executor", "applier"], ["[complex] a", None]))

    def lane(self, host, payload, **env):
        return self.run_guard(host, payload, **{"SHOAL_GUARD": "enforce", "SHOAL_GUARD_LANES": "on", "SHOAL_GUARD_R1": "", **env})

    def test_claude_denies_missing_and_mismatched_labels_with_the_mapping(self) -> None:
        out = self.lane("claude", claude_tool("Agent", {"subagent_type": "executor", "description": "fix: x"}, cwd=self.work))
        reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
        for word in ("[fast]", "[complex]", "[rigorous]", "applier", "executor", "security-executor"):
            self.assertIn(word, reason)
        out = self.lane("claude", claude_tool("Agent", {"subagent_type": "executor", "description": "[fast] fix: x"}, cwd=self.work))
        self.assertIn("Dispatch applier for [fast]", json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"])
        ok = self.lane("claude", claude_tool("Agent", {"subagent_type": "executor", "description": "[complex] fix: x"}, cwd=self.work))
        self.assertEqual(ok, "")
        self.assertEqual(self.lane("claude", claude_tool("Agent", {"subagent_type": "scout", "description": "look"}, cwd=self.work)), "")
        self.assertEqual(self.lane("claude", claude_tool("Agent", {"subagent_type": "executor", "description": "x"}, cwd=self.work),
                                   SHOAL_GUARD_LANES="off"), "")

    def test_codex_and_grok_deny_without_a_label(self) -> None:
        out = self.lane("codex", CodexAdapterTests.tool("spawn_agent", {"agent_type": "executor", "task_name": "t", "message": "m"}, cwd=self.work))
        self.assertIn("lane label", out)
        out = self.lane("codex", CodexAdapterTests.tool("spawn_agent", {"agent_type": "executor", "task_name": "t", "message": "[complex] m"}, cwd=self.work))
        self.assertEqual(out, "")
        self.assertEqual(self.lane("grok", GrokAdapterTests.tool("spawn_subagent", {"subagent_type": "applier", "description": "[fast] x"}, cwd=self.work)), "")


if __name__ == "__main__":
    unittest.main()
