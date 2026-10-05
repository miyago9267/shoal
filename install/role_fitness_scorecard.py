"""Deterministic offline scoring for the role-fitness operational contract."""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


ARCHITECTURE_CHECKS = (
    "role_binding",
    "stage_ownership",
    "handoff_validation",
    "receipt_correlation",
    "public_projection",
)


def score_architecture(checks: Mapping[str, bool], *, required_rate: float = 0.80) -> dict[str, Any]:
    """Score static architecture invariants without treating unrun live checks as passes."""
    if set(checks) != set(ARCHITECTURE_CHECKS) or not 0 < required_rate <= 1:
        raise ValueError("architecture check schema is invalid")
    if any(type(value) is not bool for value in checks.values()):
        raise ValueError("architecture checks must be boolean")
    passed = sum(checks.values())
    total = len(ARCHITECTURE_CHECKS)
    rate = passed / total
    return {
        "numerator": passed,
        "denominator": total,
        "rate": rate,
        "score": min(10, int(10 * rate)),
        "required_rate": required_rate,
        "proven": rate >= required_rate,
        "failed_checks": [name for name, value in checks.items() if not value],
    }


def wilson_lower_bound(successes: int, trials: int, *, z: float = 1.96) -> float:
    """Return the two-sided Wilson lower bound for a binomial proportion."""
    if trials <= 0 or successes < 0 or successes > trials or z <= 0:
        raise ValueError("invalid binomial sample")
    rate = successes / trials
    denominator = 1 + z * z / trials
    center = rate + z * z / (2 * trials)
    spread = z * math.sqrt(rate * (1 - rate) / trials + z * z / (4 * trials * trials))
    return (center - spread) / denominator


def score_rate(
    numerator: int,
    denominator: int,
    *,
    minimum_samples: int = 0,
    required_lower_bound: float | None = None,
) -> dict[str, Any]:
    """Score a 0–10 rate while keeping statistical proof separate."""
    if denominator <= 0 or numerator < 0 or numerator > denominator:
        raise ValueError("invalid rate")
    if minimum_samples < 0 or required_lower_bound is not None and not 0 <= required_lower_bound <= 1:
        raise ValueError("invalid score gate")
    rate = numerator / denominator
    lower_bound = wilson_lower_bound(numerator, denominator)
    proven = denominator >= minimum_samples and (
        required_lower_bound is None or lower_bound >= required_lower_bound
    )
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": rate,
        "lower_bound": lower_bound,
        "score": min(10, int(10 * rate)),
        "confidence_adjusted_score": min(10, int(10 * lower_bound)),
        "proven": proven,
    }


def score_repeat_stability(
    passed_repeats: int,
    eligible_repeats: int,
    *,
    minimum_repeats: int = 3,
) -> dict[str, Any]:
    """Score deterministic repeat integrity without a misleading Wilson gate."""
    if (
        eligible_repeats <= 0
        or passed_repeats < 0
        or passed_repeats > eligible_repeats
        or minimum_repeats <= 0
    ):
        raise ValueError("invalid stability repeat count")
    rate = passed_repeats / eligible_repeats
    return {
        "numerator": passed_repeats,
        "denominator": eligible_repeats,
        "rate": rate,
        "score": min(10, int(10 * rate)),
        "proven": eligible_repeats >= minimum_repeats and passed_repeats == eligible_repeats,
    }


def score_mechanical_execution(
    *, first_pass: int, total: int, rework_free: int
) -> dict[str, Any]:
    """Score executor delivery only after verifier-confirmed acceptance."""
    if total <= 0 or not 0 <= first_pass <= total or not 0 <= rework_free <= total:
        raise ValueError("invalid mechanical execution counts")
    first = first_pass / total
    clean = rework_free / total
    rate = 0.70 * first + 0.30 * clean
    return {
        "first_pass": score_rate(first_pass, total),
        "rework_free": score_rate(rework_free, total),
        "rate": rate,
        "score": min(10, int(10 * rate)),
        "proven": first_pass == total and rework_free == total,
    }


