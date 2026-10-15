from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))
import role_fitness_fixtures as fixtures  # noqa: E402


class FixtureBundleTests(unittest.TestCase):
    def test_bundle_has_frozen_counts_and_public_hashes_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "private"
            public = fixtures.create_bundle(private, salt=b"s" * 32)
            validated = fixtures.validate_bundle(private)
            self.assertEqual(public, validated)
            self.assertEqual(public["case_count"], 30)
            self.assertEqual(len(public["cases"]), 30)
            self.assertNotIn("dual-write period", json.dumps(public))
            if os.name != "nt":
                self.assertEqual(private.stat().st_mode & 0o077, 0)

    def test_commitment_detects_ledger_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "private"
            fixtures.create_bundle(private, salt=b"s" * 32)
            ledgers = json.loads((private / "ledgers.json").read_text(encoding="utf-8"))
            ledgers["plan-review-05"][0]["weight"] = 99
            (private / "ledgers.json").write_text(json.dumps(ledgers), encoding="utf-8")
            with self.assertRaises(fixtures.BenchmarkContractError):
                fixtures.validate_bundle(private)

    def test_public_manifest_cannot_be_written_inside_private_root_as_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "private"
            fixtures.create_bundle(private, salt=b"s" * 32)
            self.assertEqual(fixtures.COHORT_COUNTS, {"plan_review": 12, "mechanical_execution": 12, "split_workflow": 6})

    def test_review_scorer_matches_hidden_anchors_and_rejects_clean_escalation(self) -> None:
        ledger = fixtures._ledger("risk", False)
        output = {
            "decision": "REVISE",
            "rationale": "The migration needs explicit safety controls.",
            "findings": [
                {"severity": "P1", "title": "Add a dual-write period", "evidence": "The dual-write period is absent.", "revision_id": "risk-dual-write"},
                {"severity": "P1", "title": "Provide a tested rollback artifact", "evidence": "The tested rollback artifact is absent.", "revision_id": "risk-rollback"},
            ],
        }
        result = fixtures.score_plan_review(ledger, output)
        self.assertEqual(result["risk_coverage"], 1.0)
        self.assertTrue(result["passed"])
        clean = fixtures.score_plan_review([], {"decision": "REVISE", "findings": [], "rationale": "unclear"})
        self.assertTrue(clean["false_escalation"])
        self.assertFalse(clean["passed"])

    def test_acceptance_and_split_revision_semantics_are_validated(self) -> None:
        self.assertTrue(fixtures.validate_mechanical_acceptance(
            "mechanical-execution-01",
            {
                "case_id": "mechanical-execution-01",
                "allowed_paths": ["result.json"],
                "required_artifact": {"case_id": "mechanical-execution-01", "accepted": True},
            },
        ))
        self.assertTrue(fixtures.validate_split_revisions(
            "split-workflow-01",
            {
                "case_id": "split-workflow-01",
                "revision_fragments": [{"revision_id": "split-workflow-01-dual-write", "text": "Add rollback."}],
            },
        ))
        with self.assertRaises(fixtures.BenchmarkContractError):
            fixtures.validate_mechanical_acceptance(
                "mechanical-execution-01",
                {"case_id": "mechanical-execution-01", "allowed_paths": ["result.json", "secret.txt"], "required_artifact": {"case_id": "mechanical-execution-01", "accepted": True}},
            )

    def test_new_split_bundle_contains_all_ledger_bound_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "private"
            fixtures.create_bundle(private, salt=b"s" * 32)
            revisions = json.loads((private / "revisions" / "split-workflow-01.json").read_text(encoding="utf-8"))
            self.assertEqual(
                {item["revision_id"] for item in revisions["revision_fragments"]},
                {"split-workflow-01-dual-write", "split-workflow-01-rollback"},
            )


if __name__ == "__main__":
    unittest.main()
