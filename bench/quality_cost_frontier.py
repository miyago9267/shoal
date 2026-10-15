"""Quality-first cost-frontier calculations for routing experiments."""

from __future__ import annotations

from typing import Any, Mapping


def effective_unit_costs(summary: Mapping[str, Any]) -> dict[str, float]:
    """Derive auditable USD/weighted-token rates from a recorded cohort."""
    candidates = summary.get("candidate_aggregates")
    if not isinstance(candidates, Mapping):
        raise ValueError("pricing summary is missing candidate aggregates")
    rates: dict[str, float] = {}
    for name in ("luna", "sol", "terra"):
        arm = candidates.get(name)
        if not isinstance(arm, Mapping):
            raise ValueError(f"pricing summary is missing {name}")
        cost = arm.get("equivalent_cost_usd")
        tokens = arm.get("weighted_tokens")
        if not isinstance(cost, (int, float)) or not isinstance(tokens, (int, float)) or cost <= 0 or tokens <= 0:
            raise ValueError(f"invalid pricing data for {name}")
        rates[name] = float(cost) / float(tokens)
    return rates


def score_quality_first_frontier(
    *,
    candidate_quality: float,
    luna_quality: float,
    quality_ci_low_vs_luna: float,
    candidate_cost_usd: float,
    pure_sol_cost_usd: float,
    pure_terra_cost_usd: float,
    quality_floor_epsilon: float = 0.0,
) -> dict[str, Any]:
    """Apply the author's quality-first OR rule.

    A candidate cannot win by being cheap while below Luna's quality floor.
    Once the floor is met, it passes either by costing less than at least one
    high-reasoning reference or by having a confidence-supported quality win
    over Luna.  Cost and quality wins are reported separately for auditability.
    """
    values = {
        "candidate_quality": candidate_quality,
        "luna_quality": luna_quality,
        "quality_ci_low_vs_luna": quality_ci_low_vs_luna,
        "candidate_cost_usd": candidate_cost_usd,
        "pure_sol_cost_usd": pure_sol_cost_usd,
        "pure_terra_cost_usd": pure_terra_cost_usd,
    }
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values.values()):
        raise ValueError("frontier metrics must be numeric")
    for name, value in values.items():
        if name != "quality_ci_low_vs_luna" and float(value) < 0:
            raise ValueError("frontier metrics cannot be negative")
    if candidate_cost_usd <= 0 or pure_sol_cost_usd <= 0 or pure_terra_cost_usd <= 0:
        raise ValueError("frontier costs must be positive")

    quality_floor_met = candidate_quality >= luna_quality - quality_floor_epsilon and quality_ci_low_vs_luna >= 0
    quality_win_over_luna = quality_ci_low_vs_luna > 0
    cheaper_than_sol = candidate_cost_usd < pure_sol_cost_usd
    cheaper_than_terra = candidate_cost_usd < pure_terra_cost_usd
    cost_frontier_pass = quality_floor_met and (cheaper_than_sol or cheaper_than_terra)
    quality_frontier_pass = quality_floor_met and quality_win_over_luna
    return {
        "quality_floor_met": quality_floor_met,
        "quality_win_over_luna": quality_win_over_luna,
        "cheaper_than_pure_sol": cheaper_than_sol,
        "cheaper_than_pure_terra": cheaper_than_terra,
        "cheaper_than_any_high_reasoning_reference": cheaper_than_sol or cheaper_than_terra,
        "cost_frontier_pass": cost_frontier_pass,
        "quality_frontier_pass": quality_frontier_pass,
        "acceptable_under_quality_first_rule": cost_frontier_pass or quality_frontier_pass,
        "quality_floor_epsilon": quality_floor_epsilon,
        "candidate_cost_vs_pure_sol": candidate_cost_usd / max(pure_sol_cost_usd, 1e-12),
    }
