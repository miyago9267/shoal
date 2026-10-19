"""P0 characterization (docs/specs/code-restructure T0.3, T0.6): adapter golden and security regressions.

tests/fixtures/adapter_golden.json was produced from the guard before P1; P1-P5 must not edit it.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
import shoal_guard as guard  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
