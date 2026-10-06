"""Offline checks for the Claude stage adapter (claude-eval-parity AC-CE-011..017).

No test starts ``claude`` or calls a model: ``subprocess.run`` is replaced by a
stub that replays a stream sample.  The samples under
``tests/fixtures/claude_stream/`` are synthetic and have not been compared with
real output yet.  The token is a placeholder and ``HOME`` points at a temp
directory, so the real ``~/.claude`` is never touched.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import role_fitness_claude as claude  # noqa: E402
import role_fitness_fixtures as fixtures  # noqa: E402
import run_role_fitness_content as content  # noqa: E402
from role_fitness_stage import (  # noqa: E402
    StageEvidenceError,
    StageOutcome,
    StageRequest,
    StageSetupError,
    StageTimeout,
)

SAMPLES = ROOT / "tests" / "fixtures" / "claude_stream"
FAKE_TOKEN = "placeholder-subscription-token-for-offline-tests"
TOKEN_ENV = claude.SUBSCRIPTION_TOKEN_ENV


def _sample(name: str) -> str:
    return (SAMPLES / f"{name}.jsonl").read_text(encoding="utf-8")


def _events(name: str = "dispatch-ok") -> list[dict[str, Any]]:
    return [json.loads(line) for line in _sample(name).splitlines()]


def _stream(events: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(event) + "\n" for event in events)


def _tree(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*"))


def _file_texts(root: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in root.rglob("*")
        if path.is_file()
    )


class _Host:
    """Stands in for ``subprocess.run``: records the call and replays a stream."""

    def __init__(
        self,
        *,
        stdout: str | None = None,
        stderr: str = "",
        returncode: int = 0,
        error: BaseException | None = None,
        on_run: Any = None,
    ) -> None:
        self.stdout = _sample("dispatch-ok") if stdout is None else stdout
        self.stderr = stderr
        self.returncode = returncode
        self.error = error
        self.on_run = on_run
        self.calls: list[dict[str, Any]] = []

    def run(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        env = dict(kwargs["env"])
        config, cwd = Path(env["CLAUDE_CONFIG_DIR"]), Path(kwargs["cwd"])
        self.calls.append(
            {
                "argv": list(argv),
                "kwargs": {key: value for key, value in kwargs.items() if key != "env"},
                "env": env,
                "config_is_empty_dir": config.is_dir() and not any(config.iterdir()),
                "staged_agents": {
                    path.name: path.read_bytes()
                    for path in (cwd / ".claude" / "agents").iterdir()
                },
            }
        )
        # What a real session would leave behind in its private locations.
        (config / "projects").mkdir()
        (config / "projects" / "transcript.jsonl").write_text(
            self.stdout, encoding="utf-8"
        )
        (config / ".credentials.json").write_text("{}", encoding="utf-8")
        (Path(env["HOME"]) / "session-state.json").write_text("{}", encoding="utf-8")
        (Path(env["TMPDIR"]) / "scratch.tmp").write_text("x", encoding="utf-8")
        (cwd / ".claude" / "settings.local.json").write_text("{}", encoding="utf-8")
        if self.on_run is not None:
            self.on_run(argv, kwargs)
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(
            argv, self.returncode, self.stdout, self.stderr
        )


class ClaudeStageCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="claude-stage-test-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.home = self.root / "user-home"
        (self.home / ".claude").mkdir(parents=True)
        (self.home / ".claude" / ".credentials.json").write_text(
            "user login sentinel", encoding="utf-8"
        )
        self.user_config_before = self._user_config_state()
        environment = {
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            TOKEN_ENV: FAKE_TOKEN,
        }
        patcher = patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY"):
            os.environ.pop(name, None)
        self.stage_count = 0
        self.adapter = claude.ClaudeStageAdapter(
            claude_bin="claude-stub", max_budget_usd="0.50"
        )

    def _user_config_state(self) -> list[tuple[str, int, int]]:
        config = self.home / ".claude"
        return sorted(
            (
                str(path.relative_to(config)),
                path.stat().st_mtime_ns,
                path.stat().st_size,
            )
            for path in config.rglob("*")
        )

    def request(
        self,
        *,
        role: str | None = "plan-verifier",
        sandbox: str = "read-only",
        prompt: str = "stage prompt",
        name: str = "stage",
        timeout: int = 30,
    ) -> StageRequest:
        self.stage_count += 1
        scratch = self.root / f"{name}-{self.stage_count}"
        workdir = scratch / "clean-cwd"
        workdir.mkdir(parents=True)
        return StageRequest(
            prompt=prompt,
            role=role,
            sandbox=sandbox,
            workdir=workdir,
            scratch=scratch,
            timeout=timeout,
            task_name="role_fitness_plan_review",
        )

    def run_stage(
        self, host: _Host | None = None, **request: Any
    ) -> tuple[StageOutcome, _Host, StageRequest]:
        host = host or _Host()
        stage_request = self.request(**request)
        with patch.object(claude.subprocess, "run", host.run):
            outcome = self.adapter.run_stage(stage_request)
        return outcome, host, stage_request

    def run_failing(
        self, error: type[BaseException], host: _Host | None = None, **request: Any
    ) -> tuple[BaseException, _Host, StageRequest]:
        host = host or _Host()
        stage_request = self.request(**request)
        with (
            patch.object(claude.subprocess, "run", host.run),
            self.assertRaises(error) as raised,
        ):
            self.adapter.run_stage(stage_request)
        return raised.exception, host, stage_request


class DispatchEvidenceTests(ClaudeStageCase):
    """AC-CE-011, plus the fail-closed parser."""

    def test_agent_call_subagent_type_is_dispatch_evidence(self) -> None:
        outcome, _, _ = self.run_stage()
        self.assertEqual(
            (
                outcome.evidence.ok,
                outcome.evidence.status,
                outcome.evidence.reason_code,
            ),
            (True, "NATIVE_OK", "ok"),
        )
        self.assertEqual(outcome.messages, ["READY"])
        self.assertEqual(outcome.returncode, 0)

    def test_usage_cost_and_model_come_from_the_result_event(self) -> None:
        outcome, _, _ = self.run_stage()
        self.assertEqual(
            outcome.usage,
            {
                "input_tokens": 460,
                "cached_input_tokens": 300,
                "cache_write_input_tokens": 40,
                "output_tokens": 25,
            },
        )
        self.assertEqual(outcome.child_usage, outcome.usage)
        self.assertEqual(
            content._weighted_tokens(outcome.usage), 120 + 300 * 0.1 + 40 * 1.25 + 25
        )
        self.assertEqual(outcome.cost_usd, 0.0421)
        self.assertEqual(outcome.evidence.model, "synthetic-model")
        self.assertIsNone(outcome.evidence.reasoning_effort)
        self.assertEqual(
            outcome.event_counts,
            {
                "system": 1,
                "assistant": 4,
                "user": 2,
                "rate_limit_event": 1,
                "result": 1,
            },
        )

    def test_model_is_not_guessed_when_the_run_used_several(self) -> None:
        events = _events()
        events[-1]["modelUsage"]["synthetic-parent-model"] = {"costUSD": 0.01}
        outcome, _, _ = self.run_stage(_Host(stdout=_stream(events)))
        self.assertTrue(outcome.evidence.ok)
        self.assertIsNone(outcome.evidence.model)

    def test_stream_without_agent_call_is_a_dispatch_failure(self) -> None:
        outcome, _, _ = self.run_stage(_Host(stdout=_sample("no-agent-call")))
        self.assertEqual(
            (
                outcome.evidence.ok,
                outcome.evidence.status,
                outcome.evidence.reason_code,
            ),
            (False, "NATIVE_DISPATCH_FAILED", "no_agent_call"),
        )
        self.assertEqual(outcome.messages, [])
        self.assertIsNone(outcome.evidence.model)

    def _mutated(self, mutate: Any) -> StageOutcome:
        events = _events()
        mutate(events)
        return self.run_stage(_Host(stdout=_stream(events)))[0]

    def test_other_dispatch_failures(self) -> None:
        def wrong_role(events: list[dict[str, Any]]) -> None:
            events[1]["message"]["content"][1]["input"]["subagent_type"] = (
                "general-purpose"
            )

        def no_role(events: list[dict[str, Any]]) -> None:
            del events[1]["message"]["content"][1]["input"]["subagent_type"]

        def other_tool(events: list[dict[str, Any]]) -> None:
            events[1]["message"]["content"][1]["name"] = "Task"

        def second_call(events: list[dict[str, Any]]) -> None:
            events[5]["message"]["content"].append(
                {
                    "type": "tool_use",
                    "id": "toolu_second",
                    "name": "Agent",
                    "input": {"subagent_type": "plan-verifier"},
                }
            )

        def no_result(events: list[dict[str, Any]]) -> None:
            del events[4]

        def failed_result(events: list[dict[str, Any]]) -> None:
            events[4]["message"]["content"][0]["is_error"] = True

        def only_in_subagent(events: list[dict[str, Any]]) -> None:
            events[1]["parent_tool_use_id"] = "toolu_outer"
            events[4]["parent_tool_use_id"] = "toolu_outer"

        expected = {
            wrong_role: "unexpected_subagent_type",
            no_role: "unexpected_subagent_type",
            other_tool: "no_agent_call",
            second_call: "multiple_agent_calls",
            no_result: "agent_call_without_result",
            failed_result: "agent_call_failed",
            only_in_subagent: "no_agent_call",
        }
        for mutate, reason in expected.items():
            with self.subTest(mutate.__name__):
                outcome = self._mutated(mutate)
                self.assertFalse(outcome.evidence.ok)
                self.assertEqual(outcome.evidence.status, "NATIVE_DISPATCH_FAILED")
                self.assertEqual(outcome.evidence.reason_code, reason)
                self.assertEqual(outcome.messages, [])

    def test_host_reported_failure_never_reads_as_a_clean_exit(self) -> None:
        def budget_stop(events: list[dict[str, Any]]) -> None:
            events[-1].update({"subtype": "error_max_budget_usd", "is_error": True})

        outcome = self._mutated(budget_stop)
        self.assertNotEqual(outcome.returncode, 0)
        self.assertEqual(outcome.cost_usd, 0.0421)
        outcome, _, _ = self.run_stage(_Host(returncode=3), name="exit-code")
        self.assertEqual(outcome.returncode, 3)

    def test_unrecognised_shapes_fail_closed(self) -> None:
        def missing_parent_marker(events: list[dict[str, Any]]) -> None:
            del events[1]["parent_tool_use_id"]

        def result_not_last(events: list[dict[str, Any]]) -> None:
            events.append(events[0])

        def too_many_results(events: list[dict[str, Any]]) -> None:
            # A dispatching stream really holds two results (live, 2026-10-05);
            # only more than MAX_STAGE_ROUNDS is refused.
            for _ in range(claude.MAX_STAGE_ROUNDS):
                events.insert(2, events[-1])

        def no_result(events: list[dict[str, Any]]) -> None:
            del events[-1]

        def usage_missing(events: list[dict[str, Any]]) -> None:
            del events[-1]["usage"]["cache_read_input_tokens"]

        def usage_negative(events: list[dict[str, Any]]) -> None:
            events[-1]["usage"]["output_tokens"] = -1

        def cost_missing(events: list[dict[str, Any]]) -> None:
            del events[-1]["total_cost_usd"]

        def cost_not_finite(events: list[dict[str, Any]]) -> None:
            events[-1]["total_cost_usd"] = float("nan")

        def cost_boolean(events: list[dict[str, Any]]) -> None:
            events[-1]["total_cost_usd"] = True

        def model_usage_missing(events: list[dict[str, Any]]) -> None:
            del events[-1]["modelUsage"]

        def error_flag_missing(events: list[dict[str, Any]]) -> None:
            del events[-1]["is_error"]

        def tool_use_without_input(events: list[dict[str, Any]]) -> None:
            del events[1]["message"]["content"][1]["input"]

        def tool_result_shape(events: list[dict[str, Any]]) -> None:
            events[4]["message"]["content"][0]["content"] = {"text": "READY"}

        def content_not_blocks(events: list[dict[str, Any]]) -> None:
            events[1]["message"]["content"] = "READY"

        def system_without_subtype(events: list[dict[str, Any]]) -> None:
            del events[0]["subtype"]

        mutations = [
            missing_parent_marker,
            result_not_last,
            too_many_results,
            no_result,
            usage_missing,
            usage_negative,
            cost_missing,
            cost_not_finite,
            cost_boolean,
            model_usage_missing,
            error_flag_missing,
            tool_use_without_input,
            tool_result_shape,
            content_not_blocks,
            system_without_subtype,
        ]
        streams = {mutate.__name__: mutate for mutate in mutations}
        raw = {
            "unknown_event_sample": _sample("unknown-event"),
            "not_json": _sample("dispatch-ok") + "plain text line\n",
            "empty": "",
            "json_array": "[]\n",
        }
        for index, name in enumerate([*streams, *raw]):
            with self.subTest(name):
                if name in raw:
                    stdout = raw[name]
                else:
                    events = _events()
                    streams[name](events)
                    stdout = _stream(events)
                error, _, request = self.run_failing(
                    StageEvidenceError, _Host(stdout=stdout), name=f"shape-{index}"
                )
                # A short code, never stream content.
                self.assertRegex(error.detail, r"^[a-z_]+$")
                self.assertEqual(_tree(request.scratch), ["clean-cwd"])

    def test_rate_limit_event_is_a_known_informational_event(self) -> None:
        """Live shape (CLI 2.1.289): accepted, and its content is not interpreted."""
        self.assertIn("rate_limit_event", [event["type"] for event in _events()])
        without = [event for event in _events() if event["type"] != "rate_limit_event"]
        plain, _, _ = self.run_stage(_Host(stdout=_stream(without)), name="plain")
        for index, info in enumerate(
            (
                {"status": "allowed"},
                {"status": "allowed_warning", "isUsingOverage": False},
                {"status": "allowed", "rateLimitType": "seven_day", "unknown_key": 1},
            )
        ):
            events = _events()
            events[6]["rate_limit_info"] = info
            events.insert(2, dict(events[6]))
            with self.subTest(info):
                outcome, _, _ = self.run_stage(
                    _Host(stdout=_stream(events)), name=f"rate-{index}"
                )
                self.assertEqual(outcome.evidence, plain.evidence)
                self.assertEqual(outcome.messages, plain.messages)
                self.assertEqual((outcome.returncode, outcome.usage), (0, plain.usage))
                self.assertEqual(outcome.event_counts["rate_limit_event"], 2)

    def test_malformed_rate_limit_event_fails_closed(self) -> None:
        for index, info in enumerate((None, "allowed", [], 1, "absent")):
            events = _events()
            if info == "absent":
                del events[6]["rate_limit_info"]
            else:
                events[6]["rate_limit_info"] = info
            with self.subTest(repr(info)):
                # An unreadable usage report is an unknown usage state: it
                # stops the run like a reported limit, not just the stage.
                error, _, request = self.run_failing(
                    claude.StageRateLimited,
                    _Host(stdout=_stream(events)),
                    name=f"bad-rate-{index}",
                )
                self.assertEqual(error.detail, "rate_limit_status_unknown")
                self.assertEqual(_tree(request.scratch), ["clean-cwd"])

    def test_rate_limit_that_is_not_plainly_allowed_stops_the_stage(self) -> None:
        """AC-CE-032; inferred from the observed ``allowed*`` values."""
        cases = (
            ({"status": "rejected"}, "rate_limit_not_allowed"),
            ({"status": "blocked", "isUsingOverage": False}, "rate_limit_not_allowed"),
            ({"status": "Allowed"}, "rate_limit_not_allowed"),
            ({"status": "not_allowed"}, "rate_limit_not_allowed"),
            ({"status": ""}, "rate_limit_status_unknown"),
            ({"status": None}, "rate_limit_status_unknown"),
            ({"status": 1}, "rate_limit_status_unknown"),
            ({}, "rate_limit_status_unknown"),
            ({"rateLimitType": "five_hour"}, "rate_limit_status_unknown"),
            ({"status": "allowed", "isUsingOverage": True}, "rate_limit_overage"),
            ({"status": "allowed_warning", "isUsingOverage": "false"}, "rate_limit_overage"),
            ({"status": "allowed", "isUsingOverage": None}, "rate_limit_overage"),
        )
        for index, (info, detail) in enumerate(cases):
            events = _events()
            events[6]["rate_limit_info"] = info
            with self.subTest(info):
                error, _, request = self.run_failing(
                    claude.StageRateLimited,
                    _Host(stdout=_stream(events)),
                    name=f"limited-{index}",
                )
                self.assertIsInstance(error, StageEvidenceError)
                self.assertEqual(error.detail, detail)
                self.assertEqual(_tree(request.scratch), ["clean-cwd"])
        # One bad event among allowed ones is enough.
        events = _events()
        events.insert(2, {**events[6], "rate_limit_info": {"status": "rejected"}})
        error, _, _ = self.run_failing(
            claude.StageRateLimited, _Host(stdout=_stream(events)), name="limited-mix"
        )
        self.assertEqual(error.detail, "rate_limit_not_allowed")

    def test_rate_limit_stop_closes_admission_for_the_run(self) -> None:
        events = _events()
        events[6]["rate_limit_info"]["status"] = "rejected"
        admission = claude.CostAdmission(per_stage_cap_usd="0.50")
        admitted = claude.AdmittedStageAdapter(self.adapter, admission)
        limited, later = _Host(stdout=_stream(events)), _Host()
        with (
            patch.object(claude.subprocess, "run", limited.run),
            self.assertRaises(claude.StageRateLimited),
        ):
            admitted.run_stage(self.request(name="limited"))
        # The limited stage is charged its reservation; nothing else may start.
        self.assertEqual(admission.spent_usd, Decimal("0.50"))
        with (
            patch.object(claude.subprocess, "run", later.run),
            self.assertRaises(claude.StageNotAdmitted),
        ):
            admitted.run_stage(self.request(name="after-limit"))
        self.assertEqual((len(limited.calls), later.calls), (1, []))

    def test_informational_system_events_anywhere_change_nothing(self) -> None:
        """Task and thinking bookkeeping seen in live dispatch runs."""
        plain, _, _ = self.run_stage(name="plain")
        extra = [
            event
            for event in _events("dispatch-two-rounds")
            if event["type"] == "system" and event["subtype"] != "init"
        ]
        self.assertEqual(
            sorted({event["subtype"] for event in extra}),
            [
                "background_tasks_changed",
                "task_notification",
                "task_started",
                "task_updated",
                "thinking_tokens",
            ],
        )
        base = _events()
        for position in range(1, len(base)):
            events = base[:position] + extra + base[position:]
            with self.subTest(position):
                outcome, _, _ = self.run_stage(
                    _Host(stdout=_stream(events)), name=f"system-{position}"
                )
                self.assertEqual(outcome.evidence, plain.evidence)
                self.assertEqual(
                    (outcome.messages, outcome.usage, outcome.cost_usd, outcome.returncode),
                    (plain.messages, plain.usage, plain.cost_usd, 0),
                )
        # After the result only a new round may start.
        error, _, _ = self.run_failing(
            StageEvidenceError, _Host(stdout=_stream(base + extra[:1])), name="trailing"
        )
        self.assertEqual(error.detail, "no_result_event")

    def test_task_events_are_never_dispatch_evidence(self) -> None:
        events = [
            event
            for event in _events("dispatch-two-rounds")
            if not any(
                block.get("type") in ("tool_use", "tool_result")
                for block in event.get("message", {}).get("content", [])
            )
        ]
        started = [event for event in events if event.get("subtype") == "task_started"]
        self.assertEqual(started[0]["subagent_type"], "plan-verifier")
        outcome, _, _ = self.run_stage(_Host(stdout=_stream(events)))
        self.assertEqual(
            (outcome.evidence.ok, outcome.evidence.reason_code, outcome.messages),
            (False, "no_agent_call", []),
        )

    def test_two_round_stream_is_one_stage(self) -> None:
        events = _events("dispatch-two-rounds")
        self.assertEqual(
            [index for index, event in enumerate(events) if event["type"] == "result"],
            [17, 23],
        )
        outcome, _, _ = self.run_stage(_Host(stdout=_stream(events)))
        self.assertEqual(
            (outcome.evidence.ok, outcome.evidence.reason_code, outcome.messages),
            (True, "ok", ["READY"]),
        )
        # Two models were used over the stage, so none is reported.
        self.assertIsNone(outcome.evidence.model)
        self.assertEqual(outcome.returncode, 0)
        # Cost is the cumulative total of the last round, not the first (0.03).
        self.assertEqual(outcome.cost_usd, 0.0421)
        # Per-round sums: input 200, cache write 60, cache read 500, output 40;
        # the last round's per-model totals are larger and win field by field.
        self.assertEqual(
            outcome.usage,
            {
                "input_tokens": 220 + 500 + 70,
                "cached_input_tokens": 500,
                "cache_write_input_tokens": 70,
                "output_tokens": 45,
            },
        )
        self.assertEqual(outcome.child_usage, outcome.usage)
        self.assertEqual(
            (outcome.event_counts["result"], outcome.event_counts["system"]), (2, 13)
        )

    def test_usage_never_drops_a_round_or_a_subagent(self) -> None:
        events = _events("dispatch-two-rounds")
        for index in (17, 23):
            events[index]["usage"].update(
                {
                    "input_tokens": 1000,
                    "cache_creation_input_tokens": 100,
                    "cache_read_input_tokens": 10,
                    "output_tokens": 1,
                }
            )
        outcome, _, _ = self.run_stage(_Host(stdout=_stream(events)), name="sum")
        self.assertEqual(
            outcome.usage,
            {
                "input_tokens": 2000 + 500 + 200,
                "cached_input_tokens": 500,
                "cache_write_input_tokens": 200,
                "output_tokens": 45,
            },
        )
        # Without usable per-model totals the per-round sum stands alone.
        for index in (17, 23):
            del events[index]["modelUsage"]["synthetic-model"]["inputTokens"]
        outcome, _, _ = self.run_stage(_Host(stdout=_stream(events)), name="no-model")
        self.assertEqual(
            outcome.usage,
            {
                "input_tokens": 2000 + 20 + 200,
                "cached_input_tokens": 20,
                "cache_write_input_tokens": 200,
                "output_tokens": 2,
            },
        )

    def test_any_failed_round_fails_the_stage(self) -> None:
        for index in (17, 23):
            for change in ({"is_error": True}, {"subtype": "error_during_execution"}):
                events = _events("dispatch-two-rounds")
                events[index].update(change)
                with self.subTest((index, list(change))):
                    outcome, _, _ = self.run_stage(
                        _Host(stdout=_stream(events)), name=f"failed-{index}"
                    )
                    self.assertEqual(outcome.returncode, 1)
                    self.assertEqual(outcome.cost_usd, 0.0421)

    def test_round_rules_fail_closed(self) -> None:
        base = _events("dispatch-two-rounds")
        second = base[18:]

        def cheaper() -> list[dict[str, Any]]:
            events = _events("dispatch-two-rounds")
            events[17]["total_cost_usd"] = 0.05
            return events

        def bad_first_result() -> list[dict[str, Any]]:
            events = _events("dispatch-two-rounds")
            del events[17]["usage"]
            return events

        def second_agent_call() -> list[dict[str, Any]]:
            events = _events("dispatch-two-rounds")
            again = json.loads(json.dumps(events[4]))
            again["message"]["content"][0]["id"] = "toolu_synthetic_02"
            return events[:21] + [again] + events[21:]

        cases = {
            "three_rounds_ok": (base[:18] + [base[17]] + base[18:], None),
            "four_rounds": (base[:18] + [base[17]] * 2 + base[18:], "too_many_rounds"),
            "second_wake_without_notification": (
                base + second,
                "wake_result_without_task_notification",
            ),
            "ends_inside_a_round": (base[:-1], "no_result_event"),
            "bad_first_result": (bad_first_result(), "unrecognized_result_event"),
        }
        self.assertEqual(claude.MAX_STAGE_ROUNDS, 3)
        for index, (label, (events, detail)) in enumerate(cases.items()):
            with self.subTest(label):
                host = _Host(stdout=_stream(events))
                if detail is None:
                    outcome, _, _ = self.run_stage(host, name=f"rounds-{index}")
                    self.assertTrue(outcome.evidence.ok)
                    self.assertEqual(outcome.event_counts["result"], 3)
                else:
                    error, _, request = self.run_failing(
                        StageEvidenceError, host, name=f"rounds-{index}"
                    )
                    self.assertEqual(error.detail, detail)
                    self.assertEqual(_tree(request.scratch), ["clean-cwd"])
        # Position carries no meaning: a larger total in an earlier result is
        # still the stage cost.
        outcome, _, _ = self.run_stage(_Host(stdout=_stream(cheaper())), name="max")
        self.assertEqual((outcome.cost_usd, outcome.evidence.ok), (0.05, True))
        outcome, _, _ = self.run_stage(
            _Host(stdout=_stream(base[:18] + base[19:])), name="no-second-init"
        )
        self.assertTrue(outcome.evidence.ok)
        outcome, _, _ = self.run_stage(
            _Host(stdout=_stream(second_agent_call())), name="second-call"
        )
        self.assertEqual(
            (outcome.evidence.ok, outcome.evidence.reason_code),
            (False, "multiple_agent_calls"),
        )

    def _dispatch_outcome(self, events: list[dict[str, Any]], name: str) -> Any:
        outcome, _, _ = self.run_stage(_Host(stdout=_stream(events)), name=name)
        return (
            outcome.evidence,
            outcome.messages,
            outcome.usage,
            outcome.cost_usd,
            outcome.returncode,
            outcome.event_counts,
        )

    def test_both_observed_orders_give_the_same_stage(self) -> None:
        """Reports 4 and 5 (2026-10-05): same stage, different event order."""
        first = _events("dispatch-two-rounds")
        second = _events("dispatch-results-last")
        self.assertEqual(
            [index for index, event in enumerate(second) if event["type"] == "result"],
            [20, 21],
        )
        self.assertEqual((second[17]["type"], second[17]["subtype"]), ("system", "init"))
        expected = self._dispatch_outcome(first, "order-4")
        self.assertEqual((expected[0].ok, expected[1], expected[3]), (True, ["READY"], 0.0421))
        got = self._dispatch_outcome(second, "order-5")
        # Only the number of thinking_tokens events differs between the runs.
        self.assertEqual(got[:5], expected[:5])
        self.assertEqual((got[5]["result"], expected[5]["result"]), (2, 2))

    def test_event_order_does_not_matter(self) -> None:
        import random

        for sample in ("dispatch-two-rounds", "dispatch-results-last"):
            base = _events(sample)
            expected = self._dispatch_outcome(base, f"{sample}-base")
            results = [index for index, event in enumerate(base) if event["type"] == "result"]
            moved = base[: results[0]] + base[results[0] + 1 :]
            # The first result anywhere before the end, the child's message included.
            for position in range(1, len(moved)):
                events = moved[:position] + [base[results[0]]] + moved[position:]
                with self.subTest(sample=sample, position=position):
                    self.assertEqual(
                        self._dispatch_outcome(events, f"{sample}-move-{position}"),
                        expected,
                    )
            for seed in range(8):
                events = base[:-1]
                random.Random(seed).shuffle(events)
                with self.subTest(sample=sample, seed=seed):
                    self.assertEqual(
                        self._dispatch_outcome(events + base[-1:], f"{sample}-mix-{seed}"),
                        expected,
                    )
            # The last event must still be a result, whatever the order.
            error, _, _ = self.run_failing(
                StageEvidenceError,
                _Host(
                    stdout=_stream(
                        [event for event in base if event["type"] == "result"]
                        + [event for event in base if event["type"] != "result"]
                    )
                ),
                name=f"{sample}-result-first",
            )
            self.assertEqual(error.detail, "no_result_event")

    def test_negative_samples_are_still_refused(self) -> None:
        error, _, _ = self.run_failing(
            StageEvidenceError,
            _Host(stdout=_sample("dispatch-two-rounds-ends-without-result")),
            name="neg-order",
        )
        self.assertEqual(error.detail, "no_result_event")
        outcome, _, _ = self.run_stage(
            _Host(stdout=_sample("dispatch-results-last-no-child-message")), name="neg-child"
        )
        self.assertEqual(
            (outcome.evidence.ok, outcome.evidence.reason_code, outcome.messages),
            (False, "agent_call_without_child_message", []),
        )
        self.assertIsNone(outcome.evidence.model)

    def test_child_message_is_the_answer_not_the_tool_result(self) -> None:
        receipt = "LAUNCH RECEIPT " * 80
        for sample in ("dispatch-ok", "dispatch-two-rounds", "dispatch-results-last"):
            events = _events(sample)
            call = next(
                block["id"]
                for event in events
                for block in event.get("message", {}).get("content", [])
                if block.get("type") == "tool_use" and block.get("name") == "Agent"
            )
            children = [
                event
                for event in events
                if event["type"] == "assistant" and event.get("parent_tool_use_id") == call
            ]
            for event in events:
                for block in event.get("message", {}).get("content", []):
                    if block.get("tool_use_id") == call:
                        block["content"] = [{"type": "text", "text": receipt}]
            children[-1]["message"]["content"] = [
                {"type": "thinking", "thinking": "hidden", "signature": "s"},
                {"type": "text", "text": "first part"},
                {"type": "text", "text": "   "},
                {"type": "text", "text": "FINAL ANSWER"},
            ]
            with self.subTest(sample):
                outcome, _, _ = self.run_stage(
                    _Host(stdout=_stream(events)), name=f"answer-{sample}"
                )
                self.assertEqual(outcome.messages, ["first part", "FINAL ANSWER"])
                self.assertNotIn("LAUNCH RECEIPT", "".join(outcome.messages))
                self.assertTrue(outcome.evidence.ok)

    def test_missing_or_foreign_child_message_fails_closed(self) -> None:
        def drop_child_text(events: list[dict[str, Any]]) -> None:
            events[:] = [
                event
                for event in events
                if event.get("parent_tool_use_id") is None or event["type"] != "assistant"
            ]

        def blank_child_text(events: list[dict[str, Any]]) -> None:
            events[10]["message"]["content"] = [{"type": "text", "text": " \n"}]

        def other_parent(events: list[dict[str, Any]]) -> None:
            events[10]["parent_tool_use_id"] = "toolu_someone_else"

        def parent_level_text_only(events: list[dict[str, Any]]) -> None:
            events[10]["parent_tool_use_id"] = None

        def task_failed(events: list[dict[str, Any]]) -> None:
            events[13]["status"] = "failed"

        def task_never_notified(events: list[dict[str, Any]]) -> None:
            # The wake result goes too: nothing was notified.
            del events[23]["origin"]
            del events[13]

        expected = {
            drop_child_text: "agent_call_without_child_message",
            blank_child_text: "agent_call_without_child_message",
            other_parent: "agent_call_without_child_message",
            parent_level_text_only: "agent_call_without_child_message",
            task_failed: "agent_task_not_completed",
            task_never_notified: "agent_task_without_notification",
        }
        for index, (mutate, reason) in enumerate(expected.items()):
            events = _events("dispatch-two-rounds")
            self.assertEqual(events[10]["parent_tool_use_id"], "toolu_synthetic_01")
            mutate(events)
            with self.subTest(mutate.__name__):
                outcome, _, _ = self.run_stage(
                    _Host(stdout=_stream(events)), name=f"child-{index}"
                )
                self.assertEqual(
                    (outcome.evidence.ok, outcome.evidence.reason_code, outcome.messages),
                    (False, reason, []),
                )
        for index, change in enumerate(
            (
                lambda events: events[13].pop("tool_use_id"),
                lambda events: events[13].update(status=None),
                lambda events: events[6].update(tool_use_id=7),
                lambda events: events[10]["message"]["content"][0].update(text=None),
            )
        ):
            events = _events("dispatch-two-rounds")
            change(events)
            with self.subTest(index):
                error, _, _ = self.run_failing(
                    StageEvidenceError,
                    _Host(stdout=_stream(events)),
                    name=f"task-shape-{index}",
                )
                self.assertEqual(error.detail, "unrecognized_stream_event")

    def test_wake_origin_is_a_hint_not_a_requirement(self) -> None:
        """Report 4 did not record ``origin``; a stream without it still parses."""
        expected = self._dispatch_outcome(_events("dispatch-results-last"), "origin-base")
        for origin in ("absent", {}, {"kind": "something-else"}, None, "text"):
            events = _events("dispatch-results-last")
            for event in events:
                if event["type"] == "result":
                    if origin == "absent":
                        event.pop("origin", None)
                    else:
                        event["origin"] = origin
            with self.subTest(repr(origin)):
                self.assertEqual(
                    self._dispatch_outcome(events, f"origin-{origin!r:.8}".replace("'", "").replace("{", "x").replace("}", "x").replace(" ", "").replace(":", "")),
                    expected,
                )

    def test_rate_limit_event_cannot_stand_in_for_the_result(self) -> None:
        error, _, _ = self.run_failing(
            StageEvidenceError, _Host(stdout=_stream(_events()[:-1]))
        )
        self.assertEqual(error.detail, "no_result_event")

    def test_unknown_event_sample_is_otherwise_a_valid_dispatch(self) -> None:
        events = [
            event
            for event in _events("unknown-event")
            if event["type"] != "synthetic_unknown_event"
        ]
        self.assertEqual(events, _events("dispatch-ok"))


class CommandAndEnvironmentTests(ClaudeStageCase):
    """AC-CE-012."""

    def test_argv_carries_the_required_flags(self) -> None:
        _, host, request = self.run_stage()
        argv = host.calls[0]["argv"]
        self.assertEqual(argv[:2], ["claude-stub", "-p"])
        for pair in (
            ["--output-format", "stream-json"],
            ["--setting-sources", "project"],
            ["--max-budget-usd", "0.50"],
            ["--permission-mode", "manual"],
            ["--permission-prompts", "none"],
        ):
            index = argv.index(pair[0])
            self.assertEqual(argv[index : index + 2], pair)
        self.assertIn("--verbose", argv)
        self.assertIn("--strict-mcp-config", argv)
        for forbidden in (
            "--dangerously-skip-permissions",
            "--allow-dangerously-skip-permissions",
            "bypassPermissions",
            "--bare",
            "--settings",
            "--add-dir",
        ):
            self.assertNotIn(forbidden, argv)
        self.assertNotIn(request.prompt, argv)
        kwargs = host.calls[0]["kwargs"]
        self.assertEqual(kwargs["input"], request.prompt)
        self.assertEqual(kwargs["cwd"], str(request.workdir))
        self.assertEqual(
            (kwargs["timeout"], kwargs["check"], kwargs["capture_output"]),
            (30, False, True),
        )

    def test_sandbox_maps_to_a_permission_mode(self) -> None:
        _, host, _ = self.run_stage(role="mech-executor", sandbox="workspace-write")
        argv = host.calls[0]["argv"]
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "acceptEdits")
        _, host, request = self.run_failing(
            StageSetupError, sandbox="danger-full-access", name="unknown-sandbox"
        )
        self.assertEqual(host.calls, [])
        self.assertEqual(_tree(request.scratch), ["clean-cwd"])

    def test_budget_must_be_a_positive_bounded_amount(self) -> None:
        for bad in (0, -1, "31", float("inf"), float("nan"), "abc", None, True):
            with (
                self.subTest(repr(bad)),
                self.assertRaises(fixtures.BenchmarkContractError),
            ):
                claude.ClaudeStageAdapter(claude_bin="claude-stub", max_budget_usd=bad)

    def test_config_dir_is_fresh_per_stage_and_outside_the_user_config(self) -> None:
        _, first, _ = self.run_stage(name="one")
        _, second, _ = self.run_stage(name="two")
        configs = [
            Path(host.calls[0]["env"]["CLAUDE_CONFIG_DIR"]) for host in (first, second)
        ]
        self.assertNotEqual(configs[0], configs[1])
        user_config = Path(os.path.realpath(self.home / ".claude"))
        for host, config in zip((first, second), configs):
            self.assertTrue(host.calls[0]["config_is_empty_dir"])
            real = Path(os.path.realpath(config))
            self.assertNotEqual(real, user_config)
            self.assertNotIn(user_config, real.parents)
            self.assertIn(Path(os.path.realpath(self.root)), real.parents)

    def test_environment_is_an_allowlist_with_a_private_home(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "placeholder-api-key",
                "ANTHROPIC_BASE_URL": "http://localhost:1",
                "UNRELATED_SECRET": "placeholder",
            },
        ):
            _, host, _ = self.run_stage()
        env = host.calls[0]["env"]
        allowed = set(claude._PASSTHROUGH_ENV) | {
            "HOME",
            "USERPROFILE",
            "TMPDIR",
            "TEMP",
            "TMP",
            "CLAUDE_CONFIG_DIR",
            TOKEN_ENV,
        }
        self.assertLessEqual(set(env), allowed)
        self.assertEqual(env.get("PATH"), os.environ.get("PATH"))
        self.assertNotEqual(env["HOME"], str(self.home))
        self.assertEqual(env["HOME"], env["USERPROFILE"])
        self.assertEqual(
            Path(env["HOME"]).parent, Path(env["CLAUDE_CONFIG_DIR"]).parent
        )

    def test_agents_are_staged_from_the_committed_dist(self) -> None:
        _, host, _ = self.run_stage()
        committed = {
            path.name: path.read_bytes()
            for path in (ROOT / "hosts" / "claude" / "dist" / "agents").iterdir()
        }
        self.assertEqual(len(committed), 8)
        self.assertEqual(host.calls[0]["staged_agents"], committed)

    def test_stage_inside_the_user_config_is_refused(self) -> None:
        scratch = self.home / ".claude" / "stage"
        (scratch / "clean-cwd").mkdir(parents=True)
        before = self._user_config_state()
        request = StageRequest(
            prompt="p",
            role="plan-verifier",
            sandbox="read-only",
            workdir=scratch / "clean-cwd",
            scratch=scratch,
            timeout=30,
        )
        host = _Host()
        with (
            patch.object(claude.subprocess, "run", host.run),
            self.assertRaises(StageSetupError),
        ):
            self.adapter.run_stage(request)
        self.assertEqual(host.calls, [])
        self.assertEqual(self._user_config_state(), before)

    def test_stage_inside_an_inherited_config_dir_is_refused(self) -> None:
        request = self.request(name="inherited")
        host = _Host()
        with (
            patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(request.scratch)}),
            patch.object(claude.subprocess, "run", host.run),
            self.assertRaises(StageSetupError),
        ):
            self.adapter.run_stage(request)
        self.assertEqual(host.calls, [])
        self.assertEqual(_tree(request.scratch), ["clean-cwd"])

    def test_role_must_be_a_committed_agent(self) -> None:
        for index, role in enumerate(
            (None, "not-a-role", "../plan-verifier", "plan-verifier.md", "")
        ):
            with self.subTest(role):
                _, host, request = self.run_failing(
                    StageSetupError, role=role, name=f"role-{index}"
                )
                self.assertEqual(host.calls, [])
                self.assertEqual(_tree(request.scratch), ["clean-cwd"])

    def test_workdir_with_existing_project_config_is_refused(self) -> None:
        request = self.request()
        (request.workdir / ".claude").mkdir()
        host = _Host()
        with (
            patch.object(claude.subprocess, "run", host.run),
            self.assertRaises(StageSetupError),
        ):
            self.adapter.run_stage(request)
        self.assertEqual(host.calls, [])
        self.assertTrue((request.workdir / ".claude").is_dir())


class PromptTests(unittest.TestCase):
    """AC-CE-013."""

    def test_claude_prompts_do_not_use_codex_dispatch_tools(self) -> None:
        plan = "# Plan\nChange one documentation line."
        prompts = [
            claude.claude_native_review_prompt(plan),
            claude.claude_dispatch_prompt(
                role="mech-executor",
                task_name="role_fitness_mechanical_execution",
                message="Execute the fixture.",
            ),
        ]
        for prompt in prompts:
            for word in ("spawn_agent", "wait_agent", "fork_turns", "timeout_ms"):
                self.assertNotIn(word, prompt)
            self.assertIn("Agent tool exactly once", prompt)
        self.assertIn("subagent_type='plan-verifier'", prompts[0])
        self.assertIn("description='role_fitness_plan_review'", prompts[0])
        self.assertIn("subagent_type='mech-executor'", prompts[1])

    def test_review_message_is_the_one_the_codex_prompt_carries(self) -> None:
        plan = "# Plan\nChange one documentation line."
        codex = content._native_review_prompt(plan)
        message = codex.split("fork_turns='none':\n\n", 1)[1].split(
            "\n\nThen call wait_agent", 1
        )[0]
        self.assertIn(plan, message)
        self.assertIn(
            "\n\n" + message + "\n\n", claude.claude_native_review_prompt(plan)
        )


class CleanupTests(ClaudeStageCase):
    """AC-CE-014 and R6."""

    def test_stream_and_private_dirs_are_gone_when_the_stage_returns(self) -> None:
        request_holder: dict[str, Any] = {}

        def leave_artifact(argv: list[str], kwargs: dict[str, Any]) -> None:
            request_holder["during"] = _tree(Path(kwargs["cwd"]).parent)
            (Path(kwargs["cwd"]) / "result.json").write_text("{}", encoding="utf-8")

        outcome, host, request = self.run_stage(_Host(on_run=leave_artifact))
        self.assertTrue(
            any(name.endswith("transcript.jsonl") for name in request_holder["during"])
        )
        # Only what the caller owns is left: its workdir and the stage's artifact.
        self.assertEqual(
            _tree(request.scratch),
            ["clean-cwd", os.path.join("clean-cwd", "result.json")],
        )
        self.assertFalse(Path(host.calls[0]["env"]["CLAUDE_CONFIG_DIR"]).exists())
        self.assertFalse(Path(host.calls[0]["env"]["HOME"]).exists())
        self.assertNotIn("synthetic review request", _file_texts(self.root))
        self.assertEqual(outcome.events, [])
        self.assertEqual(self._user_config_state(), self.user_config_before)

    def test_private_dirs_are_deleted_when_the_stage_fails(self) -> None:
        failures = {
            StageTimeout: _Host(error=subprocess.TimeoutExpired(["claude-stub"], 30)),
            StageSetupError: _Host(error=FileNotFoundError("claude-stub")),
            StageEvidenceError: _Host(stdout=_sample("unknown-event")),
            KeyboardInterrupt: _Host(error=KeyboardInterrupt()),
        }
        for index, (error, host) in enumerate(failures.items()):
            with self.subTest(error.__name__):
                _, _, request = self.run_failing(error, host, name=f"failure-{index}")
                self.assertEqual(len(host.calls), 1)
                self.assertEqual(_tree(request.scratch), ["clean-cwd"])

    def _failing_rmtree(self, needle: str) -> Any:
        real = shutil.rmtree

        def rmtree(path: Any, *args: Any, **kwargs: Any) -> None:
            if needle in Path(path).name:
                raise PermissionError(f"cannot remove {path}")
            real(path, *args, **kwargs)

        return rmtree

    def test_failed_deletion_fails_the_stage(self) -> None:
        for index, needle in enumerate(("claude-stage-", ".claude")):
            with (
                self.subTest(needle),
                patch.object(claude.shutil, "rmtree", self._failing_rmtree(needle)),
            ):
                error, host, _ = self.run_failing(
                    claude.StageCleanupError, name=f"undeletable-{index}"
                )
                self.assertEqual(len(host.calls), 1)
                self.assertEqual(str(error), "claude stage cleanup failed")

    def test_failed_deletion_outranks_other_stage_failures(self) -> None:
        hosts = [
            _Host(error=subprocess.TimeoutExpired(["claude-stub"], 30)),
            _Host(stdout=_sample("no-agent-call")),
            _Host(stdout="not json\n"),
        ]
        for index, host in enumerate(hosts):
            with (
                self.subTest(index),
                patch.object(
                    claude.shutil, "rmtree", self._failing_rmtree("claude-stage-")
                ),
            ):
                self.run_failing(
                    claude.StageCleanupError, host, name=f"outrank-{index}"
                )

    def test_swapped_in_symlink_is_not_followed(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep", encoding="utf-8")

        def swap(argv: list[str], kwargs: dict[str, Any]) -> None:
            staged = Path(kwargs["cwd"]) / ".claude"
            shutil.rmtree(staged)
            staged.symlink_to(outside, target_is_directory=True)

        try:
            (self.root / "probe").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks are not available")
        self.run_failing(claude.StageCleanupError, _Host(on_run=swap))
        self.assertEqual((outside / "keep.txt").read_text(encoding="utf-8"), "keep")


class ManifestTests(unittest.TestCase):
    """AC-CE-015."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="claude-manifest-test-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.private_root = self.root / "private"
        self.public = fixtures.create_bundle(self.private_root)

    def test_pinned_hash_is_the_committed_manifest_v2(self) -> None:
        committed = json.loads(
            (
                ROOT
                / "docs"
                / "benchmarks"
                / "role-fitness-v1-fixtures-manifest-v2.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(claude.FROZEN_MANIFEST_V2_HASH, committed["manifest_hash"])

    def test_manifest_with_a_different_hash_is_rejected(self) -> None:
        self.assertNotEqual(
            self.public["manifest_hash"], claude.FROZEN_MANIFEST_V2_HASH
        )
        with self.assertRaisesRegex(fixtures.BenchmarkContractError, "frozen v2"):
            claude.require_frozen_manifest(self.private_root)
        with self.assertRaisesRegex(fixtures.BenchmarkContractError, "frozen v2"):
            claude.open_claude_run(
                private_root=self.private_root,
                claude_bin="claude-stub",
                per_stage_cap_usd="0.50",
            )

    def test_matching_manifest_is_accepted(self) -> None:
        with patch.object(
            claude, "FROZEN_MANIFEST_V2_HASH", self.public["manifest_hash"]
        ):
            self.assertEqual(
                claude.require_frozen_manifest(self.private_root), self.public
            )
            run = claude.open_claude_run(
                private_root=self.private_root,
                claude_bin="claude-stub",
                per_stage_cap_usd="0.50",
            )
        self.assertEqual(run.inner.max_budget_usd, run.admission.per_stage_cap_usd)

    def test_modified_fixture_is_rejected_even_when_the_manifest_hash_matches(
        self,
    ) -> None:
        fixture = self.private_root / "fixtures" / "plan-review-01.md"
        fixture.write_text(
            fixture.read_text(encoding="utf-8") + "\nextra", encoding="utf-8"
        )
        with (
            patch.object(
                claude, "FROZEN_MANIFEST_V2_HASH", self.public["manifest_hash"]
            ),
            self.assertRaises(fixtures.BenchmarkContractError),
        ):
            claude.require_frozen_manifest(self.private_root)


class TokenTests(ClaudeStageCase):
    """AC-CE-016."""

    def test_token_reaches_the_child_through_the_environment_only(self) -> None:
        seen: dict[str, Any] = {}

        def inspect(argv: list[str], kwargs: dict[str, Any]) -> None:
            seen["files"] = _file_texts(self.root)

        logs = io.StringIO()
        handler = logging.StreamHandler(logs)
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
            outcome, host, _ = self.run_stage(_Host(on_run=inspect))
        call = host.calls[0]
        self.assertEqual(call["env"][TOKEN_ENV], FAKE_TOKEN)
        self.assertEqual(
            [key for key, value in call["env"].items() if FAKE_TOKEN in value],
            [TOKEN_ENV],
        )
        self.assertFalse(any(FAKE_TOKEN in part for part in call["argv"]))
        self.assertNotIn(FAKE_TOKEN, repr(call["kwargs"]))
        self.assertNotIn(FAKE_TOKEN, seen["files"])
        self.assertNotIn(FAKE_TOKEN, _file_texts(self.root))
        self.assertNotIn(FAKE_TOKEN, logs.getvalue())
        self.assertNotIn(FAKE_TOKEN, repr(outcome))
        self.assertNotIn(FAKE_TOKEN, repr(vars(self.adapter)))

    def test_missing_token_fails_closed_before_anything_starts(self) -> None:
        for index, value in enumerate(
            (None, "", "   ", "two words", "trailing-newline\n")
        ):
            with self.subTest(repr(value)):
                with patch.dict(os.environ):
                    os.environ.pop(TOKEN_ENV, None)
                    if value is not None:
                        os.environ[TOKEN_ENV] = value
                    error, host, request = self.run_failing(
                        StageSetupError, name=f"no-token-{index}"
                    )
                self.assertEqual(host.calls, [])
                self.assertEqual(_tree(request.scratch), ["clean-cwd"])
                self.assertIn(TOKEN_ENV, str(error))
                if value and value.strip():
                    self.assertNotIn(value.strip(), str(error))
        # No fallback to a stored login: the user's config is exactly as it was.
        self.assertEqual(self._user_config_state(), self.user_config_before)

    def test_token_never_appears_in_a_raised_error(self) -> None:
        leaking_output = f"env dump {FAKE_TOKEN}"
        # A timeout whose partial output carries the token is a leak, not a
        # plain timeout; a timeout with clean output stays a timeout.
        hosts = [
            (
                StageEvidenceError,
                _Host(
                    error=subprocess.TimeoutExpired(
                        ["claude-stub"], 30, output=leaking_output, stderr=leaking_output
                    )
                ),
            ),
            (
                StageTimeout,
                _Host(error=subprocess.TimeoutExpired(["claude-stub"], 30, output="x")),
            ),
            (StageSetupError, _Host(error=OSError(f"exec failed {FAKE_TOKEN}"))),
            (StageEvidenceError, _Host(stdout=leaking_output + "\n")),
        ]
        for index, (error_type, host) in enumerate(hosts):
            with self.subTest(f"{index}-{error_type.__name__}"):
                error, _, request = self.run_failing(
                    error_type, host, name=f"leak-{index}"
                )
                rendered = (
                    "".join(
                        traceback.format_exception(
                            type(error), error, error.__traceback__
                        )
                    )
                    + repr(error)
                    + str(error)
                )
                self.assertNotIn(FAKE_TOKEN, rendered)
                self.assertIsNone(error.__cause__)
                self.assertIsNone(error.__context__)
                self.assertNotIn(FAKE_TOKEN, _file_texts(request.scratch))

    def test_stream_that_echoes_the_token_is_rejected(self) -> None:
        events = _events()
        events[4]["message"]["content"][0]["content"][0]["text"] = f"READY {FAKE_TOKEN}"
        for index, host in enumerate(
            (_Host(stdout=_stream(events)), _Host(stderr=f"warning {FAKE_TOKEN}"))
        ):
            with self.subTest(index):
                error, _, _ = self.run_failing(
                    StageEvidenceError, host, name=f"echo-{index}"
                )
                self.assertEqual(error.detail, "credential_in_stream")

    def test_prompt_carrying_the_token_is_refused(self) -> None:
        _, host, _ = self.run_failing(StageSetupError, prompt=f"use {FAKE_TOKEN}")
        self.assertEqual(host.calls, [])
        with patch.object(self.adapter, "claude_bin", f"claude-{FAKE_TOKEN}"):
            error, host, _ = self.run_failing(StageSetupError, name="token-in-argv")
        self.assertEqual(host.calls, [])
        self.assertNotIn(FAKE_TOKEN, str(error))

    def test_token_variable_is_named_in_exactly_one_place(self) -> None:
        source = (ROOT / "install" / "role_fitness_claude.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(source.count(f'"{TOKEN_ENV}"'), 1)
        self.assertIn(
            "UNVERIFIED", source.split(f'"{TOKEN_ENV}"', 1)[0].rsplit("\n\n", 1)[1]
        )


class _RecordedCosts:
    """Inner adapter that replays recorded stage costs (or failures)."""

    def __init__(self, costs: list[Any]) -> None:
        self.costs = list(costs)
        self.started = 0

    def run_stage(self, request: StageRequest) -> StageOutcome:
        self.started += 1
        cost = self.costs.pop(0)
        if isinstance(cost, BaseException):
            raise cost
        return StageOutcome(0, [], {}, {}, {}, [], 1.0, None, cost)


class CostAdmissionTests(ClaudeStageCase):
    """AC-CE-017."""

    def _run(
        self, cap: Any, costs: list[Any]
    ) -> tuple[claude.AdmittedStageAdapter, _RecordedCosts, list[str]]:
        inner = _RecordedCosts(costs)
        runner = claude.AdmittedStageAdapter(
            inner, claude.CostAdmission(per_stage_cap_usd=cap)
        )
        request = self.request()
        log: list[str] = []
        for _ in costs:
            try:
                runner.run_stage(request)
                log.append("ran")
            except claude.StageNotAdmitted as exc:
                log.append(f"refused: {exc}")
            except (
                StageTimeout,
                StageEvidenceError,
                StageSetupError,
                RuntimeError,
            ) as exc:
                log.append(type(exc).__name__)
        return runner, inner, log

    def test_stage_is_not_admitted_when_spend_plus_reservation_exceeds_the_cap(
        self,
    ) -> None:
        runner, inner, log = self._run("10", [9.5, 9.5, 9.5, 9.5])
        self.assertEqual(
            log, ["ran", "ran", "ran", "refused: cumulative cost cap reached"]
        )
        self.assertEqual(inner.started, 3)
        self.assertEqual(runner.admission.spent_usd, Decimal("28.5"))

    def test_reaching_the_cap_exactly_is_still_admitted(self) -> None:
        _, inner, log = self._run("10", [10, 10, 10, 10])
        self.assertEqual(
            log, ["ran", "ran", "ran", "refused: cumulative cost cap reached"]
        )
        self.assertEqual(inner.started, 3)
        _, inner, log = self._run("0.1", [0.1] * 301)
        self.assertEqual((log.count("ran"), inner.started), (300, 300))

    def test_unknown_cost_is_charged_the_full_reservation(self) -> None:
        costs = [
            None,
            float("nan"),
            -1.0,
            StageTimeout(),
            StageEvidenceError("no_result_event"),
            RuntimeError("boom"),
        ]
        runner, inner, log = self._run("5", costs + [0.0])
        self.assertEqual(
            log,
            [
                "ran",
                "ran",
                "ran",
                "StageTimeout",
                "StageEvidenceError",
                "RuntimeError",
                "refused: cumulative cost cap reached",
            ],
        )
        self.assertEqual(inner.started, 6)
        self.assertEqual(runner.admission.spent_usd, Decimal("30"))

    def test_setup_failure_before_the_host_starts_costs_nothing(self) -> None:
        runner, inner, log = self._run("10", [StageSetupError("no token"), 1.0])
        self.assertEqual(log, ["StageSetupError", "ran"])
        self.assertEqual(runner.admission.spent_usd, Decimal("1.0"))

    def test_cost_above_the_reservation_closes_admission(self) -> None:
        runner, inner, log = self._run("1", [1.5, 0.1])
        self.assertEqual(log, ["ran", "refused: per-stage cap was exceeded"])
        self.assertEqual(inner.started, 1)
        self.assertEqual(runner.admission.spent_usd, Decimal("1.5"))

    def test_cap_must_be_a_positive_bounded_amount(self) -> None:
        for bad in (0, -5, "30.01", float("nan"), None, False):
            with (
                self.subTest(repr(bad)),
                self.assertRaises(fixtures.BenchmarkContractError),
            ):
                claude.CostAdmission(per_stage_cap_usd=bad)
        admission = claude.CostAdmission(per_stage_cap_usd=1)
        with self.assertRaises(fixtures.BenchmarkContractError):
            admission.settle(0.1)
        admission.admit()
        with self.assertRaises(claude.StageNotAdmitted):
            admission.admit()

    def test_recorded_stream_costs_drive_the_stop_through_the_claude_adapter(
        self,
    ) -> None:
        events = _events()
        events[-1]["total_cost_usd"] = 10.25
        host = _Host(stdout=_stream(events))
        adapter = claude.ClaudeStageAdapter(
            claude_bin="claude-stub", max_budget_usd="14"
        )
        runner = claude.AdmittedStageAdapter(
            adapter, claude.CostAdmission(per_stage_cap_usd="14")
        )
        with patch.object(claude.subprocess, "run", host.run):
            runner.run_stage(self.request(name="first"))
            runner.run_stage(self.request(name="second"))
            with self.assertRaises(claude.StageNotAdmitted):
                runner.run_stage(self.request(name="third"))
            # The content runner turns the refusal into a run-level contract error.
            with self.assertRaises(fixtures.BenchmarkContractError):
                content._run_stage(
                    runner, self.request(name="fourth"), "claude stage not admitted"
                )
        self.assertEqual(len(host.calls), 2)
        self.assertEqual(runner.admission.spent_usd, Decimal("20.5"))


class AbsolutePathTests(ClaudeStageCase):
    """Review finding F1: isolation paths are never relative."""

    def _refused(self, workdir: Path, scratch: Path) -> _Host:
        host = _Host()
        request = StageRequest(prompt="p", role="plan-verifier", sandbox="read-only", workdir=workdir, scratch=scratch, timeout=30)
        with patch.object(claude.subprocess, "run", host.run), self.assertRaisesRegex(StageSetupError, "absolute"):
            self.adapter.run_stage(request)
        self.assertEqual(host.calls, [])
        return host

    def test_relative_stage_paths_are_refused_before_the_host_starts(self) -> None:
        base = self.root / "relative-base"
        (base / "work" / "scratch" / "clean-cwd").mkdir(parents=True)
        previous = os.getcwd()
        os.chdir(base)
        self.addCleanup(os.chdir, previous)
        relative = Path("work") / "scratch"
        absolute = base / "work" / "scratch"
        for workdir, scratch in ((relative / "clean-cwd", relative), (absolute / "clean-cwd", relative), (relative / "clean-cwd", absolute)):
            with self.subTest(workdir=str(workdir), scratch=str(scratch)):
                self._refused(workdir, scratch)
                self.assertEqual(_tree(base), ["work", os.path.join("work", "scratch"), os.path.join("work", "scratch", "clean-cwd")])

    def test_parent_references_in_stage_paths_are_refused(self) -> None:
        scratch = self.root / "dotdot"
        (scratch / "clean-cwd").mkdir(parents=True)
        (self.root / "other").mkdir()
        escaping = self.root / "other" / ".." / "dotdot"
        for workdir, target in ((escaping / "clean-cwd", scratch), (scratch / "clean-cwd", escaping)):
            with self.subTest(str(target)):
                self._refused(workdir, target)
                self.assertEqual(_tree(scratch), ["clean-cwd"])


class WorkdirCredentialTests(ClaudeStageCase):
    """Review finding F2 (AC-CE-016): the token must not stay in workdir files."""

    def _leak(self, relative: str, body: bytes) -> Any:
        def write(argv: list[str], kwargs: dict[str, Any]) -> None:
            target = Path(kwargs["cwd"]) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            (Path(kwargs["cwd"]) / "result.json").write_text("{}", encoding="utf-8")

        return write

    def _assert_failed_and_clean(self, detail: str, host: _Host) -> None:
        error, host, request = self.run_failing(StageEvidenceError, host)
        self.assertEqual(len(host.calls), 1)
        self.assertEqual(error.detail, detail)
        rendered = "".join(traceback.format_exception(type(error), error, error.__traceback__)) + repr(error)
        self.assertNotIn(FAKE_TOKEN, rendered)
        self.assertEqual(_tree(request.scratch), ["clean-cwd"])
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(FAKE_TOKEN.encode(), path.read_bytes())

    def test_token_in_a_workdir_text_file_fails_the_stage(self) -> None:
        self._assert_failed_and_clean("credential_in_workdir", _Host(on_run=self._leak("leak.txt", f"token={FAKE_TOKEN}\n".encode())))

    def test_token_in_a_nested_workdir_file_fails_the_stage(self) -> None:
        body = b"\x00\xff" + FAKE_TOKEN.encode() + b"\x00"
        self._assert_failed_and_clean("credential_in_workdir", _Host(on_run=self._leak(os.path.join("a", "b", "c", "leak.bin"), body)))

    def test_file_over_the_size_bound_fails_closed(self) -> None:
        body = b"x" * claude.WORKDIR_SCAN_MAX_FILE_BYTES + FAKE_TOKEN.encode()
        self._assert_failed_and_clean("workdir_scan_limit", _Host(on_run=self._leak("big.bin", body)))

    def test_tree_over_the_count_or_total_bound_fails_closed(self) -> None:
        def many(argv: list[str], kwargs: dict[str, Any]) -> None:
            for index in range(4):
                (Path(kwargs["cwd"]) / f"file-{index}.txt").write_text("clean", encoding="utf-8")

        with patch.object(claude, "WORKDIR_SCAN_MAX_FILES", 3):
            self._assert_failed_and_clean("workdir_scan_limit", _Host(on_run=many))
        with patch.object(claude, "WORKDIR_SCAN_MAX_BYTES", 12):
            self._assert_failed_and_clean("workdir_scan_limit", _Host(on_run=many))

    def test_leak_is_removed_when_the_stage_also_fails_otherwise(self) -> None:
        leak = self._leak("leak.txt", FAKE_TOKEN.encode())
        hosts = [
            _Host(on_run=leak, error=subprocess.TimeoutExpired(["claude-stub"], 30)),
            _Host(on_run=leak, stdout=_sample("unknown-event")),
            _Host(on_run=leak, stdout=_sample("no-agent-call")),
        ]
        for index, host in enumerate(hosts):
            with self.subTest(index):
                self._assert_failed_and_clean("credential_in_workdir", host)

    def test_workdir_that_cannot_be_emptied_is_a_cleanup_failure(self) -> None:
        with patch.object(claude.os, "unlink", side_effect=PermissionError("denied")):
            error, _, _ = self.run_failing(claude.StageCleanupError, _Host(on_run=self._leak("leak.txt", FAKE_TOKEN.encode())))
        self.assertNotIn(FAKE_TOKEN, str(error))

    def test_clean_artifacts_and_symlinks_are_left_alone(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text("unrelated", encoding="utf-8")

        def artifacts(argv: list[str], kwargs: dict[str, Any]) -> None:
            (Path(kwargs["cwd"]) / "sub").mkdir()
            (Path(kwargs["cwd"]) / "sub" / "result.json").write_text("{}", encoding="utf-8")
            with contextlib.suppress(OSError):
                (Path(kwargs["cwd"]) / "link").symlink_to(outside)

        outcome, _, request = self.run_stage(_Host(on_run=artifacts))
        self.assertTrue(outcome.evidence.ok)
        self.assertTrue((request.workdir / "sub" / "result.json").is_file())
        self.assertEqual(outside.read_text(encoding="utf-8"), "unrelated")


class AccountHomeTests(ClaudeStageCase):
    """Review finding F3: `HOME` cannot move the protected config away.

    These tests only compare path strings; nothing under the real home's
    `.claude` is read, listed or created.
    """

    def test_account_home_config_stays_protected_when_home_is_redirected(self) -> None:
        account = os.path.realpath(claude._account_home() / ".claude")
        if os.name != "nt":
            import pwd

            self.assertEqual(account, os.path.realpath(os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".claude")))
        redirected = os.path.realpath(self.home / ".claude")
        self.assertNotEqual(account, redirected)
        protected = claude._protected_config_dirs()
        self.assertIn(account, protected)
        self.assertIn(redirected, protected)
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.root / "custom-config")}):
            self.assertEqual(
                set(claude._protected_config_dirs()),
                {account, redirected, os.path.realpath(self.root / "custom-config")},
            )

    def test_stage_under_the_account_home_config_is_refused(self) -> None:
        # The path is never created: the refusal comes from the path alone.
        scratch = claude._account_home() / ".claude" / "role-fitness-stage-that-does-not-exist"
        request = StageRequest(prompt="p", role="plan-verifier", sandbox="read-only", workdir=scratch / "clean-cwd", scratch=scratch, timeout=30)
        host = _Host()
        with patch.object(claude.subprocess, "run", host.run), self.assertRaisesRegex(StageSetupError, "inside the user's Claude config"):
            self.adapter.run_stage(request)
        self.assertEqual(host.calls, [])

    def test_undeterminable_account_home_fails_closed(self) -> None:
        with patch.object(claude, "_account_home", side_effect=StageSetupError("user home cannot be determined")):
            _, host, request = self.run_failing(StageSetupError)
        self.assertEqual(host.calls, [])
        self.assertEqual(_tree(request.scratch), ["clean-cwd"])


if __name__ == "__main__":
    unittest.main()
