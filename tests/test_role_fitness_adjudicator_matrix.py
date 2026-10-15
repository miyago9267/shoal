import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("role_fitness_adjudicator_matrix", ROOT / "bench" / "role_fitness_adjudicator_matrix.py")
matrix = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(matrix)


class AdjudicatorMatrixTests(unittest.TestCase):
    def test_matrix_has_fixed_scenarios_and_policies(self) -> None:
        result = matrix.run_matrix()
        self.assertFalse(result["formal_claim"])
        self.assertEqual(len(result["cells"]), 24)
        self.assertEqual(result["contract"]["max_adjudications_per_fingerprint"], 1)

    def test_luna_only_never_adjudicates(self) -> None:
        result = matrix.run_matrix()
        aggregate = result["aggregates"]["luna_only"]
        self.assertEqual(aggregate["sol_adjudications"], 0)
        self.assertEqual(aggregate["luna_routes"], 6)
        self.assertEqual(aggregate["inconclusive"], 2)

    def test_risk_gated_adjudication_preserves_hard_risk_boundary(self) -> None:
        result = matrix.run_matrix()
        aggregate = result["aggregates"]["risk_gated_adjudication"]
        self.assertEqual(aggregate["sol_adjudications"], 3)
        by_id = {(cell["policy"], cell["scenario"]): cell for cell in result["cells"]}
        self.assertEqual(by_id[("risk_gated_adjudication", "semantic_security")]["route"], "sol_adjudicator")
        self.assertEqual(by_id[("risk_gated_adjudication", "semantic_routine")]["route"], "luna")

    def test_deterministic_conflict_and_missing_evidence_fail_closed(self) -> None:
        result = matrix.run_matrix()
        for policy in matrix.POLICIES:
            for scenario in ("deterministic_conflict", "missing_evidence"):
                cell = next(item for item in result["cells"] if item["policy"] == policy and item["scenario"] == scenario)
                self.assertEqual(cell["route"], "inconclusive")

    def test_semantic_policy_is_not_a_quality_claim(self) -> None:
        result = matrix.run_matrix()
        self.assertIn("unchanged hidden-ledger rubric", result["interpretation"])


if __name__ == "__main__":
    unittest.main()
