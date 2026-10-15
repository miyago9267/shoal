#!/usr/bin/env python3
"""Run a bounded Luna-verifier / one-shot Sol-adjudicator live cohort."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from role_fitness_fixtures import BenchmarkContractError, validate_bundle
from role_fitness_scorecard import score_switch_cohort
from run_role_fitness_content import _review_prompt, run_review_case, _write_report


VERSION = "role-fitness-adjudicator-live-v2"


def _verifier_prompt(plan: str, primary: dict[str, Any]) -> str:
    return (
        "Act as the independent Luna verifier for the Plan below. Review the Plan and the first anonymous verdict. "
        "Return exactly one JSON object with keys decision, findings, rationale. "
        "Use READY only when the first verdict is supported and the Plan has no concrete P0/P1 blocker. "
        "Use REVISE only for concrete P0/P1 omissions relevant to the stated Plan; do not invent risks. "
        "Findings must contain severity, title, evidence, revision_id. Do not call tools, modify files, or delegate.\n\n"
        f"First anonymous verdict:\n{json.dumps(primary, sort_keys=True)}\n\nPlan:\n{plan}"
    )


def _adjudicator_prompt(plan: str, primary: dict[str, Any], verifier: dict[str, Any]) -> str:
    return (
        "Act as a one-shot Sol adjudicator. Resolve the semantic disagreement between two anonymous Luna verdicts for the same Plan. "
        "Do not invent risks, use external evidence, or repair missing evidence. Return exactly one JSON object with keys decision, findings, rationale. "
        "Preserve a valid finding only when its evidence is present in the Plan; otherwise return READY or an empty finding set. "
        "Do not call tools, modify files, delegate, or mention model identities.\n\n"
        f"Verdict A:\n{json.dumps(primary, sort_keys=True)}\n\n"
        f"Verdict B:\n{json.dumps(verifier, sort_keys=True)}\n\nPlan:\n{plan}"
    )


def _fingerprint_disagrees(primary: dict[str, Any], verifier: dict[str, Any]) -> bool:
    if primary.get("decision") != verifier.get("decision"):
        return True
    def findings(value: dict[str, Any]) -> set[tuple[str, str]]:
        return {
            (
                str(item.get("revision_id")),
                str(item.get("title", "")).strip().casefold(),
            )
            for item in value.get("findings", [])
            if isinstance(item, dict)
        }
    return findings(primary) != findings(verifier)


def _needs_verifier(review: dict[str, Any]) -> bool:
    """Skip only an explicitly clean READY; risk-bearing REVISE needs review."""
    return not (review.get("decision") == "READY" and not review.get("findings"))


def _arm(row: dict[str, Any], *, extra_tokens: int = 0, extra_wall: float = 0.0) -> dict[str, Any]:
    arm = {
        "supported_findings": row["supported_findings"],
        "quality_score": row["quality_score"],
        "weighted_tokens": row["weighted_tokens"] + extra_tokens,
        "wall_seconds": row["wall_seconds"] + extra_wall,
        "status": row["status"],
        "false_escalation": row["false_escalation"],
    }
    if isinstance(row.get("risk_coverage"), (int, float)) and not isinstance(row.get("risk_coverage"), bool):
        arm["risk_coverage"] = row["risk_coverage"]
    return arm


def _report_arm(row: dict[str, Any], *, include_status: bool) -> dict[str, Any]:
    """Project optional fixture metrics without inventing risk coverage."""
    keys = ["quality_score", "supported_findings", "weighted_tokens", "wall_seconds", "false_escalation"]
    if include_status:
        keys.append("status")
    projected = {key: row[key] for key in keys}
    if "risk_coverage" in row:
        projected["risk_coverage"] = row["risk_coverage"]
    return projected


def run_adjudicator_case(
    *, private_root: Path, active_home: Path, codex_bin: str, case_id: str, timeout: int
) -> dict[str, Any]:
    manifest = json.loads((private_root / "manifest.json").read_text(encoding="utf-8"))
    case = next((item for item in manifest["cases"] if item.get("case_id") == case_id), None)
    if not isinstance(case, dict) or case.get("cohort") != "plan_review":
        raise BenchmarkContractError("adjudicator case is not a plan-review fixture")
    plan = (private_root / "fixtures" / f"{case_id}.md").read_text(encoding="utf-8")
    primary = run_review_case(
        private_root=private_root, active_home=active_home, codex_bin=codex_bin,
        case_id=case_id, candidate="luna_xhigh", timeout=timeout,
    )
    if primary.get("status") != "accepted":
        return {"case_id": case_id, "status": "inconclusive", "reason": "primary_luna_failed", "primary": primary}
    if not _needs_verifier(primary["review_output"]):
        primary_arm = _report_arm(primary, include_status=True)
        return {
            "case_id": case_id,
            "status": "accepted",
            "verifier_skipped": True,
            "disagreement": False,
            "adjudicated": False,
            "primary": primary_arm,
            "primary_verdict": primary["review_output"],
            "verifier": None,
            "adjudicator": None,
            "final": primary_arm,
            "switched_arm": _arm(primary),
        }
    verifier = run_review_case(
        private_root=private_root, active_home=active_home, codex_bin=codex_bin,
        case_id=case_id, candidate="luna_xhigh", timeout=timeout,
        prompt_override=_verifier_prompt(plan, primary["review_output"]),
    )
    if verifier.get("status") != "accepted":
        return {"case_id": case_id, "status": "inconclusive", "reason": "luna_verifier_failed", "primary": primary}
    disagreement = _fingerprint_disagrees(primary["review_output"], verifier["review_output"])
    # The verifier checks the primary output; it does not replace it when the
    # two Luna views agree. Only a material disagreement is eligible for Sol.
    final = primary
    adjudicator = None
    if disagreement:
        adjudicator = run_review_case(
            private_root=private_root, active_home=active_home, codex_bin=codex_bin,
            case_id=case_id, candidate="sol_high", timeout=timeout,
            prompt_override=_adjudicator_prompt(plan, primary["review_output"], verifier["review_output"]),
        )
        if adjudicator.get("status") != "accepted":
            return {"case_id": case_id, "status": "inconclusive", "reason": "sol_adjudicator_failed", "primary": primary, "verifier": verifier, "disagreement": True}
        final = adjudicator
    total_tokens = verifier["weighted_tokens"] + (adjudicator["weighted_tokens"] if adjudicator else 0)
    total_wall = verifier["wall_seconds"] + (adjudicator["wall_seconds"] if adjudicator else 0)
    return {
        "case_id": case_id,
        "status": "accepted",
        "disagreement": disagreement,
        "adjudicated": adjudicator is not None,
        "primary": _report_arm(primary, include_status=True),
        "primary_verdict": primary["review_output"],
        "verifier_verdict": verifier["review_output"],
        "verifier": _report_arm(verifier, include_status=False),
        "adjudicator": None if adjudicator is None else _report_arm(adjudicator, include_status=False),
        "final": _report_arm(final, include_status=True),
        "switched_arm": _arm(
            final,
            extra_tokens=primary["weighted_tokens"] + (0 if adjudicator is None else verifier["weighted_tokens"]),
            extra_wall=primary["wall_seconds"] + (0 if adjudicator is None else verifier["wall_seconds"]),
        ),
    }


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--active-codex-home", type=Path, required=True)
    parser.add_argument("--codex-bin", required=True)
    parser.add_argument("--case-id", action="append", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.live or not args.yes:
        parser.error("adjudicator cohort requires both --live and --yes")
    validate_bundle(args.private_root)
    manifest = json.loads((args.private_root / "manifest.json").read_text(encoding="utf-8"))
    risk_case_ids = {item["case_id"] for item in manifest["cases"] if not item.get("clean_control", False)}
    rows = [run_adjudicator_case(private_root=args.private_root, active_home=args.active_codex_home, codex_bin=args.codex_bin, case_id=case_id, timeout=args.timeout) for case_id in args.case_id]
    matched = []
    for row in rows:
        if row.get("status") != "accepted":
            continue
        matched.append({"case_id": row["case_id"], "baseline": row["primary"], "switched": row["switched_arm"]})
    score = score_switch_cohort(matched, risk_case_ids=risk_case_ids) if len(matched) == len(rows) else None
    report = {"version": VERSION, "formal_claim": False, "rows": rows, "matched_cohort": matched, "switch_score": score}
    _write_report(args.output, report)
    return report


if __name__ == "__main__":
    try:
        json.dump(main(), sys.stdout, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
    except BenchmarkContractError as exc:
        print(f"adjudicator_cohort_failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
