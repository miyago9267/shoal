from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))

from intent_review_matrix import build_matrix, validate_matrix  # noqa: E402


class IntentReviewMatrixTests(unittest.TestCase):
    def test_matrix_has_five_families_four_intents_and_three_repeats(self) -> None:
        matrix = validate_matrix(build_matrix())
        self.assertEqual(len(matrix["cases"]), 60)
        self.assertEqual(
            {case["intent_variant"] for case in matrix["cases"]},
            {"none", "fast", "strict", "conflicting_or_quoted"},
        )
        self.assertEqual(
            {case["expected"]["task_mode"] for case in matrix["cases"]},
            {"execute", "explore_then_plan"},
        )

    def test_fast_changes_only_optional_review(self) -> None:
        matrix = build_matrix()
        cases = [case for case in matrix["cases"] if case["intent_variant"] == "fast"]
        self.assertTrue(cases)
        for case in cases:
            self.assertEqual(case["expected"]["review_intent"], "fast")
            self.assertEqual(case["expected"]["optional_review"], "skip")
            self.assertEqual(
                case["expected"]["approval_required"],
                case["expected"]["hard_gate_preserved"],
            )

    def test_conflicting_or_quoted_intent_defaults(self) -> None:
        matrix = build_matrix()
        cases = [
            case for case in matrix["cases"]
            if case["intent_variant"] == "conflicting_or_quoted"
        ]
        self.assertTrue(cases)
        self.assertTrue(all(case["expected"]["review_intent"] == "default" for case in cases))
        self.assertTrue(
            all(case["expected"]["review_intent_source"] == "risk_default" for case in cases)
        )


if __name__ == "__main__":
    unittest.main()
