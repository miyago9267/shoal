import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))
spec = importlib.util.spec_from_file_location("role_fitness_adjudicator", ROOT / "bench" / "run_role_fitness_adjudicator.py")
runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(runner)


class AdjudicatorLiveContractTests(unittest.TestCase):
    def test_disagreement_requires_decision_or_revision_identity_change(self) -> None:
        ready = {"decision": "READY", "findings": []}
        self.assertFalse(runner._fingerprint_disagrees(ready, ready))
        self.assertTrue(runner._fingerprint_disagrees(ready, {"decision": "REVISE", "findings": []}))
        self.assertTrue(runner._fingerprint_disagrees(
            {"decision": "REVISE", "findings": [{"revision_id": "a"}]},
            {"decision": "REVISE", "findings": [{"revision_id": "b"}]},
        ))
        self.assertFalse(runner._fingerprint_disagrees(
            {"decision": "REVISE", "findings": [{"revision_id": "a", "evidence": "missing rollback"}]},
            {"decision": "REVISE", "findings": [{"revision_id": "a", "evidence": "missing dual write"}]},
        ))
        self.assertTrue(runner._fingerprint_disagrees(
            {"decision": "REVISE", "findings": [{"revision_id": "a", "title": "rollback"}]},
            {"decision": "REVISE", "findings": [{"revision_id": "a", "title": "dual write"}]},
        ))

    def test_switched_arm_includes_all_protocol_calls(self) -> None:
        final = {
            "supported_findings": 1,
            "quality_score": 50,
            "weighted_tokens": 30,
            "wall_seconds": 3,
            "status": "accepted",
            "false_escalation": False,
        }
        arm = runner._arm(final, extra_tokens=70, extra_wall=7)
        self.assertEqual(arm["weighted_tokens"], 100)
        self.assertEqual(arm["wall_seconds"], 10)
        self.assertEqual(arm["status"], "accepted")
        self.assertEqual(
            set(arm),
            {"supported_findings", "quality_score", "weighted_tokens", "wall_seconds", "status", "false_escalation"},
        )

    def test_report_arm_does_not_require_optional_risk_coverage(self) -> None:
        projected = runner._report_arm(
            {
                "supported_findings": 0,
                "quality_score": 75,
                "weighted_tokens": 10,
                "wall_seconds": 2,
                "status": "accepted",
                "false_escalation": False,
            },
            include_status=True,
        )
        self.assertNotIn("risk_coverage", projected)

    def test_adjudicator_prompt_does_not_expose_model_identity(self) -> None:
        prompt = runner._adjudicator_prompt("Plan", {"decision": "READY"}, {"decision": "REVISE"})
        self.assertIn("Verdict A", prompt)
        self.assertNotIn("gpt-5.6-sol", prompt)
        self.assertNotIn("gpt-5.6-luna", prompt)

    def test_primary_pre_gate_skips_clean_and_concrete_multi_finding_reviews(self) -> None:
        self.assertFalse(runner._needs_verifier({"decision": "READY", "findings": []}))
        self.assertTrue(runner._needs_verifier({"decision": "REVISE", "findings": [{"revision_id": "a"}, {"revision_id": "b"}]}))
        self.assertTrue(runner._needs_verifier({"decision": "REVISE", "findings": [{"revision_id": "a"}, {"revision_id": "b"}, {"revision_id": "c"}, {"revision_id": "d"}]}))
        self.assertTrue(runner._needs_verifier({"decision": "REVISE", "findings": [{"revision_id": "a"}]}))


if __name__ == "__main__":
    unittest.main()
