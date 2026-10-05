"""Rerun accounting, stage-id shape and malformed fields for content failure classes.

Covers the B3b review findings: a rerun hides only a verifier INCONCLUSIVE stage
(R7, Decision 4, AC-CE-028); summary stage ids keep the `<case_id>#<attempt>`
shape; malformed `reason` values fall to `unclassified` instead of raising.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "tests"))
import benchmark_role_fitness as runner  # noqa: E402
import role_fitness_scorecard as scorecard  # noqa: E402
import test_role_fitness_content_failure as recorded  # noqa: E402

MECH = "mechanical-execution-01"


def _review_fail(case_id: str, attempt: int = 1) -> dict[str, Any]:
    return {
        "case_id": case_id, "status": "inconclusive", "reason": "invalid_native_review_output",
        "dispatch_status": "NATIVE_OK", "attempt": attempt,
    }


def _review_ok(case_id: str, attempt: int, rerun_of: str) -> dict[str, Any]:
    return {
        "case_id": case_id, "status": "accepted", "native_role": "plan-verifier",
        "dispatch_status": "NATIVE_OK", "false_escalation": False, "attempt": attempt,
        "rerun_of": rerun_of, "quality_score": 80.0,
        "score": {"expected_decision": "READY", "risk_coverage": 1.0},
    }


def _executor_fail(case_id: str, reason: str = "invalid_native_mechanical_acceptance") -> dict[str, Any]:
    return {"case_id": case_id, "status": "inconclusive", "reason": reason, "dispatch_status": "NATIVE_OK", "attempt": 1}


def _verifier_inconclusive(case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id, "status": "inconclusive", "reason": "verifier_did_not_confirm",
        "dispatch_status": "NATIVE_OK", "attempt": 1,
    }


class RerunCountingTests(unittest.TestCase):
    def _taxonomy(self, stages: list[dict[str, Any]]) -> dict[str, int]:
        return scorecard.content_failure_taxonomy(scorecard.classify_content_stages(stages))

    def test_review_failure_then_rerun_is_counted_once_each(self) -> None:
        stages = [_review_fail("plan-review-03"), _review_ok("plan-review-03", 2, "plan-review-03#1")]
        self.assertEqual(scorecard.classify_content_stages(stages), ["unparseable_output", None])
        self.assertEqual(self._taxonomy(stages), {"content.unparseable_output": 1})

    def test_split_executor_failure_then_rerun_is_counted(self) -> None:
        stages = [
            _executor_fail("split-workflow-01", "invalid_split_executor_acceptance"),
            _review_ok("split-workflow-01", 2, "split-workflow-01#1"),
        ]
        self.assertEqual(scorecard.classify_content_stages(stages), ["executor_no_artifact", None])
        self.assertEqual(self._taxonomy(stages), {"content.executor_no_artifact": 1})

    def test_timeout_then_rerun_is_counted(self) -> None:
        timeout = {"case_id": "plan-review-02", "status": "inconclusive", "reason": "timeout", "native_role": "plan-verifier", "attempt": 1}
        stages = [timeout, _review_ok("plan-review-02", 2, "plan-review-02#1")]
        self.assertEqual(scorecard.classify_content_stages(stages), ["unclassified", None])
        self.assertEqual(self._taxonomy(stages), {"content.unclassified": 1})

    def test_verifier_timeout_then_verifier_rerun_keeps_the_timeout(self) -> None:
        timeout = {"case_id": MECH, "status": "inconclusive", "reason": "timeout", "native_role": "verifier", "attempt": 1}
        rerun = recorded._verifier_stage(MECH, attempt=2, rerun_of=f"{MECH}#1")
        self.assertEqual(scorecard.classify_content_stages([timeout, rerun]), ["unclassified", "verifier_retry"])

    def test_existing_verifier_cases_are_unchanged(self) -> None:
        initial = _verifier_inconclusive(MECH)
        rerun = recorded._verifier_stage(MECH, attempt=2, rerun_of=f"{MECH}#1")
        self.assertEqual(scorecard.classify_content_stages([initial]), ["verifier_inconclusive"])
        self.assertEqual(scorecard.classify_content_stages([initial, rerun]), [None, "verifier_retry"])

    def test_verifier_rerun_does_not_hide_the_same_case_executor_stage(self) -> None:
        executor = _executor_fail(MECH)
        verifier = _verifier_inconclusive(MECH)
        rerun = recorded._verifier_stage(MECH, attempt=2, rerun_of=f"{MECH}#1")
        expected = {"executor_no_artifact", None, "verifier_retry"}
        for stages in ([executor, verifier, rerun], [verifier, rerun, executor], [rerun, executor, verifier]):
            classes = scorecard.classify_content_stages(stages)
            self.assertEqual(sorted(classes, key=str), sorted(expected, key=str))
            self.assertEqual(classes[stages.index(executor)], "executor_no_artifact")
            self.assertIsNone(classes[stages.index(verifier)])

    def test_report_counts_every_stage_once_except_the_superseded_verifier_stage(self) -> None:
        stages = [
            _executor_fail(MECH), _verifier_inconclusive(MECH),
            recorded._verifier_stage(MECH, attempt=2, rerun_of=f"{MECH}#1"),
            _review_fail("plan-review-03"), _review_ok("plan-review-03", 2, "plan-review-03#1"),
        ]
        block = scorecard.content_failure_report({"a": {"R1": stages}})["arms"]["a"]["repeats"]["R1"]
        self.assertEqual(block["stages"], 4)
        counts = {name: item["count"] for name, item in block["classes"].items() if item["count"]}
        self.assertEqual(counts, {"executor_no_artifact": 1, "verifier_retry": 1, "unparseable_output": 1})
        self.assertEqual(block["passed"], 1)


class MalformedFieldTests(unittest.TestCase):
    def test_non_string_reason_is_unclassified(self) -> None:
        for reason in (["invalid_native_review_output"], {"k": "v"}, 7, None, set()):
            stage = {"case_id": "plan-review-01", "status": "inconclusive", "reason": reason, "dispatch_status": "NATIVE_OK"}
            with self.subTest(reason=reason):
                self.assertEqual(scorecard.classify_content_failure(stage), "unclassified")
                self.assertEqual(scorecard.classify_content_stages([stage]), ["unclassified"])
                block = scorecard.content_failure_report({"a": {"R1": [stage]}})["arms"]["a"]["pooled"]
                self.assertEqual(block["classes"]["unclassified"]["count"], 1)

    def test_other_unhashable_fields_do_not_raise(self) -> None:
        stage = {"case_id": ["x"], "status": ["inconclusive"], "reason": "timeout", "dispatch_status": {"k": 1}, "attempt": {"a": 1}}
        self.assertEqual(scorecard.classify_content_failure(stage), "unclassified")
        self.assertEqual(scorecard.classify_content_failure({"status": "inconclusive", "reason": "verifier_did_not_confirm", "rerun_of": ["x"]}), "verifier_inconclusive")


class StageIdShapeTests(unittest.TestCase):
    def _build(self, stages: list[dict[str, Any]]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as directory:
            return runner.build_live_run_summary(
                run_id="R1", manifest_hash="m", scorecard_hash="s",
                receipt_paths=[recorded._dispatch_receipt(directory)], content_stages=stages,
            )

    def test_real_case_ids_are_accepted_on_build_and_validate(self) -> None:
        stages = [_review_fail("plan-review-12"), recorded._verifier_stage("split-workflow-06", attempt=2, rerun_of="split-workflow-06#1")]
        summary = self._build(stages)
        self.assertEqual([row["stage_id"] for row in summary["content_stages"]], ["plan-review-12#1", "split-workflow-06#2"])
        runner.validate_live_run_summary(summary)

    def test_build_rejects_path_newline_and_secret_like_ids(self) -> None:
        for case_id in ("../../etc/passwd", "/private/fixtures/plan-review-01", "plan-review-01\nnext", "api_key=sk-123", "Plan-Review-01", "a b", "x" * 80, "", "plan#1"):
            with self.subTest(case_id=case_id), self.assertRaises(runner.BenchmarkContractError):
                self._build([_review_fail(case_id)])

    def test_build_rejects_bad_attempts(self) -> None:
        for attempt in (0, -1, "abc", "1; rm", True, 1.5, None):
            stage = {**_review_fail("plan-review-01"), "attempt": attempt}
            with self.subTest(attempt=attempt), self.assertRaises(runner.BenchmarkContractError):
                self._build([stage])

    def test_validate_rejects_the_same_ids_in_a_summary(self) -> None:
        summary = self._build([_review_fail("plan-review-01")])
        for stage_id in ("../x#1", "a\nb#1", "api_key=sk#1", "plan-review-01", "plan-review-01#0", "plan-review-01#x", "plan-review-01#1\n", "P#1", ""):
            tampered = {**summary, "content_stages": [{"stage_id": stage_id, "content_failure_class": "unparseable_output"}]}
            with self.subTest(stage_id=stage_id), self.assertRaises(runner.BenchmarkContractError):
                runner.validate_live_run_summary(tampered)


if __name__ == "__main__":
    unittest.main()
