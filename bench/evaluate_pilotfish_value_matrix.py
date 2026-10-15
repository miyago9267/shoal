#!/usr/bin/env python3
"""Build a quality-or-Sol-cost value matrix from recorded benchmark artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from quality_cost_frontier import effective_unit_costs


def _policy_quality(value: dict[str, Any], name: str) -> dict[str, float]:
    policy = value["policy_projection"][name]
    return {
        "quality": float(policy["quality_mean"]),
        "supported_findings": float(policy["supported_findings"]),
        "weighted_tokens": float(policy["weighted_tokens"]),
        "wall_seconds": float(policy["wall_seconds"]),
    }


def evaluate(*, pricing: dict[str, Any], full_quality: dict[str, Any], slice_quality: dict[str, Any], frontier: dict[str, Any]) -> dict[str, Any]:
    rates = effective_unit_costs(pricing)
    full = {
        name: _policy_quality(full_quality, name)
        for name in ("always_luna", "always_sol", "selective_v2")
    }
    full["always_luna"]["estimated_cost_usd"] = full["always_luna"]["weighted_tokens"] * rates["luna"]
    full["always_sol"]["estimated_cost_usd"] = full["always_sol"]["weighted_tokens"] * rates["sol"]
    # This is deliberately conservative: pricing all selective tokens as Sol
    # overstates cost when the policy routes some work to Luna.
    full["selective_v2"]["estimated_cost_upper_bound_usd"] = full["selective_v2"]["weighted_tokens"] * rates["sol"]
    selective = full["selective_v2"]
    always_sol = full["always_sol"]
    selective_vs_sol = {
        "quality_delta": selective["quality"] - always_sol["quality"],
        "supported_findings_delta": selective["supported_findings"] - always_sol["supported_findings"],
        "weighted_token_saving_fraction": 1 - selective["weighted_tokens"] / always_sol["weighted_tokens"],
        "estimated_cost_upper_bound_saving_fraction": 1 - selective["estimated_cost_upper_bound_usd"] / always_sol["estimated_cost_usd"],
        "quality_retained": selective["quality"] >= always_sol["quality"],
        "cheaper_than_direct_sol": selective["weighted_tokens"] < always_sol["weighted_tokens"],
    }
    slice_policies = slice_quality["policies"]
    slice_selective = slice_policies["selective_v2"]
    slice_sol = slice_policies["always_sol"]
    slice_comparison = {
        "quality_delta": float(slice_selective["quality_mean"]) - float(slice_sol["quality_mean"]),
        "weighted_token_saving_fraction": 1 - float(slice_selective["weighted_tokens"]) / float(slice_sol["weighted_tokens"]),
        "estimated_cost_upper_bound_saving_fraction": 1 - float(slice_selective["weighted_tokens"]) * rates["sol"] / (float(slice_sol["weighted_tokens"]) * rates["sol"]),
        "quality_retained": float(slice_selective["quality_mean"]) >= float(slice_sol["quality_mean"]),
        "cheaper_than_direct_sol": float(slice_selective["weighted_tokens"]) < float(slice_sol["weighted_tokens"]),
    }
    return {
        "version": "pilotfish-value-matrix-v1",
        "formal_claim": False,
        "pricing_basis": "repo_recorded_effective_unit_cost_per_weighted_token",
        "effective_unit_cost_usd_per_weighted_token": rates,
        "quality_or_cost_rule": "quality must not fall below the comparison floor; then quality win OR lower cost than direct Sol is sufficient",
        "matrix": {
            "luna_only": {
                "quality": full["always_luna"]["quality"],
                "supported_findings": full["always_luna"]["supported_findings"],
                "weighted_tokens": full["always_luna"]["weighted_tokens"],
                "estimated_cost_usd": full["always_luna"]["estimated_cost_usd"],
            },
            "sol_only": {
                "quality": full["always_sol"]["quality"],
                "supported_findings": full["always_sol"]["supported_findings"],
                "weighted_tokens": full["always_sol"]["weighted_tokens"],
                "estimated_cost_usd": full["always_sol"]["estimated_cost_usd"],
            },
            "pilotfish_selective_sol_primary": {
                **selective,
                "comparison_to_sol_only": selective_vs_sol,
            },
            "pilotfish_luna_first_disagreement_adjudicator": {
                "quality": frontier["aggregate"]["candidate_quality"],
                "quality_delta_vs_luna": frontier["aggregate"]["quality_delta"],
                "quality_ci_low_vs_luna": frontier["aggregate"]["quality_ci_low_vs_luna"],
                "estimated_cost_usd": frontier["aggregate"]["candidate_cost_usd"],
                "cheaper_than_pure_sol": frontier["frontier"]["cheaper_than_pure_sol"],
                "cheaper_than_pure_terra": frontier["frontier"]["cheaper_than_pure_terra"],
                "quality_win_over_luna": frontier["frontier"]["quality_win_over_luna"],
            },
        },
        "sol_primary_assist_slice": {
            "cases": int(slice_quality["policies"]["always_sol"]["arms"]),
            "direct_sol_quality": float(slice_sol["quality_mean"]),
            "pilotfish_quality": float(slice_selective["quality_mean"]),
            **slice_comparison,
        },
        "conclusion": {
            "pilotfish_has_quality_uplift_evidence": frontier["aggregate"]["quality_delta"] > 0,
            "pilotfish_has_quality_supported_uplift": frontier["frontier"]["quality_win_over_luna"],
            "pilotfish_is_cheaper_than_direct_sol_in_sol_primary_mode": selective_vs_sol["cheaper_than_direct_sol"],
            "pilotfish_meets_quality_or_sol_cost_value": selective_vs_sol["quality_retained"] and selective_vs_sol["cheaper_than_direct_sol"] or frontier["frontier"]["quality_win_over_luna"],
        },
        "limitations": [
            "The Sol-primary comparison is a recorded selective routing projection and a six-case live slice, not a fresh 12-case Sol-primary native run.",
            "Selective USD is an upper bound priced as if every token used Sol; actual Luna routing should be no higher under the recorded effective rates.",
            "The adjudicator quality uplift is a positive point estimate but its paired confidence lower bound is zero.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pricing", type=Path, required=True)
    parser.add_argument("--full-quality", type=Path, required=True)
    parser.add_argument("--slice-quality", type=Path, required=True)
    parser.add_argument("--frontier", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(
        pricing=json.loads(args.pricing.read_text()),
        full_quality=json.loads(args.full_quality.read_text()),
        slice_quality=json.loads(args.slice_quality.read_text()),
        frontier=json.loads(args.frontier.read_text()),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["conclusion"], sort_keys=True))


if __name__ == "__main__":
    main()
