#!/usr/bin/env python3
"""Run a bounded, anonymous content-bearing review probe.

This path compares direct model/effort candidates as a directional quality
probe.  The formal role-fitness claim still requires the native role contract,
mechanical stages, and the full frozen cohort.
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

from role_fitness_fixtures import BenchmarkContractError, score_plan_review, validate_bundle
from role_fitness_scorecard import content_failure_report, render_content_failure_report, score_switch_cohort
from role_fitness_stage import (
    DispatchEvidence,
    StageEvidenceError,
    StageOutcome,
    StageRequest,
    StageSetupError,
    StageTimeout,
)
from benchmark_role_fitness import build_split_handoff, validate_mechanical_result
from stage_smoke_home import StageError, materialize
import verify_dispatch as dispatch


CANDIDATES = {
    "luna_xhigh": ("gpt-5.6-luna", "xhigh"),
    "sol_high": ("gpt-5.6-sol", "high"),
}
CHECKPOINT_VERSION = "role-fitness-content-probe-v1"


RERUN_OF_RE = re.compile(r"^(?P<case_id>.+)#(?P<attempt>[1-9][0-9]*)$")


def _with_attempt(run_case: Any) -> Any:
    """Stamp a stage dict with `attempt` and, only on an operator rerun, `rerun_of`.

    The operator names a rerun by passing `attempt` (>= 2) and `rerun_of`
    (`<case_id>#<attempt>` of the INCONCLUSIVE stage being rerun) to the case
    function.  A first run passes neither, so it records `attempt: 1` and no
    `rerun_of`.  Nothing here, or anywhere in this module, calls a case function
    again by itself: every rerun is a separate, explicitly approved invocation
    (role-fitness SPEC no automatic retries; claude-eval-parity R11).
    """

    @functools.wraps(run_case)
    def wrapper(*args: Any, attempt: int = 1, rerun_of: str | None = None, **kwargs: Any) -> dict[str, Any]:
        if type(attempt) is not int or attempt < 1:
            raise BenchmarkContractError("stage attempt must be a positive integer")
        if rerun_of is None:
            if attempt != 1:
                raise BenchmarkContractError("a rerun attempt must name the stage it reruns")
        else:
            match = RERUN_OF_RE.fullmatch(rerun_of) if isinstance(rerun_of, str) else None
            if (
                match is None
                or match["case_id"] != kwargs.get("case_id")
                or int(match["attempt"]) >= attempt
            ):
                raise BenchmarkContractError("rerun_of must name an earlier attempt of the same case")
        stage = run_case(*args, **kwargs)
        stage["attempt"] = attempt
        if rerun_of is not None:
            stage["rerun_of"] = rerun_of
        return stage

    return wrapper


def build_matched_cohort(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project complete probe rows into the scorecard's anonymous pair shape."""
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        case_id = row.get("case_id")
        candidate = row.get("candidate")
        if not isinstance(case_id, str) or candidate not in CANDIDATES:
            raise BenchmarkContractError("content row identity is invalid")
        if candidate in grouped.setdefault(case_id, {}):
            raise BenchmarkContractError("duplicate content row")
        if row.get("status") == "accepted":
            arm = {
                "supported_findings": row["supported_findings"],
                "quality_score": row["quality_score"],
                "weighted_tokens": row["weighted_tokens"],
                "wall_seconds": row["wall_seconds"],
                "status": "accepted",
                "false_escalation": row["false_escalation"],
            }
            if isinstance(row.get("risk_coverage"), (int, float)) and not isinstance(row.get("risk_coverage"), bool):
                arm["risk_coverage"] = row["risk_coverage"]
        else:
            arm = {
                "supported_findings": 0,
                "quality_score": 0,
                "weighted_tokens": 1,
                "wall_seconds": max(float(row.get("wall_seconds", 0)), 0.001),
                "status": "inconclusive",
                "false_escalation": False,
            }
        grouped[case_id][candidate] = arm
    matched: list[dict[str, Any]] = []
    for case_id in sorted(grouped):
        pair = grouped[case_id]
        if set(pair) == set(CANDIDATES):
            matched.append({"case_id": case_id, "baseline": pair["luna_xhigh"], "switched": pair["sol_high"]})
    return matched


