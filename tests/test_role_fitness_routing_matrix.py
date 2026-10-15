from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))
import role_fitness_routing_matrix as matrix  # noqa: E402


class RoutingMatrixTests(unittest.TestCase):
    def test_matrix_compares_three_policies(self) -> None:
        report = matrix.run_matrix()
        self.assertEqual(report["version"], "role-fitness-routing-matrix-v2")
        self.assertEqual(len(report["cells"]), 18)
        self.assertEqual(report["aggregates"]["always_sol"]["sol_routes"], 6)
        self.assertEqual(report["aggregates"]["selective_v2"]["sol_routes"], 3)
        self.assertEqual(report["aggregates"]["selective_v2_uncertainty"]["sol_routes"], 4)

    def test_security_and_uncertainty_are_not_downgraded(self) -> None:
        report = matrix.run_matrix()
        cells = {(cell["policy"], cell["scenario"]): cell for cell in report["cells"]}
        self.assertEqual(cells[("selective_v2", "security_boundary")]["route"], "sol_high")
        self.assertEqual(cells[("selective_v2_uncertainty", "uncertain_single_data")]["route"], "sol_high")
        self.assertEqual(cells[("selective_v2", "single_data")]["route"], "luna_first")


if __name__ == "__main__":
    unittest.main()
