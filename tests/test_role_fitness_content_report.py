"""Failure counts in the report (AC-CE-026) and the public projection (AC-CE-027)."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import benchmark_role_fitness as runner  # noqa: E402
import role_fitness_fixtures as fixtures  # noqa: E402
import role_fitness_scorecard as scorecard  # noqa: E402
import run_role_fitness_content as content  # noqa: E402

CLASSES = scorecard.CONTENT_FAILURE_CLASSES


def _accepted(case_id: str, *, quality: float = 80.0, escalated: bool = False) -> dict[str, Any]:
    return {
        "case_id": case_id, "status": "accepted", "native_role": "plan-verifier",
        "dispatch_status": "NATIVE_OK", "false_escalation": escalated,
        "quality_score": quality, "risk_coverage": 1.0,
        "score": {"expected_decision": "READY", "risk_coverage": 1.0},
    }


def _unparseable(case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id, "status": "inconclusive", "reason": "invalid_native_review_output",
        "dispatch_status": "NATIVE_OK",
    }


def _arms() -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {
        "claude_main": {
            "R1": [_accepted("c1", quality=90), _accepted("c2", quality=70, escalated=True), _unparseable("c3"), _accepted("c4")],
            "R2": [_accepted("c1"), _accepted("c2"), _accepted("c3"), _accepted("c4")],
            "R3": [_unparseable("c1"), _unparseable("c2")],
        },
        "codex_main": {"R1": [_accepted("c1", quality=60)]},
    }


class FailureReportTests(unittest.TestCase):
    def test_ac_ce_026_counts_and_shares_per_arm_beside_the_score(self) -> None:
        r1 = scorecard.content_failure_report(_arms())["arms"]["claude_main"]["repeats"]["R1"]
        self.assertEqual(r1["stages"], 4)
        self.assertEqual(r1["passed"], 2)
        self.assertAlmostEqual(r1["mean_quality_score"], (90 + 70 + 80) / 3)
        self.assertEqual(r1["classes"]["false_escalation"], {"count": 1, "share": 0.25})
        self.assertEqual(r1["classes"]["unparseable_output"], {"count": 1, "share": 0.25})
        self.assertEqual(set(r1["classes"]), set(CLASSES))
        self.assertEqual(r1["classes"]["missed_risk"], {"count": 0, "share": 0.0})

    def test_ac_ce_026_repeats_are_listed_separately_not_only_pooled(self) -> None:
        arm = scorecard.content_failure_report(_arms())["arms"]["claude_main"]
        self.assertEqual(sorted(arm["repeats"]), ["R1", "R2", "R3"])
        shares = [arm["repeats"][label]["classes"]["unparseable_output"]["share"] for label in ("R1", "R2", "R3")]
        self.assertEqual(shares, [0.25, 0.0, 1.0])
        self.assertEqual(arm["pooled"]["stages"], 10)
        self.assertEqual(arm["pooled"]["classes"]["unparseable_output"]["count"], 3)
        # The pooled share (0.3) would hide the R2 and R3 spread above.
        self.assertAlmostEqual(arm["pooled"]["classes"]["unparseable_output"]["share"], 0.3)

    def test_ac_ce_026_each_arm_is_reported_on_its_own(self) -> None:
        report = scorecard.content_failure_report(_arms())["arms"]
        self.assertEqual(sorted(report), ["claude_main", "codex_main"])
        self.assertEqual(report["codex_main"]["repeats"]["R1"]["passed"], 1)
        self.assertEqual(report["codex_main"]["pooled"]["stages"], 1)

    def test_ac_ce_026_superseded_initial_stage_is_not_counted_twice(self) -> None:
        initial = {
            "case_id": "m1", "status": "inconclusive", "reason": "verifier_did_not_confirm",
            "dispatch_status": "NATIVE_OK", "attempt": 1,
        }
        rerun = {
            "case_id": "m1", "status": "accepted", "native_role": "verifier",
            "dispatch_status": "NATIVE_OK", "attempt": 2, "rerun_of": "m1#1",
        }
        block = scorecard.content_failure_report({"a": {"R1": [initial, rerun]}})["arms"]["a"]["repeats"]["R1"]
        self.assertEqual(block["stages"], 1)
        self.assertEqual(block["classes"]["verifier_retry"]["count"], 1)
        self.assertEqual(block["classes"]["verifier_inconclusive"]["count"], 0)

    def test_empty_arm_or_repeat_is_rejected(self) -> None:
        for arms in ({"a": {}}, {"a": {"R1": []}}):
            with self.subTest(arms=arms), self.assertRaises(ValueError):
                scorecard.content_failure_report(arms)

    def test_rendered_report_lists_every_arm_and_repeat_with_counts_and_shares(self) -> None:
        text = scorecard.render_content_failure_report(scorecard.content_failure_report(_arms()))
        lines = text.splitlines()
        self.assertEqual(
            [line.split(" n=")[0] for line in lines],
            ["claude_main R1", "claude_main R2", "claude_main R3", "claude_main pooled", "codex_main R1", "codex_main pooled"],
        )
        self.assertEqual(
            lines[0],
            "claude_main R1 n=4 mean_quality=80.0 | false_escalation 1/4 (25.0%), unparseable_output 1/4 (25.0%)",
        )
        self.assertTrue(lines[1].endswith("| no failures"))

    def test_content_probe_report_carries_the_failure_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures.create_bundle(root / "private", salt=b"s" * 32)

            def fake(**kwargs: Any) -> dict[str, Any]:
                if kwargs["candidate"] == "luna_xhigh":
                    return {**_accepted("plan-review-01"), "candidate": "luna_xhigh", "supported_findings": 0, "weighted_tokens": 10, "wall_seconds": 1.0}
                return {"case_id": "plan-review-01", "candidate": "sol_high", "status": "inconclusive", "reason": "timeout"}

            with patch.object(content, "run_review_case", side_effect=fake):
                report = content.main([
                    "--live", "--yes", "--private-root", str(root / "private"),
                    "--active-codex-home", str(root / "active"), "--codex-bin", "codex",
                    "--case-id", "plan-review-01", "--repeat-label", "R2",
                ])
        arms = report["failure_report"]["arms"]
        self.assertEqual(sorted(arms), ["luna_xhigh", "sol_high"])
        self.assertEqual(list(arms["luna_xhigh"]["repeats"]), ["R2"])
        self.assertEqual(arms["sol_high"]["repeats"]["R2"]["classes"]["unclassified"]["count"], 1)


class PublicProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.counts = runner.public_content_failure_counts(scorecard.content_failure_report(_arms()))
        self.report = {"version": "role-fitness-public-v1", "content_failure_counts": self.counts}

    def test_ac_ce_027_accepts_enum_and_counts_only(self) -> None:
        self.assertEqual(runner.validate_public_projection(self.report), self.report)
        self.assertIn("content_failure_counts", runner.PUBLIC_KEYS)
        arm = self.counts["claude_main"]
        self.assertEqual(sorted(arm), ["R1", "R2", "R3", "pooled"])
        self.assertEqual(arm["R1"]["false_escalation"], 1)
        self.assertEqual(set(arm["R1"]), set(CLASSES))
        for counts in arm.values():
            self.assertTrue(all(type(value) is int for value in counts.values()))

    def test_ac_ce_027_projection_drops_shares_scores_and_stage_details(self) -> None:
        self.assertNotIn("share", repr(self.counts))
        self.assertNotIn("mean_quality_score", repr(self.counts))

    def test_ac_ce_027_rejects_free_text_prompts_fixture_content_and_paths(self) -> None:
        def reject(mutate: Any) -> None:
            report = copy.deepcopy(self.report)
            mutate(report["content_failure_counts"])
            with self.assertRaises(runner.BenchmarkContractError):
                runner.validate_public_projection(report)

        arm = "claude_main"
        # free text and prompt text as a value, a class name, an arm name or a repeat label
        reject(lambda c: c[arm]["R1"].update(false_escalation="the reviewer said the plan was fine"))
        reject(lambda c: c[arm]["R1"].update({"the reviewer said the plan was fine": 1}))
        reject(lambda c: c.update({"Return READY if the plan is clean": c.pop(arm)}))
        reject(lambda c: c[arm].update({"R1 notes": c[arm].pop("R1")}))
        reject(lambda c: c[arm]["R1"].update(prompt="Call spawn_agent exactly once"))
        # fixture content and paths
        reject(lambda c: c[arm]["R1"].update({"/private/fixtures/plan-review-01.md": 1}))
        reject(lambda c: c.update({"fixtures/plan-review-01": c.pop(arm)}))
        reject(lambda c: c[arm].update({"C:\\private\\ledgers.json": c[arm].pop("R1")}))
        reject(lambda c: c.update({"plan-review-01": {"R1": {"missed_risk": 1}}}))
        # a category name outside the enum
        reject(lambda c: c[arm]["R1"].update(prompt_leak=1))
        reject(lambda c: c[arm]["R1"].update(content_failure_class_x=1))
        reject(lambda c: c[arm]["R1"].update({"content.false_escalation": 1}))
        # counts must be plain non-negative integers
        reject(lambda c: c[arm]["R1"].update(missed_risk=True))
        reject(lambda c: c[arm]["R1"].update(missed_risk=-1))
        reject(lambda c: c[arm]["R1"].update(missed_risk=0.5))
        reject(lambda c: c[arm]["R1"].update(missed_risk={"count": 1}))
        reject(lambda c: c[arm]["R1"].update(missed_risk=["plan text"]))
        # structure
        reject(lambda c: c.clear())
        reject(lambda c: c.update({arm: []}))
        reject(lambda c: c.update({arm: {"R1": "text"}}))

    def test_ac_ce_027_still_rejects_unknown_top_level_fields(self) -> None:
        with self.assertRaises(runner.BenchmarkContractError):
            runner.validate_public_projection({**self.report, "review_output": {}})
        with self.assertRaises(runner.BenchmarkContractError):
            runner.validate_public_projection({**self.report, "absolute_path": "/private/x"})
        with self.assertRaises(runner.BenchmarkContractError):
            runner.validate_public_projection({"version": "role-fitness-public-v1", "content_failure_counts": "free text"})


if __name__ == "__main__":
    unittest.main()
