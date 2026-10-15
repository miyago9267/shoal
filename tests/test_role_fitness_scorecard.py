from __future__ import annotations

import sys
import tempfile
import unittest


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))
import role_fitness_scorecard as scorecard  # noqa: E402


class RateScoreTests(unittest.TestCase):
    def test_wilson_lower_bound_is_conservative(self) -> None:
        lower = scorecard.wilson_lower_bound(27, 30)
        self.assertGreater(lower, 0.70)
        self.assertLess(lower, 0.95)

    def test_rate_score_is_unproven_below_sample_floor(self) -> None:
        result = scorecard.score_rate(8, 10, minimum_samples=30)
        self.assertEqual(result["score"], 8)
        self.assertFalse(result["proven"])

    def test_rate_score_uses_lower_bound_for_operational_claim(self) -> None:
        result = scorecard.score_rate(
            30, 30, minimum_samples=30, required_lower_bound=0.80
        )
        self.assertTrue(result["proven"])
        self.assertGreaterEqual(result["lower_bound"], 0.80)

    def test_stability_uses_deterministic_repeat_gate(self) -> None:
        result = scorecard.score_repeat_stability(3, 3)
        self.assertTrue(result["proven"])
        self.assertEqual(result["score"], 10)


class RepeatAggregationTests(unittest.TestCase):
    def test_aggregate_requires_same_manifest_and_unique_run_ids(self) -> None:
        runs = [
            {"run_id": "R1", "manifest_hash": "m", "scorecard_hash": "s", "availability": {"passed": 9, "total": 10}},
            {"run_id": "R2", "manifest_hash": "m", "scorecard_hash": "s", "availability": {"passed": 10, "total": 10}},
        ]
        aggregate = scorecard.aggregate_repeats(runs)
        self.assertEqual(aggregate["availability"], {"passed": 19, "total": 20})

        with self.assertRaises(ValueError):
            scorecard.aggregate_repeats(runs + [dict(runs[0])])
        mismatched = dict(runs[1], manifest_hash="other")
        with self.assertRaises(ValueError):
            scorecard.aggregate_repeats([runs[0], mismatched])

    def test_append_repeat_record_preserves_prior_rows(self) -> None:
        runs = [
            {"run_id": "R1", "manifest_hash": "m", "scorecard_hash": "s", "availability": {"passed": 9, "total": 10}},
            {"run_id": "R2", "manifest_hash": "m", "scorecard_hash": "s", "availability": {"passed": 10, "total": 10}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = __import__("pathlib").Path(directory) / "runs.jsonl"
            scorecard.append_repeat_record(path, runs[0])
            aggregate = scorecard.append_repeat_record(path, runs[1])
            self.assertEqual(aggregate["run_ids"], ["R1", "R2"])
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)

    def test_three_repeats_produce_a_provable_pooled_rate(self) -> None:
        runs = [
            {"run_id": "R1", "manifest_hash": "m", "scorecard_hash": "s", "availability": {"passed": 30, "total": 30}},
            {"run_id": "R2", "manifest_hash": "m", "scorecard_hash": "s", "availability": {"passed": 29, "total": 30}},
            {"run_id": "R3", "manifest_hash": "m", "scorecard_hash": "s", "availability": {"passed": 30, "total": 30}},
        ]
        aggregate = scorecard.aggregate_repeats(runs)
        result = scorecard.score_rate(
            aggregate["availability"]["passed"],
            aggregate["availability"]["total"],
            minimum_samples=30,
            required_lower_bound=0.80,
        )
        self.assertEqual(result["score"], 9)
        self.assertTrue(result["proven"])

    def test_mechanical_score_requires_verifier_confirmed_counts(self) -> None:
        result = scorecard.score_mechanical_execution(first_pass=10, total=12, rework_free=9)
        self.assertEqual(result["score"], 8)
        self.assertFalse(result["proven"])

    def test_split_score_is_final_completion_rate(self) -> None:
        result = scorecard.score_split_workflow(confirmed=6, total=6)
        self.assertEqual(result["score"], 10)
        self.assertTrue(result["proven"])


class SwitchCostTests(unittest.TestCase):
    def _cases(self) -> list[dict]:
        return [
            {
                "case_id": f"risk-{index}",
                "baseline": {
                    "supported_findings": 1,
                    "quality_score": 50,
                    "weighted_tokens": 100_000,
                    "wall_seconds": 10,
                    "status": "accepted",
                    "false_escalation": False,
                },
                "switched": {
                    "supported_findings": 2,
                    "quality_score": 65,
                    "weighted_tokens": 108_000,
                    "wall_seconds": 10.8,
                    "status": "accepted",
                    "false_escalation": False,
                },
            }
            for index in range(6)
        ]

    def test_paired_cohort_reaches_nine_with_fixed_bootstrap(self) -> None:
        result = scorecard.score_switch_cohort(self._cases(), bootstrap_samples=500)
        self.assertEqual(result["additional_findings"], 6)
        self.assertEqual(result["inconclusive"], 0)
        self.assertEqual(result["score"], 9)
        self.assertTrue(result["quality_ci_low"] > 0)

    def test_paired_cohort_is_fail_closed_for_inconclusive_case(self) -> None:
        cases = self._cases()
        cases[0]["switched"]["status"] = "inconclusive"
        result = scorecard.score_switch_cohort(cases, bootstrap_samples=100)
        self.assertEqual(result["inconclusive"], 1)
        self.assertEqual(result["score"], 5)
        self.assertFalse(result["proven"])

    def test_inconclusive_or_zero_quality_caps_score_at_five(self) -> None:
        result = scorecard.score_switch_cost_performance(
            additional_findings=3,
            extra_weighted_tokens=10_000,
            quality_delta=0,
            quality_ci_low=-1,
            p95_wall_premium=0.05,
            weighted_token_premium=0.05,
            false_escalations=0,
            inconclusive=0,
        )
        self.assertEqual(result["score"], 5)
        self.assertFalse(result["proven"])

    def test_efficient_positive_switch_reaches_nine(self) -> None:
        result = scorecard.score_switch_cost_performance(
            additional_findings=3,
            extra_weighted_tokens=10_000,
            quality_delta=15,
            quality_ci_low=4,
            p95_wall_premium=0.08,
            weighted_token_premium=0.08,
            false_escalations=0,
            inconclusive=0,
        )
        self.assertEqual(result["score"], 9)

    def test_risk_coverage_delta_allows_quality_positive_switch_over_premium_cap(self) -> None:
        cases = self._cases()
        for case in cases:
            case["baseline"]["risk_coverage"] = 0.50
            case["switched"]["risk_coverage"] = 0.70
            case["switched"]["weighted_tokens"] = 130_000
            case["switched"]["wall_seconds"] = 14
        result = scorecard.score_switch_cohort(cases, bootstrap_samples=500)
        self.assertAlmostEqual(result["risk_coverage_delta"], 20.0)
        self.assertEqual(result["score"], 8)
        self.assertTrue(result["proven"])
        self.assertTrue(result["proven"])

    def test_quality_positive_cost_saving_switch_is_scored_not_rejected(self) -> None:
        result = scorecard.score_switch_cost_performance(
            additional_findings=3,
            extra_weighted_tokens=-10_000,
            quality_delta=15,
            quality_ci_low=4,
            p95_wall_premium=-0.08,
            weighted_token_premium=-0.08,
            false_escalations=0,
            inconclusive=0,
        )
        self.assertEqual(result["score"], 9)
        self.assertTrue(result["cost_saving"])
        self.assertTrue(result["proven"])

    def test_cohort_uses_equivalent_cost_when_both_arms_provide_it(self) -> None:
        cases = self._cases()
        for case in cases:
            case["baseline"]["equivalent_cost"] = 1.0
            case["switched"]["equivalent_cost"] = 0.8
        result = scorecard.score_switch_cohort(cases, bootstrap_samples=100)
        self.assertEqual(result["cost_basis"], "equivalent_cost")
        self.assertTrue(result["quality_adjusted_cost_efficiency"]["maximizes_cost_efficiency"])

    def test_negative_incremental_findings_are_fail_closed_evidence(self) -> None:
        result = scorecard.score_switch_cost_performance(
            additional_findings=-1,
            extra_weighted_tokens=10_000,
            quality_delta=-5,
            quality_ci_low=-10,
            p95_wall_premium=0.05,
            weighted_token_premium=0.05,
            false_escalations=0,
            inconclusive=0,
        )
        self.assertEqual(result["score"], 5)
        self.assertLess(result["switch_value"], 0)
        self.assertFalse(result["proven"])

    def test_quality_adjusted_cost_efficiency_requires_quality_floor(self) -> None:
        result = scorecard.quality_adjusted_cost_efficiency(
            baseline_quality=70,
            switched_quality=80,
            baseline_cost=1.0,
            switched_cost=1.1,
            quality_delta_ci_low=2.0,
        )
        self.assertTrue(result["quality_supported"])
        self.assertGreater(result["switched_efficiency"], 0)
        self.assertGreater(result["efficiency_delta"], 0)
        self.assertTrue(result["maximizes_cost_efficiency"])

    def test_quality_adjusted_cost_efficiency_rejects_cheaper_lower_quality(self) -> None:
        result = scorecard.quality_adjusted_cost_efficiency(
            baseline_quality=80,
            switched_quality=60,
            baseline_cost=1.0,
            switched_cost=0.5,
            quality_delta_ci_low=-5.0,
        )
        self.assertFalse(result["quality_supported"])
        self.assertEqual(result["switched_efficiency"], 0.0)
        self.assertFalse(result["maximizes_cost_efficiency"])


if __name__ == "__main__":
    unittest.main()