def _load_checkpoint(path: Path, case_ids: set[str]) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkContractError("content checkpoint is unreadable") from exc
    if not isinstance(value, dict) or value.get("version") != CHECKPOINT_VERSION or value.get("formal_claim") is not False or not isinstance(value.get("rows"), list):
        raise BenchmarkContractError("content checkpoint schema is invalid")
    rows = value["rows"]
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("case_id"), str) or row["case_id"] not in case_ids or row.get("candidate") not in CANDIDATES:
            raise BenchmarkContractError("content checkpoint row is invalid")
        if row.get("status") not in {"accepted", "inconclusive"}:
            raise BenchmarkContractError("content checkpoint row status is invalid")
        if row["status"] == "accepted":
            required = {"case_id", "candidate", "status", "wall_seconds", "weighted_tokens", "false_escalation", "supported_findings", "quality_score"}
            if set(row) < required or type(row["false_escalation"]) is not bool:
                raise BenchmarkContractError("content checkpoint accepted row is incomplete")
            for key in ("wall_seconds", "weighted_tokens", "supported_findings", "quality_score"):
                minimum = 0 if key in {"supported_findings", "quality_score"} else 0.000001
                if isinstance(row[key], bool) or not isinstance(row[key], (int, float)) or not math.isfinite(row[key]) or row[key] < minimum:
                    raise BenchmarkContractError("content checkpoint metric is invalid")
        identity = (row["case_id"], row["candidate"])
        if identity in seen:
            raise BenchmarkContractError("content checkpoint contains duplicate rows")
        seen.add(identity)
    return rows


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _message_texts(value: Any) -> list[str]:
    """Extract model-message text across current and older JSON event shapes."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        texts: list[str] = []
        for item in value:
            texts.extend(_message_texts(item))
        return texts
    if not isinstance(value, dict):
        return []
    texts: list[str] = []
    item_type = value.get("type")
    if item_type in {"agent_message", "output_text", "text", "input_text"} and isinstance(value.get("text"), str):
        texts.append(value["text"])
    if item_type == "agent_message" and isinstance(value.get("message"), str):
        texts.append(value["message"])
    content = value.get("content")
    if content is not None:
        texts.extend(_message_texts(content))
    return texts


def _messages(stdout: str) -> tuple[list[str], dict[str, int], dict[str, int]]:
    messages: list[str] = []
    event_counts: dict[str, int] = {}
    usage: dict[str, int] = {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type", "unknown")
        event_counts[kind] = event_counts.get(kind, 0) + 1
        if kind == "item.completed":
            messages.extend(_message_texts(event.get("item")))
        if kind == "response_item":
            messages.extend(_message_texts(event.get("payload")))
        if kind == "event_msg":
            messages.extend(_message_texts(event.get("payload")))
        if kind == "turn.completed":
            candidate = _find_usage(event.get("usage"))
            if candidate is not None:
                usage = candidate
        if kind == "event_msg":
            candidate = _find_usage(event.get("payload"))
            if candidate is not None:
                usage = candidate
    return messages, event_counts, usage


def _find_usage(value: Any) -> dict[str, int] | None:
    required = {"input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens"}
    if isinstance(value, dict):
        if required.issubset(value) and all(isinstance(value[key], int) and value[key] >= 0 for key in required):
            return {key: value[key] for key in required}
        for item in value.values():
            found = _find_usage(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_usage(item)
            if found is not None:
                return found
    return None


def _merge_usage(*usages: dict[str, int]) -> dict[str, int]:
    required = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens")
    merged = {key: 0 for key in required}
    for usage in usages:
        for key in required:
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                merged[key] += value
    return merged if any(merged.values()) else {}


def _event_shape_summary(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return bounded schema diagnostics without retaining model text."""
    summary: list[dict[str, Any]] = []
    for event in events:
        if len(summary) >= 12:
            break
        item = event.get("item") if isinstance(event.get("item"), dict) else event.get("payload")
        if isinstance(item, dict):
            summary.append({
                "event_type": event.get("type"),
                "item_type": item.get("type"),
                "item_keys": sorted(item)[:12],
                "content_types": [part.get("type") for part in item.get("content", []) if isinstance(part, dict)][:8],
            })
    return summary


