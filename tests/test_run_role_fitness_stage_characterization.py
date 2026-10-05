"""Characterization of every content-runner stage on recorded inputs (AC-CE-010).

Each case replays a recorded Codex stdout / rollout through the runner with the
subprocess, materialization and dispatch-inspection boundaries stubbed, then pins
the full stage dict, the argv/env handed to the host, and the cleanup effect.
The expectations were captured from the runner before the host-adapter
extraction and must not change with it.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import role_fitness_fixtures as fixtures  # noqa: E402
import run_role_fitness_content as content  # noqa: E402
import verify_dispatch as dispatch  # noqa: E402
from stage_smoke_home import StageError  # noqa: E402

PLAN_CASE = "plan-review-01"
MECH_CASE = "mechanical-execution-01"
SPLIT_CASE = "split-workflow-01"
GOOD_RESULT = {"case_id": MECH_CASE, "accepted": True}

PARENT_USAGE = {
    "input_tokens": 50,
    "cached_input_tokens": 10,
    "cache_write_input_tokens": 2,
    "output_tokens": 7,
}
CHILD_USAGE = {
    "input_tokens": 100,
    "cached_input_tokens": 20,
    "cache_write_input_tokens": 4,
    "output_tokens": 30,
}


def _message(text: str) -> dict[str, Any]:
    return {"type": "item.completed", "item": {"type": "agent_message", "text": text}}


def _usage(usage: dict[str, int]) -> dict[str, Any]:
    return {"type": "turn.completed", "usage": usage}


PARENT_EVENTS = [_usage(PARENT_USAGE)]


def _child_events(text: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            },
        },
        _message(text),
        _usage(CHILD_USAGE),
    ]


def _verdict(status: str = "NATIVE_OK", reason: str = "ok") -> dispatch.Verdict:
    return dispatch.Verdict(
        status, reason, model="gpt-5.6-luna", reasoning_effort="low"
    )


class _Host:
    """Records what the runner hands to the host and replays a recorded run."""

    def __init__(
        self,
        *,
        stdout: str = "recorded-stdout",
        returncode: int = 0,
        timeout: bool = False,
        seed_result: dict[str, Any] | None = None,
        child_events: list[dict[str, Any]] | None = None,
        verdict: dispatch.Verdict | None = None,
        evidence_error: Exception | None = None,
        materialize_error: Exception | None = None,
    ) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.timeout = timeout
        self.seed_result = seed_result
        self.child_events = (
            child_events if child_events is not None else _child_events("READY")
        )
        self.verdict = verdict or _verdict()
        self.evidence_error = evidence_error
        self.materialize_error = materialize_error
        self.run_calls: list[dict[str, Any]] = []
        self.materialize_calls: list[tuple[str, str]] = []
        self.inspect_calls: list[dict[str, Any]] = []
        self.binding_paths: list[str] = []
        self.rollout_dirs: list[str] = []
        self.cwd_seen: Path | None = None
        self.directory_seen: Path | None = None
        self.cwd_entries_at_run: list[str] = []

    def run(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        cwd = Path(argv[argv.index("-C") + 1])
        self.cwd_seen = cwd
        self.directory_seen = cwd.parent
        self.cwd_entries_at_run = sorted(path.name for path in cwd.iterdir())
        env = kwargs["env"]
        self.run_calls.append(
            {
                "argv": list(argv[:-1]),
                "prompt_sha256": hashlib.sha256(argv[-1].encode()).hexdigest(),
                "prompt": argv[-1],
                "codex_home_name": Path(env["CODEX_HOME"]).name,
                "sqlite_home_is_codex_home": env["CODEX_SQLITE_HOME"]
                == env["CODEX_HOME"],
                "stdin_devnull": kwargs["stdin"] is subprocess.DEVNULL,
                "capture_output": kwargs["capture_output"],
                "text": kwargs["text"],
                "check": kwargs["check"],
                "timeout": kwargs["timeout"],
            }
        )
        if self.timeout:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        if self.seed_result is not None:
            (cwd / "result.json").write_text(
                json.dumps(self.seed_result), encoding="utf-8"
            )
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "")

    def materialize(self, active_home: Path, home: Path) -> None:
        self.materialize_calls.append((Path(active_home).name, home.name))
        if self.materialize_error is not None:
            raise self.materialize_error

    # -- dispatch evidence boundary ------------------------------------
    def parse_exec_thread_id(self, stdout: str) -> str:
        if self.evidence_error is not None:
            raise self.evidence_error
        return "parent-thread"

    def locate_rollout(self, sessions: Path, thread_id: str) -> Path:
        self.rollout_dirs.append(f"{sessions.parent.name}/{sessions.name}")
        return Path(thread_id)

    def load_jsonl(self, path: Path) -> list[dict[str, Any]]:
        return PARENT_EVENTS if path.name == "parent-thread" else self.child_events

    def child_thread_from_parent(self, events: list[dict[str, Any]]) -> str:
        return "child-thread"

    def read_role_binding(self, path: Path) -> dispatch.RoleBinding:
        self.binding_paths.append(f"{path.parent.name}/{path.name}")
        return dispatch.RoleBinding("gpt-5.6-luna", "low")

    def inspect_dispatch(
        self, parent: list, child: list, **kwargs: Any
    ) -> dispatch.Verdict:
        self.inspect_calls.append(
            {
                "expected_role_name": kwargs["expected_role_name"],
                "expected_task_name": kwargs["expected_task_name"],
                "expected_role": kwargs["expected_role"],
                "parent_is_recorded": parent == PARENT_EVENTS,
                "child_is_recorded": child == self.child_events,
            }
        )
        return self.verdict

    @contextmanager
    def installed(self) -> Iterator[None]:
        clock = iter([100.0, 102.3456])
        with (
            patch.object(content.subprocess, "run", side_effect=self.run),
            patch.object(content, "materialize", side_effect=self.materialize),
            patch.object(
                content.time, "monotonic", side_effect=lambda: next(clock, 102.3456)
            ),
            patch.object(
                content.dispatch,
                "parse_exec_thread_id",
                side_effect=self.parse_exec_thread_id,
            ),
            patch.object(
                content.dispatch, "locate_rollout", side_effect=self.locate_rollout
            ),
            patch.object(content.dispatch, "load_jsonl", side_effect=self.load_jsonl),
            patch.object(
                content.dispatch,
                "child_thread_from_parent",
                side_effect=self.child_thread_from_parent,
            ),
            patch.object(
                content.dispatch,
                "read_role_binding",
                side_effect=self.read_role_binding,
            ),
            patch.object(
                content.dispatch, "inspect_dispatch", side_effect=self.inspect_dispatch
            ),
        ):
            yield


NATIVE_ARGV_HEAD = [
    "codex",
    "exec",
    "--enable",
    "multi_agent_v2",
    "--json",
    "--strict-config",
    "--skip-git-repo-check",
    "-C",
]
NATIVE_ARGV_TAIL = ["-m", "gpt-5.6-luna", "-c", 'model_reasoning_effort="low"', "-s"]


class StageCharacterizationTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.private_root = self.root / "private"
        fixtures.create_bundle(self.private_root, salt=b"s" * 32)
        self.active_home = self.root / "active"

    def _stage(self, host: _Host, call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        with host.installed():
            row = call()
        self.assertIsNotNone(host.directory_seen, "host never ran")
        self.assertFalse(
            host.directory_seen.exists(), "stage directory must be removed"
        )
        return row

    def _assert_native_run(
        self,
        host: _Host,
        *,
        sandbox: str,
        prompt_sha256: str,
        role: str,
        timeout: int = 360,
    ) -> None:
        self.assertEqual(len(host.run_calls), 1)
        call = host.run_calls[0]
        self.assertEqual(
            call["argv"],
            NATIVE_ARGV_HEAD + [str(host.cwd_seen)] + NATIVE_ARGV_TAIL + [sandbox],
        )
        self.assertEqual(call["prompt_sha256"], prompt_sha256)
        self.assertEqual(call["codex_home_name"], "codex-home")
        self.assertTrue(call["sqlite_home_is_codex_home"])
        self.assertTrue(call["stdin_devnull"])
        self.assertTrue(call["capture_output"] and call["text"] and not call["check"])
        self.assertEqual(call["timeout"], timeout)
        self.assertEqual(host.materialize_calls, [("active", "codex-home")])

    def _assert_binding(self, host: _Host, role: str, task: str) -> None:
        self.assertEqual(host.binding_paths, [f"agents/{role}.toml"])
        self.assertEqual(
            host.rollout_dirs, ["codex-home/sessions", "codex-home/sessions"]
        )
        self.assertEqual(len(host.inspect_calls), 1)
        inspected = host.inspect_calls[0]
        self.assertEqual(inspected["expected_role_name"], role)
        self.assertEqual(inspected["expected_task_name"], task)
        self.assertEqual(
            inspected["expected_role"], dispatch.RoleBinding("gpt-5.6-luna", "low")
        )
        self.assertTrue(
            inspected["parent_is_recorded"] and inspected["child_is_recorded"]
        )

    # -- direct (non-native) review ------------------------------------
    def _direct(self, host: _Host, **overrides: Any) -> dict[str, Any]:
        return self._stage(
            host,
            lambda: content.run_review_case(
                private_root=self.private_root,
                active_home=self.active_home,
                codex_bin="codex",
                case_id=PLAN_CASE,
                candidate="luna_xhigh",
                timeout=7,
                **overrides,
            ),
        )

    def _assert_direct_run(self, host: _Host) -> None:
        call = host.run_calls[0]
        model, effort = content.CANDIDATES["luna_xhigh"]
        self.assertEqual(
            call["argv"],
            [
                "codex",
                "exec",
                "--json",
                "--strict-config",
                "--skip-git-repo-check",
                "-C",
                str(host.cwd_seen),
                "-m",
                model,
                "-c",
                f'model_reasoning_effort="{effort}"',
                "-s",
                "read-only",
            ],
        )
        self.assertEqual(call["prompt_sha256"], DIRECT_PROMPT_SHA256)
        self.assertEqual(call["timeout"], 7)
        self.assertEqual(call["codex_home_name"], "codex-home")
        self.assertTrue(call["sqlite_home_is_codex_home"] and call["stdin_devnull"])
        self.assertEqual(host.inspect_calls, [])

    def test_direct_review_accepted(self) -> None:
        stdout = "\n".join(
            json.dumps(event)
            for event in [
                _message(
                    json.dumps({"decision": "READY", "findings": [], "rationale": "ok"})
                ),
                _usage(CHILD_USAGE),
            ]
        )
        host = _Host(stdout=stdout)
        row = self._direct(host)
        self._assert_direct_run(host)
        self.assertEqual(row, EXPECTED["direct_accepted"])

    def test_direct_review_prompt_override_and_model_override(self) -> None:
        host = _Host(stdout="not json", returncode=1)
        row = self._direct(
            host,
            prompt_override="OVERRIDE PROMPT",
            model_effort_override=("m-x", "high"),
        )
        call = host.run_calls[0]
        self.assertEqual(call["prompt"], "OVERRIDE PROMPT")
        self.assertEqual(
            call["argv"][-6:],
            ["-m", "m-x", "-c", 'model_reasoning_effort="high"', "-s", "read-only"],
        )
        self.assertEqual(row, EXPECTED["direct_invalid"])

    def test_direct_review_timeout(self) -> None:
        row = self._direct(_Host(timeout=True))
        self.assertEqual(
            row,
            {
                "case_id": PLAN_CASE,
                "candidate": "luna_xhigh",
                "status": "inconclusive",
                "reason": "timeout",
            },
        )

    def test_direct_review_materialization_failure(self) -> None:
        host = _Host(materialize_error=StageError("boom"))
        with (
            host.installed(),
            self.assertRaises(content.BenchmarkContractError) as caught,
        ):
            content.run_review_case(
                private_root=self.private_root,
                active_home=self.active_home,
                codex_bin="codex",
                case_id=PLAN_CASE,
                candidate="luna_xhigh",
            )
        self.assertEqual(
            str(caught.exception), "content stage materialization failed: boom"
        )
        self.assertEqual(host.run_calls, [])

    # -- native plan-verifier review -----------------------------------
    def _native_review(self, host: _Host) -> dict[str, Any]:
        return self._stage(
            host,
            lambda: content.run_native_review_case(
                private_root=self.private_root,
                active_home=self.active_home,
                codex_bin="codex",
                case_id=PLAN_CASE,
                timeout=9,
            ),
        )

    def test_native_review_accepted(self) -> None:
        host = _Host(child_events=_child_events("READY"))
        row = self._native_review(host)
        self._assert_native_run(
            host,
            sandbox="read-only",
            prompt_sha256=NATIVE_REVIEW_PROMPT_SHA256,
            role="plan-verifier",
            timeout=9,
        )
        self._assert_binding(host, "plan-verifier", "role_fitness_plan_review")
        self.assertEqual(host.cwd_entries_at_run, [])
        self.assertEqual(row, EXPECTED["native_review_accepted"])

    def test_native_review_invalid_output_reports_bounded_diagnostics(self) -> None:
        host = _Host(
            child_events=_child_events("REVISE\n- Blocker: something\n  Evidence: e"),
            verdict=_verdict("FAILED", "policy_violation"),
            returncode=0,
        )
        row = self._native_review(host)
        self.assertEqual(row, EXPECTED["native_review_invalid"])

    def test_native_review_nonzero_exit_is_invalid(self) -> None:
        row = self._native_review(
            _Host(child_events=_child_events("READY"), returncode=3)
        )
        self.assertEqual(row["reason"], "invalid_native_review_output")
        self.assertEqual(row["dispatch_status"], "NATIVE_OK")
        self.assertEqual(row["wall_seconds"], 2.346)

    def test_native_review_timeout(self) -> None:
        row = self._native_review(_Host(timeout=True))
        self.assertEqual(
            row,
            {
                "case_id": PLAN_CASE,
                "status": "inconclusive",
                "reason": "timeout",
                "native_role": "plan-verifier",
            },
        )

    def test_native_review_evidence_unavailable(self) -> None:
        for error in (
            dispatch.EvidenceError("x"),
            dispatch.ReceiptError("x"),
            FileNotFoundError("x"),
        ):
            with self.subTest(error=type(error).__name__):
                row = self._native_review(_Host(evidence_error=error))
                self.assertEqual(
                    row,
                    {
                        "case_id": PLAN_CASE,
                        "status": "inconclusive",
                        "reason": "native_evidence_unavailable",
                        "detail": type(error).__name__,
                    },
                )

    def test_native_review_materialization_failure(self) -> None:
        host = _Host(materialize_error=StageError("boom"))
        with (
            host.installed(),
            self.assertRaises(content.BenchmarkContractError) as caught,
        ):
            content.run_native_review_case(
                private_root=self.private_root,
                active_home=self.active_home,
                codex_bin="codex",
                case_id=PLAN_CASE,
            )
        self.assertEqual(
            str(caught.exception), "native content stage materialization failed: boom"
        )

    # -- native mechanical executor ------------------------------------
    def _mechanical(self, host: _Host) -> dict[str, Any]:
        return self._stage(
            host,
            lambda: content.run_native_mechanical_case(
                private_root=self.private_root,
                active_home=self.active_home,
                codex_bin="codex",
                case_id=MECH_CASE,
                timeout=11,
            ),
        )

    def test_native_mechanical_accepted_uses_child_usage_only(self) -> None:
        host = _Host(seed_result=GOOD_RESULT)
        row = self._mechanical(host)
        self._assert_native_run(
            host,
            sandbox="workspace-write",
            prompt_sha256=MECH_PROMPT_SHA256,
            role="mech-executor",
            timeout=11,
        )
        self._assert_binding(host, "mech-executor", "role_fitness_mechanical_execution")
        self.assertEqual(host.cwd_entries_at_run, [])
        self.assertEqual(row["usage"], CHILD_USAGE)
        self.assertEqual(row, EXPECTED["mechanical_accepted"])

    def test_native_mechanical_missing_or_wrong_artifact(self) -> None:
        for name, seed in (
            ("missing", None),
            ("wrong", {"case_id": MECH_CASE, "accepted": False}),
        ):
            with self.subTest(name):
                row = self._mechanical(_Host(seed_result=seed))
                self.assertEqual(row, EXPECTED["mechanical_invalid"])

    def test_native_mechanical_dispatch_not_ok(self) -> None:
        row = self._mechanical(
            _Host(seed_result=GOOD_RESULT, verdict=_verdict("FAILED", "wrong_role"))
        )
        self.assertEqual(row["reason"], "invalid_native_mechanical_acceptance")
        self.assertEqual(
            (row["dispatch_status"], row["dispatch_reason"]), ("FAILED", "wrong_role")
        )

    def test_native_mechanical_timeout_and_evidence(self) -> None:
        self.assertEqual(
            self._mechanical(_Host(timeout=True)),
            {
                "case_id": MECH_CASE,
                "status": "inconclusive",
                "reason": "timeout",
                "native_role": "mech-executor",
            },
        )
        self.assertEqual(
            self._mechanical(_Host(evidence_error=dispatch.EvidenceError("x"))),
            {
                "case_id": MECH_CASE,
                "status": "inconclusive",
                "reason": "native_evidence_unavailable",
                "detail": "EvidenceError",
            },
        )

    def test_native_mechanical_materialization_failure(self) -> None:
        host = _Host(materialize_error=StageError("boom"))
        with (
            host.installed(),
            self.assertRaises(content.BenchmarkContractError) as caught,
        ):
            content.run_native_mechanical_case(
                private_root=self.private_root,
                active_home=self.active_home,
                codex_bin="codex",
                case_id=MECH_CASE,
            )
        self.assertEqual(
            str(caught.exception),
            "native mechanical stage materialization failed: boom",
        )

    # -- native verifier -----------------------------------------------
    def _verifier(self, host: _Host) -> dict[str, Any]:
        return self._stage(
            host,
            lambda: content.run_native_verifier_case(
                private_root=self.private_root,
                active_home=self.active_home,
                codex_bin="codex",
                case_id=MECH_CASE,
                timeout=13,
            ),
        )

    def test_native_verifier_accepted(self) -> None:
        host = _Host(child_events=_child_events("CONFIRMED case_id and accepted match"))
        row = self._verifier(host)
        self._assert_native_run(
            host,
            sandbox="workspace-write",
            prompt_sha256=VERIFIER_PROMPT_SHA256,
            role="verifier",
            timeout=13,
        )
        self._assert_binding(host, "verifier", "role_fitness_mechanical_verification")
        self.assertEqual(host.cwd_entries_at_run, ["result.json"])
        self.assertEqual(row, EXPECTED["verifier_accepted"])

    def test_native_verifier_not_confirmed(self) -> None:
        refuted = self._verifier(_Host(child_events=_child_events("REFUTED mismatch")))
        self.assertEqual(refuted, EXPECTED["verifier_refuted"])
        silent = self._verifier(_Host(child_events=[_usage(CHILD_USAGE)]))
        self.assertEqual(
            (silent["verification"], silent["status_candidates"]), ("INCONCLUSIVE", [])
        )

    def test_native_verifier_timeout_evidence_and_materialization(self) -> None:
        self.assertEqual(
            self._verifier(_Host(timeout=True)),
            {
                "case_id": MECH_CASE,
                "status": "inconclusive",
                "reason": "timeout",
                "native_role": "verifier",
            },
        )
        self.assertEqual(
            self._verifier(_Host(evidence_error=dispatch.ReceiptError("x"))),
            {
                "case_id": MECH_CASE,
                "status": "inconclusive",
                "reason": "native_evidence_unavailable",
                "detail": "ReceiptError",
            },
        )
        host = _Host(materialize_error=StageError("boom"))
        with (
            host.installed(),
            self.assertRaises(content.BenchmarkContractError) as caught,
        ):
            content.run_native_verifier_case(
                private_root=self.private_root,
                active_home=self.active_home,
                codex_bin="codex",
                case_id=MECH_CASE,
            )
        self.assertEqual(
            str(caught.exception), "native verifier stage materialization failed: boom"
        )

    # -- native split executor -----------------------------------------
    def _split(self, host: _Host, case_id: str = SPLIT_CASE) -> dict[str, Any]:
        handoff = {"scenario_id": SPLIT_CASE, "steps": ["a", "b"]}
        return self._stage(
            host,
            lambda: content.run_native_split_executor_case(
                active_home=self.active_home,
                codex_bin="codex",
                case_id=case_id,
                handoff=handoff,
                timeout=15,
            ),
        )

    def test_native_split_executor_accepted_merges_parent_usage(self) -> None:
        host = _Host(seed_result={"case_id": SPLIT_CASE, "accepted": True})
        row = self._split(host)
        self._assert_native_run(
            host,
            sandbox="workspace-write",
            prompt_sha256=SPLIT_PROMPT_SHA256,
            role="mech-executor",
            timeout=15,
        )
        self._assert_binding(host, "mech-executor", "role_fitness_split_execution")
        self.assertEqual(host.cwd_entries_at_run, [])
        self.assertEqual(row, EXPECTED["split_accepted"])

    def test_native_split_executor_invalid(self) -> None:
        self.assertEqual(self._split(_Host()), EXPECTED["split_invalid"])
        self.assertEqual(
            self._split(
                _Host(
                    seed_result={"case_id": SPLIT_CASE, "accepted": True}, returncode=2
                )
            )["reason"],
            "invalid_split_executor_acceptance",
        )

    def test_native_split_executor_identity_and_materialization(self) -> None:
        with self.assertRaises(content.BenchmarkContractError) as caught:
            content.run_native_split_executor_case(
                active_home=self.active_home,
                codex_bin="codex",
                case_id=SPLIT_CASE,
                handoff={"scenario_id": "other"},
            )
        self.assertEqual(
            str(caught.exception), "split executor handoff identity is invalid"
        )
        host = _Host(materialize_error=StageError("boom"))
        with (
            host.installed(),
            self.assertRaises(content.BenchmarkContractError) as caught,
        ):
            content.run_native_split_executor_case(
                active_home=self.active_home,
                codex_bin="codex",
                case_id=SPLIT_CASE,
                handoff={"scenario_id": SPLIT_CASE},
            )
        self.assertEqual(
            str(caught.exception), "native split executor materialization failed: boom"
        )


DIRECT_PROMPT_SHA256 = "62709909982b301177c7c787092ab6755f337c8939c87941a12c1b33db2a4673"
NATIVE_REVIEW_PROMPT_SHA256 = "09071640ad9f9a519acab154d8c8c208db1911528757d05a14ce539f81e2f480"
MECH_PROMPT_SHA256 = "f55526f98a1e38ff7ca2dc02b800d79657af5b401b0ac9c3e6ac8bf0d40b9f4d"
VERIFIER_PROMPT_SHA256 = "be3c6182e921a48d39c490d3ffcd70c0c4cf4a976b9e85ab65c647346bb97ab6"
SPLIT_PROMPT_SHA256 = "3d29bbc7e1d89b93954689d66f1752fdccc4238929708bfaef2295d831e41380"
EXPECTED: dict[str, Any] = {'direct_accepted': {'candidate': 'luna_xhigh',
                     'case_id': 'plan-review-01',
                     'event_types': {'item.completed': 1, 'turn.completed': 1},
                     'false_escalation': False,
                     'quality_score': 100.0,
                     'review_output': {'decision': 'READY', 'findings': [], 'rationale': 'ok'},
                     'score': {'actionable_revision': 1.0,
                               'claimed_findings': 0,
                               'critical_precision': 1.0,
                               'decision': 'READY',
                               'expected_decision': 'READY',
                               'false_escalation': False,
                               'inconclusive': False,
                               'matched_findings': 0,
                               'passed': True,
                               'risk_coverage': 1.0,
                               'supported_findings': 0},
                     'status': 'accepted',
                     'supported_findings': 0,
                     'usage': {'cache_write_input_tokens': 4,
                               'cached_input_tokens': 20,
                               'input_tokens': 100,
                               'output_tokens': 30},
                     'wall_seconds': 2.346,
                     'weighted_tokens': 113.0},
 'direct_invalid': {'candidate': 'luna_xhigh',
                    'case_id': 'plan-review-01',
                    'event_types': {},
                    'reason': 'invalid_review_output',
                    'status': 'inconclusive',
                    'wall_seconds': 2.346},
 'mechanical_accepted': {'accepted': True,
                         'case_id': 'mechanical-execution-01',
                         'dispatch_reason': 'ok',
                         'dispatch_status': 'NATIVE_OK',
                         'event_types': {'item.completed': 1,
                                         'response_item': 1,
                                         'turn.completed': 1},
                         'model': 'gpt-5.6-luna',
                         'native_role': 'mech-executor',
                         'reasoning_effort': 'low',
                         'status': 'accepted',
                         'usage': {'cache_write_input_tokens': 4,
                                   'cached_input_tokens': 20,
                                   'input_tokens': 100,
                                   'output_tokens': 30},
                         'wall_seconds': 2.346,
                         'weighted_tokens': 113.0},
 'mechanical_invalid': {'case_id': 'mechanical-execution-01',
                        'dispatch_reason': 'ok',
                        'dispatch_status': 'NATIVE_OK',
                        'event_types': {'item.completed': 1,
                                        'response_item': 1,
                                        'turn.completed': 1},
                        'reason': 'invalid_native_mechanical_acceptance',
                        'status': 'inconclusive',
                        'wall_seconds': 2.346},
 'native_review_accepted': {'case_id': 'plan-review-01',
                            'dispatch_reason': 'ok',
                            'dispatch_status': 'NATIVE_OK',
                            'event_types': {'item.completed': 1,
                                            'response_item': 1,
                                            'turn.completed': 1},
                            'false_escalation': False,
                            'model': 'gpt-5.6-luna',
                            'native_role': 'plan-verifier',
                            'quality_score': 100.0,
                            'reasoning_effort': 'low',
                            'review_output': {'decision': 'READY',
                                              'findings': [],
                                              'rationale': 'native role returned READY'},
                            'risk_coverage': 1.0,
                            'score': {'actionable_revision': 1.0,
                                      'claimed_findings': 0,
                                      'critical_precision': 1.0,
                                      'decision': 'READY',
                                      'expected_decision': 'READY',
                                      'false_escalation': False,
                                      'inconclusive': False,
                                      'matched_findings': 0,
                                      'passed': True,
                                      'risk_coverage': 1.0,
                                      'supported_findings': 0},
                            'status': 'accepted',
                            'supported_findings': 0,
                            'usage': {'cache_write_input_tokens': 6,
                                      'cached_input_tokens': 30,
                                      'input_tokens': 150,
                                      'output_tokens': 37},
                            'wall_seconds': 2.346,
                            'weighted_tokens': 161.5},
 'native_review_invalid': {'case_id': 'plan-review-01',
                           'dispatch_reason': 'policy_violation',
                           'dispatch_status': 'FAILED',
                           'event_shapes': [{'content_types': ['output_text'],
                                             'event_type': 'response_item',
                                             'item_keys': ['content', 'type'],
                                             'item_type': 'message'},
                                            {'content_types': [],
                                             'event_type': 'item.completed',
                                             'item_keys': ['text', 'type'],
                                             'item_type': 'agent_message'}],
                           'event_types': {'item.completed': 1,
                                           'response_item': 1,
                                           'turn.completed': 1},
                           'message_count': 2,
                           'message_signals': [{'field_count': 2,
                                                'first': 'R',
                                                'has_decision': False,
                                                'has_findings': False,
                                                'has_revise': True,
                                                'last': 'e',
                                                'length': 41},
                                               {'field_count': 2,
                                                'first': 'R',
                                                'has_decision': False,
                                                'has_findings': False,
                                                'has_revise': True,
                                                'last': 'e',
                                                'length': 41}],
                           'reason': 'invalid_native_review_output',
                           'role_shapes': [{'blank_blocks': 0,
                                            'field_count': 2,
                                            'fields': ['Blocker', 'Evidence'],
                                            'length': 41,
                                            'prefix': 'REVISE\n- Blo'},
                                           {'blank_blocks': 0,
                                            'field_count': 2,
                                            'fields': ['Blocker', 'Evidence'],
                                            'length': 41,
                                            'prefix': 'REVISE\n- Blo'}],
                           'status': 'inconclusive',
                           'wall_seconds': 2.346},
 'split_accepted': {'accepted': True,
                    'case_id': 'split-workflow-01',
                    'dispatch_reason': 'ok',
                    'dispatch_status': 'NATIVE_OK',
                    'event_types': {'item.completed': 1, 'response_item': 1, 'turn.completed': 1},
                    'model': 'gpt-5.6-luna',
                    'native_role': 'mech-executor',
                    'reasoning_effort': 'low',
                    'status': 'accepted',
                    'usage': {'cache_write_input_tokens': 6,
                              'cached_input_tokens': 30,
                              'input_tokens': 150,
                              'output_tokens': 37},
                    'wall_seconds': 2.346,
                    'weighted_tokens': 161.5},
 'split_invalid': {'case_id': 'split-workflow-01',
                   'dispatch_reason': 'ok',
                   'dispatch_status': 'NATIVE_OK',
                   'event_types': {'item.completed': 1, 'response_item': 1, 'turn.completed': 1},
                   'reason': 'invalid_split_executor_acceptance',
                   'status': 'inconclusive',
                   'wall_seconds': 2.346},
 'verifier_accepted': {'case_id': 'mechanical-execution-01',
                       'dispatch_reason': 'ok',
                       'dispatch_status': 'NATIVE_OK',
                       'event_types': {'item.completed': 1,
                                       'response_item': 1,
                                       'turn.completed': 1},
                       'model': 'gpt-5.6-luna',
                       'native_role': 'verifier',
                       'reasoning_effort': 'low',
                       'status': 'accepted',
                       'usage': {'cache_write_input_tokens': 6,
                                 'cached_input_tokens': 30,
                                 'input_tokens': 150,
                                 'output_tokens': 37},
                       'verification': 'CONFIRMED',
                       'wall_seconds': 2.346,
                       'weighted_tokens': 161.5},
 'verifier_refuted': {'case_id': 'mechanical-execution-01',
                      'dispatch_reason': 'ok',
                      'dispatch_status': 'NATIVE_OK',
                      'event_types': {'item.completed': 1, 'response_item': 1, 'turn.completed': 1},
                      'reason': 'verifier_did_not_confirm',
                      'status': 'inconclusive',
                      'status_candidates': ['REFUTED', 'REFUTED'],
                      'verification': 'REFUTED',
                      'wall_seconds': 2.346}}


if __name__ == "__main__":
    unittest.main()
