"""Replay recorded role-fitness results through the content failure classifier.

Each fixture is a runner-format stage built from the fields of a frozen result
file in docs/benchmarks, following the mapping table in
docs/specs/claude-eval-parity/TESTS.md.  The benchmark JSON is read only to
source values; it is never fed to the classifier directly.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import benchmark_role_fitness as runner  # noqa: E402
import role_fitness_scorecard as scorecard  # noqa: E402
import verify_dispatch  # noqa: E402

BENCHMARKS = ROOT / "docs" / "benchmarks"


def _recorded(name: str) -> dict[str, Any]:
    return json.loads(
        (BENCHMARKS / f"role-fitness-v1-{name}.json").read_text(encoding="utf-8")
    )


def _plan_case(case_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    recorded = _recorded("native-content-plan-r1")
    row = next(item for item in recorded["cases"] if item["case_id"] == case_id)
    return row, recorded["aggregate"]


def _review_stage(case_id: str) -> dict[str, Any]:
    """Build the recorded plan-review stage the way the spec table maps it."""
    row, aggregate = _plan_case(case_id)
    clean_control = case_id == "plan-review-01"
    # The file has no per-case risk_coverage.  Clean control scores 1.0 in
    # score_plan_review; the risk cases take the file aggregate (inferred,
    # not re-scored against the private ledger).
    coverage = 1.0 if clean_control else aggregate["risk_coverage"]
    return {
        "case_id": case_id,
        "status": row["status"],
        "native_role": "plan-verifier",
        "dispatch_status": row["dispatch_status"],
        "false_escalation": row["false_escalation"],
        "risk_coverage": coverage,
        "score": {
            "expected_decision": "READY" if clean_control else "REVISE",
            "risk_coverage": coverage,
        },
    }


def _executor_stage(case_id: str, *, accepted: bool) -> dict[str, Any]:
    if accepted:
        return {
            "case_id": case_id,
            "status": "accepted",
            "native_role": "mech-executor",
            "dispatch_status": "NATIVE_OK",
            "accepted": True,
        }
    return {
        "case_id": case_id,
        "status": "inconclusive",
        "reason": "invalid_split_executor_acceptance",
        "dispatch_status": "NATIVE_OK",
    }


def _verifier_stage(
    case_id: str, *, attempt: int = 1, rerun_of: str | None = None
) -> dict[str, Any]:
    stage: dict[str, Any] = {
        "case_id": case_id,
        "status": "accepted",
        "native_role": "verifier",
        "dispatch_status": "NATIVE_OK",
        "verification": "CONFIRMED",
        "attempt": attempt,
    }
    if rerun_of is not None:
        stage["rerun_of"] = rerun_of
    return stage


class ReplayRecordedStagesTests(unittest.TestCase):
    def test_ac_ce_020_plan_review_false_escalation_and_missed_risk(self) -> None:
        row, aggregate = _plan_case("plan-review-01")
        self.assertTrue(row["false_escalation"])
        self.assertEqual(
            scorecard.classify_content_failure(_review_stage("plan-review-01")),
            "false_escalation",
        )
        for case_id in ("plan-review-05", "plan-review-06"):
            row, _ = _plan_case(case_id)
            self.assertFalse(row["false_escalation"])
            self.assertEqual(row["supported_findings"], 1)
            self.assertLess(_review_stage(case_id)["risk_coverage"], 1.0)
            self.assertEqual(
                scorecard.classify_content_failure(_review_stage(case_id)),
                "missed_risk",
            )

    def test_ac_ce_020_clean_control_without_escalation_gets_no_class(self) -> None:
        stage = _review_stage("plan-review-01")
        stage["false_escalation"] = False
        self.assertIsNone(scorecard.classify_content_failure(stage))

    def test_ac_ce_020_missed_risk_ignores_supported_findings(self) -> None:
        stage = _review_stage("plan-review-06")
        stage["supported_findings"] = 0
        self.assertEqual(scorecard.classify_content_failure(stage), "missed_risk")
        stage["risk_coverage"] = 1.0
        stage["supported_findings"] = 0
        self.assertIsNone(scorecard.classify_content_failure(stage))

    def test_ac_ce_021_unparseable_output_from_native_content_probe(self) -> None:
        recorded = _recorded("native-content-probe")
        self.assertIs(recorded["review_json_valid"], False)
        stage = {
            "case_id": recorded["case_id"],
            "status": recorded["status"],
            "reason": "invalid_native_review_output",
            "dispatch_status": recorded["dispatch_status"],
        }
        self.assertEqual(
            scorecard.classify_content_failure(stage), "unparseable_output"
        )
        # Direct path records no dispatch_status; the class still applies.
        direct = {
            "case_id": "plan-review-05",
            "status": "inconclusive",
            "reason": "invalid_review_output",
        }
        self.assertEqual(
            scorecard.classify_content_failure(direct), "unparseable_output"
        )
        # A dispatch-layer failure is not an unparseable review.
        broken = {**stage, "dispatch_status": "SKIPPED"}
        self.assertEqual(scorecard.classify_content_failure(broken), "unclassified")

    def test_ac_ce_022_executor_no_artifact_for_split_v2_and_v5(self) -> None:
        v2 = _recorded("native-split-v2")
        self.assertFalse(v2["executor"]["accepted_artifact"])
        self.assertIs(v2["verifier_started"], False)
        self.assertEqual(
            scorecard.classify_content_failure(
                _executor_stage(v2["case_id"], accepted=False)
            ),
            "executor_no_artifact",
        )
        v5 = _recorded("native-split-v5")
        classes = {
            row["case_id"]: scorecard.classify_content_failure(
                _executor_stage(row["case_id"], accepted=row["executor"] == "accepted")
            )
            for row in v5["cases"]
        }
        self.assertEqual(
            {case_id: name for case_id, name in classes.items() if name is not None},
            {
                "split-workflow-04": "executor_no_artifact",
                "split-workflow-05": "executor_no_artifact",
            },
        )
        # Accepted executor and accepted verifier stages get no class.
        for row in v5["cases"]:
            if row["verifier"] == "CONFIRMED":
                self.assertIsNone(
                    scorecard.classify_content_failure(_verifier_stage(row["case_id"]))
                )
        mechanical = {
            "case_id": "mechanical-execution-01",
            "status": "inconclusive",
            "reason": "invalid_native_mechanical_acceptance",
            "dispatch_status": "NATIVE_OK",
        }
        self.assertEqual(
            scorecard.classify_content_failure(mechanical), "executor_no_artifact"
        )

    def test_ac_ce_023_verifier_retry_requires_rerun_of(self) -> None:
        recorded = _recorded("native-mechanical-verifier-r2")
        by_id = {row["case_id"]: row for row in recorded["cases"]}
        self.assertTrue(
            by_id["mechanical-execution-02"]["retry_after_initial_inconclusive"]
        )
        self.assertNotIn(
            "retry_after_initial_inconclusive", by_id["mechanical-execution-01"]
        )
        rerun = _verifier_stage(
            "mechanical-execution-02", attempt=2, rerun_of="mechanical-execution-02#1"
        )
        self.assertEqual(scorecard.classify_content_failure(rerun), "verifier_retry")
        without = _verifier_stage("mechanical-execution-02", attempt=2)
        self.assertNotEqual(
            scorecard.classify_content_failure(without), "verifier_retry"
        )
        self.assertIsNone(scorecard.classify_content_failure(without))
        for case_id in ("mechanical-execution-01", "mechanical-execution-03"):
            self.assertIsNone(
                scorecard.classify_content_failure(_verifier_stage(case_id))
            )

    def test_ac_ce_028_verifier_inconclusive_and_rerun_not_double_counted(self) -> None:
        recorded = _recorded("native-mechanical-verifier-r1")
        self.assertEqual(recorded["verification"], "INCONCLUSIVE")
        initial = {
            "case_id": recorded["case_id"],
            "status": recorded["status"],
            "reason": "verifier_did_not_confirm",
            "verification": recorded["verification"],
            "dispatch_status": recorded["dispatch_status"],
        }
        self.assertEqual(
            scorecard.classify_content_failure(initial), "verifier_inconclusive"
        )
        self.assertEqual(
            scorecard.classify_content_stages([initial]), ["verifier_inconclusive"]
        )
        rerun = _verifier_stage(
            recorded["case_id"], attempt=2, rerun_of=f"{recorded['case_id']}#1"
        )
        self.assertEqual(
            scorecard.classify_content_stages([initial, rerun]),
            [None, "verifier_retry"],
        )
        # A rerun of some other case does not supersede this stage.
        other = _verifier_stage(
            "mechanical-execution-02", attempt=2, rerun_of="mechanical-execution-02#1"
        )
        self.assertEqual(
            scorecard.classify_content_stages([initial, other]),
            ["verifier_inconclusive", "verifier_retry"],
        )


class UnclassifiedTests(unittest.TestCase):
    def test_ac_ce_024_timeout_and_dispatch_failures_are_unclassified(self) -> None:
        for stage in (
            {
                "case_id": "c1",
                "status": "inconclusive",
                "reason": "timeout",
                "native_role": "verifier",
            },
            {
                "case_id": "c1",
                "status": "inconclusive",
                "reason": "native_evidence_unavailable",
                "detail": "x",
            },
            {"case_id": "c1", "status": "inconclusive", "reason": "some_future_reason"},
            {"case_id": "c1", "status": "inconclusive"},
            {"case_id": "c1", "status": "failed"},
            {"case_id": "c1"},
        ):
            with self.subTest(stage=stage):
                self.assertEqual(
                    scorecard.classify_content_failure(stage), "unclassified"
                )

    def test_ac_ce_024_every_failed_stage_gets_a_known_class(self) -> None:
        stages = [
            _review_stage("plan-review-01"),
            _review_stage("plan-review-05"),
            {"case_id": "c1", "status": "inconclusive", "reason": "timeout"},
            {
                "case_id": "c2",
                "status": "accepted",
                "native_role": "plan-verifier",
                "false_escalation": False,
                "risk_coverage": 1.0,
                "score": {"expected_decision": "REVISE", "passed": False},
            },
        ]
        classes = scorecard.classify_content_stages(stages)
        self.assertNotIn(None, classes)
        self.assertTrue(set(classes) <= set(scorecard.CONTENT_FAILURE_CLASSES))
        self.assertEqual(classes[3], "unclassified")

    def test_first_matching_rule_wins(self) -> None:
        stage = _review_stage("plan-review-06")
        stage["false_escalation"] = True
        self.assertEqual(scorecard.classify_content_failure(stage), "false_escalation")

    def test_malformed_risk_coverage_is_not_missed_risk(self) -> None:
        stage = _review_stage("plan-review-06")
        for value in (None, "0.5", True):
            stage["risk_coverage"] = value
            self.assertIsNone(scorecard.classify_content_failure(stage))


def _dispatch_receipt(directory: str) -> Path:
    """Write a failing dispatch receipt, the same way the existing summary tests do."""
    receipt = Path(directory) / "stage-1.json"
    verdict = verify_dispatch._verdict("SKIPPED", "native_spawn_evidence_missing", phase="post-spawn", child_created="unknown")
    payload = verify_dispatch.receipt_payload(
        verdict,
        codex_version="0.147.0-alpha.1.2",
        active={"config": "a" * 64, "role_manifest": "b" * 64, "policy": "c" * 64},
        target={"config": "a" * 64, "role_manifest": "b" * 64, "policy": "c" * 64},
    )
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    return receipt


class RunSummaryTaxonomyTests(unittest.TestCase):
    def _content_stages(self) -> list[dict[str, Any]]:
        initial = {"case_id": "mechanical-execution-01", "status": "inconclusive", "reason": "verifier_did_not_confirm", "dispatch_status": "NATIVE_OK"}
        rerun = _verifier_stage("mechanical-execution-01", attempt=2, rerun_of="mechanical-execution-01#1")
        return [
            _review_stage("plan-review-01"),
            _review_stage("plan-review-05"),
            _review_stage("plan-review-06"),
            initial,
            rerun,
            {"case_id": "plan-review-02", "status": "inconclusive", "reason": "timeout"},
        ]

    def test_ac_ce_025_taxonomy_holds_dispatch_and_content_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            summary = runner.build_live_run_summary(
                run_id="R1", manifest_hash="m", scorecard_hash="s",
                receipt_paths=[_dispatch_receipt(directory)],
                content_stages=self._content_stages(),
            )
        self.assertEqual(
            summary["failure_taxonomy"],
            {
                "native_spawn": 1,
                "content.false_escalation": 1,
                "content.missed_risk": 2,
                "content.verifier_retry": 1,
                "content.unclassified": 1,
            },
        )
        runner.validate_live_run_summary(summary)

    def test_ac_ce_025_dispatch_only_summary_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            summary = runner.build_live_run_summary(
                run_id="R1", manifest_hash="m", scorecard_hash="s",
                receipt_paths=[_dispatch_receipt(directory)],
            )
        self.assertEqual(summary["failure_taxonomy"], {"native_spawn": 1})
        self.assertNotIn("content_stages", summary)
        runner.validate_live_run_summary(summary)

    def test_summary_carries_only_ids_and_classes_for_content_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            summary = runner.build_live_run_summary(
                run_id="R1", manifest_hash="m", scorecard_hash="s",
                receipt_paths=[_dispatch_receipt(directory)],
                content_stages=self._content_stages(),
            )
        for row in summary["content_stages"]:
            self.assertEqual(set(row), {"stage_id", "content_failure_class"})
        self.assertNotIn("review_output", json.dumps(summary))

    def test_validate_rejects_taxonomy_that_does_not_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            summary = runner.build_live_run_summary(
                run_id="R1", manifest_hash="m", scorecard_hash="s",
                receipt_paths=[_dispatch_receipt(directory)],
                content_stages=self._content_stages(),
            )
        tampered = {**summary, "failure_taxonomy": {**summary["failure_taxonomy"], "content.missed_risk": 1}}
        with self.assertRaises(runner.BenchmarkContractError):
            runner.validate_live_run_summary(tampered)
        stray = {**summary, "failure_taxonomy": {"native_spawn": 1, "content.false_escalation": 1}}
        stray.pop("content_stages")
        with self.assertRaises(runner.BenchmarkContractError):
            runner.validate_live_run_summary(stray)
        bad_class = {**summary, "content_stages": [{"stage_id": "x#1", "content_failure_class": "made_up"}]}
        with self.assertRaises(runner.BenchmarkContractError):
            runner.validate_live_run_summary(bad_class)
        extra_key = {**summary, "content_stages": [{"stage_id": "x#1", "content_failure_class": None, "detail": "free text"}]}
        with self.assertRaises(runner.BenchmarkContractError):
            runner.validate_live_run_summary(extra_key)


if __name__ == "__main__":
    unittest.main()
