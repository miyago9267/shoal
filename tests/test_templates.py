from __future__ import annotations

import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))
from validate_agents import ROLES, validate_agents_config, validate_config, validate_dir  # noqa: E402


class NativeTemplateTests(unittest.TestCase):
    def test_exact_agents_table_has_no_legacy_transport(self) -> None:
        with (ROOT / "templates" / "config.snippet.toml").open("rb") as handle:
            config = tomllib.load(handle)
        self.assertEqual(config["model"], "gpt-6-luna")
        self.assertEqual(config["model_reasoning_effort"], "max")
        self.assertEqual(config["plan_mode_reasoning_effort"], "xhigh")
        self.assertTrue(config["features"]["default_mode_request_user_input"])
        self.assertEqual(config["agents"]["max_concurrent_threads_per_session"], 3)
        self.assertNotIn("max_concurrent_threads_per_session", config)
        self.assertNotIn("multi_agent_v2", config.get("features", {}))
        errors, warnings = validate_agents_config(config)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_role_manifest_is_exact_and_recursively_validated(self) -> None:
        agents = ROOT / "templates" / "agents"
        self.assertEqual({path.stem for path in agents.glob("*.toml")}, ROLES)
        self.assertEqual(validate_dir(agents, expected_names=ROLES), [])

    def test_model_routing_matches_cost_policy(self) -> None:
        agents = ROOT / "templates" / "agents"
        with (agents / "plan-critic.toml").open("rb") as handle:
            plan_verifier = tomllib.load(handle)
        with (agents / "verifier.toml").open("rb") as handle:
            verifier = tomllib.load(handle)
        with (agents / "security-executor.toml").open("rb") as handle:
            security_executor = tomllib.load(handle)
        with (agents / "sol-executor.toml").open("rb") as handle:
            sol_executor = tomllib.load(handle)
        with (agents / "executor.toml").open("rb") as handle:
            executor = tomllib.load(handle)
        self.assertEqual(
            (plan_verifier["model"], plan_verifier["model_reasoning_effort"]),
            ("gpt-6-sol", "high"),
        )
        self.assertEqual(
            (verifier["model"], verifier["model_reasoning_effort"]),
            ("gpt-6-sol", "high"),
        )
        self.assertEqual(
            (security_executor["model"], security_executor["model_reasoning_effort"]),
            ("gpt-6-sol", "high"),
        )
        self.assertEqual(
            (executor["model"], executor["model_reasoning_effort"]),
            ("gpt-6-astra", "high"),
        )
        self.assertEqual(
            (sol_executor["model"], sol_executor["model_reasoning_effort"]),
            ("gpt-6-sol", "high"),
        )
        for path in agents.glob("*.toml"):
            with path.open("rb") as handle:
                self.assertNotEqual(tomllib.load(handle).get("model"), "gpt-5.6-terra")

    def test_rejects_forced_adapter_keys_and_duplicate_names(self) -> None:
        config = {"features": {"multi_agent_v2": {"enabled": True, "max_concurrent_threads_per_session": 4, "tool_namespace": "agents"}}, "agents": {"max_concurrent_threads_per_session": 3}}
        errors, _ = validate_agents_config(config)
        self.assertTrue(any("legacy features.multi_agent_v2" in item for item in errors))
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory); source = (ROOT / "templates" / "agents" / "scout.toml").read_text(encoding="utf-8")
            (agents / "scout.toml").write_text(source, encoding="utf-8")
            (agents / "copy.toml").write_text(source, encoding="utf-8")
            problems = validate_dir(agents, expected_names=ROLES)
            self.assertTrue(any("duplicate role" in item for item in problems))
            self.assertTrue(any("manifest missing" in item for item in problems))

    def test_validator_rejects_nonpackaged_agents_keys(self) -> None:
        config = {"agents": {"max_concurrent_threads_per_session": 3, "max_depth": 1}}
        errors, _ = validate_agents_config(config)
        self.assertTrue(any("unsupported inline role" in item for item in errors))

    def test_runbook_names_the_native_smoke_flow(self) -> None:
        runbook = (ROOT / "install" / "AGENT-INSTALL.md").read_text(encoding="utf-8")
        self.assertTrue((ROOT / "install" / "stage_smoke_home.py").is_file())
        self.assertIn("stage_smoke_home.py", runbook)
        self.assertIn("NATIVE_OK", runbook)
        self.assertIn("NATIVE_OK", (ROOT / "install" / "verify_dispatch.py").read_text(encoding="utf-8"))
        self.assertNotIn("ADAPTER_OK", runbook)


if __name__ == "__main__":
    unittest.main()