def score_split_workflow(*, confirmed: int, total: int) -> dict[str, Any]:
    """Score the final verifier-confirmed completion branch."""
    if total <= 0 or not 0 <= confirmed <= total:
        raise ValueError("invalid split workflow counts")
    return score_rate(confirmed, total)


CONTENT_FAILURE_CLASSES = (
    "false_escalation",
    "missed_risk",
    "unparseable_output",
    "executor_no_artifact",
    "verifier_retry",
    "verifier_inconclusive",
    "unclassified",
)
CONTENT_TAXONOMY_PREFIX = "content."


def stage_key(stage: Mapping[str, Any]) -> str:
    """Return the `<case_id>#<attempt>` identity that a rerun's `rerun_of` names."""
    return f"{stage.get('case_id')}#{stage.get('attempt', 1)}"


def classify_content_failure(
    stage: Mapping[str, Any], *, superseded: bool = False
) -> str | None:
    """Classify one runner-format content stage; None means it needs no class.

    Rules run in order and the first match wins (claude-eval-parity Decision 4).
    They read only recorded runner fields, never benchmark summaries or model
    judgments.  `superseded` applies to one case only: a verifier `INCONCLUSIVE`
    stage that a verifier rerun names in `rerun_of`.  The rerun stage stands for
    it, so it is not counted twice.  Every other failure keeps its own class even
    when a later stage reruns it.
    """
    status = stage.get("status")
    if status == "accepted":
        if stage.get("false_escalation") is True:
            return "false_escalation"
        score = stage.get("score")
        score = score if isinstance(score, Mapping) else {}
        coverage = stage.get("risk_coverage")
        if (
            score.get("expected_decision") == "REVISE"
            and isinstance(coverage, (int, float))
            and not isinstance(coverage, bool)
            and coverage < 1.0
        ):
            return "missed_risk"
        if stage.get("native_role") == "verifier" and stage.get("rerun_of"):
            return "verifier_retry"
        # An accepted review that still failed its own pass check must not go unlabelled.
        return "unclassified" if score.get("passed") is False else None
    reason = stage.get("reason")
    dispatch = stage.get("dispatch_status")
    if status == "inconclusive" and isinstance(reason, str):
        # The direct review path records no dispatch_status, so absence is allowed there only.
        if reason in {"invalid_native_review_output", "invalid_review_output"} and dispatch in (None, "NATIVE_OK"):
            return "unparseable_output"
        if reason in {"invalid_split_executor_acceptance", "invalid_native_mechanical_acceptance"} and dispatch == "NATIVE_OK":
            return "executor_no_artifact"
        if reason == "verifier_did_not_confirm":
            return None if superseded else "verifier_inconclusive"
    return "unclassified"


def _is_verifier_inconclusive(stage: Mapping[str, Any]) -> bool:
    return stage.get("status") == "inconclusive" and stage.get("reason") == "verifier_did_not_confirm"


def superseded_flags(stages: Iterable[Mapping[str, Any]]) -> list[bool]:
    """Mark verifier INCONCLUSIVE stages that a verifier rerun's `rerun_of` names.

    `<case_id>#<attempt>` alone also matches the same case's executor or review
    stage, so a stage is only superseded when it is itself a verifier
    inconclusive and the stage naming it is a verifier stage.
    """
    rows = list(stages)
    targets = {
        row["rerun_of"]
        for row in rows
        if isinstance(row.get("rerun_of"), str)
        and (row.get("native_role") == "verifier" or _is_verifier_inconclusive(row))
    }
    return [_is_verifier_inconclusive(row) and stage_key(row) in targets for row in rows]


def classify_content_stages(stages: Iterable[Mapping[str, Any]]) -> list[str | None]:
    """Classify a run's content stages, resolving which verifier stages were rerun."""
    rows = list(stages)
    return [
        classify_content_failure(row, superseded=flag)
        for row, flag in zip(rows, superseded_flags(rows))
    ]