def _parse_review(messages: list[str], ledger: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    for text in reversed(messages):
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                value = None
            else:
                try:
                    value = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    value = None
        if isinstance(value, dict) and set(value) == {"decision", "findings", "rationale"}:
            return value
        if ledger is not None:
            role_value = _parse_role_verdict(text, ledger)
            if role_value is not None:
                return role_value
    return None


def _parse_role_verdict(text: str, ledger: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Adapt the installed plan-verifier's native READY/REVISE contract."""
    stripped = re.sub(r"<[^>]+>", "", text).strip()
    revise_index = stripped.rfind("REVISE")
    if revise_index > 0:
        stripped = stripped[revise_index:]
    if stripped == "READY":
        return {"decision": "READY", "findings": [], "rationale": "native role returned READY"}
    if not stripped.startswith("REVISE"):
        return None
    body = stripped[len("REVISE"):]
    starts = [match.start() for match in re.finditer(r"(?:^|\n)\s*[-*]?\s*Blocker:", body)]
    blocks = [body[start:end].strip() for start, end in zip(starts, [*starts[1:], len(body)])]
    findings: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        fields: dict[str, str] = {}
        current: str | None = None
        for line in block.splitlines():
            match = re.match(r"^[-*]?\s*(Blocker|Evidence|Minimum revision|Acceptance check):\s*(.*)$", line.strip())
            if match:
                current = match.group(1)
                fields[current] = match.group(2).strip()
            elif current is not None and line.strip():
                fields[current] += " " + line.strip()
        required = {"Blocker", "Evidence", "Minimum revision", "Acceptance check"}
        if set(fields) != required or any(not value for value in fields.values()):
            return None
        haystack = " ".join(fields.values()).casefold()
        match = next((entry for entry in ledger if entry["anchor"].casefold() in haystack), None)
        findings.append({
            "severity": match["severity"] if match else "P1",
            "title": fields["Blocker"],
            "evidence": fields["Evidence"] + " " + fields["Acceptance check"],
            "revision_id": match["revision_id"] if match else f"native-revision-{index}",
        })
    return {"decision": "REVISE", "findings": findings, "rationale": "native role REVISE"} if findings else None


def _role_shape(text: str) -> dict[str, Any]:
    """Summarize role-verdict structure without exposing its contents."""
    stripped = re.sub(r"<[^>]+>", "", text).strip()
    index = stripped.rfind("REVISE")
    candidate = stripped[index:] if index >= 0 else stripped
    fields = [field for field in ("Blocker", "Evidence", "Minimum revision", "Acceptance check") if f"{field}:" in candidate]
    return {"prefix": candidate[:12], "length": len(candidate), "fields": fields, "field_count": len(fields), "blank_blocks": candidate.count("\n\n")}


def _weighted_tokens(usage: dict[str, int]) -> int | None:
    required = {"input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens"}
    if not required.issubset(usage):
        return None
    values = {key: usage[key] for key in required}
    if any(value < 0 for value in values.values()):
        return None
    return (
        values["input_tokens"]
        - values["cached_input_tokens"]
        - values["cache_write_input_tokens"]
        + values["cached_input_tokens"] * 0.1
        + values["cache_write_input_tokens"] * 1.25
        + values["output_tokens"]
    )


def _review_prompt(plan: str) -> str:
    return (
        "Review the Plan below independently and respect its stated scope. Do not invent risks, dependencies, or controls that are not relevant to the stated change. "
        "For a reversible non-production documentation or local-only change with no data migration or external dependency, return READY unless the Plan itself contains a concrete safety defect. "
        "For a production, data, schema, migration, release, security, or irreversible change, return REVISE only for concrete omissions that materially affect that stated change. "
        "Report only P0/P1 blockers with explicit evidence that the omission prevents safe execution; do not promote general best practices, optional hardening, or P2 advice into findings. "
        "Do not call tools, modify files, or delegate. "
        "Return exactly one JSON object with keys decision, findings, rationale. decision is READY or REVISE. "
        "findings is an array of objects with keys severity, title, evidence, revision_id; severity is P0, P1, or P2. "
        "For a clean Plan return READY and an empty findings array. No markdown.\n\n" + plan
    )


def _native_review_message(plan: str) -> str:
    """The host-neutral request the plan-verifier child receives."""
    return _review_prompt(plan).replace("Do not call tools, modify files, or delegate. ", "Do not call tools or modify files. ")


def _native_review_prompt(plan: str) -> str:
    """Ask the installed plan-verifier role for one machine-readable review."""
    message = _native_review_message(plan)
    return (
        "Call spawn_agent exactly once with the following message, using "
        "agent_type='plan-verifier', task_name='role_fitness_plan_review', "
        "fork_turns='none':\n\n" + message +
        "\n\nThen call wait_agent exactly once with timeout_ms=30000. "
        "Do not use an untyped fallback, a second spawn, or any child override."
    )


def _native_review_command(*, codex_bin: str, cwd: Path, prompt: str, sandbox_mode: str = "read-only") -> list[str]:
    return [
        codex_bin,
        "exec",
        "--enable",
        "multi_agent_v2",
        "--json",
        "--strict-config",
        "--skip-git-repo-check",
        "-C",
        str(cwd),
        "-m",
        "gpt-5.6-luna",
        "-c",
        'model_reasoning_effort="low"',
        "-s",
        sandbox_mode,
        prompt,
    ]


class CodexStageAdapter:
    """Run one stage through ``codex exec`` in a materialized private CODEX_HOME.

    ``model``/``effort`` apply to single-agent stages (``role`` is None); a
    native stage uses the fixed command from ``_native_review_command``.
    """

    def __init__(self, *, codex_bin: str, active_home: Path, model: str | None = None, effort: str | None = None) -> None:
        self.codex_bin = codex_bin
        self.active_home = active_home
        self.model = model
        self.effort = effort

    def _command(self, request: StageRequest) -> list[str]:
        if request.role is not None:
            return _native_review_command(
                codex_bin=self.codex_bin, cwd=request.workdir, prompt=request.prompt, sandbox_mode=request.sandbox,
            )
        return [
            self.codex_bin, "exec", "--json", "--strict-config", "--skip-git-repo-check", "-C", str(request.workdir),
            "-m", str(self.model), "-c", f'model_reasoning_effort="{self.effort}"', "-s", request.sandbox, request.prompt,
        ]

    def run_stage(self, request: StageRequest) -> StageOutcome:
        home = request.scratch / "codex-home"
        try:
            materialize(self.active_home, home)
        except StageError as exc:
            raise StageSetupError(str(exc)) from exc
        command = self._command(request)
        env = {**os.environ, "CODEX_HOME": str(home), "CODEX_SQLITE_HOME": str(home)}
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env, timeout=request.timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise StageTimeout() from exc
        elapsed = time.monotonic() - started
        if request.role is None:
            messages, event_counts, usage = _messages(completed.stdout)
            return StageOutcome(completed.returncode, messages, event_counts, usage, usage, [], elapsed, None)
        try:
            parent_id = dispatch.parse_exec_thread_id(completed.stdout)
            parent_events = dispatch.load_jsonl(dispatch.locate_rollout(home / "sessions", parent_id))
            child_id = dispatch.child_thread_from_parent(parent_events)
            child_events = dispatch.load_jsonl(dispatch.locate_rollout(home / "sessions", child_id))
            verdict = dispatch.inspect_dispatch(
                parent_events,
                child_events,
                expected_role=dispatch.read_role_binding(home / "agents" / f"{request.role}.toml"),
                expected_role_name=request.role,
                expected_task_name=request.task_name,
            )
        except (dispatch.EvidenceError, dispatch.ReceiptError, OSError) as exc:
            raise StageEvidenceError(type(exc).__name__) from exc
        messages, event_counts, child_usage = _messages("\n".join(json.dumps(event) for event in child_events))
        _, _, parent_usage = _messages("\n".join(json.dumps(event) for event in parent_events))
        evidence = DispatchEvidence(
            verdict.status == "NATIVE_OK", verdict.status, verdict.reason_code, verdict.model, verdict.reasoning_effort,
        )
        return StageOutcome(
            completed.returncode, messages, event_counts, _merge_usage(parent_usage, child_usage), child_usage,
            child_events, elapsed, evidence,
        )


def _codex_dispatch_prompt(*, role: str, task_name: str, message: str) -> str:
    """Codex parent prompt that hands ``message`` to one named role."""
    return (
        "Call spawn_agent exactly once with the following message, using "
        f"agent_type='{role}', task_name='{task_name}', fork_turns='none':\n\n"
        + message
        + "\nThen call wait_agent exactly once with timeout_ms=30000."
    )


def _stage_host(adapter: Any, dispatch_prompt: Any, active_home: Path | None, codex_bin: str | None) -> tuple[Any, Any]:
    """Pick the host of a native stage: Codex by default, or a caller-supplied one.

    Codex needs ``active_home`` and ``codex_bin`` and builds its own prompts
    (``dispatch_prompt`` None).  Another host passes its ``StageAdapter`` together
    with ``dispatch_prompt(role=, task_name=, message=)``, which wraps the same
    child message in that host's dispatch wording; the Codex arguments must then
    be absent, so a stage can never be half one host and half another.
    """
    if adapter is None and dispatch_prompt is None:
        if active_home is None or codex_bin is None:
            raise BenchmarkContractError("codex stage needs active_home and codex_bin")
        return CodexStageAdapter(codex_bin=codex_bin, active_home=active_home), None
    if adapter is None or not callable(dispatch_prompt) or active_home is not None or codex_bin is not None:
        raise BenchmarkContractError("stage host arguments are inconsistent")
    return adapter, dispatch_prompt


def _run_stage(adapter: Any, request: StageRequest, setup_failure: str) -> StageOutcome:
    """Run a stage, reporting a setup failure as a contract error."""
    try:
        return adapter.run_stage(request)
    except StageSetupError as exc:
        raise BenchmarkContractError(f"{setup_failure}: {exc}") from exc


@_with_attempt
def run_native_review_case(
    *,
    private_root: Path,
    active_home: Path | None = None,
    codex_bin: str | None = None,
    case_id: str,
    timeout: int = 360,
    adapter: Any = None,
    dispatch_prompt: Any = None,
) -> dict[str, Any]:
    """Run one native plan-verifier child and score only its child rollout."""
    host, wrap = _stage_host(adapter, dispatch_prompt, active_home, codex_bin)
    manifest = json.loads((private_root / "manifest.json").read_text(encoding="utf-8"))
    case = next((item for item in manifest["cases"] if item.get("case_id") == case_id), None)
    if not isinstance(case, dict) or case.get("cohort") not in {"plan_review", "split_workflow"}:
        raise BenchmarkContractError("native content case is not a plan fixture")
    plan = (private_root / "fixtures" / f"{case_id}.md").read_text(encoding="utf-8")
    ledger = json.loads((private_root / "ledgers.json").read_text(encoding="utf-8"))[case_id]
    directory = Path(tempfile.mkdtemp(prefix=f"shoal-native-content-{case_id}-"))
    try:
        cwd = directory / "clean-cwd"
        cwd.mkdir()
        prompt = _native_review_prompt(plan) if wrap is None else wrap(
            role="plan-verifier", task_name="role_fitness_plan_review", message=_native_review_message(plan),
        )
        request = StageRequest(
            prompt=prompt, role="plan-verifier", sandbox="read-only", workdir=cwd,
            scratch=directory, timeout=timeout, task_name="role_fitness_plan_review",
        )
        try:
            stage = _run_stage(host, request, "native content stage materialization failed")
        except StageTimeout:
            return {"case_id": case_id, "status": "inconclusive", "reason": "timeout", "native_role": "plan-verifier"}
        except StageEvidenceError as exc:
            return {"case_id": case_id, "status": "inconclusive", "reason": "native_evidence_unavailable", "detail": exc.detail}
        verdict, elapsed, usage, event_counts, messages = stage.evidence, stage.wall_seconds, stage.usage, stage.event_counts, stage.messages
        output = _parse_review(messages, ledger)
        weighted_tokens = _weighted_tokens(usage)
        if not verdict.ok or stage.returncode != 0 or output is None or weighted_tokens is None or weighted_tokens <= 0:
            return {
                "case_id": case_id,
                "status": "inconclusive",
                "reason": "invalid_native_review_output",
                "dispatch_status": verdict.status,
                "dispatch_reason": verdict.reason_code,
                "wall_seconds": round(elapsed, 3),
                "event_types": event_counts,
                "message_count": len(messages),
                "message_signals": [
                    {
                        "length": len(text),
                        "has_decision": "decision" in text,
                        "has_findings": "findings" in text,
                        "has_revise": "REVISE" in text,
                        "field_count": sum(text.count(f"{field}:") for field in ("Blocker", "Evidence", "Minimum revision", "Acceptance check")),
                        "first": text.lstrip()[:1],
                        "last": text.rstrip()[-1:],
                    }
                    for text in messages[-8:]
                ],
                "event_shapes": _event_shape_summary(stage.events),
                "role_shapes": [_role_shape(text) for text in messages[-8:]],
            }
        score = score_plan_review(ledger, output)
        return {
            "case_id": case_id,
            "status": "accepted",
            "native_role": "plan-verifier",
            "model": verdict.model,
            "reasoning_effort": verdict.reasoning_effort,
            "dispatch_status": verdict.status,
            "dispatch_reason": verdict.reason_code,
            "wall_seconds": round(elapsed, 3),
            "usage": usage,
            "weighted_tokens": weighted_tokens,
            "event_types": event_counts,
            "false_escalation": score["false_escalation"],
            "supported_findings": score["supported_findings"],
            "quality_score": _quality_score(score),
            "score": score,
            "risk_coverage": score["risk_coverage"],
            "review_output": output,
        }
    finally:
        _remove(directory)


@_with_attempt
def run_native_mechanical_case(
    *,
    private_root: Path,
    active_home: Path | None = None,
    codex_bin: str | None = None,
    case_id: str,
    timeout: int = 360,
    adapter: Any = None,
    dispatch_prompt: Any = None,
) -> dict[str, Any]:
    """Run one native mech-executor child and validate its declared artifact."""
    host, wrap = _stage_host(adapter, dispatch_prompt, active_home, codex_bin)
    manifest = json.loads((private_root / "manifest.json").read_text(encoding="utf-8"))
    case = next((item for item in manifest["cases"] if item.get("case_id") == case_id), None)
    if not isinstance(case, dict) or case.get("cohort") != "mechanical_execution":
        raise BenchmarkContractError("native mechanical case is not in the fixture manifest")
    fixture = json.loads((private_root / "fixtures" / f"{case_id}.json").read_text(encoding="utf-8"))
    directory = Path(tempfile.mkdtemp(prefix=f"shoal-native-mechanical-{case_id}-"))
    task_name = "role_fitness_mechanical_execution"
    message = (
        "Work only in the current isolated directory. Execute the fixture exactly. "
        "Create result.json with exactly this JSON object and no other files: "
        + json.dumps({"case_id": case_id, "accepted": True}, sort_keys=True)
        + "\nFixture:\n" + json.dumps(fixture, sort_keys=True)
    )
    prompt = (wrap or _codex_dispatch_prompt)(role="mech-executor", task_name=task_name, message=message)
    try:
        cwd = directory / "clean-cwd"
        cwd.mkdir()
        request = StageRequest(
            prompt=prompt, role="mech-executor", sandbox="workspace-write", workdir=cwd,
            scratch=directory, timeout=timeout, task_name=task_name,
        )
        try:
            stage = _run_stage(host, request, "native mechanical stage materialization failed")
        except StageTimeout:
            return {"case_id": case_id, "status": "inconclusive", "reason": "timeout", "native_role": "mech-executor"}
        except StageEvidenceError as exc:
            return {"case_id": case_id, "status": "inconclusive", "reason": "native_evidence_unavailable", "detail": exc.detail}
        verdict, elapsed, usage, event_counts = stage.evidence, stage.wall_seconds, stage.child_usage, stage.event_counts
        result_path = cwd / "result.json"
        result: dict[str, Any] | None = None
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            validate_mechanical_result(case_id, result)
        except (OSError, json.JSONDecodeError, BenchmarkContractError):
            result = None
        weighted_tokens = _weighted_tokens(usage)
        if not verdict.ok or stage.returncode != 0 or result is None or weighted_tokens is None:
            return {
                "case_id": case_id,
                "status": "inconclusive",
                "reason": "invalid_native_mechanical_acceptance",
                "dispatch_status": verdict.status,
                "dispatch_reason": verdict.reason_code,
                "wall_seconds": round(elapsed, 3),
                "event_types": event_counts,
            }
        return {
            "case_id": case_id,
            "status": "accepted",
            "native_role": "mech-executor",
            "model": verdict.model,
            "reasoning_effort": verdict.reasoning_effort,
            "dispatch_status": verdict.status,
            "dispatch_reason": verdict.reason_code,
            "wall_seconds": round(elapsed, 3),
            "usage": usage,
            "weighted_tokens": weighted_tokens,
            "event_types": event_counts,
            "accepted": True,
        }
    finally:
        _remove(directory)


@_with_attempt
def run_native_verifier_case(
    *,
    private_root: Path,
    active_home: Path | None = None,
    codex_bin: str | None = None,
    case_id: str,
    timeout: int = 360,
    adapter: Any = None,
    dispatch_prompt: Any = None,
) -> dict[str, Any]:
    """Run an independent verifier against an identity-free accepted artifact."""
    host, wrap = _stage_host(adapter, dispatch_prompt, active_home, codex_bin)
    manifest = json.loads((private_root / "manifest.json").read_text(encoding="utf-8"))
    case = next((item for item in manifest["cases"] if item.get("case_id") == case_id), None)
    if not isinstance(case, dict) or case.get("cohort") not in {"mechanical_execution", "split_workflow"}:
        raise BenchmarkContractError("native verifier case is not executable")
    directory = Path(tempfile.mkdtemp(prefix=f"shoal-native-verifier-{case_id}-"))
    task_name = "role_fitness_mechanical_verification"
    message = (
        "Contract: outcome_verification. The artifact is already present in the child "
        "cwd; read result.json directly and do not look for any other evidence. "
        "The exact claim is: the mechanical executor produced the declared artifact. "
        "Acceptance condition: result.json is "
        f"exactly {json.dumps({'case_id': case_id, 'accepted': True}, sort_keys=True)}; "
        "After reading it, return CONFIRMED with the observed case_id and accepted "
        "value when it matches; otherwise return REFUTED with the mismatch. "
        "Do not modify files or delegate."
    )
    prompt = (wrap or _codex_dispatch_prompt)(role="verifier", task_name=task_name, message=message)
    try:
        cwd = directory / "clean-cwd"
        cwd.mkdir()
        (cwd / "result.json").write_text(json.dumps({"case_id": case_id, "accepted": True}) + "\n", encoding="utf-8")
        request = StageRequest(
            prompt=prompt, role="verifier", sandbox="workspace-write", workdir=cwd,
            scratch=directory, timeout=timeout, task_name=task_name,
        )
        try:
            stage = _run_stage(host, request, "native verifier stage materialization failed")
        except StageTimeout:
            return {"case_id": case_id, "status": "inconclusive", "reason": "timeout", "native_role": "verifier"}
        except StageEvidenceError as exc:
            return {"case_id": case_id, "status": "inconclusive", "reason": "native_evidence_unavailable", "detail": exc.detail}
        verdict, elapsed, usage, event_counts, messages = stage.evidence, stage.wall_seconds, stage.usage, stage.event_counts, stage.messages
        statuses = [
            match.group(1)
            for message in messages
            for match in re.finditer(r"\b(CONFIRMED|REFUTED|INCONCLUSIVE)\b", re.sub(r"<[^>]+>", "", message))
        ]
        verification = statuses[-1] if statuses else "INCONCLUSIVE"
        weighted_tokens = _weighted_tokens(usage)
        if not verdict.ok or stage.returncode != 0 or verification != "CONFIRMED" or weighted_tokens is None:
            return {
                "case_id": case_id,
                "status": "inconclusive",
                "reason": "verifier_did_not_confirm",
                "dispatch_status": verdict.status,
                "dispatch_reason": verdict.reason_code,
                "verification": verification,
                "status_candidates": statuses[-8:],
                "wall_seconds": round(elapsed, 3),
                "event_types": event_counts,
            }
        return {
            "case_id": case_id,
            "status": "accepted",
            "native_role": "verifier",
            "model": verdict.model,
            "reasoning_effort": verdict.reasoning_effort,
            "dispatch_status": verdict.status,
            "dispatch_reason": verdict.reason_code,
            "verification": verification,
            "wall_seconds": round(elapsed, 3),
            "usage": usage,
            "weighted_tokens": weighted_tokens,
            "event_types": event_counts,
        }
    finally:
        _remove(directory)


@_with_attempt
def run_native_split_executor_case(
    *,
    active_home: Path | None = None,
    codex_bin: str | None = None,
    case_id: str,
    handoff: dict[str, Any],
    timeout: int = 360,
    adapter: Any = None,
    dispatch_prompt: Any = None,
) -> dict[str, Any]:
    """Execute one already-approved split handoff through mech-executor."""
    host, wrap = _stage_host(adapter, dispatch_prompt, active_home, codex_bin)
    if handoff.get("scenario_id") != case_id:
        raise BenchmarkContractError("split executor handoff identity is invalid")
    directory = Path(tempfile.mkdtemp(prefix=f"shoal-native-split-executor-{case_id}-"))
    task_name = "role_fitness_split_execution"
    message = (
        "Execute only the approved split handoff below in the current isolated directory. "
        "Create result.json with exactly " + json.dumps({"case_id": case_id, "accepted": True}, sort_keys=True) + " after "
        "the approved revision fragments are applied. Do not modify any other file.\n"
        + json.dumps(handoff, sort_keys=True)
    )
    prompt = (wrap or _codex_dispatch_prompt)(role="mech-executor", task_name=task_name, message=message)
    try:
        cwd = directory / "clean-cwd"
        cwd.mkdir()
        request = StageRequest(
            prompt=prompt, role="mech-executor", sandbox="workspace-write", workdir=cwd,
            scratch=directory, timeout=timeout, task_name=task_name,
        )
        stage = _run_stage(host, request, "native split executor materialization failed")
        verdict, elapsed, usage, event_counts = stage.evidence, stage.wall_seconds, stage.usage, stage.event_counts
        result = None
        try:
            result = json.loads((cwd / "result.json").read_text(encoding="utf-8"))
            validate_mechanical_result(case_id, result)
        except (OSError, json.JSONDecodeError, BenchmarkContractError):
            pass
        weighted_tokens = _weighted_tokens(usage)
        if not verdict.ok or stage.returncode != 0 or result is None or weighted_tokens is None:
            return {"case_id": case_id, "status": "inconclusive", "reason": "invalid_split_executor_acceptance", "dispatch_status": verdict.status, "dispatch_reason": verdict.reason_code, "wall_seconds": round(elapsed, 3), "event_types": event_counts}
        return {"case_id": case_id, "status": "accepted", "native_role": "mech-executor", "model": verdict.model, "reasoning_effort": verdict.reasoning_effort, "dispatch_status": verdict.status, "dispatch_reason": verdict.reason_code, "accepted": True, "wall_seconds": round(elapsed, 3), "usage": usage, "weighted_tokens": weighted_tokens, "event_types": event_counts}
    finally:
        _remove(directory)


def _quality_score(score: dict[str, Any]) -> float:
    """Apply the SPEC's Planning Quality Score weights exactly."""
    return 100 * (
        0.50 * score["risk_coverage"]
        + 0.25 * score["critical_precision"]
        + 0.25 * score["actionable_revision"]
    )


def _remove(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except OSError as exc:
        raise BenchmarkContractError("content probe cleanup failed") from exc
    if path.exists() or path.is_symlink():
        raise BenchmarkContractError("content probe cleanup incomplete")


@_with_attempt
def run_review_case(
    *,
    private_root: Path,
    active_home: Path,
    codex_bin: str,
    case_id: str,
    candidate: str,
    timeout: int = 360,
    prompt_override: str | None = None,
    model_effort_override: tuple[str, str] | None = None,
) -> dict[str, Any]:
    if candidate not in CANDIDATES:
        raise BenchmarkContractError("unknown content candidate")
    manifest = json.loads((private_root / "manifest.json").read_text(encoding="utf-8"))
    case = next((item for item in manifest["cases"] if item["case_id"] == case_id), None)
    if not isinstance(case, dict) or case["cohort"] != "plan_review":
        raise BenchmarkContractError("content case is not a plan fixture")
    plan = (private_root / "fixtures" / f"{case_id}.md").read_text(encoding="utf-8")
    ledger = json.loads((private_root / "ledgers.json").read_text(encoding="utf-8"))[case_id]
    model, effort = model_effort_override or CANDIDATES[candidate]
    prompt = prompt_override if prompt_override is not None else _review_prompt(plan)
    directory = Path(tempfile.mkdtemp(prefix=f"shoal-content-{case_id}-{candidate}-"))
    try:
        cwd = directory / "clean-cwd"
        cwd.mkdir()
        request = StageRequest(prompt=prompt, role=None, sandbox="read-only", workdir=cwd, scratch=directory, timeout=timeout)
        try:
            stage = _run_stage(
                CodexStageAdapter(codex_bin=codex_bin, active_home=active_home, model=model, effort=effort),
                request, "content stage materialization failed",
            )
        except StageTimeout:
            return {"case_id": case_id, "candidate": candidate, "status": "inconclusive", "reason": "timeout"}
        elapsed, messages, event_counts, usage = stage.wall_seconds, stage.messages, stage.event_counts, stage.usage
        output = _parse_review(messages)
        weighted_tokens = _weighted_tokens(usage)
        if stage.returncode != 0 or output is None or weighted_tokens is None or weighted_tokens <= 0:
            return {"case_id": case_id, "candidate": candidate, "status": "inconclusive", "reason": "invalid_review_output", "wall_seconds": round(elapsed, 3), "event_types": event_counts}
        score = score_plan_review(ledger, output)
        quality_score = _quality_score(score)
        return {
            "case_id": case_id,
            "candidate": candidate,
            "status": "accepted",
            "wall_seconds": round(elapsed, 3),
            "usage": usage,
            "weighted_tokens": weighted_tokens,
            "event_types": event_counts,
            "false_escalation": score["false_escalation"],
            "supported_findings": score["supported_findings"],
            "quality_score": quality_score,
            "score": score,
            "review_output": output,
        }
    finally:
        _remove(directory)


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--active-codex-home", type=Path, required=True)
    parser.add_argument("--codex-bin", required=True)
    parser.add_argument("--case-id", action="append", required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeat-label", default="R1", help="repeat this run belongs to (R1..R3) in the failure report")
    args = parser.parse_args(argv)
    if not args.live or not args.yes:
        parser.error("content probe requires both --live and --yes")
    if args.resume and args.checkpoint is None:
        parser.error("--resume requires --checkpoint")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if not re.fullmatch(r"R[1-9][0-9]*", args.repeat_label):
        parser.error("--repeat-label must look like R1")
    validate_bundle(args.private_root)
    rows: list[dict[str, Any]] = _load_checkpoint(args.checkpoint, set(args.case_id)) if args.resume and args.checkpoint else []
    completed = {(row["case_id"], row["candidate"]) for row in rows}
    for case_id in args.case_id:
        for candidate in CANDIDATES:
            if (case_id, candidate) in completed:
                continue
            row = run_review_case(
                private_root=args.private_root,
                active_home=args.active_codex_home,
                codex_bin=args.codex_bin,
                case_id=case_id,
                candidate=candidate,
                timeout=args.timeout,
            )
            rows.append(row)
            if args.checkpoint:
                _write_report(args.checkpoint, {"version": CHECKPOINT_VERSION, "formal_claim": False, "rows": rows})
    by_arm: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        by_arm.setdefault(row["candidate"], {args.repeat_label: []})[args.repeat_label].append(row)
    matched = build_matched_cohort(rows)
    switch_score = score_switch_cohort(matched) if len(matched) == len(args.case_id) else None
    report = {
        "version": CHECKPOINT_VERSION,
        "formal_claim": False,
        "rows": rows,
        "matched_cohort": matched,
        "switch_score": switch_score,
        "failure_report": content_failure_report(by_arm),
    }
    if args.output:
        _write_report(args.output, report)
    return report


if __name__ == "__main__":
    try:
        result = main()
        json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
        print(render_content_failure_report(result["failure_report"]), file=sys.stderr)
    except BenchmarkContractError as exc:
        print(f"content_probe_failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
