from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))

from evaluate_intent_matrix import evaluate  # noqa: E402
from intent_review_matrix import build_matrix  # noqa: E402


class IntentRuntimeMatrixTests(unittest.TestCase):
    def test_real_hook_runtime_meets_local_matrix_contract(self) -> None:
        report = evaluate(build_matrix())
        self.assertEqual(report["cases"], 60)
        self.assertEqual(report["metrics"]["intent_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["risk_category_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["signal_contract_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["hook_process_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["sol_trigger_accuracy"], 1.0)
        self.assertTrue(report["metrics"]["hard_gate_parity"])
        self.assertTrue(report["metrics"]["mandatory_review_trigger_preserved"])

    def test_runtime_report_is_machine_readable(self) -> None:
        report = evaluate(build_matrix())
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertIn('"version": "intent-review-runtime-matrix-v1"', encoded)
        self.assertEqual(len(report["rows"]), 60)


if __name__ == "__main__":
    unittest.main()
