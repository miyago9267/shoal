from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))
import quality_cost_frontier as frontier  # noqa: E402


class QualityFirstFrontierTests(unittest.TestCase):
    def test_quality_floor_blocks_cheap_but_lower_quality_candidate(self) -> None:
        result = frontier.score_quality_first_frontier(
            candidate_quality=70,
            luna_quality=80,
            quality_ci_low_vs_luna=-2,
            candidate_cost_usd=1,
            pure_sol_cost_usd=3,
            pure_terra_cost_usd=2,
        )
        self.assertFalse(result["quality_floor_met"])
        self.assertFalse(result["acceptable_under_quality_first_rule"])

    def test_cost_frontier_passes_when_quality_floor_and_any_reference_saving_hold(self) -> None:
        result = frontier.score_quality_first_frontier(
            candidate_quality=80,
            luna_quality=80,
            quality_ci_low_vs_luna=0,
            candidate_cost_usd=1.5,
            pure_sol_cost_usd=3,
            pure_terra_cost_usd=1,
        )
        self.assertTrue(result["quality_floor_met"])
        self.assertTrue(result["cheaper_than_pure_sol"])
        self.assertFalse(result["cheaper_than_pure_terra"])
        self.assertTrue(result["cost_frontier_pass"])

    def test_quality_win_passes_even_when_not_cheaper(self) -> None:
        result = frontier.score_quality_first_frontier(
            candidate_quality=90,
            luna_quality=80,
            quality_ci_low_vs_luna=3,
            candidate_cost_usd=4,
            pure_sol_cost_usd=3,
            pure_terra_cost_usd=2,
        )
        self.assertTrue(result["quality_frontier_pass"])
        self.assertTrue(result["acceptable_under_quality_first_rule"])

    def test_effective_unit_costs_are_derived_from_recorded_summary(self) -> None:
        result = frontier.effective_unit_costs(
            {"candidate_aggregates": {
                "luna": {"equivalent_cost_usd": 1, "weighted_tokens": 100},
                "sol": {"equivalent_cost_usd": 2, "weighted_tokens": 100},
                "terra": {"equivalent_cost_usd": 3, "weighted_tokens": 100},
            }}
        )
        self.assertEqual(result, {"luna": 0.01, "sol": 0.02, "terra": 0.03})
