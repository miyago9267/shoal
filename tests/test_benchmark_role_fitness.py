from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))
import benchmark_role_fitness as runner  # noqa: E402
import role_fitness_scorecard as scorecard  # noqa: E402
import verify_dispatch  # noqa: E402


class RoleFitnessDryRunTests(unittest.TestCase):
    def test_dry_run_validates_all_installed_bindings(self) -> None:
        report = runner.build_dry_run_report(ROOT / "templates" / "agents")
        self.assertEqual(report["version"], "role-fitness-v1")
        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual(report["live_calls"], 0)
        self.assertEqual(set(report["role_bindings"]), set(runner.EXPECTED_BINDINGS))
        self.assertTrue(all(item["valid"] for item in report["role_bindings"].values()))
        self.assertTrue(report["scorecard_path"]["valid"])
        self.assertEqual(report["architecture"]["score"], 10)
        self.assertTrue(report["architecture"]["proven"])
        self.assertEqual(report["architecture"]["failed_checks"], [])
        self.assertTrue(all(value == "valid" for value in report["offline_contracts"].values()))

    def test_dry_run_fails_closed_on_binding_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            role_root = Path(directory)
            source = ROOT / "templates" / "agents" / "scout.toml"
            role_root.joinpath("scout.toml").write_bytes(source.read_bytes().replace(b'gpt-5.6-luna', b'gpt-5.6-sol'))
            with self.assertRaises(runner.BenchmarkContractError):
                runner.validate_role_bindings(role_root)

    def test_cli_dry_run_is_json_and_never_requests_live_work(self) -> None:
        report = runner.main(["--dry-run", "--role-root", str(ROOT / "templates" / "agents")])
        self.assertEqual(report["live_calls"], 0)

    def test_repeat_summary_requires_explicit_run_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "run.json"
            summary.write_text(json.dumps({
                "run_id": "R1", "manifest_hash": "m", "scorecard_hash": "s",
                "mode": "live-evidence",
                "availability": {"passed": 1, "total": 1},
                "stability": {"passed": 0, "total": 1},
                "stages": [{
                    "stage_id": "s1", "status": "NATIVE_OK", "phase": "post-spawn",
                    "reason_code": "native_verified", "admitted": True, "passed": True,
                    "failure_class": "none",
                }],
                "failure_taxonomy": {},
            }), encoding="utf-8")
            result = runner.append_run_summary(Path(directory) / "runs.jsonl", summary)
            self.assertEqual(result["run_ids"], ["R1"])

    def test_live_summary_counts_only_admitted_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "stage-1.json"
            verdict = verify_dispatch._verdict("SKIPPED", "native_spawn_evidence_missing", phase="post-spawn", child_created="unknown")
            payload = verify_dispatch.receipt_payload(
                verdict,
                codex_version="0.147.0-alpha.1.2",
                active={"config": "a" * 64, "role_manifest": "b" * 64, "policy": "c" * 64},
                target={"config": "a" * 64, "role_manifest": "b" * 64, "policy": "c" * 64},
            )
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            summary = runner.build_live_run_summary(
                run_id="R1", manifest_hash="m", scorecard_hash="s", receipt_paths=[receipt], stability_passed=True
            )
            self.assertEqual(summary["availability"], {"passed": 0, "total": 1})
            self.assertEqual(summary["stability"], {"passed": 1, "total": 1})
            self.assertEqual(summary["failure_taxonomy"], {"native_spawn": 1})

    def test_cli_build_summary_is_receipt_driven(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "stage-1.json"
            verdict = verify_dispatch._verdict("SKIPPED", "native_spawn_evidence_missing", phase="post-spawn", child_created="unknown")
            payload = verify_dispatch.receipt_payload(
                verdict,
                codex_version="0.146.0",
                active={"config": "a" * 64, "role_manifest": "b" * 64, "policy": "c" * 64},
                target={"config": "a" * 64, "role_manifest": "b" * 64, "policy": "c" * 64},
            )
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            summary = runner.main([
                "--build-summary", "--receipt", str(receipt), "--run-id", "R1",
                "--manifest-hash", "m", "--scorecard-hash", "s",
            ])
            self.assertEqual(summary["evidence"]["raw_sessions_published"], 0)


class RoleFitnessContractTests(unittest.TestCase):
    def test_architecture_score_rejects_unknown_or_non_boolean_checks(self) -> None:
        checks = {name: True for name in scorecard.ARCHITECTURE_CHECKS}
        self.assertEqual(scorecard.score_architecture(checks)["score"], 10)
        with self.assertRaises(ValueError):
            scorecard.score_architecture({**checks, "extra": True})
        with self.assertRaises(ValueError):
            scorecard.score_architecture({**checks, "role_binding": 1})

    def test_fixture_commitment_changes_when_hidden_bytes_change(self) -> None:
        first = runner.fixture_commitment(b"salt", "fixture", b"ledger", b"rubric")
        second = runner.fixture_commitment(b"salt", "fixture", b"changed", b"rubric")
        self.assertEqual(len(first), 64)
        self.assertNotEqual(first, second)

    def test_handoff_requires_exact_identity_free_schema(self) -> None:
        handoff = {
            "scenario_id": "s1",
            "fixture_hash": "f",
            "original_plan_hash": "o",
            "approved_plan_hash": "a",
            "ledger_commitment": "l",
            "revision_ids": ["r1"],
            "review_score_hash": "s",
        }
        self.assertTrue(runner.validate_handoff(handoff))
        with self.assertRaises(runner.BenchmarkContractError):
            runner.validate_handoff({**handoff, "model": "gpt-5.6-sol"})

    def test_public_projection_rejects_paths_and_unknown_fields(self) -> None:
        report = {"version": "role-fitness-public-v1", "cohort": {"cases": 1}}
        self.assertEqual(runner.validate_public_projection(report), report)
        with self.assertRaises(runner.BenchmarkContractError):
            runner.validate_public_projection({**report, "absolute_path": "/private/x"})

    def test_resource_admission_rejects_unbounded_run(self) -> None:
        runner.validate_resource_admission(arms=60, paid_processes=108, wall_seconds=21600)
        with self.assertRaises(runner.BenchmarkContractError):
            runner.validate_resource_admission(arms=61, paid_processes=108, wall_seconds=21600)

    def test_mechanical_result_and_split_handoff_are_fail_closed(self) -> None:
        self.assertTrue(runner.validate_mechanical_result(
            "mechanical-execution-01", {"case_id": "mechanical-execution-01", "accepted": True}
        ))
        with self.assertRaises(runner.BenchmarkContractError):
            runner.validate_mechanical_result(
                "mechanical-execution-01", {"case_id": "mechanical-execution-01", "accepted": False}
            )
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "private"
            import role_fitness_fixtures as fixtures
            fixtures.create_bundle(private, salt=b"s" * 32)
            output = {
                "decision": "REVISE",
                "rationale": "The migration needs both controls.",
                "findings": [
                    {"severity": "P1", "title": "Add a dual-write period", "evidence": "The dual-write period is absent.", "revision_id": "split-workflow-01-dual-write"},
                ],
            }
            handoff = runner.build_split_handoff(private_root=private, case_id="split-workflow-01", review_output=output)
            self.assertIsNotNone(handoff)
            self.assertEqual(handoff["revision_ids"], ["split-workflow-01-dual-write"])
            self.assertNotEqual(handoff["original_plan_hash"], handoff["approved_plan_hash"])


if __name__ == "__main__":
    unittest.main()
