#!/usr/bin/env python3
"""Claude smoke for the role-fitness content cohorts (claude-eval-parity B4).

One case per cohort through ``ClaudeStageAdapter``, scored by the same case
functions, classifier and report as the Codex path:

- plan_review: the plan-verifier's committed binding (frontier) against the
  strong tier, one ``claude -p`` process per arm;
- mechanical_execution: the committed binding, executor then verifier;
- split_workflow: the committed binding, review, executor then verifier.

That is seven processes, which is also the hard cap.  ``--dry-run`` prints the
stages, arms, per-stage reservation and totals and starts nothing; it needs no
token and no private root.  A live run consumes subscription usage and needs
``--live --yes``, the frozen private root, the token injected by the credential
broker and ``--approved-processes`` equal to the planned process count.

The output is a JSON report of scores, class enums, counts, usage and cost
numbers, stage status and reason codes.  It carries no model output, prompt,
fixture content, token or path; the raw stream and the child's answer only ever
exist in memory.  Nothing is retried.

Exit status: 0 the run was not stopped; 1 a stop condition ended it early;
2 it did not start or its report was withheld.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import claude_live_probe as probe
import role_fitness_claude as claude
import run_role_fitness_content as content
from benchmark_role_fitness import (
    build_split_handoff,
    public_content_failure_counts,
    validate_public_projection,
)
from role_fitness_fixtures import BenchmarkContractError
from role_fitness_scorecard import (
    classify_content_stages,
    content_failure_report,
    content_failure_taxonomy,
)
from role_fitness_stage import (
    StageEvidenceError,
    StageOutcome,
    StageRequest,
    StageSetupError,
    StageTimeout,
)

sys.path.insert(0, str(claude.ROOT / "tools"))
import resolve  # noqa: E402


SCHEMA = "claude-eval-smoke-v1"
PUBLIC_VERSION = "role-fitness-public-v1"
PUBLIC_MANIFEST = (
    claude.ROOT / "docs" / "benchmarks" / "role-fitness-v1-fixtures-manifest-v2.json"
)
REPEAT_LABEL = "R1"

# SPEC "Live run 與成本": plan review 1 + 1 (two arms), mechanical 2, split 3.
SMOKE_MAX_PROCESSES = 7
# Settled stop point of one run, next to claude.RUN_COST_CAP_USD.
WEIGHTED_TOKEN_CAP = 8_000_000
# Every stage is a parent session that dispatches one child.  The budget flag
# is checked only after a turn ends, so each of the two agents can finish one
# more turn after the flag value has been reached.
STAGE_AGENTS = 2
DEFAULT_PARENT_MODEL = "haiku"
DEFAULT_TIMEOUT = 360
MAX_TIMEOUT = 600

PLAN_ROLE, EXECUTOR_ROLE, VERIFIER_ROLE = "plan-verifier", "mech-executor", "verifier"
COHORT_PROCESSES = {"plan_review": 1, "mechanical_execution": 2, "split_workflow": 3}

_CODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
_EVENT_RE = re.compile(r"[a-z][a-z0-9_.]{0,63}")
_USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
)

# Why admission refused a stage, as a reason code.
_PROCESS_CAP = "process cap reached"
_TOKEN_CAP = "weighted token cap reached"
_ADMISSION_CODES = {
    "cumulative cost cap reached": "total_budget_reached",
    "per-stage cap was exceeded": "stage_cost_exceeded_reservation",
    claude.USAGE_LIMIT_REPORTED: "usage_limit_reported",
    claude.USAGE_STATE_UNKNOWN: "usage_limit_unknown",
    "previous stage is not settled": "previous_stage_not_settled",
    _PROCESS_CAP: "process_cap_reached",
    _TOKEN_CAP: "weighted_token_cap_reached",
}
# What score_plan_review says about a child answer in the wrong format.  That
# is a content failure of one stage, not a reason to end the run.
_REVIEW_FORMAT_ERRORS = frozenset(
    {
        "review output shape is invalid",
        "review output values are invalid",
        "review finding shape is invalid",
        "review finding values are invalid",
    }
)
MODEL_PLACEHOLDER = "unrecognized_model"
# What may follow a known model name in a full version name.
_MODEL_SUFFIX_RE = re.compile(r"(?:-[a-z0-9.]{1,12}){0,4}(?:\[1m\])?")
# A stage that ends with one of these puts the whole run in doubt: stop.
_STOP_CODES = frozenset(
    {
        "setup_failed",
        "cleanup_failed",
        "contract_error",
        "host_error",
        "runner_error",
        "split_handoff_error",
        "credential_in_stream",
        "credential_in_workdir",
        "workdir_scan_limit",
        "workdir_scan_failed",
        "workdir_cleanup_failed",
    }
)


@dataclass(frozen=True)
class PlannedStage:
    index: int
    cohort: str
    arm: str
    stage: str
    role: str
    case_id: str
    child_model: str


@dataclass(frozen=True)
class SmokePlan:
    stages: tuple[PlannedStage, ...]
    role_models: dict[str, dict[str, str]]
    stage_budget: Decimal
    turn_reserve: Decimal
    stage_reserve: Decimal
    total_budget: Decimal
    parent_model: str
    timeout: int

    def public(self) -> dict[str, Any]:
        """The approval sheet: what would run and what it may cost at most."""
        return {
            "manifest_hash": claude.FROZEN_MANIFEST_V2_HASH,
            "parent_model": self.parent_model,
            "timeout_seconds": self.timeout,
            "stage_budget_usd": format(self.stage_budget, "f"),
            "turn_reserve_usd": format(self.turn_reserve, "f"),
            "agents_per_stage": STAGE_AGENTS,
            "stage_reserve_usd": format(self.stage_reserve, "f"),
            "worst_case_usd": format(self.stage_reserve * len(self.stages), "f"),
            "total_budget_usd": format(self.total_budget, "f"),
            "run_cost_cap_usd": format(claude.RUN_COST_CAP_USD, "f"),
            "weighted_token_cap": WEIGHTED_TOKEN_CAP,
            "processes": {"planned": len(self.stages), "hard_cap": SMOKE_MAX_PROCESSES},
            "arms": sorted({stage.arm for stage in self.stages}),
            "stages": [
                {
                    "index": stage.index,
                    "cohort": stage.cohort,
                    "arm": stage.arm,
                    "stage": stage.stage,
                    "role": stage.role,
                    "case_id": stage.case_id,
                    "child_model": stage.child_model,
                    "reserved_usd": format(self.stage_reserve, "f"),
                }
                for stage in self.stages
            ],
        }


def _bound_model(role: str) -> str:
    """The model the committed Claude agent file binds ``role`` to."""
    try:
        text = (claude.DIST_AGENTS / f"{role}.md").read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise BenchmarkContractError("committed Claude agent is unreadable") from None
    end = text.find("\n---\n", 4)
    bound = [
        line.partition(":")[2].strip()
        for line in (
            text[4:end].split("\n") if text.startswith("---\n") and end > 0 else []
        )
        if line.startswith("model:")
    ]
    if len(bound) != 1 or not claude._MODEL_RE.fullmatch(bound[0]):
        raise BenchmarkContractError(
            "committed Claude agent has no single model binding"
        )
    return bound[0]


def _tier_model(tier: str) -> str:
    """What the repo's tier rules pick for ``tier`` among the Claude host's models."""
    try:
        core: dict[str, Any] = {}
        for name in ("roles", "models", "tiers"):
            with (claude.ROOT / "core" / f"{name}.toml").open("rb") as handle:
                core.update(tomllib.load(handle))
        with (claude.ROOT / "hosts" / "claude" / "binding.toml").open("rb") as handle:
            binding = tomllib.load(handle)
        model = resolve.resolve(core, binding, tier=tier).model
    except (OSError, tomllib.TOMLDecodeError, resolve.ResolveError, KeyError):
        raise BenchmarkContractError("tier binding cannot be resolved") from None
    if not isinstance(model, str) or not claude._MODEL_RE.fullmatch(model):
        raise BenchmarkContractError("tier binding cannot be resolved")
    return model


def _cases() -> dict[str, list[dict[str, Any]]]:
    """Case ids of the committed public manifest v2, by cohort."""
    try:
        manifest = json.loads(PUBLIC_MANIFEST.read_text(encoding="utf-8"))
        if manifest["manifest_hash"] != claude.FROZEN_MANIFEST_V2_HASH:
            raise BenchmarkContractError(
                "public manifest is not the frozen v2 manifest"
            )
        cohorts: dict[str, list[dict[str, Any]]] = {
            name: [] for name in COHORT_PROCESSES
        }
        for case in manifest["cases"]:
            cohorts[case["cohort"]].append(case)
    except (OSError, ValueError, KeyError, TypeError):
        raise BenchmarkContractError("public manifest is unreadable") from None
    return cohorts


def _case(
    cohorts: dict[str, list[dict[str, Any]]], cohort: str, chosen: str | None
) -> str:
    cases = cohorts[cohort]
    if chosen is None:
        # A risk case exercises the reviewer; a clean control only checks READY.
        preferred = [case for case in cases if not case.get("clean_control")] or cases
        if not preferred:
            raise BenchmarkContractError("public manifest has an empty cohort")
        return preferred[0]["case_id"]
    if chosen not in {case["case_id"] for case in cases}:
        raise BenchmarkContractError(
            f"case is not in the {cohort} cohort of the frozen manifest"
        )
    return chosen


def build_plan(options: argparse.Namespace) -> SmokePlan:
    """Validate the options and lay out every stage of the smoke."""
    budget = probe._amount(options.stage_budget_usd, "--stage-budget-usd")
    turn = probe._amount(options.turn_reserve_usd, "--turn-reserve-usd")
    total = probe._amount(options.total_budget_usd, "--total-budget-usd")
    if not isinstance(options.parent_model, str) or not claude._MODEL_RE.fullmatch(
        options.parent_model
    ):
        raise BenchmarkContractError("--parent-model must be a model alias or name")
    if not 10 <= options.timeout <= MAX_TIMEOUT:
        raise BenchmarkContractError(f"--timeout must be 10 to {MAX_TIMEOUT} seconds")
    reserve = budget + STAGE_AGENTS * turn
    cohorts = _cases()
    plan_case = _case(cohorts, "plan_review", options.plan_case)
    mechanical_case = _case(cohorts, "mechanical_execution", options.mechanical_case)
    split_case = _case(cohorts, "split_workflow", options.split_case)
    current = {
        role: _bound_model(role) for role in (PLAN_ROLE, EXECUTOR_ROLE, VERIFIER_ROLE)
    }
    frontier, strong = _tier_model("frontier"), _tier_model("strong")
    if current[PLAN_ROLE] != frontier:
        raise BenchmarkContractError("plan-verifier is not bound to the frontier tier")
    if strong == frontier:
        raise BenchmarkContractError(
            "strong and frontier tiers resolve to the same model"
        )
    layout = [
        (
            "plan_review",
            "plan_frontier",
            "review",
            PLAN_ROLE,
            plan_case,
            current[PLAN_ROLE],
        ),
        ("plan_review", "plan_strong", "review", PLAN_ROLE, plan_case, strong),
        (
            "mechanical_execution",
            "mechanical_current",
            "executor",
            EXECUTOR_ROLE,
            mechanical_case,
            current[EXECUTOR_ROLE],
        ),
        (
            "mechanical_execution",
            "mechanical_current",
            "verifier",
            VERIFIER_ROLE,
            mechanical_case,
            current[VERIFIER_ROLE],
        ),
        (
            "split_workflow",
            "split_current",
            "review",
            PLAN_ROLE,
            split_case,
            current[PLAN_ROLE],
        ),
        (
            "split_workflow",
            "split_current",
            "executor",
            EXECUTOR_ROLE,
            split_case,
            current[EXECUTOR_ROLE],
        ),
        (
            "split_workflow",
            "split_current",
            "verifier",
            VERIFIER_ROLE,
            split_case,
            current[VERIFIER_ROLE],
        ),
    ]
    stages = tuple(
        PlannedStage(index, *row) for index, row in enumerate(layout, start=1)
    )
    plan = SmokePlan(
        stages=stages,
        role_models={"plan_strong": {PLAN_ROLE: strong}},
        stage_budget=budget,
        turn_reserve=turn,
        stage_reserve=reserve,
        total_budget=total,
        parent_model=options.parent_model,
        timeout=options.timeout,
    )
    check_plan(plan)
    return plan


def check_plan(plan: SmokePlan) -> None:
    """Refuse a plan that could exceed the process cap or the approved total."""
    arms = {(stage.cohort, stage.arm) for stage in plan.stages}
    expected = sum(COHORT_PROCESSES[cohort] for cohort, _ in arms)
    if len(plan.stages) != expected or len(plan.stages) > SMOKE_MAX_PROCESSES:
        raise BenchmarkContractError(
            f"smoke plan exceeds the cap of {SMOKE_MAX_PROCESSES} processes"
        )
    if plan.stage_reserve > claude.RUN_COST_CAP_USD:
        raise BenchmarkContractError("stage reservation exceeds the run cap")
    if plan.stage_reserve * len(plan.stages) > plan.total_budget:
        raise BenchmarkContractError(
            "--total-budget-usd does not cover every stage's reservation"
        )


class RunLedger:
    """What each started stage reported, kept as numbers and codes only.

    Wraps the admitted adapters of one run.  It enforces the process cap and
    the weighted-token stop through the run's admission, and remembers for the
    last stage its cost, usage, wall time and the reason code of whatever it
    raised.  No message text or exception text is kept.
    """

    def __init__(self, max_processes: int, known_models: Any = ()) -> None:
        if not 0 < max_processes <= SMOKE_MAX_PROCESSES:
            raise BenchmarkContractError("process cap is out of range")
        self.known_models = frozenset(known_models)
        self.max_processes = max_processes
        self.admission: claude.CostAdmission | None = None
        self.started = 0
        self.weighted_tokens = 0.0
        self.reported_usd = Decimal("0")
        self.last: dict[str, Any] | None = None
        self._models: list[str] = []
        self._unknown_models = 0

    def _model_name(self, name: Any) -> str | None:
        """``name`` if it is a planned model or a version of one, else None."""
        if isinstance(name, str):
            for known in self.known_models:
                for prefix in (known, f"claude-{known}"):
                    if name.startswith(prefix) and _MODEL_SUFFIX_RE.fullmatch(
                        name[len(prefix) :]
                    ):
                        return name
        return None

    def observe(self, observation: claude.StageObservation) -> None:
        """Which planned models the finished stream's result events name.

        A name the plan does not account for is never copied: such names are
        counted and shown as one fixed placeholder.
        """
        names: set[str] = set()
        seen: set[str] = set()
        for line in observation.stdout.splitlines():
            try:
                event = json.loads(line)
            except (ValueError, RecursionError):
                continue
            models = (
                event.get("modelUsage")
                if isinstance(event, dict) and event.get("type") == "result"
                else None
            )
            if isinstance(models, dict):
                seen.update(str(name) for name in models)
        for name in seen:
            names.add(self._model_name(name) or MODEL_PLACEHOLDER)
        self._models = sorted(names)[:8]
        self._unknown_models = sum(1 for name in seen if self._model_name(name) is None)

    def wrap(self, admitted: claude.AdmittedStageAdapter) -> "_LedgerAdapter":
        return _LedgerAdapter(self, admitted)

    def run(
        self, admitted: claude.AdmittedStageAdapter, request: StageRequest
    ) -> StageOutcome:
        admission = admitted.admission
        if admission is not self.admission:
            raise BenchmarkContractError("stage does not belong to this run")
        if self.started >= self.max_processes:
            admission.close(_PROCESS_CAP)
        self._models, self._unknown_models = [], 0
        spent = admission.spent_usd
        record: dict[str, Any] = {"started": True, "code": None}
        self.last = record
        try:
            outcome = admitted.run_stage(request)
        except claude.StageNotAdmitted as exc:
            record.update(
                started=False, code=_ADMISSION_CODES.get(str(exc), "not_admitted")
            )
            raise
        except StageSetupError:
            # Raised before the host starts: no process ran.
            record.update(started=False, code="setup_failed")
            raise
        except StageEvidenceError as exc:
            # Includes StageRateLimited; ``detail`` is a short code, never content.
            record["code"] = (
                exc.detail
                if _CODE_RE.fullmatch(str(exc.detail))
                else "evidence_unavailable"
            )
            raise
        except StageTimeout:
            record["code"] = "timeout"
            raise
        except claude.StageCleanupError:
            record["code"] = "cleanup_failed"
            raise
        except BenchmarkContractError:
            record["code"] = "contract_error"
            raise
        except Exception:
            record["code"] = "host_error"
            raise
        finally:
            if record["started"]:
                self.started += 1
            record["charged_usd"] = admission.spent_usd - spent
            record["models_observed"] = self._models
            record["models_unrecognized"] = self._unknown_models
        weighted = content._weighted_tokens(outcome.usage)
        cost = outcome.cost_usd if probe._valid_cost(outcome.cost_usd) else None
        if cost is not None:
            self.reported_usd += Decimal(str(cost))
        if weighted is not None and weighted > 0:
            self.weighted_tokens += weighted
        if self.weighted_tokens >= WEIGHTED_TOKEN_CAP:
            admission.close(_TOKEN_CAP)
        record.update(
            cost_usd=cost,
            usage={key: outcome.usage.get(key) for key in _USAGE_KEYS},
            weighted_tokens=weighted,
            wall_seconds=round(outcome.wall_seconds, 3),
        )
        return outcome


class _LedgerAdapter:
    """A ``StageAdapter`` whose stages are recorded in a ``RunLedger``."""

    def __init__(
        self, ledger: RunLedger, admitted: claude.AdmittedStageAdapter
    ) -> None:
        self.ledger = ledger
        self.admitted = admitted

    def run_stage(self, request: StageRequest) -> StageOutcome:
        return self.ledger.run(self.admitted, request)


def _code(value: Any) -> str | None:
    if value is None:
        return None
    return (
        value
        if isinstance(value, str) and _CODE_RE.fullmatch(value)
        else "unrecognized"
    )


def _num(value: Any) -> int | float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        return None
    return value


def _flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _public_stage(
    planned: PlannedStage,
    reserve: Decimal,
    *,
    status: str,
    reason: str | None,
    stage: dict[str, Any] | None,
    record: dict[str, Any] | None,
) -> dict[str, Any]:
    """Allowlisted projection of one stage: identifiers, enums, codes, numbers."""
    stage = stage or {}
    record = record or {}
    score = stage.get("score") if isinstance(stage.get("score"), dict) else {}
    events = (
        stage.get("event_types") if isinstance(stage.get("event_types"), dict) else {}
    )
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else None
    charged = record.get("charged_usd")
    return {
        "index": planned.index,
        "cohort": planned.cohort,
        "arm": planned.arm,
        "stage": planned.stage,
        "role": planned.role,
        "case_id": planned.case_id,
        "child_model_bound": planned.child_model,
        "reserved_usd": format(reserve, "f"),
        "started": bool(record.get("started")),
        "status": status,
        "reason": _code(reason),
        "host_code": _code(record.get("code")),
        "attempt": _num(stage.get("attempt")),
        "dispatch_status": _code(stage.get("dispatch_status")),
        "dispatch_reason": _code(stage.get("dispatch_reason")),
        "verification": _code(stage.get("verification")),
        "artifact_accepted": _flag(stage.get("accepted")),
        "decision": _code(score.get("decision")),
        "expected_decision": _code(score.get("expected_decision")),
        "review_passed": _flag(score.get("passed")),
        "false_escalation": _flag(stage.get("false_escalation")),
        "supported_findings": _num(stage.get("supported_findings")),
        "quality_score": _num(stage.get("quality_score")),
        "risk_coverage": _num(stage.get("risk_coverage")),
        "content_failure_class": None,
        "cost_usd": _num(record.get("cost_usd")),
        "charged_usd": (
            format(charged.normalize(), "f") if isinstance(charged, Decimal) else None
        ),
        "usage": None
        if usage is None
        else {key: _num(usage.get(key)) for key in _USAGE_KEYS},
        "weighted_tokens": _num(record.get("weighted_tokens")),
        "wall_seconds": _num(record.get("wall_seconds")),
        "models_observed": [
            name
            for name in record.get("models_observed", [])
            if isinstance(name, str) and claude._MODEL_RE.fullmatch(name)
        ],
        "models_unrecognized": _num(record.get("models_unrecognized")),
        "event_types": {
            name: count
            for name, count in sorted(events.items())
            if isinstance(name, str)
            and _EVENT_RE.fullmatch(name)
            and type(count) is int
        },
    }


class SmokeRun:
    """Runs the planned stages in order and keeps one public row per stage."""

    def __init__(self, plan: SmokePlan, private_root: Path, claude_bin: str) -> None:
        self.plan = plan
        self.private_root = private_root
        self.ledger = RunLedger(
            len(plan.stages),
            {plan.parent_model, *(stage.child_model for stage in plan.stages)},
        )
        base = claude.open_claude_run(
            private_root=private_root,
            claude_bin=claude_bin,
            per_stage_cap_usd=plan.stage_budget,
            reserve_usd=plan.stage_reserve,
            run_cap_usd=plan.total_budget,
            model=plan.parent_model,
            observer=self.ledger.observe,
        )
        self.ledger.admission = self.admission = base.admission
        self._adapters = {
            arm: self.ledger.wrap(
                claude.AdmittedStageAdapter(
                    base.inner.with_role_models(models), base.admission
                )
            )
            for arm, models in plan.role_models.items()
        }
        self._default = self.ledger.wrap(base)
        self.rows: list[dict[str, Any]] = []
        # arm -> runner-format stages of the stages whose process started.
        self.content: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        self.stopped: str | None = None

    def _planned(self, arm: str, stage: str) -> PlannedStage:
        return next(
            item for item in self.plan.stages if item.arm == arm and item.stage == stage
        )

    def skip(self, arm: str, stage: str, reason: str) -> None:
        self.rows.append(
            _public_stage(
                self._planned(arm, stage),
                self.plan.stage_reserve,
                status="not_run",
                reason=self.stopped or reason,
                stage=None,
                record=None,
            )
        )

    def execute(
        self,
        arm: str,
        stage: str,
        run_case: Callable[..., dict[str, Any]],
        **arguments: Any,
    ) -> dict[str, Any] | None:
        """Run one stage unless the run has stopped; returns its stage dict if accepted."""
        planned = self._planned(arm, stage)
        if self.stopped is not None:
            self.skip(arm, stage, self.stopped)
            return None
        print(
            f"claude-eval-smoke: stage {planned.index} {arm} {stage}", file=sys.stderr
        )
        self.ledger.last = None
        result: dict[str, Any] | None = None
        escaped = False
        try:
            result = run_case(
                case_id=planned.case_id,
                timeout=self.plan.timeout,
                adapter=self._adapters.get(arm, self._default),
                dispatch_prompt=claude.claude_dispatch_prompt,
                **arguments,
            )
        except BenchmarkContractError as error:
            done = self.ledger.last
            if (
                stage == "review"
                and done is not None
                and done["started"]
                and done["code"] is None
                and str(error) in _REVIEW_FORMAT_ERRORS
            ):
                # The dispatch worked and the child answered, but not in a form
                # the scorer accepts: the same stage an unparseable answer gives.
                result = {
                    "case_id": planned.case_id,
                    "status": "inconclusive",
                    "reason": "invalid_native_review_output",
                    "dispatch_status": claude.DISPATCH_OK,
                    "dispatch_reason": "ok",
                    "attempt": 1,
                }
            else:
                escaped = True
        except Exception:
            # The ledger already holds the reason code; no exception text is kept.
            escaped = True
        record = self.ledger.last
        started = bool(record and record["started"])
        host_code = record["code"] if record else None
        fatal: str | None = host_code if host_code in _STOP_CODES else None
        if escaped:
            reason = host_code or "runner_error"
            if reason in _STOP_CODES or not started:
                # Nothing the next stage could do differently: stop the run.
                fatal = reason
            status = (
                "error"
                if reason in _STOP_CODES
                else "inconclusive" if started else "not_run"
            )
            # A stage that started but left no stage dict is still one
            # inconclusive stage for the classifier.
            result = (
                {
                    "case_id": planned.case_id,
                    "status": "inconclusive",
                    "reason": (
                        "timeout"
                        if reason == "timeout"
                        else "native_evidence_unavailable"
                    ),
                    "native_role": planned.role,
                    "attempt": 1,
                }
                if started
                else None
            )
        else:
            status, reason = result.get("status"), result.get("reason")
            status = status if status in {"accepted", "inconclusive"} else "error"
        row = _public_stage(
            planned,
            self.plan.stage_reserve,
            status=status,
            reason=reason,
            stage=result,
            record=record,
        )
        self.rows.append(row)
        if result is not None and started:
            self.content.setdefault(arm, []).append((len(self.rows) - 1, result))
        closed = self.admission.closed_reason
        if closed is not None:
            self.stopped = _ADMISSION_CODES.get(closed, "not_admitted")
        elif fatal is not None:
            self.stopped = fatal
        print(f"claude-eval-smoke: stage {planned.index}: {status}", file=sys.stderr)
        return result if status == "accepted" and not escaped else None

    def run(self) -> None:
        root = self.private_root
        self.execute(
            "plan_frontier", "review", content.run_native_review_case, private_root=root
        )
        self.execute(
            "plan_strong", "review", content.run_native_review_case, private_root=root
        )

        arm = "mechanical_current"
        made = self.execute(
            arm, "executor", content.run_native_mechanical_case, private_root=root
        )
        if made is None:
            self.skip(arm, "verifier", "executor_not_accepted")
        else:
            self.execute(
                arm, "verifier", content.run_native_verifier_case, private_root=root
            )

        arm = "split_current"
        review = self.execute(
            arm, "review", content.run_native_review_case, private_root=root
        )
        handoff = None
        if review is not None:
            try:
                handoff = build_split_handoff(
                    private_root=root,
                    case_id=self._planned(arm, "review").case_id,
                    review_output=review["review_output"],
                )
            except Exception:
                self.stopped = self.stopped or "split_handoff_error"
        if handoff is None:
            reason = (
                "review_not_accepted" if review is None else "split_handoff_unavailable"
            )
            self.skip(arm, "executor", reason)
            self.skip(arm, "verifier", reason)
            return
        made = self.execute(
            arm, "executor", content.run_native_split_executor_case, handoff=handoff
        )
        if made is None:
            self.skip(arm, "verifier", "executor_not_accepted")
        else:
            self.execute(
                arm, "verifier", content.run_native_verifier_case, private_root=root
            )

    def report(self) -> dict[str, Any]:
        """The public report; every stage dict is reduced before it gets here."""
        taxonomy: dict[str, int] = {}
        arms: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for arm, entries in self.content.items():
            stages = [stage for _, stage in entries]
            classes = classify_content_stages(stages)
            for (row_index, _), name in zip(entries, classes):
                self.rows[row_index]["content_failure_class"] = name
            for key, count in content_failure_taxonomy(classes).items():
                taxonomy[key] = taxonomy.get(key, 0) + count
            arms[arm] = {REPEAT_LABEL: stages}
        failure_report = content_failure_report(arms) if arms else {"arms": {}}
        counts = public_content_failure_counts(failure_report)
        if counts:
            validate_public_projection(
                {"version": PUBLIC_VERSION, "content_failure_counts": counts}
            )
        return {
            "schema": SCHEMA,
            "mode": "live",
            "token_env": claude.SUBSCRIPTION_TOKEN_ENV,
            "status": "completed" if self.stopped is None else "stopped",
            "stopped": self.stopped,
            "exit_code": 0 if self.stopped is None else 1,
            "plan": self.plan.public(),
            "processes": {
                "started": self.ledger.started,
                "cap": self.ledger.max_processes,
            },
            "cost": {
                "reported_usd": format(self.ledger.reported_usd, "f"),
                "charged_usd": format(self.admission.spent_usd, "f"),
            },
            "weighted_tokens": self.ledger.weighted_tokens,
            "stages": self.rows,
            "failure_taxonomy": taxonomy,
            "content_failure_counts": counts,
            "arm_summary": {
                arm: {
                    label: {
                        "stages": block["stages"],
                        "passed": block["passed"],
                        "mean_quality_score": block["mean_quality_score"],
                    }
                    for label, block in data["repeats"].items()
                }
                for arm, data in failure_report["arms"].items()
            },
        }


def _withheld(
    report: dict[str, Any], text: str, private_root: Path | None, *, needs_token: bool
) -> list[str]:
    """Kinds of forbidden content found in the report (token, home or private paths)."""
    try:
        found = probe._forbidden(report, text, Path(tempfile.gettempdir()))
    except StageSetupError:
        # The home to look for cannot be determined: do not publish.
        return ["home_unknown"]
    if not needs_token:
        # A dry run has no token to leak; everything else is still checked.
        found = [kind for kind in found if kind != "token_unavailable"]
    if private_root is not None:
        paths = {str(private_root), str(private_root.absolute()), os.path.realpath(private_root)}
        # text 是序列化後的 JSON；Windows 路徑的反斜線會被 escape，escape 後的寫法也要比對。
        forms = paths | {json.dumps(p, ensure_ascii=a)[1:-1] for p in paths for a in (True, False)}
        if any(form in text for form in forms):
            found.append("private_root_path")
    return found


def _inside(path: str, directory: Path) -> bool:
    """Whether ``path`` resolves to ``directory`` or below it (symlinks, ``..``)."""
    target, parent = Path(os.path.realpath(path)), Path(os.path.realpath(directory))
    return target == parent or parent in target.parents


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Claude smoke for the role-fitness content cohorts (claude-eval-parity "
            f"B4): at most {SMOKE_MAX_PROCESSES} claude processes. A live run consumes "
            "subscription usage; run it only with approval, with the token injected "
            f"into {claude.SUBSCRIPTION_TOKEN_ENV} by the credential broker. The JSON "
            "report holds no model output, prompt, fixture content, token or path. "
            "Never retries."
        ),
        epilog=(
            "Exit status: 0 the run was not stopped; 1 a stop condition ended it "
            "early; 2 it did not start or its report was withheld."
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="print the stages, arms, reservations and totals; start nothing, need no token",
    )
    mode.add_argument(
        "--live", action="store_true", help="run the smoke (also needs --yes)"
    )
    parser.add_argument("--yes", action="store_true", help="confirm a live run")
    parser.add_argument(
        "--stage-budget-usd",
        required=True,
        help="--max-budget-usd of every stage (from the approval sheet; no default)",
    )
    parser.add_argument(
        "--turn-reserve-usd",
        required=True,
        help=(
            "the most a single turn of one agent may cost; each stage reserves "
            f"the stage budget plus {STAGE_AGENTS} of these (no default)"
        ),
    )
    parser.add_argument(
        "--total-budget-usd",
        required=True,
        help=(
            "approved total; must cover every stage's reservation "
            f"(at most {claude.RUN_COST_CAP_USD}; no default)"
        ),
    )
    parser.add_argument(
        "--approved-processes",
        type=int,
        help="process total on the approval sheet; a live run needs it to equal the plan",
    )
    parser.add_argument(
        "--private-root", type=Path, help="frozen private fixture root (live only)"
    )
    parser.add_argument(
        "--plan-case", help="plan_review case (default: first risk case)"
    )
    parser.add_argument(
        "--mechanical-case", help="mechanical_execution case (default: first)"
    )
    parser.add_argument(
        "--split-case", help="split_workflow case (default: first risk case)"
    )
    parser.add_argument(
        "--parent-model",
        default=DEFAULT_PARENT_MODEL,
        help="model of the dispatching parent session (default: %(default)s)",
    )
    parser.add_argument(
        "--claude-bin", help="claude executable (default: found on PATH)"
    )
    parser.add_argument(
        "--timeout",
        type=probe._seconds,
        default=DEFAULT_TIMEOUT,
        help=f"seconds per stage, 10 to {MAX_TIMEOUT} (default: %(default)s)",
    )
    parser.add_argument("--report", help="write the JSON report here (default: stdout)")
    return parser


def _say(message: str) -> None:
    print(f"claude-eval-smoke: {message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    options = parser.parse_args(argv)
    try:
        plan = build_plan(options)
    except BenchmarkContractError as error:
        parser.error(str(error))
    if options.dry_run:
        report = {"schema": SCHEMA, "mode": "dry-run", "plan": plan.public()}
        text = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if _withheld(report, text, None, needs_token=False):
            _say("dry-run output withheld")
            return 2
        sys.stdout.write(text)
        return 0
    if not options.yes:
        parser.error("a live run requires both --live and --yes")
    if options.approved_processes != len(plan.stages):
        parser.error(
            f"--approved-processes must equal the planned process count ({len(plan.stages)})"
        )
    if options.private_root is None:
        parser.error("a live run requires --private-root")
    # Fail closed before anything is created: no token, no run.
    try:
        claude._subscription_token()
    except StageSetupError:
        _say(
            f"subscription token is not available in {claude.SUBSCRIPTION_TOKEN_ENV}; "
            "refusing to start"
        )
        return 2
    claude_bin = options.claude_bin or shutil.which("claude")
    if not claude_bin:
        _say("claude executable not found")
        return 2
    if options.report is not None and _inside(options.report, options.private_root):
        _say("report path is inside the private root; refusing to start")
        return 2
    try:
        run = SmokeRun(plan, options.private_root.absolute(), claude_bin)
    except BenchmarkContractError as error:
        # Fixed validator messages (manifest, budgets); they carry no path.
        _say(f"refusing to start: {error}")
        return 2
    except (OSError, ValueError, KeyError, TypeError):
        # An incomplete or damaged bundle; the error would name its path.
        _say("refusing to start: private root is unreadable")
        return 2
    descriptor: int | None = None
    if options.report is not None:
        try:
            descriptor = probe._open_report(options.report)
        except OSError:
            _say("report path exists or cannot be created; refusing to start")
            return 2
    written = False
    try:
        run.run()
        report = run.report()
        exit_code = report["exit_code"]
        forbidden = _withheld(
            report, json.dumps(report), options.private_root, needs_token=True
        )
        if forbidden:
            report = {
                "schema": SCHEMA,
                "mode": "live",
                "status": "withheld",
                "exit_code": 2,
                "error": "report_withheld",
                "forbidden_content": forbidden,
            }
            exit_code = 2
        try:
            probe._emit(report, descriptor)
            written = True
        except OSError:
            _say("report could not be written")
            return 2
        return exit_code
    finally:
        if descriptor is not None and not written:
            # Only ever the empty file this run created itself.
            try:
                os.close(descriptor)
            except OSError:
                pass
            try:
                os.unlink(options.report)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
