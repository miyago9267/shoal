"""Operator-only rerun fields on content stages (claude-eval-parity R11, AC-CE-029)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "tests"))
import role_fitness_fixtures as fixtures  # noqa: E402
import role_fitness_scorecard as scorecard  # noqa: E402
import run_role_fitness_content as content  # noqa: E402
import test_run_role_fitness_stage_characterization as recorded  # noqa: E402

MECH_CASE = recorded.MECH_CASE


class RerunFieldTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.private_root = self.root / "private"
        fixtures.create_bundle(self.private_root, salt=b"s" * 32)
        self.active_home = self.root / "active"

    def _verify(self, host: Any, **rerun: Any) -> dict[str, Any]:
        with host.installed():
            return content.run_native_verifier_case(
                private_root=self.private_root,
                active_home=self.active_home,
                codex_bin="codex",
                case_id=MECH_CASE,
                **rerun,
            )

    def test_first_run_emits_attempt_one_and_no_rerun_of(self) -> None:
        refuted = recorded._Host(child_events=recorded._child_events("REFUTED mismatch"))
        accepted = recorded._Host(child_events=recorded._child_events("CONFIRMED ok"))
        for host in (refuted, accepted, recorded._Host(timeout=True)):
            stage = self._verify(host)
            self.assertEqual(stage["attempt"], 1)
            self.assertNotIn("rerun_of", stage)

    def test_every_case_function_stamps_attempt(self) -> None:
        for name in (
            "run_native_review_case",
            "run_native_mechanical_case",
            "run_native_verifier_case",
            "run_native_split_executor_case",
            "run_review_case",
        ):
            self.assertTrue(hasattr(getattr(content, name), "__wrapped__"), name)

    def test_operator_named_rerun_emits_attempt_and_rerun_of(self) -> None:
        initial = self._verify(recorded._Host(child_events=[recorded._usage(recorded.CHILD_USAGE)]))
        self.assertEqual(initial["status"], "inconclusive")
        self.assertEqual(initial["reason"], "verifier_did_not_confirm")
        rerun = self._verify(
            recorded._Host(child_events=recorded._child_events("CONFIRMED ok")),
            attempt=2,
            rerun_of=scorecard.stage_key(initial),
        )
        self.assertEqual((rerun["attempt"], rerun["rerun_of"]), (2, f"{MECH_CASE}#1"))
        # The recorded pair reaches the classifier as a verifier_retry, once.
        self.assertEqual(
            scorecard.classify_content_stages([initial, rerun]), [None, "verifier_retry"]
        )

    def test_rerun_requires_a_consistent_operator_request(self) -> None:
        bad_requests = [
            {"attempt": 2},
            {"rerun_of": f"{MECH_CASE}#1"},
            {"attempt": 2, "rerun_of": "plan-review-01#1"},
            {"attempt": 2, "rerun_of": f"{MECH_CASE}#2"},
            {"attempt": 2, "rerun_of": f"{MECH_CASE}#0"},
            {"attempt": 2, "rerun_of": MECH_CASE},
            {"attempt": 0},
            {"attempt": True},
            {"attempt": 2, "rerun_of": 7},
        ]
        for request in bad_requests:
            host = recorded._Host()
            with self.subTest(request=request), self.assertRaises(content.BenchmarkContractError):
                self._verify(host, **request)
            self.assertEqual(host.run_calls, [], "a rejected rerun must not start a stage")

    def test_runner_never_retries_by_itself(self) -> None:
        host = recorded._Host(child_events=[recorded._usage(recorded.CHILD_USAGE)])
        stage = self._verify(host)
        self.assertEqual(stage["status"], "inconclusive")
        self.assertEqual(len(host.run_calls), 1)

        inconclusive = {"case_id": recorded.PLAN_CASE, "status": "inconclusive", "reason": "timeout"}
        output = self.root / "report.json"
        with patch.object(
            content, "run_review_case", side_effect=lambda **kw: {**inconclusive, "candidate": kw["candidate"]}
        ) as run_case:
            content.main(
                [
                    "--live", "--yes",
                    "--private-root", str(self.private_root),
                    "--active-codex-home", str(self.active_home),
                    "--codex-bin", "codex",
                    "--case-id", recorded.PLAN_CASE,
                    "--output", str(output),
                ]
            )
        self.assertEqual(run_case.call_count, len(content.CANDIDATES))
        for call in run_case.call_args_list:
            self.assertNotIn("rerun_of", call.kwargs)
            self.assertNotIn("attempt", call.kwargs)

    def test_runner_has_no_retry_path(self) -> None:
        source = (ROOT / "install" / "run_role_fitness_content.py").read_text(encoding="utf-8")
        # The only code that reads the rerun fields is the operator-facing stamp.
        self.assertEqual(source.count("rerun_of="), 0)
        self.assertEqual(source.count("attempt="), 0)
        self.assertNotIn("retry", source.lower().replace("no automatic retries", ""))


if __name__ == "__main__":
    unittest.main()
