#!/usr/bin/env python3
"""Run a bounded native typed Sol adjudicator slice after Luna reviews."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

from benchmark_role_fitness import validate_mechanical_result
from role_fitness_fixtures import BenchmarkContractError, score_plan_review, validate_bundle
from role_fitness_scorecard import score_switch_cohort
from run_role_fitness_adjudicator import _fingerprint_disagrees, _needs_verifier, _verifier_prompt
from run_role_fitness_content import (
    _merge_usage,
    _messages,
    _native_review_command,
    _parse_review,
    _quality_score,
    _remove,
    _review_prompt,
    _weighted_tokens,
    run_review_case,
    _write_report,
)
from stage_smoke_home import StageError, materialize
import verify_dispatch as dispatch


VERSION = "role-fitness-native-adjudicator-v2"


def _prompt(plan: str, primary: dict[str, Any], verifier: dict[str, Any]) -> str:
    message = (
        "Act as a one-shot Sol adjudicator. Resolve the semantic disagreement between two anonymous Luna verdicts for the same Plan. "
        "Do not invent risks, use external evidence, or repair missing evidence. Preserve every concrete blocker from either verdict when its evidence is present in the Plan; do not drop a supported blocker merely because the other verdict omitted it. Return exactly the installed plan-verifier contract: either READY, or REVISE followed by one or more blocks with the exact fields Blocker:, Evidence:, Minimum revision:, and Acceptance check:. "
        "Do not return JSON, markdown fences, extra headings, or commentary. Do not call tools, modify files, delegate, or mention model identities.\n\n"
        f"Verdict A:\n{json.dumps(primary, sort_keys=True)}\n\n"
        f"Verdict B:\n{json.dumps(verifier, sort_keys=True)}\n\nPlan:\n{plan}"
    )
    return (
        "Call spawn_agent exactly once with the following message, using "
        "agent_type='plan-verifier', task_name='role_fitness_adjudication', fork_turns='none':\n\n"
        + message
        + "\n\nThen call wait_agent exactly once with timeout_ms=30000. Do not use an untyped fallback or a second spawn."
    )


def _native_case(*, private_root: Path, active_home: Path, codex_bin: str, case_id: str, primary: dict[str, Any], verifier: dict[str, Any], timeout: int) -> dict[str, Any]:
    manifest = json.loads((private_root / "manifest.json").read_text(encoding="utf-8"))
    plan = (private_root / "fixtures" / f"{case_id}.md").read_text(encoding="utf-8")
    ledger = json.loads((private_root / "ledgers.json").read_text(encoding="utf-8"))[case_id]
    directory = Path(tempfile.mkdtemp(prefix=f"shoal-native-adjudicator-{case_id}-"))
    try:
        home = directory / "codex-home"
        cwd = directory / "clean-cwd"
        cwd.mkdir()
        try:
            materialize(active_home, home)
        except StageError as exc:
            raise BenchmarkContractError(f"native adjudicator materialization failed: {exc}") from exc
        env = {**os.environ, "CODEX_HOME": str(home), "CODEX_SQLITE_HOME": str(home)}
        started = time.monotonic()
        completed = subprocess.run(
            _native_review_command(codex_bin=codex_bin, cwd=cwd, prompt=_prompt(plan, primary, verifier), sandbox_mode="read-only"),
            capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env, timeout=timeout, check=False,
        )
        elapsed = time.monotonic() - started
        parent_id = dispatch.parse_exec_thread_id(completed.stdout)
        parent_events = dispatch.load_jsonl(dispatch.locate_rollout(home / "sessions", parent_id))
        child_id = dispatch.child_thread_from_parent(parent_events)
        child_events = dispatch.load_jsonl(dispatch.locate_rollout(home / "sessions", child_id))
        receipt = dispatch.inspect_dispatch(
            parent_events, child_events,
            expected_role=dispatch.read_role_binding(home / "agents" / "plan-verifier.toml"),
            expected_role_name="plan-verifier", expected_task_name="role_fitness_adjudication",
        )
        child_messages, event_types, child_usage = _messages("\n".join(json.dumps(event) for event in child_events))
        _, _, parent_usage = _messages("\n".join(json.dumps(event) for event in parent_events))
        usage = _merge_usage(parent_usage, child_usage)
        output = _parse_review(child_messages, ledger)
        weighted_tokens = _weighted_tokens(usage)
        if receipt.status != "NATIVE_OK" or completed.returncode != 0 or output is None or weighted_tokens is None:
            return {"case_id": case_id, "status": "inconclusive", "reason": "invalid_native_adjudicator", "dispatch_status": receipt.status, "dispatch_reason": receipt.reason_code, "wall_seconds": round(elapsed, 3), "event_types": event_types}
        score = score_plan_review(ledger, output)
        return {
            "case_id": case_id, "status": "accepted", "native_role": "plan-verifier", "model": receipt.model, "reasoning_effort": receipt.reasoning_effort,
            "dispatch_status": receipt.status, "dispatch_reason": receipt.reason_code, "weighted_tokens": weighted_tokens, "wall_seconds": round(elapsed, 3),
            "supported_findings": score["supported_findings"], "quality_score": _quality_score(score), "false_escalation": score["false_escalation"], "risk_coverage": score["risk_coverage"],
        }
    except (dispatch.EvidenceError, dispatch.ReceiptError, OSError, subprocess.TimeoutExpired) as exc:
        return {"case_id": case_id, "status": "inconclusive", "reason": type(exc).__name__}
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
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.live or not args.yes:
        parser.error("native adjudicator requires both --live and --yes")
    validate_bundle(args.private_root)
    rows = []
    for case_id in args.case_id:
        primary = run_review_case(private_root=args.private_root, active_home=args.active_codex_home, codex_bin=args.codex_bin, case_id=case_id, candidate="luna_xhigh", timeout=args.timeout)
        primary_output = primary.get("review_output", {})
        if primary.get("status") != "accepted" or not _needs_verifier(primary_output):
            rows.append({"case_id": case_id, "primary": primary, "verifier": None, "native_adjudicator": None, "disagreement": False, "route": "luna_only"})
            continue
        plan = (args.private_root / "fixtures" / f"{case_id}.md").read_text(encoding="utf-8")
        verifier = run_review_case(private_root=args.private_root, active_home=args.active_codex_home, codex_bin=args.codex_bin, case_id=case_id, candidate="luna_xhigh", timeout=args.timeout, prompt_override=_verifier_prompt(plan, primary_output))
        if verifier.get("status") != "accepted":
            rows.append({"case_id": case_id, "primary": primary, "verifier": verifier, "native_adjudicator": None, "disagreement": None, "route": "inconclusive"})
            continue
        verifier_output = verifier["review_output"]
        disagreement = _fingerprint_disagrees(primary_output, verifier_output)
        native = None
        route = "luna_verified"
        if disagreement:
            native = _native_case(private_root=args.private_root, active_home=args.active_codex_home, codex_bin=args.codex_bin, case_id=case_id, primary=primary_output, verifier=verifier_output, timeout=args.timeout)
            route = "native_sol_adjudicator" if native.get("status") == "accepted" else "inconclusive"
        rows.append({"case_id": case_id, "primary": primary, "verifier": verifier, "native_adjudicator": native, "disagreement": disagreement, "route": route})
    risk_case_ids = {item["case_id"] for item in json.loads((args.private_root / "manifest.json").read_text(encoding="utf-8")).get("cases", []) if not item.get("clean_control", False)}
    matched = []
    for row in rows:
        primary = row["primary"]
        verifier = row.get("verifier")
        native = row.get("native_adjudicator")
        if primary.get("status") != "accepted" or row["route"] == "inconclusive":
            continue
        final = primary
        extra_tokens = 0
        extra_wall = 0.0
        if verifier is not None:
            extra_tokens += verifier.get("weighted_tokens", 0)
            extra_wall += verifier.get("wall_seconds", 0.0)
        if native is not None and native.get("status") == "accepted":
            final = native
            extra_tokens += native.get("weighted_tokens", 0)
            extra_wall += native.get("wall_seconds", 0.0)
        baseline = {key: primary[key] for key in ("quality_score", "supported_findings", "weighted_tokens", "wall_seconds", "status", "false_escalation")}
        baseline["risk_coverage"] = primary.get("risk_coverage", primary.get("score", {}).get("risk_coverage", 0))
        switched = {key: final[key] for key in ("quality_score", "supported_findings", "status", "false_escalation")}
        switched["risk_coverage"] = final.get("risk_coverage", final.get("score", {}).get("risk_coverage", 0))
        switched["weighted_tokens"] = primary["weighted_tokens"] + extra_tokens
        switched["wall_seconds"] = primary["wall_seconds"] + extra_wall
        matched.append({"case_id": row["case_id"], "baseline": baseline, "switched": switched})
    score = score_switch_cohort(matched, risk_case_ids=risk_case_ids) if len(matched) == len(rows) else None
    report = {"version": VERSION, "formal_claim": False, "rows": rows, "matched_cohort": matched, "switch_score": score, "native_adjudications": sum((row["native_adjudicator"] or {}).get("status") == "accepted" for row in rows), "routes": {route: sum(row["route"] == route for row in rows) for route in sorted({row["route"] for row in rows})}}
    _write_report(args.output, report)
    return report


if __name__ == "__main__":
    main()
