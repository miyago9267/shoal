from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import role_fitness_fixtures as fixtures  # noqa: E402
import run_role_fitness_content as content  # noqa: E402


class ContentProbeTests(unittest.TestCase):
    def test_quality_score_matches_spec_weights(self) -> None:
        self.assertAlmostEqual(
            content._quality_score({"risk_coverage": 0.5, "critical_precision": 0.8, "actionable_revision": 0.4}),
            55.0,
        )

    def test_review_prompt_does_not_pollute_clean_control_scope(self) -> None:
        prompt = content._review_prompt("Update a non-production documentation index.")
        self.assertIn("respect its stated scope", prompt)
        self.assertIn("Do not invent risks", prompt)
        self.assertIn("return READY", prompt)
        self.assertIn("only P0/P1 blockers", prompt)
        self.assertNotIn("production Plan", prompt)

    def test_native_review_prompt_matches_dispatch_contract(self) -> None:
        prompt = content._native_review_prompt("# plan-review-05\nRisk fixture")
        self.assertIn("agent_type='plan-critic'", prompt)
        self.assertIn("task_name='role_fitness_plan_review'", prompt)
        self.assertIn("timeout_ms=30000", prompt)
        self.assertEqual(prompt.count("exactly once"), 2)

    def test_native_role_verdict_adapter_maps_supported_revision(self) -> None:
        ledger = [{"severity": "P1", "anchor": "dual-write period", "revision_id": "r1"}]
        review = content._parse_review([
            "<agent_message>REVISE\n\n- Blocker: Missing dual-write period\n- Evidence: The dual-write period is absent.\n- Minimum revision: Add it.\n- Acceptance check: Verify the dual-write period.</agent_message>"
        ], ledger)
        self.assertEqual(review["decision"], "REVISE")
        self.assertEqual(review["findings"][0]["revision_id"], "r1")

    def test_report_writer_replaces_output_with_restricted_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "report.json"
            content._write_report(output, {"formal_claim": False, "rows": []})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["rows"], [])
            if os.name != "nt":
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_resume_loads_only_valid_rows_for_requested_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            checkpoint.write_text(
                json.dumps(
                    {
                        "version": content.CHECKPOINT_VERSION,
                        "formal_claim": False,
                        "rows": [{"case_id": "plan-review-01", "candidate": "luna_xhigh", "status": "inconclusive"}],
                    }
                ),
                encoding="utf-8",
            )
            rows = content._load_checkpoint(checkpoint, {"plan-review-01"})
        self.assertEqual(rows[0]["candidate"], "luna_xhigh")

    def test_resume_rejects_incomplete_accepted_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            checkpoint.write_text(
                json.dumps({"version": content.CHECKPOINT_VERSION, "formal_claim": False, "rows": [{"case_id": "plan-review-01", "candidate": "luna_xhigh", "status": "accepted"}]}),
                encoding="utf-8",
            )
            with self.assertRaises(content.BenchmarkContractError):
                content._load_checkpoint(checkpoint, {"plan-review-01"})

    def test_resume_preserves_accepted_zero_quality_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            checkpoint.write_text(
                json.dumps({
                    "version": content.CHECKPOINT_VERSION,
                    "formal_claim": False,
                    "rows": [{
                        "case_id": "plan-review-05", "candidate": "luna_xhigh", "status": "accepted",
                        "wall_seconds": 1.0, "weighted_tokens": 10, "supported_findings": 0,
                        "quality_score": 0, "false_escalation": False,
                    }],
                }),
                encoding="utf-8",
            )
            rows = content._load_checkpoint(checkpoint, {"plan-review-05"})
        self.assertEqual(rows[0]["quality_score"], 0)

    def test_weighted_tokens_requires_native_usage_fields(self) -> None:
        self.assertEqual(
            content._weighted_tokens(
                {
                    "input_tokens": 100,
                    "cached_input_tokens": 20,
                    "cache_write_input_tokens": 4,
                    "output_tokens": 30,
                }
            ),
            113,
        )
        self.assertIsNone(content._weighted_tokens({"input_tokens": 100}))

    def test_messages_accepts_nested_token_count_usage(self) -> None:
        usage = {"input_tokens": 10, "cached_input_tokens": 1, "cache_write_input_tokens": 2, "output_tokens": 3}
        _, _, parsed = content._messages(json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": usage}}}))
        self.assertEqual(parsed, usage)

    def test_messages_keeps_complete_usage_when_later_event_is_empty(self) -> None:
        usage = {"input_tokens": 10, "cached_input_tokens": 1, "cache_write_input_tokens": 2, "output_tokens": 3}
        stdout = "\n".join(
            [
                json.dumps({"type": "turn.completed", "usage": usage}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10}}),
            ]
        )
        _, _, parsed = content._messages(stdout)
        self.assertEqual(parsed, usage)

    def test_messages_accept_nested_current_response_shapes(self) -> None:
        review = {"decision": "READY", "findings": [], "rationale": "bounded"}
        stdout = json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(review)}],
                },
            }
        )
        messages, event_types, usage = content._messages(stdout)
        self.assertEqual(content._parse_review(messages), review)
        self.assertEqual(event_types, {"response_item": 1})
        self.assertEqual(usage, {})

    def test_messages_accept_event_message_shape(self) -> None:
        review = {"decision": "READY", "findings": [], "rationale": "bounded"}
        messages, _, _ = content._messages(json.dumps({
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": json.dumps(review)},
        }))
        self.assertEqual(content._parse_review(messages), review)

    def test_review_case_emits_matched_switch_metrics(self) -> None:
        review = {
            "decision": "READY",
            "findings": [],
            "rationale": "The plan is reversible and has a local acceptance check.",
        }
        stdout = "\n".join(
            [
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(review)}}),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 20,
                            "cache_write_input_tokens": 4,
                            "output_tokens": 30,
                        },
                    }
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            private_root = Path(directory) / "private"
            fixtures.create_bundle(private_root, salt=b"s" * 32)
            with patch.object(content, "materialize"), patch.object(
                content.subprocess,
                "run",
                return_value=content.subprocess.CompletedProcess([], 0, stdout, ""),
            ):
                row = content.run_review_case(
                    private_root=private_root,
                    active_home=Path(directory) / "active",
                    codex_bin="codex",
                    case_id="plan-review-01",
                    candidate="luna_xhigh",
                    timeout=1,
                )
        self.assertEqual(row["status"], "accepted")
        self.assertEqual(row["supported_findings"], 0)
        self.assertEqual(row["weighted_tokens"], 113)
        self.assertIn("quality_score", row)

    def test_matched_cohort_uses_fail_closed_switch_scorer(self) -> None:
        rows = []
        for candidate in content.CANDIDATES:
            rows.append({
                "case_id": "plan-review-05",
                "candidate": candidate,
                "status": "accepted",
                "supported_findings": 0,
                "quality_score": 25,
                "weighted_tokens": 100 if candidate == "luna_xhigh" else 110,
                "wall_seconds": 10 if candidate == "luna_xhigh" else 12,
                "false_escalation": False,
            })
        matched = content.build_matched_cohort(rows)
        score = __import__("role_fitness_scorecard").score_switch_cohort(matched, bootstrap_samples=100)
        self.assertEqual(score["score"], 5)


if __name__ == "__main__":
    unittest.main()