def content_failure_taxonomy(classes: Iterable[str | None]) -> dict[str, int]:
    """Count content classes under `content.<class>` keys; unclassed stages are skipped."""
    counts: dict[str, int] = {}
    for name in classes:
        if name is None:
            continue
        if name not in CONTENT_FAILURE_CLASSES:
            raise ValueError("content failure class is invalid")
        key = CONTENT_TAXONOMY_PREFIX + name
        counts[key] = counts.get(key, 0) + 1
    return counts


def _failure_block(entries: list[tuple[str | None, float | None]]) -> dict[str, Any]:
    """Summarise counted stages as (class, quality) pairs: counts, shares, mean score."""
    total = len(entries)
    classes = {
        name: {"count": count, "share": count / total}
        for name in CONTENT_FAILURE_CLASSES
        for count in [sum(1 for found, _ in entries if found == name)]
    }
    qualities = [quality for _, quality in entries if quality is not None]
    return {
        "stages": total,
        "passed": sum(1 for found, _ in entries if found is None),
        "mean_quality_score": sum(qualities) / len(qualities) if qualities else None,
        "classes": classes,
    }


def content_failure_report(
    arms: Mapping[str, Mapping[str, Iterable[Mapping[str, Any]]]],
) -> dict[str, Any]:
    """Per-arm failure counts and shares beside the mean quality score (R9).

    `arms` maps arm -> repeat label (`R1`..`R3`) -> runner-format content stages.
    Each repeat gets its own block; `pooled` is added for comparison and never
    replaces them.  Every stage counts once, except a verifier INCONCLUSIVE stage that a
    verifier rerun's `rerun_of` names (the rerun counts instead), so shares are
    over the stages that stand.  Shares and counts cover every class in
    the fixed enum, including zeros, so arms and repeats line up column for column.
    """
    report: dict[str, Any] = {"arms": {}}
    for arm, repeats in arms.items():
        per_repeat: dict[str, list[tuple[str | None, float | None]]] = {}
        for label, stages in repeats.items():
            rows = list(stages)
            entries: list[tuple[str | None, float | None]] = []
            for row, found, superseded in zip(rows, classify_content_stages(rows), superseded_flags(rows)):
                if superseded:
                    continue
                quality = row.get("quality_score")
                numeric = isinstance(quality, (int, float)) and not isinstance(quality, bool)
                entries.append((found, float(quality) if row.get("status") == "accepted" and numeric else None))
            if not entries:
                raise ValueError("a repeat needs at least one content stage")
            per_repeat[label] = entries
        if not per_repeat:
            raise ValueError("an arm needs at least one repeat")
        report["arms"][arm] = {
            "repeats": {label: _failure_block(entries) for label, entries in per_repeat.items()},
            "pooled": _failure_block([item for entries in per_repeat.values() for item in entries]),
        }
    return report


def render_content_failure_report(report: Mapping[str, Any]) -> str:
    """One line per arm and repeat: score, then each non-zero class as count and share."""

    def line(arm: str, label: str, block: Mapping[str, Any]) -> str:
        mean = block["mean_quality_score"]
        found = [
            f"{name} {block['classes'][name]['count']}/{block['stages']} ({block['classes'][name]['share']:.1%})"
            for name in CONTENT_FAILURE_CLASSES
            if block["classes"][name]["count"]
        ]
        score = "n/a" if mean is None else f"{mean:.1f}"
        return f"{arm} {label} n={block['stages']} mean_quality={score} | " + (", ".join(found) or "no failures")

    lines: list[str] = []
    for arm, data in report["arms"].items():
        lines.extend(line(arm, label, data["repeats"][label]) for label in sorted(data["repeats"]))
        lines.append(line(arm, "pooled", data["pooled"]))
    return "\n".join(lines)


