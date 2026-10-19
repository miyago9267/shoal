"""P0 characterization (docs/specs/code-restructure T0.3, T0.6): adapter golden and security regressions.

tests/fixtures/adapter_golden.json was produced from the guard before P1; P1-P5 must not edit it.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "tests"))
import shoal_guard as guard  # noqa: E402
from test_shoal_guard import CliCase, claude_prompt, claude_tool  # noqa: E402

GOLDEN = json.loads((ROOT / "tests" / "fixtures" / "adapter_golden.json").read_text(encoding="utf-8"))["cases"]


def adapt(case: dict) -> object:
    fn = guard.ADAPTERS[case["host"]]
    if case["host"] == "agy":
        return fn(case["payload"], case["event_name"])
    return fn(case["payload"])


def by_name(host: str, name: str) -> dict:
    return next(c for c in GOLDEN if c["host"] == host and c["name"] == name)


class AdapterGoldenTests(unittest.TestCase):
    def test_every_payload_matches_golden_exactly(self) -> None:
        for case in GOLDEN:
            with self.subTest(host=case["host"], name=case["name"]):
                self.assertEqual(adapt(case), case["expected"])

    def test_golden_covers_every_adapter_and_a_minimum_of_cases(self) -> None:
        hosts = {c["host"] for c in GOLDEN}
        self.assertEqual(hosts, set(guard.ADAPTERS))
        self.assertGreaterEqual(len(GOLDEN), 150)
        names = [(c["host"], c["name"]) for c in GOLDEN]
        self.assertEqual(len(names), len(set(names)))


class SecurityRegressionTests(unittest.TestCase):
    def test_s1_5_workflow_never_has_a_dispatched_role(self) -> None:
        workflows = [c for c in GOLDEN if c["host"] == "claude" and "Workflow" in c["name"]]
        self.assertGreaterEqual(len(workflows), 4)
        for case in workflows:
            with self.subTest(name=case["name"]):
                event = adapt(case)
                self.assertEqual(event["tool_kind"], "dispatch")
                self.assertIsNone(event["dispatched_role"])
                self.assertIsNone(event["dispatch_desc"])
        agent = adapt(by_name("claude", "pre_Agent_executor"))
        self.assertEqual(agent["dispatched_role"], "shoal:executor")

    def test_s1_6_background_shell_precedes_shell(self) -> None:
        self.assertEqual(adapt(by_name("claude", "pre_bash_background"))["tool_kind"], "background_shell")
        self.assertEqual(adapt(by_name("claude", "pre_bash"))["tool_kind"], "shell")
        for name in ("pre_bash_background_false", "pre_bash_background_str"):
            self.assertEqual(adapt(by_name("claude", name))["tool_kind"], "shell", name)
        for name in ("post_bash_background", "post_failure_bash_background", "post_read"):
            self.assertIsNone(adapt(by_name("claude", name)), name)
        for name in ("post_bash", "post_failure_bash"):
            self.assertEqual(adapt(by_name("claude", name))["kind"], "post_shell", name)

    def test_s1_6_non_string_commands(self) -> None:
        self.assertIsNone(adapt(by_name("codex", "post_bash_nonstr")))
        self.assertEqual(adapt(by_name("codex", "pre_bash_nonstr"))["tool_kind"], "other")
        self.assertEqual(adapt(by_name("grok", "pre_shell_nonstr"))["tool_kind"], "other")
        self.assertIsNone(adapt(by_name("claude", "pre_bash_nonstr_command"))["command"])

    def test_s1_6_grok_stop_only_for_main_end_turn(self) -> None:
        self.assertEqual(adapt(by_name("grok", "stop_end_turn"))["kind"], "stop")
        for name in ("stop_other_reason", "stop_no_reason", "stop_sub"):
            self.assertIsNone(adapt(by_name("grok", name)), name)

    def test_s1_9_host_sets_equal_frozen_literals(self) -> None:
        frozen = {
            "ADVISE_OUTPUT_HOSTS": {"claude", "codex"},
            "AGENT_KEYED_HOSTS": {"codex"},
            "COMPOSED_TURN_HOSTS": {"agy"},
            "CONVERSATION_HOSTS": {"agy"},
            "DECLARE_HOSTS": {"agy", "claude", "codex", "grok", "opencode"},
            "DENY_MAIN_HOSTS": {"claude"},
            "MAPPED_HOSTS": {"grok"},
            "POST_HOSTS": {"claude", "codex"},
            "PROMPT_DIRECT_HOSTS": {"claude", "codex", "grok", "opencode"},
            "PROMPT_KEEP_HOSTS": {"claude"},
            "ROLE_AWARE_HOSTS": {"claude", "codex", "grok"},
            "ROLE_RUNNING_HOSTS": {"claude"},
            "START_UNLOCK_HOSTS": {"agy", "claude", "codex", "grok"},
            "STATE_TURN_HOSTS": {"agy", "claude", "grok"},
            "STOP_HOSTS": {"agy", "claude", "codex", "grok"},
            "STOP_SHADOW_DEFAULT_HOSTS": {"agy", "grok"},
            "SUBAGENT_DIRECT_HOSTS": {"claude", "codex", "grok"},
            "SUBAGENT_WRITE_DEFAULT_ON_HOSTS": {"agy", "claude", "codex", "grok"},
        }
        for name, want in frozen.items():
            with self.subTest(name=name):
                self.assertEqual(set(getattr(guard, name)), want)
        self.assertEqual(
            sorted(n for n in dir(guard) if n.endswith("_HOSTS")), sorted(frozen),
            "a host set was added or removed: freeze it here first")
        self.assertEqual(set(guard.ADAPTERS), {"claude", "codex", "grok", "agy"})
        self.assertEqual(guard.HOST_DEFAULT_MODE,
                         {"claude": "enforce", "codex": "enforce", "grok": "enforce", "agy": "enforce"})
        self.assertIsNone(guard.HOST_DEFAULT_MODE.get("opencode"))


SECRET = "SECRET-PROMPT-S18 #direct"
MAIN = {
    "claude": {"session_id": "s", "prompt_id": "p", "cwd": "/w"},
    "codex": {"session_id": "s", "turn_id": "t", "cwd": "/w"},
    "grok": {"sessionId": "s", "promptId": "p", "cwd": "/w"},
}
TOOL = {
    "claude": lambda tool, tin: {**MAIN["claude"], "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tin},
    "codex": lambda tool, tin: {**MAIN["codex"], "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tin},
    "grok": lambda tool, tin: {**MAIN["grok"], "hookEventName": "pre_tool_use", "toolName": tool, "toolInput": tin},
}
PROMPT = {
    "claude": {**MAIN["claude"], "hook_event_name": "UserPromptSubmit", "prompt": SECRET},
    "codex": {**MAIN["codex"], "hook_event_name": "UserPromptSubmit", "prompt": SECRET},
    "grok": {**MAIN["grok"], "hookEventName": "user_prompt_submit", "prompt": SECRET},
}
START = {
    "claude": {**MAIN["claude"], "hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "shoal:executor"},
    "codex": {**MAIN["codex"], "hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "executor"},
    "grok": {**MAIN["grok"], "hookEventName": "subagent_start", "subagentId": "a1", "subagentType": "executor"},
}
STATE_KEYS = ["turn_id", "dispatched", "advised", "edited", "direct", "declared", "pending", "changed", "checked",
              "stop_blocked"]


class HostInvariantTests(unittest.TestCase):
    """S1.7, S1.8 (docs/specs/code-restructure F4, F5): per-host adapter invariants, true before and after P1."""

    def test_s1_7_main_session_is_not_a_subagent(self) -> None:
        for host in ("claude", "codex", "grok"):
            for payload in (PROMPT[host], TOOL[host]("Read", {}), START[host]):
                with self.subTest(host=host, payload=payload):
                    self.assertIs(guard.ADAPTERS[host](payload)["is_subagent"], False)
        self.assertIs(guard.adapt_claude({**TOOL["claude"]("Read", {}), "agent_id": "x"})["is_subagent"], True)
        self.assertIs(guard.adapt_codex({**TOOL["codex"]("Read", {}), "agent_id": "x"})["is_subagent"], True)
        self.assertIs(guard.adapt_grok({**TOOL["grok"]("Read", {}), "subagentType": "x"})["is_subagent"], True)
        self.assertIs(guard.adapt_grok({**TOOL["grok"]("Read", {}), "subagentType": ""})["is_subagent"], False)
        self.assertIs(guard.adapt_claude({**TOOL["claude"]("Read", {}), "agent_id": ["x"]})["is_subagent"], True)

    def test_s1_7_subagent_start_turn_id_per_host(self) -> None:
        self.assertEqual(guard.adapt_claude(START["claude"])["turn_id"], "p")
        self.assertIsNone(guard.adapt_codex(START["codex"])["turn_id"])
        self.assertIsNone(guard.adapt_grok(START["grok"])["turn_id"])
        for host in ("claude", "codex", "grok"):
            event = guard.ADAPTERS[host](START[host])
            self.assertEqual((event["kind"], event["agent_id"]), ("subagent_start", "a1"), host)

    def test_s1_8_unknown_tool_is_other(self) -> None:
        for host in ("claude", "codex", "grok"):
            for tool in ("Unknown", "read_file", "", None, 7, ["Edit"], {"Agent": 1}):
                with self.subTest(host=host, tool=tool):
                    event = guard.ADAPTERS[host](TOOL[host](tool, {"file_path": "/w/a", "command": "x"}))
                    self.assertEqual(event["tool_kind"], "other")
                    self.assertIsNone(event["dispatched_role"])

    def test_s1_8_edit_name_sets_are_frozen(self) -> None:
        frozen = {
            "claude": {"Edit", "Write", "MultiEdit", "NotebookEdit"},
            "codex": {"apply_patch"},
            "grok": {"search_replace", "write", "write_file", "edit", "multi_edit", "create_file"},
        }
        candidates = set().union(*frozen.values()) | {"edit_file", "Patch", "str_replace", "notebook_edit"}
        for host, want in frozen.items():
            got = {t for t in candidates if guard.ADAPTERS[host](TOOL[host](t, {}))["tool_kind"] == "edit"}
            self.assertEqual(got, want, host)

    def test_s1_8_path_key_order(self) -> None:
        keys = ["file_path", "path", "target_file", "filePath"]
        tin = {k: "/w/" + k for k in keys}
        for i, key in enumerate(keys):
            rest = {k: tin[k] for k in keys[i:]}
            self.assertEqual(guard.adapt_grok(TOOL["grok"]("edit", {**rest, "notebook_path": "/n"}))["paths"],
                             ["/w/" + key])
        self.assertEqual(guard.adapt_grok(TOOL["grok"]("edit", {"file_path": "", "path": 3, "filePath": "/f"}))["paths"],
                         ["/f"])
        claude = TOOL["claude"]
        self.assertEqual(guard.adapt_claude(claude("Edit", {"file_path": "/a", "notebook_path": "/b"}))["paths"], ["/a"])
        self.assertEqual(guard.adapt_claude(claude("NotebookEdit", {"file_path": "", "notebook_path": "/b"}))["paths"],
                         ["/b"])
        self.assertEqual(guard.adapt_claude(claude("Write", {"path": "/a"}))["paths"], [])

    def test_s1_8_prompt_text_is_not_in_the_event(self) -> None:
        for host in ("claude", "codex", "grok"):
            event = guard.ADAPTERS[host](PROMPT[host])
            self.assertEqual((event["kind"], event["direct"]), ("prompt", True), host)
            self.assertNotIn("SECRET-PROMPT-S18", json.dumps(event), host)


class StateAndLogTests(CliCase):
    """S1.8 (prompt never logged, every host) and S1.10 (docs/specs/code-restructure F7): fresh state never inherits
    a prior state's flags."""

    def guard_blob(self) -> str:
        blob = ""
        for dirpath, _, names in os.walk(self.guard_dir):
            for name in names:
                blob += Path(dirpath, name).read_text(encoding="utf-8", errors="replace")
        return blob

    def test_s1_8_prompt_text_is_not_logged(self) -> None:
        for host in ("claude", "codex", "grok"):
            self.run_guard(host, {**PROMPT[host], "cwd": self.work})
            self.run_guard(host, {**TOOL[host]("Read", {}), "cwd": self.work})
        self.assertTrue(self.log_records())
        self.assertNotIn("SECRET-PROMPT-S18", self.guard_blob())

    def write_prior(self, prior: dict) -> Path:
        state_dir = Path(self.guard_dir, "state")
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path in (Path(self.state), Path(self.state, "shoal"), Path(self.guard_dir), state_dir):
            os.chmod(path, 0o700)
        path = state_dir / "sess-1.json"
        path.write_text(json.dumps(prior), encoding="utf-8")
        os.chmod(path, 0o600)
        return path

    PRIOR = {"turn_id": "p-1", "dispatched": "yes", "pending": 3, "role_running": True, "changed": False}

    def assert_reset(self, state: dict, turn: str) -> None:
        self.assertEqual(list(state)[:len(STATE_KEYS)], STATE_KEYS)
        self.assertEqual(state["turn_id"], turn)
        self.assertIs(state["dispatched"], False)
        self.assertEqual(state["pending"], 0)
        self.assertNotIn("role_running", state)
        self.assertNotIn("role_changed", state)

    def test_s1_10_prompt_boundary_resets_prior_flags(self) -> None:
        path = self.write_prior(self.PRIOR)
        self.run_guard("claude", claude_prompt(cwd=self.work, prompt_id="p-2"))
        state = json.loads(path.read_text(encoding="utf-8"))
        self.assert_reset(state, "p-2")
        self.assertEqual(list(state), STATE_KEYS)

    def test_s1_10_id_less_prompt_resets_prior_flags(self) -> None:
        path = self.write_prior({**self.PRIOR, "edited": ["a.py"]})
        payload = claude_prompt(cwd=self.work)
        del payload["prompt_id"]
        self.run_guard("claude", payload)
        state = json.loads(path.read_text(encoding="utf-8"))
        self.assert_reset(state, "p-1")
        self.assertEqual(state["edited"], ["a.py"])

    def test_s1_10_same_turn_coerces_prior_flags(self) -> None:
        path = self.write_prior(self.PRIOR)
        self.run_guard("claude", claude_tool("Agent", {"subagent_type": "shoal:verifier"}, cwd=self.work))
        state = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(list(state), STATE_KEYS)
        self.assertIs(state["dispatched"], False)
        self.assertEqual(state["pending"], 3)
        self.assertIs(state["checked"], True)

if __name__ == "__main__":
    unittest.main()
