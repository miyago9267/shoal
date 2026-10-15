#!/usr/bin/env python3
"""Evaluate the quality-first cost frontier from sanitized live artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from quality_cost_frontier import effective_unit_costs, score_quality_first_frontier


def _reports(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("rows"), list):
            raise ValueError(f"invalid live report: {path}")
        rows.extend(value["rows"])
    return rows


def evaluate(*, reports: list[dict[str, Any]], pricing_summary: dict[str, Any]) -> dict[str, Any]:
    rates = effective_unit_costs(pricing_summary)
    cases: dict[str, dict[str, Any]] = {}
    for row in reports:
        case_id = row.get("case_id")
        primary = row.get("primary")
        adjudicator = row.get("adjudicator")
        final = row.get("final")
        if not isinstance(case_id, str) or not isinstance(primary, dict) or not isinstance(final, dict):
            raise ValueError("live row lacks cost-bearing primary/final arms")
        if case_id in cases:
            raise ValueError(f"duplicate case: {case_id}")
        baseline_cost = float(primary["weighted_tokens"]) * rates["luna"]
        candidate_cost = baseline_cost
        if isinstance(adjudicator, dict):
            candidate_cost += float(adjudicator["weighted_tokens"]) * rates["sol"]
        cases[case_id] = {
            "luna_quality": float(primary["quality_score"]),
            "candidate_quality": float(final["quality_score"]),
            "luna_cost_usd": baseline_cost,
            "candidate_cost_usd": candidate_cost,
            "adjudicated": isinstance(adjudicator, dict),
        }
    if not cases:
        raise ValueError("no live cases")
    luna_quality = sum(item["luna_quality"] for item in cases.values()) / len(cases)
    candidate_quality = sum(item["candidate_quality"] for item in cases.values()) / len(cases)
    quality_deltas = [item["candidate_quality"] - item["luna_quality"] for item in cases.values()]
    # The paired report already records the conservative lower bound; recompute
    # only the deterministic point estimate here and preserve the source value.
    source_summary = pricing_summary.get("adjudicator_summary")
    if not isinstance(source_summary, dict):
        raise ValueError("pricing summary must include adjudicator summary")
    quality_ci_low = float(source_summary["quality_ci_low"])
    candidate_cost = sum(item["candidate_cost_usd"] for item in cases.values())
    luna_cost = sum(item["luna_cost_usd"] for item in cases.values())
    frontier = score_quality_first_frontier(
        candidate_quality=candidate_quality,
        luna_quality=luna_quality,
        quality_ci_low_vs_luna=quality_ci_low,
        candidate_cost_usd=candidate_cost,
        pure_sol_cost_usd=float(pricing_summary["candidate_aggregates"]["sol"]["equivalent_cost_usd"]),
        pure_terra_cost_usd=float(pricing_summary["candidate_aggregates"]["terra"]["equivalent_cost_usd"]),
    )
    observed_adjudications = sum(int(item["adjudicated"]) for item in cases.values())
    reported_adjudications = source_summary.get("sol_adjudications")
    consistency = {
        "observed_adjudications": observed_adjudications,
        "reported_adjudications": reported_adjudications,
        "adjudication_count_matches": reported_adjudications == observed_adjudications,
    }
    return {
        "version": "quality-first-cost-frontier-v1",
        "formal_claim": False,
        "cases": len(cases),
        "pricing_basis": "repo_recorded_effective_unit_cost_per_weighted_token",
        "effective_unit_cost_usd_per_weighted_token": rates,
        "aggregate": {
            "luna_quality": luna_quality,
            "candidate_quality": candidate_quality,
            "quality_delta": candidate_quality - luna_quality,
            "quality_ci_low_vs_luna": quality_ci_low,
            "luna_cost_usd": luna_cost,
            "candidate_cost_usd": candidate_cost,
            "candidate_cost_premium_vs_luna": candidate_cost / luna_cost - 1,
            "pure_sol_cost_usd": pricing_summary["candidate_aggregates"]["sol"]["equivalent_cost_usd"],
            "pure_terra_cost_usd": pricing_summary["candidate_aggregates"]["terra"]["equivalent_cost_usd"],
            "adjudications": observed_adjudications,
        },
        "frontier": frontier,
        "source_consistency": consistency,
        "case_costs": {case_id: item for case_id, item in sorted(cases.items())},
        "limitations": [
            "Pure Sol/Terra costs come from the recorded live-v6 reference cohort, not the same 12 matched cases.",
            "The effective unit rate is derived from recorded equivalent cost divided by weighted tokens; it is not a claim about a provider tariff table.",
            "Quality remains an artifact-rubric score, and the current paired confidence lower bound is preserved from the live adjudicator report.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pricing-summary", type=Path, required=True)
    parser.add_argument("--adjudicator-summary", type=Path, required=True)
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pricing = json.loads(args.pricing_summary.read_text(encoding="utf-8"))
    adjudicator = json.loads(args.adjudicator_summary.read_text(encoding="utf-8"))
    pricing["adjudicator_summary"] = adjudicator
    result = evaluate(reports=_reports(args.report), pricing_summary=pricing)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["frontier"], sort_keys=True))


if __name__ == "__main__":
    main()