def aggregate_repeats(runs: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Pool compatible repeat summaries without replacing earlier runs."""
    rows = list(runs)
    if not rows:
        raise ValueError("at least one repeat is required")
    run_ids = [row.get("run_id") for row in rows]
    if any(not isinstance(run_id, str) or not run_id for run_id in run_ids):
        raise ValueError("run_id is required")
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("duplicate run_id")
    manifest_hashes = {row.get("manifest_hash") for row in rows}
    scorecard_hashes = {row.get("scorecard_hash") for row in rows}
    if len(manifest_hashes) != 1 or len(scorecard_hashes) != 1:
        raise ValueError("repeat hashes do not match")

    dimensions: dict[str, dict[str, int]] = {}
    for row in rows:
        for name, value in row.items():
            if name in {"run_id", "manifest_hash", "scorecard_hash"}:
                continue
            if not isinstance(value, Mapping) or set(value) != {"passed", "total"}:
                continue
            passed = value["passed"]
            total = value["total"]
            if isinstance(passed, bool) or isinstance(total, bool) or not isinstance(passed, int) or not isinstance(total, int) or total <= 0 or not 0 <= passed <= total:
                raise ValueError(f"invalid repeat dimension: {name}")
            current = dimensions.setdefault(name, {"passed": 0, "total": 0})
            current["passed"] += passed
            current["total"] += total
    return {
        "run_ids": run_ids,
        "manifest_hash": next(iter(manifest_hashes)),
        "scorecard_hash": next(iter(scorecard_hashes)),
        **dimensions,
    }


def append_repeat_record(path: Path, run: Mapping[str, Any]) -> dict[str, Any]:
    """Append one immutable JSONL repeat and return the pooled aggregate."""
    import json

    existing: list[dict[str, Any]] = []
    if path.exists():
        if not path.is_file() or path.is_symlink():
            raise ValueError("repeat ledger path is invalid")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("repeat ledger row is not an object")
            existing.append(value)
    aggregate = aggregate_repeats([*existing, run])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(run), sort_keys=True, separators=(",", ":")))
        handle.write("\n")
    return aggregate


def score_switch_cost_performance(
    *,
    additional_findings: int,
    extra_weighted_tokens: int,
    quality_delta: float,
    quality_ci_low: float,
    p95_wall_premium: float,
    weighted_token_premium: float,
    risk_coverage_delta: float = 0,
    false_escalations: int,
    inconclusive: int,
) -> dict[str, Any]:
    """Apply the SPEC's fail-closed score caps to a matched switch cohort."""
    if false_escalations < 0 or inconclusive < 0:
        raise ValueError("invalid switch failures")
    if extra_weighted_tokens > 0:
        switch_value = additional_findings / (extra_weighted_tokens / 100_000)
    elif extra_weighted_tokens < 0 and additional_findings != 0:
        # A quality-positive switch that saves weighted tokens has unbounded
        # marginal yield; a finding loss remains negative evidence.
        switch_value = math.copysign(math.inf, additional_findings)
    elif extra_weighted_tokens == 0 and additional_findings != 0:
        switch_value = math.copysign(math.inf, additional_findings)
    else:
        switch_value = 0.0
    quality_supported = quality_delta > 0 and quality_ci_low > 0
    clean = false_escalations == 0 and inconclusive == 0
    within_eight_caps = (
        p95_wall_premium <= 0.25 and weighted_token_premium <= 0.20
    ) or risk_coverage_delta >= 10
    gate_eight = quality_supported and switch_value > 0 and clean and within_eight_caps
    gate_nine = gate_eight and p95_wall_premium <= 0.10 and weighted_token_premium <= 0.10
    score = 9 if gate_nine else 8 if gate_eight else 5
    return {
        "switch_value": switch_value,
        "cost_saving": extra_weighted_tokens < 0,
        "quality_supported": quality_supported,
        "clean": clean,
        "score": score,
        "proven": gate_eight,
    }


def quality_adjusted_cost_efficiency(
    *,
    baseline_quality: float,
    switched_quality: float,
    baseline_cost: float,
    switched_cost: float,
    quality_delta_ci_low: float,
) -> dict[str, Any]:
    """Measure cost efficiency only after the baseline quality floor holds.

    The metric is deliberately separate from the fail-closed switch score. A
    cheaper but lower-quality route gets no efficiency credit, while a route
    that is quality-supported is compared by quality points per cost unit.
    """
    values = {
        "baseline_quality": baseline_quality,
        "switched_quality": switched_quality,
        "baseline_cost": baseline_cost,
        "switched_cost": switched_cost,
        "quality_delta_ci_low": quality_delta_ci_low,
    }
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in values.values()
    ):
        raise ValueError("quality-adjusted efficiency inputs must be finite numbers")
    if baseline_cost <= 0 or switched_cost <= 0:
        raise ValueError("quality-adjusted efficiency costs must be positive")

    quality_supported = (
        switched_quality >= baseline_quality and quality_delta_ci_low >= 0
    )
    baseline_efficiency = baseline_quality / baseline_cost
    switched_efficiency = (
        switched_quality / switched_cost if quality_supported else 0.0
    )
    efficiency_delta = switched_efficiency - baseline_efficiency
    return {
        "quality_floor": baseline_quality,
        "quality_supported": quality_supported,
        "baseline_efficiency": baseline_efficiency,
        "switched_efficiency": switched_efficiency,
        "efficiency_delta": efficiency_delta,
        "maximizes_cost_efficiency": quality_supported and efficiency_delta >= 0,
    }


