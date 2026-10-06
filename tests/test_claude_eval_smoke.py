"""Offline checks for the Claude content cases and smoke (claude-eval-parity B4).

No test starts ``claude`` or calls a model: ``subprocess.run`` is replaced by a
stub that answers from a stream sample under ``tests/fixtures/claude_stream/``.
The token is a placeholder, ``HOME`` and the temp directory point into a test
directory, and the private fixture root is a synthetic bundle, so neither the
real ``~/.claude`` nor the frozen private root is touched.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "tests"))
import claude_eval_smoke as smoke  # noqa: E402
import role_fitness_claude as claude  # noqa: E402
import role_fitness_fixtures as fixtures  # noqa: E402
import role_fitness_scorecard as scorecard  # noqa: E402
import run_role_fitness_content as content  # noqa: E402
import test_role_fitness_claude as base  # noqa: E402
import test_run_role_fitness_stage_characterization as recorded  # noqa: E402
from role_fitness_stage import StageEvidenceError, StageSetupError  # noqa: E402

SCRIPT = ROOT / "install" / "claude_eval_smoke.py"
FAKE_TOKEN = base.FAKE_TOKEN
SENTINEL = "SENTINEL-MODEL-TEXT"
PLAN_RISK, PLAN_CLEAN = "plan-review-05", "plan-review-01"
MECH, SPLIT = "mechanical-execution-01", "split-workflow-01"
AMOUNTS = [
    "--stage-budget-usd",
    "0.50",
    "--turn-reserve-usd",
    "0.75",
    "--total-budget-usd",
    "14",
]
# Strings a public report may hold: identifiers, enums, codes and amounts.
PUBLIC_STRING = re.compile(r"[A-Za-z0-9_.:#\[\]-]{0,80}")


def review_answer(case_id: str, *, findings: int = 2) -> str:
    """A machine-readable review that matches the synthetic ledger."""
    rows = [
        {
            "severity": "P1",
            "title": "Add a dual-write period",
            "evidence": f"The dual-write period is absent. {SENTINEL}",
            "revision_id": f"{case_id}-dual-write",
        },
        {
            "severity": "P1",
            "title": "Add a tested rollback artifact",
            "evidence": "The tested rollback artifact is missing.",
            "revision_id": f"{case_id}-rollback",
        },
    ][:findings]
    return json.dumps(
        {
            "decision": "REVISE" if rows else "READY",
            "findings": rows,
            "rationale": f"{SENTINEL} review rationale",
        }
    )


class StubClaude:
    """Stands in for ``subprocess.run``: one scripted child answer per call.

    The default answer makes every stage succeed.  ``overrides`` maps the
    1-based call number to changes: ``text`` (the child's answer), ``write``
    (False leaves no artifact), ``subagent`` (the role the parent dispatched
    to), ``cost``, ``rate_limit`` (status of the rate limit event), ``stdout``
    (a whole stream) or ``error`` (raised instead of returning).
    """

    def __init__(self, overrides: dict[int, dict[str, Any]] | None = None) -> None:
        self.overrides = overrides or {}
        self.calls: list[dict[str, Any]] = []

    def run(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        prompt, cwd = kwargs["input"], Path(kwargs["cwd"])
        role = re.search(r"subagent_type='([^']+)'", prompt).group(1)
        agents = cwd / ".claude" / "agents"
        self.calls.append(
            {
                "argv": list(argv),
                "env": dict(kwargs["env"]),
                "prompt": prompt,
                "role": role,
                "task": re.search(r"description='([^']+)'", prompt).group(1),
                "agents": {path.name: path.read_bytes() for path in agents.iterdir()},
            }
        )
        step = self.overrides.get(len(self.calls), {})
        if "error" in step:
            raise step["error"]
        if "stdout" in step:
            return subprocess.CompletedProcess(argv, 0, step["stdout"], "")
        if role == "plan-verifier":
            case_id = re.search(
                r"# ((?:plan-review|split-workflow)-\d\d)", prompt
            ).group(1)
            text = review_answer(case_id, findings=0 if case_id == PLAN_CLEAN else 2)
        else:
            case_id = re.search(r'"case_id": "([a-z-]+-\d\d)"', prompt).group(1)
            text = f"CONFIRMED the artifact matches. {SENTINEL}"
            if role == "mech-executor" and step.get("write", True):
                (cwd / "result.json").write_text(
                    json.dumps({"case_id": case_id, "accepted": True}), encoding="utf-8"
                )
        events = base._events("dispatch-two-rounds")
        bound = re.search(rb"^model: (\S+)$", self.calls[-1]["agents"][f"{role}.md"], re.M)
        names = step.get(
            "models", ["claude-haiku-4-5-20251001", f"claude-{bound.group(1).decode()}-5-5"]
        )
        for event in events:
            if event["type"] == "result":
                event["modelUsage"] = dict(zip(names, event["modelUsage"].values()))
            if event["type"] == "result" and "cost" in step:
                event["total_cost_usd"] = step["cost"]
            if event["type"] == "rate_limit_event" and "rate_limit" in step:
                event["rate_limit_info"]["status"] = step["rate_limit"]
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == "Agent":
                    block["input"]["subagent_type"] = step.get("subagent", role)
                elif block.get("type") == "text" and event.get("parent_tool_use_id"):
                    block["text"] = step.get("text", text)
        return subprocess.CompletedProcess(argv, 0, base._stream(events), "")


class SmokeCase(base.ClaudeStageCase):
    """A synthetic private bundle standing in for the frozen one."""

    def setUp(self) -> None:
        super().setUp()
        self.private_root = self.root / "private"
        self.public = fixtures.create_bundle(self.private_root, salt=b"s" * 32)
        self.manifest = self.root / "public-manifest.json"
        self.manifest.write_text(json.dumps(self.public), encoding="utf-8")
        self.temp = self.root / "tmp"
        self.temp.mkdir()
        for patcher in (
            patch.object(
                claude, "FROZEN_MANIFEST_V2_HASH", self.public["manifest_hash"]
            ),
            patch.object(smoke, "PUBLIC_MANIFEST", self.manifest),
            patch.object(tempfile, "tempdir", str(self.temp)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def open_run(self, **options: Any) -> claude.AdmittedStageAdapter:
        return claude.open_claude_run(
            private_root=self.private_root,
            claude_bin="claude-stub",
            per_stage_cap_usd="0.50",
            **options,
        )

    def case(self, run_case: Any, stub: StubClaude, **arguments: Any) -> dict[str, Any]:
        """Run one case function through the Claude adapter."""
        arguments.setdefault("adapter", self.open_run())
        with patch.object(claude.subprocess, "run", stub.run):
            return run_case(dispatch_prompt=claude.claude_dispatch_prompt, **arguments)

    def smoke(
        self, stub: StubClaude, *extra: str, live: bool = True
    ) -> tuple[int, dict[str, Any], str]:
        argv = [*AMOUNTS, *extra]
        if live:
            argv += [
                "--live",
                "--yes",
                "--approved-processes",
                "7",
                "--private-root",
                str(self.private_root),
                "--claude-bin",
                "claude-stub",
            ]
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(claude.subprocess, "run", stub.run),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            try:
                code = smoke.main(argv)
            except SystemExit as exit_:
                code = exit_.code
        text = out.getvalue()
        return code, (json.loads(text) if text.strip() else {}), text + err.getvalue()

    def assert_nothing_left_on_disk(self) -> None:
        self.assertEqual(list(self.temp.iterdir()), [], "stage data was left behind")


class ClaudeCaseTests(SmokeCase):
    """Each case function yields the Codex stage shape through the Claude adapter."""

    def assert_codex_fields(self, stage: dict[str, Any], pinned: str) -> None:
        self.assertEqual(stage["attempt"], 1)
        self.assertNotIn("rerun_of", stage)
        self.assertEqual(set(stage) - {"attempt"}, set(recorded.EXPECTED[pinned]))

    # -- plan review ----------------------------------------------------
    def test_review_accepted_has_the_codex_fields_and_scores(self) -> None:
        stub = StubClaude()
        stage = self.case(
            content.run_native_review_case,
            stub,
            private_root=self.private_root,
            case_id=PLAN_RISK,
        )
        self.assert_codex_fields(stage, "native_review_accepted")
        self.assertEqual(
            (stage["status"], stage["native_role"]), ("accepted", "plan-verifier")
        )
        self.assertEqual(
            (stage["dispatch_status"], stage["dispatch_reason"]), ("NATIVE_OK", "ok")
        )
        self.assertEqual((stage["risk_coverage"], stage["quality_score"]), (1.0, 100.0))
        self.assertGreater(stage["weighted_tokens"], 0)
        self.assertIsNone(scorecard.classify_content_failure(stage))
        call = stub.calls[0]
        self.assertEqual(
            (call["role"], call["task"]), ("plan-verifier", "role_fitness_plan_review")
        )
        self.assertNotIn("spawn_agent", call["prompt"])
        self.assertNotIn("wait_agent", call["prompt"])
        self.assertIn("--permission-mode", call["argv"])
        self.assertEqual(
            call["argv"][call["argv"].index("--permission-mode") + 1], "manual"
        )
        self.assert_nothing_left_on_disk()

    def test_review_that_misses_a_risk_is_classified(self) -> None:
        partial = StubClaude({1: {"text": review_answer(PLAN_RISK, findings=1)}})
        stage = self.case(
            content.run_native_review_case,
            partial,
            private_root=self.private_root,
            case_id=PLAN_RISK,
        )
        self.assertEqual((stage["status"], stage["risk_coverage"]), ("accepted", 0.5))
        self.assertEqual(scorecard.classify_content_failure(stage), "missed_risk")
        escalated = StubClaude({1: {"text": review_answer(PLAN_CLEAN, findings=1)}})
        stage = self.case(
            content.run_native_review_case,
            escalated,
            private_root=self.private_root,
            case_id=PLAN_CLEAN,
        )
        self.assertEqual(scorecard.classify_content_failure(stage), "false_escalation")

    def test_unparseable_review_is_inconclusive_with_the_codex_fields(self) -> None:
        stub = StubClaude({1: {"text": f"I could not decide. {SENTINEL}"}})
        stage = self.case(
            content.run_native_review_case,
            stub,
            private_root=self.private_root,
            case_id=PLAN_RISK,
        )
        self.assert_codex_fields(stage, "native_review_invalid")
        self.assertEqual(stage["reason"], "invalid_native_review_output")
        self.assertEqual(stage["event_shapes"], [])
        self.assertEqual(
            scorecard.classify_content_failure(stage), "unparseable_output"
        )

    def test_review_dispatch_failure_is_not_a_content_class(self) -> None:
        for name, step in (
            ("other role", {"subagent": "scout"}),
            ("no agent call", {"stdout": base._sample("no-agent-call")}),
        ):
            with self.subTest(name):
                stage = self.case(
                    content.run_native_review_case,
                    StubClaude({1: step}),
                    private_root=self.private_root,
                    case_id=PLAN_RISK,
                )
                self.assertEqual(stage["status"], "inconclusive")
                self.assertEqual(stage["dispatch_status"], claude.DISPATCH_FAILED)
                self.assertEqual(stage["message_count"], 0)
                self.assertEqual(
                    scorecard.classify_content_failure(stage), "unclassified"
                )

    # -- mechanical executor --------------------------------------------
    def test_mechanical_accepted_and_missing_artifact(self) -> None:
        stub = StubClaude()
        stage = self.case(
            content.run_native_mechanical_case,
            stub,
            private_root=self.private_root,
            case_id=MECH,
        )
        self.assert_codex_fields(stage, "mechanical_accepted")
        self.assertEqual((stage["status"], stage["accepted"]), ("accepted", True))
        self.assertEqual(stub.calls[0]["role"], "mech-executor")
        self.assertEqual(
            stub.calls[0]["argv"][stub.calls[0]["argv"].index("--permission-mode") + 1],
            "acceptEdits",
        )
        missing = self.case(
            content.run_native_mechanical_case,
            StubClaude({1: {"write": False}}),
            private_root=self.private_root,
            case_id=MECH,
        )
        self.assert_codex_fields(missing, "mechanical_invalid")
        self.assertEqual(missing["reason"], "invalid_native_mechanical_acceptance")
        self.assertEqual(
            scorecard.classify_content_failure(missing), "executor_no_artifact"
        )
        self.assert_nothing_left_on_disk()

    def test_mechanical_dispatch_failure(self) -> None:
        stage = self.case(
            content.run_native_mechanical_case,
            StubClaude({1: {"subagent": "executor"}}),
            private_root=self.private_root,
            case_id=MECH,
        )
        self.assertEqual(
            (stage["status"], stage["dispatch_status"]),
            ("inconclusive", claude.DISPATCH_FAILED),
        )
        self.assertEqual(stage["dispatch_reason"], "unexpected_subagent_type")
        self.assertEqual(scorecard.classify_content_failure(stage), "unclassified")

    # -- verifier -------------------------------------------------------
    def test_verifier_confirmed_refuted_and_dispatch_failure(self) -> None:
        stage = self.case(
            content.run_native_verifier_case,
            StubClaude(),
            private_root=self.private_root,
            case_id=MECH,
        )
        self.assert_codex_fields(stage, "verifier_accepted")
        self.assertEqual(
            (stage["status"], stage["verification"]), ("accepted", "CONFIRMED")
        )
        refuted = self.case(
            content.run_native_verifier_case,
            StubClaude({1: {"text": "REFUTED the value differs"}}),
            private_root=self.private_root,
            case_id=MECH,
        )
        self.assert_codex_fields(refuted, "verifier_refuted")
        self.assertEqual(refuted["reason"], "verifier_did_not_confirm")
        self.assertEqual(
            scorecard.classify_content_failure(refuted), "verifier_inconclusive"
        )
        failed = self.case(
            content.run_native_verifier_case,
            StubClaude({1: {"subagent": "scout"}}),
            private_root=self.private_root,
            case_id=MECH,
        )
        self.assertEqual(failed["dispatch_status"], claude.DISPATCH_FAILED)
        self.assertEqual(failed["verification"], "INCONCLUSIVE")

    def test_operator_rerun_fields_pass_through(self) -> None:
        stage = self.case(
            content.run_native_verifier_case,
            StubClaude(),
            private_root=self.private_root,
            case_id=MECH,
            attempt=2,
            rerun_of=f"{MECH}#1",
        )
        self.assertEqual((stage["attempt"], stage["rerun_of"]), (2, f"{MECH}#1"))
        self.assertEqual(scorecard.classify_content_failure(stage), "verifier_retry")

    # -- split executor -------------------------------------------------
    def test_split_executor_accepted_missing_artifact_and_dispatch_failure(
        self,
    ) -> None:
        handoff = {"scenario_id": SPLIT, "revision_ids": [f"{SPLIT}-dual-write"]}
        stub = StubClaude()
        stage = self.case(
            content.run_native_split_executor_case, stub, case_id=SPLIT, handoff=handoff
        )
        self.assert_codex_fields(stage, "split_accepted")
        self.assertEqual(stub.calls[0]["task"], "role_fitness_split_execution")
        missing = self.case(
            content.run_native_split_executor_case,
            StubClaude({1: {"write": False}}),
            case_id=SPLIT,
            handoff=handoff,
        )
        self.assert_codex_fields(missing, "split_invalid")
        self.assertEqual(
            scorecard.classify_content_failure(missing), "executor_no_artifact"
        )
        failed = self.case(
            content.run_native_split_executor_case,
            StubClaude({1: {"subagent": "scout"}}),
            case_id=SPLIT,
            handoff=handoff,
        )
        self.assertEqual(failed["dispatch_status"], claude.DISPATCH_FAILED)
        self.assertEqual(scorecard.classify_content_failure(failed), "unclassified")

    # -- host selection -------------------------------------------------
    def test_a_stage_is_never_half_one_host_and_half_another(self) -> None:
        run = self.open_run()
        bad = [
            {"adapter": run, "dispatch_prompt": None},
            {"adapter": None, "dispatch_prompt": claude.claude_dispatch_prompt},
            {
                "adapter": run,
                "dispatch_prompt": claude.claude_dispatch_prompt,
                "codex_bin": "codex",
            },
            {
                "adapter": run,
                "dispatch_prompt": claude.claude_dispatch_prompt,
                "active_home": self.root,
            },
            {"adapter": None, "dispatch_prompt": None},
            {"adapter": None, "dispatch_prompt": None, "codex_bin": "codex"},
        ]
        stub = StubClaude()
        for arguments in bad:
            with (
                self.subTest(sorted(arguments)),
                patch.object(claude.subprocess, "run", stub.run),
                self.assertRaises(content.BenchmarkContractError),
            ):
                content.run_native_verifier_case(
                    private_root=self.private_root, case_id=MECH, **arguments
                )
        self.assertEqual(stub.calls, [])

    def test_missing_token_fails_closed_without_cost(self) -> None:
        run = self.open_run()
        stub = StubClaude()
        with patch.dict(os.environ):
            del os.environ[claude.SUBSCRIPTION_TOKEN_ENV]
            with self.assertRaises(content.BenchmarkContractError):
                self.case(
                    content.run_native_review_case,
                    stub,
                    private_root=self.private_root,
                    case_id=PLAN_RISK,
                    adapter=run,
                )
        self.assertEqual(stub.calls, [])
        self.assertEqual(run.admission.spent_usd, Decimal("0"))
        self.assert_nothing_left_on_disk()


class RunSettingsTests(SmokeCase):
    """Reservation, run cap and arm bindings of one Claude run."""

    def test_reservation_is_separate_from_the_budget_flag(self) -> None:
        run = self.open_run(reserve_usd="2.00", run_cap_usd="14", model="haiku")
        self.assertEqual(run.inner.max_budget_usd, Decimal("0.50"))
        self.assertEqual(run.admission.per_stage_cap_usd, Decimal("2.00"))
        self.assertEqual(run.admission.run_cap_usd, Decimal("14"))
        stub = StubClaude({1: {"cost": 1.9}})
        self.case(
            content.run_native_verifier_case,
            stub,
            private_root=self.private_root,
            case_id=MECH,
            adapter=run,
        )
        argv = stub.calls[0]["argv"]
        # The flag keeps the budget; the larger reservation never reaches argv.
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "0.50")
        self.assertEqual(argv[argv.index("--model") + 1], "haiku")
        self.assertNotIn("2.00", argv)
        self.assertIsNone(run.admission.closed_reason)
        self.assertEqual(run.admission.spent_usd, Decimal("1.9"))

    def test_reservation_below_the_flag_or_a_cap_above_the_run_cap_is_refused(
        self,
    ) -> None:
        for options in (
            {"reserve_usd": "0.49"},
            {"run_cap_usd": "30.01"},
            {"reserve_usd": "31"},
        ):
            with (
                self.subTest(options),
                self.assertRaises(fixtures.BenchmarkContractError),
            ):
                self.open_run(**options)

    def test_run_cap_stops_admission_below_the_fixed_cap(self) -> None:
        run = self.open_run(reserve_usd="2.00", run_cap_usd="3")
        stub = StubClaude({1: {"cost": 1.5}})
        self.case(
            content.run_native_verifier_case,
            stub,
            private_root=self.private_root,
            case_id=MECH,
            adapter=run,
        )
        with self.assertRaisesRegex(
            content.BenchmarkContractError, "cumulative cost cap reached"
        ):
            self.case(
                content.run_native_verifier_case,
                stub,
                private_root=self.private_root,
                case_id=MECH,
                adapter=run,
            )
        self.assertEqual(len(stub.calls), 1)

    def test_arm_binding_changes_only_the_model_line_of_the_staged_copy(self) -> None:
        run = self.open_run()
        arm = claude.AdmittedStageAdapter(
            run.inner.with_role_models({"plan-verifier": "opus"}), run.admission
        )
        stub = StubClaude()
        self.case(
            content.run_native_review_case,
            stub,
            private_root=self.private_root,
            case_id=PLAN_RISK,
            adapter=arm,
        )
        self.case(
            content.run_native_review_case,
            stub,
            private_root=self.private_root,
            case_id=PLAN_RISK,
            adapter=run,
        )
        committed = {
            path.name: path.read_bytes() for path in claude.DIST_AGENTS.iterdir()
        }
        self.assertEqual(stub.calls[1]["agents"], committed)
        staged = stub.calls[0]["agents"]
        self.assertEqual(set(staged), set(committed))
        for name, data in staged.items():
            if name != "plan-verifier.md":
                self.assertEqual(data, committed[name], name)
        before = committed["plan-verifier.md"].decode("utf-8").split("\n")
        after = staged["plan-verifier.md"].decode("utf-8").split("\n")
        changed = [
            (old, new) for old, new in zip(before, after, strict=True) if old != new
        ]
        self.assertEqual(
            changed, [(f"model: {smoke._bound_model('plan-verifier')}", "model: opus")]
        )
        # Both arms draw on the same admission.
        self.assertIs(arm.admission, run.admission)
        self.assertGreater(run.admission.spent_usd, Decimal("0.08"))

    def test_arm_binding_is_validated(self) -> None:
        run = self.open_run()
        for models in (
            {"no-such-role": "opus"},
            {"plan-verifier": "opus --flag"},
            {"plan-verifier": 3},
            ["plan-verifier"],
        ):
            with (
                self.subTest(models=models),
                self.assertRaises(fixtures.BenchmarkContractError),
            ):
                run.inner.with_role_models(models)
        for text in (
            "no frontmatter\n",
            "---\nname: x\n---\nbody\n",
            "---\nmodel: a\nmodel: b\n---\nbody\n",
        ):
            with self.subTest(text=text), self.assertRaises(StageSetupError):
                claude._with_model(text, "opus")
        self.assertEqual(
            claude._with_model(
                "---\nname: x\nmodel: a\n---\nmodel: body line\n", "opus"
            ),
            "---\nname: x\nmodel: opus\n---\nmodel: body line\n",
        )


class DryRunTests(SmokeCase):
    def test_dry_run_starts_nothing_and_needs_no_token_or_private_root(self) -> None:
        refuse = AssertionError("a dry run must not start a process")
        with (
            patch.dict(os.environ),
            patch.object(subprocess, "run", side_effect=refuse),
            patch.object(subprocess, "Popen", side_effect=refuse),
            patch.object(claude, "open_claude_run", side_effect=refuse),
        ):
            del os.environ[claude.SUBSCRIPTION_TOKEN_ENV]
            code, report, _ = self.smoke(StubClaude(), "--dry-run", live=False)
        self.assertEqual(code, 0)
        plan = report["plan"]
        self.assertEqual((report["mode"], report["schema"]), ("dry-run", smoke.SCHEMA))
        self.assertEqual(plan["processes"], {"planned": 7, "hard_cap": 7})
        # stage budget + 2 agents x one turn each.
        self.assertEqual(plan["stage_reserve_usd"], "2.00")
        self.assertEqual(
            (plan["worst_case_usd"], plan["total_budget_usd"]), ("14.00", "14")
        )
        self.assertEqual({stage["reserved_usd"] for stage in plan["stages"]}, {"2.00"})
        self.assertEqual(
            [(stage["arm"], stage["stage"], stage["role"]) for stage in plan["stages"]],
            [
                ("plan_frontier", "review", "plan-verifier"),
                ("plan_strong", "review", "plan-verifier"),
                ("mechanical_current", "executor", "mech-executor"),
                ("mechanical_current", "verifier", "verifier"),
                ("split_current", "review", "plan-verifier"),
                ("split_current", "executor", "mech-executor"),
                ("split_current", "verifier", "verifier"),
            ],
        )
        frontier, strong = plan["stages"][0], plan["stages"][1]
        self.assertEqual(frontier["child_model"], smoke._bound_model("plan-verifier"))
        self.assertEqual(strong["child_model"], smoke._tier_model("strong"))
        self.assertNotEqual(frontier["child_model"], strong["child_model"])
        self.assertEqual(frontier["case_id"], strong["case_id"])
        self.assertEqual(frontier["case_id"], PLAN_RISK)

    def test_public_manifest_with_another_hash_is_refused(self) -> None:
        with patch.object(
            smoke,
            "PUBLIC_MANIFEST",
            ROOT / "docs" / "benchmarks" / "role-fitness-v1-fixtures-manifest-v2.json",
        ):
            # The synthetic bundle's hash is not the committed one.
            code, _, text = self.smoke(StubClaude(), "--dry-run", live=False)
            self.assertEqual(code, 2)
            self.assertIn("public manifest", text)

    def test_entry_point_runs_as_a_script_without_a_token(self) -> None:
        first = SCRIPT.read_text(encoding="utf-8").split("\n", 1)[0]
        self.assertEqual(first, "#!/usr/bin/env python3")
        if os.name != "nt":
            self.assertTrue(os.access(SCRIPT, os.X_OK))
        environment = {
            key: value
            for key, value in os.environ.items()
            if key != claude.SUBSCRIPTION_TOKEN_ENV
        }
        for arguments in (["--help"], ["--dry-run", *AMOUNTS]):
            done = subprocess.run(
                [sys.executable, str(SCRIPT), *arguments],
                capture_output=True,
                text=True,
                env=environment,
                timeout=60,
                check=False,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["plan"]["processes"]["planned"], 7)

    def test_amounts_have_no_defaults_and_must_cover_every_reservation(self) -> None:
        stub = StubClaude()
        self.assertEqual(self.smoke(stub, "--dry-run", live=False)[0], 0)
        out, err = io.StringIO(), io.StringIO()
        for argv in (
            ["--dry-run"],
            ["--dry-run", "--stage-budget-usd", "0.50", "--turn-reserve-usd", "0.75"],
            [
                "--dry-run",
                "--stage-budget-usd",
                "0.50",
                "--turn-reserve-usd",
                "0.75",
                "--total-budget-usd",
                "13.99",
            ],
            [
                "--dry-run",
                "--stage-budget-usd",
                "0.50",
                "--turn-reserve-usd",
                "0.75",
                "--total-budget-usd",
                "31",
            ],
            [
                "--dry-run",
                "--stage-budget-usd",
                "1e1",
                "--turn-reserve-usd",
                "0.75",
                "--total-budget-usd",
                "14",
            ],
            [
                "--dry-run",
                "--stage-budget-usd",
                "20",
                "--turn-reserve-usd",
                "10",
                "--total-budget-usd",
                "30",
            ],
            ["--dry-run", *AMOUNTS, "--plan-case", MECH],
            ["--dry-run", *AMOUNTS, "--timeout", "5"],
            ["--dry-run", *AMOUNTS, "--parent-model", "haiku --dangerously"],
            ["--dry-run", "--live", *AMOUNTS],
        ):
            with (
                self.subTest(argv=argv),
                contextlib.redirect_stdout(out),
                contextlib.redirect_stderr(err),
                self.assertRaises(SystemExit) as stopped,
            ):
                smoke.main(argv)
            self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(stub.calls, [])


class SmokeRunTests(SmokeCase):
    def assert_public(self, report: dict[str, Any], text: str) -> None:
        """Scores, enums, counts, numbers and codes only."""

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    self.assertRegex(key, r"\A[A-Za-z0-9_.-]{1,40}\Z")
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
            elif isinstance(node, str):
                self.assertIsNotNone(PUBLIC_STRING.fullmatch(node), node)
            else:
                self.assertIsInstance(node, (int, float, type(None)))

        walk(report)
        for forbidden in (
            SENTINEL,
            FAKE_TOKEN,
            FAKE_TOKEN[:8],
            str(self.root),
            os.path.realpath(self.root),
            str(self.home),
            "dual-write",
            "Migrate a production",
            "Call the Agent tool",
            "outcome_verification",
            "rationale",
            '"review_output"',
        ):
            self.assertNotIn(forbidden, text)

    def test_full_smoke_runs_seven_processes_and_reports_numbers_only(self) -> None:
        stub = StubClaude()
        code, report, text = self.smoke(stub)
        self.assertEqual(code, 0, text)
        self.assertEqual((report["status"], report["stopped"]), ("completed", None))
        self.assertEqual(len(stub.calls), 7)
        self.assertEqual(report["processes"], {"started": 7, "cap": 7})
        self.assertEqual(
            [call["role"] for call in stub.calls],
            [
                "plan-verifier",
                "plan-verifier",
                "mech-executor",
                "verifier",
                "plan-verifier",
                "mech-executor",
                "verifier",
            ],
        )
        self.assertEqual(
            [call["task"] for call in stub.calls][-3:],
            [
                "role_fitness_plan_review",
                "role_fitness_split_execution",
                "role_fitness_mechanical_verification",
            ],
        )
        stages = report["stages"]
        self.assertEqual([stage["status"] for stage in stages], ["accepted"] * 7)
        self.assertEqual(
            [stage["content_failure_class"] for stage in stages], [None] * 7
        )
        self.assertEqual({stage["dispatch_status"] for stage in stages}, {"NATIVE_OK"})
        self.assertEqual({stage["attempt"] for stage in stages}, {1})
        for stage in stages:
            self.assertEqual(stage["cost_usd"], 0.0421)
            self.assertGreater(stage["weighted_tokens"], 0)
            self.assertEqual(set(stage["usage"]), set(smoke._USAGE_KEYS))
            self.assertIsInstance(stage["wall_seconds"], float)
            self.assertTrue(stage["models_observed"])
        self.assertEqual(
            (stages[0]["quality_score"], stages[0]["risk_coverage"]), (100.0, 1.0)
        )
        self.assertEqual(stages[3]["verification"], "CONFIRMED")
        self.assertIs(stages[5]["artifact_accepted"], True)
        self.assertEqual(
            report["cost"], {"reported_usd": "0.2947", "charged_usd": "0.2947"}
        )
        self.assertEqual(report["failure_taxonomy"], {})
        self.assertEqual(
            set(report["content_failure_counts"]),
            {"plan_frontier", "plan_strong", "mechanical_current", "split_current"},
        )
        self.assertEqual(
            report["arm_summary"]["plan_strong"]["R1"],
            {"stages": 1, "passed": 1, "mean_quality_score": 100.0},
        )
        # Only the strong arm rebinds the plan-verifier; the budget flag is the same everywhere.
        models = [
            re.search(rb"^model: (\S+)$", call["agents"]["plan-verifier.md"], re.M)
            .group(1)
            .decode()
            for call in stub.calls
        ]
        frontier = smoke._bound_model("plan-verifier")
        self.assertEqual(
            models, [frontier, smoke._tier_model("strong"), *[frontier] * 5]
        )
        for call in stub.calls:
            argv = call["argv"]
            self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "0.50")
            self.assertEqual(argv[argv.index("--model") + 1], "haiku")
            self.assertEqual(call["env"][claude.SUBSCRIPTION_TOKEN_ENV], FAKE_TOKEN)
            self.assertFalse(any(FAKE_TOKEN in part for part in argv))
        self.assert_public(report, text)
        self.assert_nothing_left_on_disk()
        self.assertEqual(self._user_config_state(), self.user_config_before)

    def test_failed_scoring_is_classified_and_later_stages_of_the_arm_do_not_run(
        self,
    ) -> None:
        stub = StubClaude(
            {
                1: {"text": review_answer(PLAN_RISK, findings=1)},
                2: {"text": f"no verdict here {SENTINEL}"},
                3: {"write": False},
                4: {"text": review_answer(SPLIT, findings=0)},
            }
        )
        code, report, text = self.smoke(stub)
        self.assertEqual(code, 0, text)
        self.assertEqual(len(stub.calls), 4)
        rows = {(stage["arm"], stage["stage"]): stage for stage in report["stages"]}
        self.assertEqual(
            rows["plan_frontier", "review"]["content_failure_class"], "missed_risk"
        )
        self.assertEqual(rows["plan_frontier", "review"]["risk_coverage"], 0.5)
        self.assertEqual(
            rows["plan_strong", "review"]["content_failure_class"], "unparseable_output"
        )
        self.assertEqual(
            rows["mechanical_current", "executor"]["content_failure_class"],
            "executor_no_artifact",
        )
        self.assertEqual(
            (
                rows["mechanical_current", "verifier"]["status"],
                rows["mechanical_current", "verifier"]["reason"],
            ),
            ("not_run", "executor_not_accepted"),
        )
        # A READY verdict on a risk case is accepted output that cannot be handed off.
        self.assertEqual(
            rows["split_current", "review"]["content_failure_class"], "missed_risk"
        )
        for stage in ("executor", "verifier"):
            self.assertEqual(
                (
                    rows["split_current", stage]["status"],
                    rows["split_current", stage]["reason"],
                ),
                ("not_run", "split_handoff_unavailable"),
            )
        self.assertEqual(
            report["failure_taxonomy"],
            {
                "content.missed_risk": 2,
                "content.unparseable_output": 1,
                "content.executor_no_artifact": 1,
            },
        )
        self.assertEqual(
            report["content_failure_counts"]["plan_frontier"]["R1"]["missed_risk"], 1
        )
        self.assertEqual(
            report["content_failure_counts"]["split_current"]["pooled"]["missed_risk"],
            1,
        )
        self.assert_public(report, text)

    def test_dispatch_failure_is_reported_and_the_run_goes_on(self) -> None:
        stub = StubClaude(
            {1: {"subagent": "scout"}, 6: {"stdout": base._sample("no-agent-call")}}
        )
        code, report, text = self.smoke(stub)
        self.assertEqual(code, 0, text)
        first = report["stages"][0]
        self.assertEqual(
            (first["status"], first["dispatch_status"]),
            ("inconclusive", claude.DISPATCH_FAILED),
        )
        self.assertEqual(first["dispatch_reason"], "unexpected_subagent_type")
        self.assertEqual(first["content_failure_class"], "unclassified")
        self.assertEqual(report["stages"][5]["dispatch_reason"], "no_agent_call")
        self.assertEqual(report["stages"][6]["status"], "not_run")
        self.assertEqual(len(stub.calls), 6)
        self.assertEqual(report["failure_taxonomy"], {"content.unclassified": 2})
        self.assert_public(report, text)

    def test_usage_limit_stops_every_later_stage(self) -> None:
        for name, step, host_code in (
            ("rejected", {"rate_limit": "rejected"}, "rate_limit_not_allowed"),
            ("split executor", {"rate_limit": "rejected"}, "rate_limit_not_allowed"),
        ):
            at = 2 if name == "rejected" else 6
            with self.subTest(name):
                stub = StubClaude({at: step})
                code, report, text = self.smoke(stub)
                self.assertEqual(code, 1, text)
                self.assertEqual(
                    (report["status"], report["stopped"]),
                    ("stopped", "usage_limit_reported"),
                )
                self.assertEqual(len(stub.calls), at)
                stopped = report["stages"][at - 1]
                self.assertEqual(
                    (stopped["status"], stopped["host_code"]),
                    ("inconclusive", host_code),
                )
                self.assertEqual(stopped["content_failure_class"], "unclassified")
                # The stage's cost is unknown, so its whole reservation is charged.
                self.assertEqual(Decimal(stopped["charged_usd"]), Decimal("2"))
                self.assertEqual(
                    [
                        (stage["status"], stage["reason"])
                        for stage in report["stages"][at:]
                    ],
                    [("not_run", "usage_limit_reported")] * (7 - at),
                )
                # Finished stages are kept.
                self.assertEqual(
                    [stage["status"] for stage in report["stages"][: at - 1]],
                    ["accepted"] * (at - 1),
                )
                self.assert_public(report, text)

    def test_cost_above_the_reservation_stops_the_run(self) -> None:
        stub = StubClaude({3: {"cost": 2.01}})
        code, report, text = self.smoke(stub)
        self.assertEqual(code, 1, text)
        self.assertEqual(report["stopped"], "stage_cost_exceeded_reservation")
        self.assertEqual(len(stub.calls), 3)
        self.assertEqual(
            (report["stages"][2]["status"], report["stages"][2]["cost_usd"]),
            ("accepted", 2.01),
        )
        self.assertEqual(Decimal(report["stages"][2]["charged_usd"]), Decimal("2.01"))
        self.assertEqual(
            [(stage["status"], stage["reason"]) for stage in report["stages"][3:]],
            [("not_run", "stage_cost_exceeded_reservation")] * 4,
        )
        # A cost at the reservation is still within it.
        stub = StubClaude({3: {"cost": 2.0}})
        self.assertEqual(self.smoke(stub)[0], 0)
        self.assertEqual(len(stub.calls), 7)

    def test_missing_token_fails_closed_before_anything_starts(self) -> None:
        stub = StubClaude()
        with patch.dict(os.environ):
            del os.environ[claude.SUBSCRIPTION_TOKEN_ENV]
            code, report, text = self.smoke(stub)
        self.assertEqual((code, report), (2, {}))
        self.assertIn("refusing to start", text)
        self.assertEqual(stub.calls, [])
        self.assert_nothing_left_on_disk()

    def test_token_lost_mid_run_stops_without_starting_a_process(self) -> None:
        def drop_token(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            done = stub.run(argv, **kwargs)
            os.environ.pop(claude.SUBSCRIPTION_TOKEN_ENV, None)
            return done

        stub = StubClaude()
        out = io.StringIO()
        with (
            patch.dict(os.environ),
            patch.object(claude.subprocess, "run", drop_token),
            patch.object(smoke.probe, "_forbidden", return_value=[]),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = smoke.main(
                [
                    *AMOUNTS,
                    "--live",
                    "--yes",
                    "--approved-processes",
                    "7",
                    "--private-root",
                    str(self.private_root),
                    "--claude-bin",
                    "claude-stub",
                ]
            )
        report = json.loads(out.getvalue())
        self.assertEqual((code, report["stopped"]), (1, "setup_failed"))
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(report["processes"]["started"], 1)
        second = report["stages"][1]
        self.assertEqual(
            (second["status"], second["started"], second["charged_usd"]),
            ("error", False, "0"),
        )
        self.assertEqual(
            [stage["status"] for stage in report["stages"][2:]], ["not_run"] * 5
        )

    def test_report_without_a_token_to_check_against_is_withheld(self) -> None:
        def drop_token(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            os.environ.pop(claude.SUBSCRIPTION_TOKEN_ENV, None)
            return stub.run(argv, **kwargs)

        stub = StubClaude()
        out = io.StringIO()
        with (
            patch.dict(os.environ),
            patch.object(claude.subprocess, "run", drop_token),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = smoke.main(
                [
                    *AMOUNTS,
                    "--live",
                    "--yes",
                    "--approved-processes",
                    "7",
                    "--private-root",
                    str(self.private_root),
                    "--claude-bin",
                    "claude-stub",
                ]
            )
        report = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(report["error"], "report_withheld")
        self.assertEqual(report["forbidden_content"], ["token_unavailable"])
        self.assertNotIn("stages", report)

    def test_report_that_would_carry_the_token_or_a_path_is_withheld(self) -> None:
        for name, leak, kind in (
            ("token", FAKE_TOKEN, "token"),
            ("fragment", FAKE_TOKEN[3:14], "token_fragment"),
            ("private root", None, "private_root_path"),
        ):
            with self.subTest(name):
                value = leak or str(self.private_root)
                original = smoke.SmokeRun.report

                def leaking(run: Any, value: str = value) -> dict[str, Any]:
                    return {**original(run), "leak": value}

                with patch.object(smoke.SmokeRun, "report", leaking):
                    code, report, text = self.smoke(StubClaude())
                self.assertEqual(code, 2)
                self.assertIn(kind, report["forbidden_content"])
                self.assertNotIn(value, text)

    def test_live_run_needs_explicit_approval_inputs(self) -> None:
        stub = StubClaude()
        live = [
            "--live",
            "--private-root",
            str(self.private_root),
            "--claude-bin",
            "claude-stub",
        ]
        for argv in (
            [*AMOUNTS, *live, "--approved-processes", "7"],
            [*AMOUNTS, *live, "--yes"],
            [*AMOUNTS, *live, "--yes", "--approved-processes", "6"],
            [*AMOUNTS, *live, "--yes", "--approved-processes", "8"],
            [*AMOUNTS, "--live", "--yes", "--approved-processes", "7"],
        ):
            with (
                self.subTest(argv=argv[6:]),
                patch.object(claude.subprocess, "run", stub.run),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as stopped,
            ):
                smoke.main(argv)
            self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(stub.calls, [])

    def test_manifest_that_is_not_the_frozen_one_does_not_start(self) -> None:
        stub = StubClaude()
        fixture = self.private_root / "fixtures" / f"{PLAN_RISK}.md"
        fixture.write_text(
            fixture.read_text(encoding="utf-8") + "\nextra", encoding="utf-8"
        )
        code, report, text = self.smoke(stub)
        self.assertEqual((code, report), (2, {}))
        self.assertIn("refusing to start", text)
        self.assertEqual(stub.calls, [])

    def test_existing_report_path_is_refused_before_any_stage(self) -> None:
        stub = StubClaude()
        target = self.root / "report.json"
        target.write_text("keep", encoding="utf-8")
        code, _, _ = self.smoke(stub, "--report", str(target))
        self.assertEqual(code, 2)
        self.assertEqual((stub.calls, target.read_text(encoding="utf-8")), ([], "keep"))
        fresh = self.root / "fresh.json"
        code, _, text = self.smoke(stub, "--report", str(fresh))
        self.assertEqual(code, 0, text)
        self.assertEqual(
            json.loads(fresh.read_text(encoding="utf-8"))["status"], "completed"
        )
        if os.name != "nt":
            self.assertEqual(fresh.stat().st_mode & 0o777, 0o600)

    def test_timeout_is_inconclusive_and_charged_the_reservation(self) -> None:
        expired = subprocess.TimeoutExpired("claude-stub", 1)
        stub = StubClaude({1: {"error": expired}, 6: {"error": expired}})
        code, report, text = self.smoke(stub)
        self.assertEqual(code, 0, text)
        for index in (0, 5):
            stage = report["stages"][index]
            self.assertEqual(
                (stage["status"], stage["reason"]), ("inconclusive", "timeout")
            )
            self.assertEqual((stage["charged_usd"], stage["cost_usd"]), ("2", None))
            self.assertEqual(stage["content_failure_class"], "unclassified")
        self.assertEqual(report["stages"][6]["reason"], "executor_not_accepted")
        self.assertEqual(report["processes"]["started"], 6)
        self.assert_public(report, text)

    def test_credential_in_the_stream_stops_the_run(self) -> None:
        stub = StubClaude({2: {"text": f"echo {FAKE_TOKEN}"}})
        code, report, text = self.smoke(stub)
        self.assertEqual((code, report["stopped"]), (1, "credential_in_stream"))
        self.assertEqual(len(stub.calls), 2)
        self.assertEqual(report["stages"][1]["host_code"], "credential_in_stream")
        self.assertNotIn(FAKE_TOKEN, text)


class CapTests(SmokeCase):
    def options(self) -> Any:
        return smoke._parser().parse_args(["--dry-run", *AMOUNTS])

    def test_plan_is_seven_processes_and_a_larger_one_is_refused(self) -> None:
        plan = smoke.build_plan(self.options())
        self.assertEqual(len(plan.stages), smoke.SMOKE_MAX_PROCESSES)
        self.assertEqual(smoke.SMOKE_MAX_PROCESSES, 7)
        extra = dataclasses.replace(plan.stages[0], index=8, arm="plan_extra")
        for stages in (
            (*plan.stages, extra),
            (*plan.stages, dataclasses.replace(plan.stages[-1], index=8)),
        ):
            with (
                self.subTest(len(stages)),
                self.assertRaisesRegex(fixtures.BenchmarkContractError, "7 processes"),
            ):
                smoke.check_plan(
                    dataclasses.replace(plan, stages=stages, total_budget=Decimal("30"))
                )
        for cap in (0, 8, 108):
            with (
                self.subTest(cap=cap),
                self.assertRaises(fixtures.BenchmarkContractError),
            ):
                smoke.RunLedger(cap)

    def test_ledger_refuses_a_process_beyond_its_cap(self) -> None:
        run = self.open_run(reserve_usd="2.00")
        ledger = smoke.RunLedger(1)
        ledger.admission = run.admission
        adapter = ledger.wrap(run)
        stub = StubClaude()
        self.case(
            content.run_native_verifier_case,
            stub,
            private_root=self.private_root,
            case_id=MECH,
            adapter=adapter,
        )
        with self.assertRaisesRegex(
            content.BenchmarkContractError, "process cap reached"
        ):
            self.case(
                content.run_native_verifier_case,
                stub,
                private_root=self.private_root,
                case_id=MECH,
                adapter=adapter,
            )
        self.assertEqual((len(stub.calls), ledger.started), (1, 1))
        self.assertEqual(ledger.last["code"], "process_cap_reached")
        self.assertFalse(ledger.last["started"])
        # A stage of another run cannot be recorded here.
        other = self.open_run()
        with self.assertRaises(content.BenchmarkContractError):
            self.case(
                content.run_native_verifier_case,
                stub,
                private_root=self.private_root,
                case_id=MECH,
                adapter=ledger.wrap(other),
            )
        self.assertEqual(len(stub.calls), 1)

    def test_weighted_token_cap_stops_the_run(self) -> None:
        with patch.object(smoke, "WEIGHTED_TOKEN_CAP", 500):
            stub = StubClaude()
            code, report, text = self.smoke(stub)
        self.assertEqual((code, report["stopped"]), (1, "weighted_token_cap_reached"))
        self.assertLess(len(stub.calls), 7)
        self.assertGreaterEqual(report["weighted_tokens"], 500)
        self.assertEqual(report["stages"][-1]["reason"], "weighted_token_cap_reached")

    def test_reservation_is_the_flag_plus_one_turn_per_agent(self) -> None:
        plan = smoke.build_plan(self.options())
        self.assertEqual(smoke.STAGE_AGENTS, 2)
        self.assertEqual(plan.stage_reserve, plan.stage_budget + 2 * plan.turn_reserve)
        self.assertGreater(plan.stage_reserve, plan.stage_budget)

    def test_stage_projection_drops_everything_that_is_not_a_code_or_number(self) -> None:
        hostile = "free text / with a path and " + SENTINEL
        plan = smoke.build_plan(self.options())
        row = smoke._public_stage(
            plan.stages[0],
            plan.stage_reserve,
            status="accepted",
            reason=hostile,
            stage={
                "attempt": hostile,
                "dispatch_status": hostile,
                "dispatch_reason": hostile,
                "verification": hostile,
                "accepted": hostile,
                "false_escalation": hostile,
                "supported_findings": hostile,
                "quality_score": float("nan"),
                "risk_coverage": hostile,
                "score": {"decision": hostile, "expected_decision": hostile, "passed": hostile},
                "event_types": {hostile: 1, "assistant": hostile, "result": 2},
                "review_output": {"rationale": hostile},
                "message_signals": [{"first": hostile}],
                "role_shapes": [{"prefix": hostile}],
                "detail": hostile,
                "model": hostile,
            },
            record={
                "started": True,
                "code": hostile,
                "cost_usd": hostile,
                "charged_usd": hostile,
                "usage": {"input_tokens": hostile, hostile: 3},
                "weighted_tokens": float("inf"),
                "wall_seconds": hostile,
                "models_observed": [hostile, "opus"],
            },
        )
        text = json.dumps(row)
        self.assertNotIn(SENTINEL, text)
        self.assertNotIn("free text", text)
        self.assertEqual((row["reason"], row["host_code"], row["decision"]), ("unrecognized",) * 3)
        self.assertEqual((row["quality_score"], row["weighted_tokens"], row["cost_usd"]), (None, None, None))
        self.assertEqual((row["models_observed"], row["event_types"]), (["opus"], {"result": 2}))
        self.assertEqual(row["usage"], dict.fromkeys(smoke._USAGE_KEYS))

    def test_evidence_detail_that_is_not_a_code_is_never_reported(self) -> None:
        run = self.open_run()
        ledger = smoke.RunLedger(1)
        ledger.admission = run.admission
        with (
            patch.object(
                run,
                "run_stage",
                side_effect=StageEvidenceError("free text / with a path"),
            ),
            self.assertRaises(StageEvidenceError),
        ):
            ledger.run(run, self.request())
        self.assertEqual(ledger.last["code"], "evidence_unavailable")


def limited_stream(shape: str, *, overage: bool = False) -> str:
    """A stream that reports a usage limit and is also not a complete stream."""
    events = base._events("dispatch-two-rounds")
    for event in events:
        if event["type"] == "rate_limit_event":
            if overage:
                event["rate_limit_info"]["isUsingOverage"] = True
            else:
                event["rate_limit_info"]["status"] = "rejected"
    if shape == "no_result":
        events = [event for event in events if event["type"] != "result"]
    elif shape == "unknown_event":
        events.insert(1, {"type": "never_seen_before"})
    lines = [json.dumps(event) for event in events]
    if shape == "broken_json":
        lines.insert(1, '{"type": "assistant", "message": {')
        lines.append("not json at all")
    return "".join(line + "\n" for line in lines)


class ReviewFindingTests(SmokeCase):
    """Findings of the offline review of the B4 wiring."""

    SHAPES = ("no_result", "unknown_event", "broken_json")

    # -- F1: a usage limit in an incomplete stream ----------------------
    def test_adapter_reports_the_usage_limit_before_any_completeness_check(self) -> None:
        for shape in self.SHAPES:
            for overage in (False, True):
                with self.subTest(shape=shape, overage=overage):
                    host = base._Host(stdout=limited_stream(shape, overage=overage))
                    error, _, _ = self.run_failing(claude.StageRateLimited, host)
                    self.assertEqual(
                        error.detail, "rate_limit_overage" if overage else "rate_limit_not_allowed"
                    )
        # Without a limit the same shapes keep their own reason.
        allowed = limited_stream("no_result").replace('"rejected"', '"allowed"')
        error, _, _ = self.run_failing(StageEvidenceError, base._Host(stdout=allowed))
        self.assertNotIsInstance(error, claude.StageRateLimited)
        self.assertEqual(error.detail, "no_result_event")

    def test_adapter_reads_the_partial_output_of_a_timeout(self) -> None:
        partial = limited_stream("no_result")
        for output in (partial.encode("utf-8"), partial, partial[: len(partial) // 2].encode("utf-8")):
            expired = subprocess.TimeoutExpired("claude-stub", 1, output=output)
            error, _, _ = self.run_failing(claude.StageRateLimited, base._Host(error=expired))
            self.assertEqual(error.detail, "rate_limit_not_allowed")
        for output in (None, b"", b"\xff\xfe not a stream", limited_stream("no_result").replace('"rejected"', '"allowed"')):
            expired = subprocess.TimeoutExpired("claude-stub", 1, output=output)
            self.run_failing(base.StageTimeout, base._Host(error=expired))

    def test_usage_limit_in_a_broken_stream_stops_every_later_stage(self) -> None:
        steps: list[tuple[str, dict[str, Any]]] = [
            (shape, {"stdout": limited_stream(shape)}) for shape in self.SHAPES
        ]
        steps.append(("overage", {"stdout": limited_stream("no_result", overage=True)}))
        steps.append(
            (
                "timeout",
                {"error": subprocess.TimeoutExpired("claude-stub", 1, output=limited_stream("no_result").encode())},
            )
        )
        for name, step in steps:
            for at in (1, 6):
                with self.subTest(name, at=at):
                    stub = StubClaude({at: step})
                    code, report, text = self.smoke(stub)
                    self.assertEqual(code, 1, text)
                    self.assertEqual(report["stopped"], "usage_limit_reported")
                    self.assertEqual(len(stub.calls), at, "a later stage was started")
                    self.assertEqual(report["processes"]["started"], at)
                    self.assertEqual(
                        [(stage["status"], stage["reason"]) for stage in report["stages"][at:]],
                        [("not_run", "usage_limit_reported")] * (7 - at),
                    )
                    self.assertTrue(report["stages"][at - 1]["host_code"].startswith("rate_limit_"))

    def test_broken_stream_without_a_usage_limit_does_not_stop_the_run(self) -> None:
        stub = StubClaude({1: {"stdout": limited_stream("no_result").replace('"rejected"', '"allowed"')}})
        code, report, text = self.smoke(stub)
        self.assertEqual((code, report["stopped"], len(stub.calls)), (0, None, 7), text)
        self.assertEqual(report["stages"][0]["host_code"], "no_result_event")

    # -- an unreadable usage report --------------------------------------
    def unreadable_streams(self) -> dict[str, str]:
        def with_info(change: Any) -> str:
            events = base._events("dispatch-two-rounds")
            for event in events:
                if event["type"] == "rate_limit_event":
                    change(event)
            return base._stream(events)

        broken = with_info(lambda event: None).splitlines()
        index = next(i for i, line in enumerate(broken) if '"rate_limit_event"' in line)
        broken[index] = broken[index][: len(broken[index]) // 2]
        return {
            "info missing": with_info(lambda event: event.pop("rate_limit_info")),
            "info not an object": with_info(lambda event: event.update(rate_limit_info="allowed")),
            "status missing": with_info(lambda event: event["rate_limit_info"].pop("status")),
            "status not a string": with_info(lambda event: event["rate_limit_info"].update(status=1)),
            "line cut short": "\n".join(broken) + "\n",
            "cut short, no result": "\n".join(broken[: index + 1]),
        }

    def test_unreadable_usage_report_stops_every_later_stage(self) -> None:
        for name, stdout in self.unreadable_streams().items():
            with self.subTest(name, level="adapter"):
                error, _, _ = self.run_failing(claude.StageRateLimited, base._Host(stdout=stdout))
                self.assertEqual(error.detail, "rate_limit_status_unknown")
            steps = [{"stdout": stdout}]
            if name == "cut short, no result":
                steps.append({"error": subprocess.TimeoutExpired("claude-stub", 1, output=stdout.encode())})
            for step in steps:
                for at in (1, 6):
                    with self.subTest(name, at=at, timeout="error" in step):
                        stub = StubClaude({at: step})
                        code, report, text = self.smoke(stub)
                        self.assertEqual(code, 1, text)
                        # Told apart from a limit the host actually reported.
                        self.assertEqual(report["stopped"], "usage_limit_unknown")
                        self.assertEqual(len(stub.calls), at, "a later stage was started")
                        self.assertEqual(report["stages"][at - 1]["host_code"], "rate_limit_status_unknown")
                        self.assertEqual(
                            [(stage["status"], stage["reason"]) for stage in report["stages"][at:]],
                            [("not_run", "usage_limit_unknown")] * (7 - at),
                        )

    def test_text_that_only_mentions_the_event_is_not_a_usage_report(self) -> None:
        mention = 'the "type": "rate_limit_event" marker, quoted in an answer {'
        stub = StubClaude({2: {"text": mention}})
        code, report, text = self.smoke(stub)
        self.assertEqual((code, report["stopped"], len(stub.calls)), (0, None, 7), text)

    # -- a token in the partial output of a timeout -----------------------
    def test_token_in_timeout_output_is_a_credential_leak_and_stops_the_run(self) -> None:
        leak = f"partial line {FAKE_TOKEN}"
        outputs = {
            "stdout bytes": {"output": leak.encode()},
            "stdout text": {"output": leak},
            "stderr bytes": {"output": b"clean", "stderr": leak.encode()},
            "stderr only": {"stderr": leak},
            "with a usage limit": {"output": (limited_stream("no_result") + leak).encode()},
        }
        for name, streams in outputs.items():
            expired = subprocess.TimeoutExpired("claude-stub", 1, **streams)
            with self.subTest(name, level="adapter"):
                error, _, request = self.run_failing(StageEvidenceError, base._Host(error=expired))
                self.assertEqual(error.detail, "credential_in_stream")
                self.assertNotIsInstance(error, claude.StageRateLimited)
                self.assertNotIn(FAKE_TOKEN, repr(error) + str(error))
                self.assertEqual(base._tree(request.scratch), ["clean-cwd"])
            for at in (1, 6):
                with self.subTest(name, at=at):
                    stub = StubClaude({at: {"error": expired}})
                    code, report, text = self.smoke(stub)
                    self.assertEqual((code, report["stopped"]), (1, "credential_in_stream"), text)
                    self.assertEqual(len(stub.calls), at, "a later stage was started")
                    self.assertEqual(report["stages"][at - 1]["host_code"], "credential_in_stream")
                    self.assertEqual([stage["status"] for stage in report["stages"][at:]], ["not_run"] * (7 - at))
                    self.assertNotIn(FAKE_TOKEN, text)
                    self.assert_nothing_left_on_disk()

    # -- A1: model names -------------------------------------------------
    def test_only_planned_model_names_reach_the_report(self) -> None:
        secret = "sk-ant-oat01-LOOKSLIKEACREDENTIAL"
        stub = StubClaude(
            {
                1: {"models": [secret, "some-other-identifier"]},
                2: {"models": ["haiku", "claude-opus-4-8[1m]"]},
                3: {"models": ["claude-haiku-" + "x" * 40, "claude-sonnet-5-5"]},
            }
        )
        code, report, text = self.smoke(stub)
        self.assertEqual(code, 0, text)
        self.assertNotIn(secret, text)
        self.assertNotIn("some-other-identifier", text)
        self.assertNotIn("x" * 40, text)
        rows = report["stages"]
        self.assertEqual((rows[0]["models_observed"], rows[0]["models_unrecognized"]), ([smoke.MODEL_PLACEHOLDER], 2))
        self.assertEqual((rows[1]["models_observed"], rows[1]["models_unrecognized"]), (["claude-opus-4-8[1m]", "haiku"], 0))
        self.assertEqual(
            (rows[2]["models_observed"], rows[2]["models_unrecognized"]),
            (["claude-sonnet-5-5", smoke.MODEL_PLACEHOLDER], 1),
        )
        self.assertEqual(rows[3]["models_observed"], ["claude-haiku-4-5-20251001", "claude-opus-5-5"])

    # -- A2: a child answer in the wrong format --------------------------
    def test_review_in_the_wrong_format_is_a_content_failure_not_a_stop(self) -> None:
        answers = [
            json.dumps({"decision": "MAYBE", "findings": [], "rationale": SENTINEL}),
            json.dumps({"decision": "REVISE", "findings": ["x"], "rationale": SENTINEL}),
            json.dumps({"decision": "REVISE", "findings": [{"severity": "P9", "title": "t", "evidence": "e", "revision_id": "r"}], "rationale": SENTINEL}),
            json.dumps({"decision": "READY", "findings": [], "rationale": " "}),
        ]
        for answer in answers:
            with self.subTest(answer=answer[:40]):
                stub = StubClaude({1: {"text": answer}, 5: {"text": answer}})
                code, report, text = self.smoke(stub)
                self.assertEqual((code, report["stopped"]), (0, None), text)
                self.assertEqual(len(stub.calls), 5)
                for index in (0, 4):
                    row = report["stages"][index]
                    self.assertEqual((row["status"], row["reason"]), ("inconclusive", "invalid_native_review_output"))
                    self.assertEqual(row["content_failure_class"], "unparseable_output")
                self.assertEqual(report["stages"][1]["status"], "accepted")
                self.assertEqual(
                    [(row["status"], row["reason"]) for row in report["stages"][5:]],
                    [("not_run", "review_not_accepted")] * 2,
                )
                self.assertEqual(report["failure_taxonomy"], {"content.unparseable_output": 2})
                self.assertNotIn(SENTINEL, text)

    def test_case_function_itself_treats_that_answer_as_on_the_codex_path(self) -> None:
        answer = json.dumps({"decision": "MAYBE", "findings": [], "rationale": "x"})
        with self.assertRaisesRegex(content.BenchmarkContractError, "review output values are invalid"):
            self.case(
                content.run_native_review_case, StubClaude({1: {"text": answer}}),
                private_root=self.private_root, case_id=PLAN_RISK,
            )
        codex = recorded._Host(child_events=recorded._child_events(answer))
        with codex.installed(), self.assertRaisesRegex(content.BenchmarkContractError, "review output values are invalid"):
            content.run_native_review_case(
                private_root=self.private_root, active_home=self.root / "active", codex_bin="codex", case_id=PLAN_RISK,
            )
        self.assert_nothing_left_on_disk()

    def test_cleanup_failure_after_a_stage_still_stops_the_run(self) -> None:
        with patch.object(content, "_remove", side_effect=content.BenchmarkContractError("content probe cleanup failed")):
            stub = StubClaude()
            code, report, _ = self.smoke(stub)
        self.assertEqual((code, report["stopped"], len(stub.calls)), (1, "runner_error", 1))

    # -- A3: an incomplete private root ----------------------------------
    def test_incomplete_private_root_does_not_start_and_prints_no_path(self) -> None:
        for name in (f"fixtures/{PLAN_RISK}.md", f"acceptance/{MECH}.json", "ledgers.json", "salt.bin"):
            with self.subTest(name):
                target = self.private_root / name
                data = target.read_bytes()
                target.unlink()
                stub = StubClaude()
                try:
                    code, report, text = self.smoke(stub)
                finally:
                    target.write_bytes(data)
                    os.chmod(target, 0o600)
                self.assertEqual((code, report, stub.calls), (2, {}, []))
                self.assertIn("refusing to start", text)
                self.assertNotIn("Traceback", text)
                for path in (str(self.private_root), os.path.realpath(self.private_root), str(self.root), os.sep):
                    self.assertNotIn(path, text)

    # -- A4: the report path ---------------------------------------------
    def test_report_inside_the_private_root_is_refused(self) -> None:
        before = base._tree(self.private_root)
        outside = self.root / "outside"
        outside.mkdir()
        targets = [
            self.private_root / "report.json",
            self.private_root / "fixtures" / "report.json",
            outside / ".." / "private" / "report.json",
        ]
        if os.name != "nt":
            link = self.root / "link"
            link.symlink_to(self.private_root, target_is_directory=True)
            targets.append(link / "report.json")
            dangling = outside / "report.json"
            dangling.symlink_to(self.private_root / "via-symlink.json")
            targets.append(dangling)
        for target in targets:
            with self.subTest(str(target.relative_to(self.root))):
                stub = StubClaude()
                code, report, text = self.smoke(stub, "--report", str(target))
                self.assertEqual((code, report, stub.calls), (2, {}, []))
                self.assertIn("refusing to start", text)
                self.assertEqual(base._tree(self.private_root), before)


if __name__ == "__main__":
    unittest.main()


class WithheldPathEscapeTests(unittest.TestCase):
    """報表是序列化後的 JSON：含反斜線的路徑（Windows）escape 後也要被擋下。"""

    def test_backslash_private_root_is_found_in_json_text(self) -> None:
        root = Path("D:\\a\\shoal\\private")
        text = json.dumps({"leak": str(root)})
        self.assertNotIn(str(root), text)
        found = smoke._withheld({"leak": str(root)}, text, root, needs_token=False)
        self.assertIn("private_root_path", found)