def _percentile(values: list[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise ValueError("invalid percentile input")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def score_switch_cohort(
    cases: Iterable[Mapping[str, Any]],
    *,
    bootstrap_samples: int = 10_000,
    seed: int = 20260805,
    risk_case_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Score a matched Luna/Sol cohort with deterministic paired bootstrap."""
    rows = list(cases)
    if not rows or bootstrap_samples <= 0:
        raise ValueError("matched cohort and bootstrap samples are required")
    required = {"case_id", "baseline", "switched"}
    nested = {
        "supported_findings",
        "quality_score",
        "weighted_tokens",
        "wall_seconds",
        "status",
        "false_escalation",
    }
    ids: set[str] = set()
    use_equivalent_cost = all(
        isinstance(row, Mapping)
        and isinstance(row.get("baseline"), Mapping)
        and isinstance(row.get("switched"), Mapping)
        and "equivalent_cost" in row["baseline"]
        and "equivalent_cost" in row["switched"]
        for row in rows
    )
    quality_deltas: list[float] = []
    finding_deltas: list[int] = []
    baseline_tokens: list[float] = []
    switched_tokens: list[float] = []
    baseline_wall: list[float] = []
    switched_wall: list[float] = []
    baseline_costs: list[float] = []
    switched_costs: list[float] = []
    coverage_deltas: list[float] = []
    false_escalations = 0
    inconclusive = 0
    for row in rows:
        if set(row) != required or not isinstance(row.get("case_id"), str) or not row["case_id"] or row["case_id"] in ids:
            raise ValueError("matched cohort identity is invalid")
        ids.add(row["case_id"])
        arms: list[Mapping[str, Any]] = []
        for name in ("baseline", "switched"):
            arm = row[name]
            allowed_shapes = (
                nested,
                nested | {"risk_coverage"},
                nested | {"equivalent_cost"},
                nested | {"risk_coverage", "equivalent_cost"},
            )
            if not isinstance(arm, Mapping) or set(arm) not in allowed_shapes:
                raise ValueError("matched cohort arm schema is invalid")
            if "risk_coverage" in arm:
                coverage = arm["risk_coverage"]
                if isinstance(coverage, bool) or not isinstance(coverage, (int, float)) or not math.isfinite(coverage) or not 0 <= coverage <= 1:
                    raise ValueError("matched cohort risk coverage is invalid")
            if arm["status"] not in {"accepted", "inconclusive"} or type(arm["false_escalation"]) is not bool:
                raise ValueError("matched cohort arm status is invalid")
            for field in ("supported_findings", "quality_score", "weighted_tokens", "wall_seconds"):
                value = arm[field]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError("matched cohort metric is invalid")
            if arm["weighted_tokens"] <= 0 or arm["wall_seconds"] <= 0:
                raise ValueError("matched cohort usage must be positive")
            if "equivalent_cost" in arm:
                cost = arm["equivalent_cost"]
                if (
                    isinstance(cost, bool)
                    or not isinstance(cost, (int, float))
                    or not math.isfinite(cost)
                    or cost <= 0
                ):
                    raise ValueError("matched cohort equivalent cost is invalid")
            arms.append(arm)
        baseline, switched = arms
        if baseline["status"] != "accepted" or switched["status"] != "accepted":
            inconclusive += 1
        quality_deltas.append(float(switched["quality_score"] - baseline["quality_score"]))
        finding_deltas.append(int(switched["supported_findings"] - baseline["supported_findings"]))
        baseline_tokens.append(float(baseline["weighted_tokens"]))
        switched_tokens.append(float(switched["weighted_tokens"]))
        baseline_wall.append(float(baseline["wall_seconds"]))
        switched_wall.append(float(switched["wall_seconds"]))
        if use_equivalent_cost:
            baseline_costs.append(float(baseline["equivalent_cost"]))
            switched_costs.append(float(switched["equivalent_cost"]))
        else:
            baseline_costs.append(float(baseline["weighted_tokens"]) / 100_000)
            switched_costs.append(float(switched["weighted_tokens"]) / 100_000)
        if "risk_coverage" in baseline and "risk_coverage" in switched and (risk_case_ids is None or row["case_id"] in risk_case_ids):
            coverage_deltas.append((float(switched["risk_coverage"]) - float(baseline["risk_coverage"])) * 100)
        false_escalations += int(switched["false_escalation"])

    rng = random.Random(seed)
    bootstrap_means: list[float] = []
    for _ in range(bootstrap_samples):
        sample = [quality_deltas[rng.randrange(len(quality_deltas))] for _ in quality_deltas]
        bootstrap_means.append(sum(sample) / len(sample))
    quality_delta = sum(quality_deltas) / len(quality_deltas)
    quality_ci_low = _percentile(bootstrap_means, 0.025)
    quality_ci_high = _percentile(bootstrap_means, 0.975)
    extra_tokens = int(sum(switched_tokens) - sum(baseline_tokens))
    token_premium = sum(switched_tokens) / sum(baseline_tokens) - 1
    wall_premium = _percentile(switched_wall, 0.95) / _percentile(baseline_wall, 0.95) - 1
    expected_coverage_cases = len(risk_case_ids.intersection(ids)) if risk_case_ids is not None else len(rows)
    risk_coverage_delta = sum(coverage_deltas) / len(coverage_deltas) if coverage_deltas and len(coverage_deltas) == expected_coverage_cases else 0
    score = score_switch_cost_performance(
        additional_findings=sum(finding_deltas),
        extra_weighted_tokens=extra_tokens,
        quality_delta=quality_delta,
        quality_ci_low=quality_ci_low,
        p95_wall_premium=wall_premium,
        weighted_token_premium=token_premium,
        risk_coverage_delta=risk_coverage_delta,
        false_escalations=false_escalations,
        inconclusive=inconclusive,
    )
    quality_efficiency = quality_adjusted_cost_efficiency(
        baseline_quality=sum(
            float(row["baseline"]["quality_score"]) for row in rows
        )
        / len(rows),
        switched_quality=sum(
            float(row["switched"]["quality_score"]) for row in rows
        )
        / len(rows),
        baseline_cost=sum(baseline_costs),
        switched_cost=sum(switched_costs),
        quality_delta_ci_low=quality_ci_low,
    )
    return {
        **score,
        "quality_adjusted_cost_efficiency": quality_efficiency,
        "cost_basis": "equivalent_cost" if use_equivalent_cost else "weighted_token_proxy",
        "cases": len(rows),
        "additional_findings": sum(finding_deltas),
        "extra_weighted_tokens": extra_tokens,
        "quality_delta": quality_delta,
        "quality_ci_low": quality_ci_low,
        "quality_ci_high": quality_ci_high,
        "p95_wall_premium": wall_premium,
        "weighted_token_premium": token_premium,
        "risk_coverage_delta": risk_coverage_delta,
        "false_escalations": false_escalations,
        "inconclusive": inconclusive,
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": seed,
    }
