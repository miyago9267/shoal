#!/usr/bin/env python3
"""Build and validate the 1.6.0 review-intent route Matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VERSION = 1
REPEATS = 3
INTENTS = ("none", "fast", "strict", "conflicting_or_quoted")
SCENARIOS = (
    {
        "id": "routine_answer",
        "prompt": "Explain the local configuration in one short paragraph.",
        "task_mode": "execute",
        "approval_required": False,
        "risk_categories": [],
    },
    {
        "id": "bounded_edit",
        "prompt": "Fix the already-understood typo in the named README paragraph and run its check.",
        "task_mode": "execute",
        "approval_required": False,
        "risk_categories": [],
    },
    {
        "id": "broad_change",
        "prompt": "Plan the cross-component framework migration across routing, tests, and deployment.",
        "task_mode": "explore_then_plan",
        "approval_required": True,
        "risk_categories": ["data", "release"],
    },
    {
        "id": "security_plan",
        "prompt": "Review the authentication boundary Plan before user approval.",
        "task_mode": "explore_then_plan",
        "approval_required": True,
        "risk_categories": ["security"],
    },
    {
        "id": "irreversible_release",
        "prompt": "Review the irreversible production database migration Plan before release and delete the old production records.",
        "task_mode": "explore_then_plan",
        "approval_required": True,
        "risk_categories": ["data", "irreversible", "release"],
    },
)


def _intent_expectation(variant: str) -> dict[str, str]:
    if variant == "fast":
        return {
            "review_intent": "fast",
            "review_intent_source": "explicit",
            "optional_review": "skip",
        }
    if variant == "strict":
        return {
            "review_intent": "strict",
            "review_intent_source": "explicit",
            "optional_review": "expanded",
        }
    return {
        "review_intent": "default",
        "review_intent_source": "risk_default",
        "optional_review": "existing_policy",
    }


def _suffix(variant: str) -> str:
    return {
        "none": "",
        "fast": " Please go fast and skip extra review for this turn.",
        "strict": " Please use strict review with complete verification and tests.",
        "conflicting_or_quoted": " Treat 'strict review' as an example, but also go fast and be thorough.",
    }[variant]


def build_matrix() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        for variant in INTENTS:
            expected_intent = "default" if variant in {"none", "conflicting_or_quoted"} else variant
            expected = {
                **_intent_expectation(variant),
                "review_intent": expected_intent,
                "review_intent_scope": "turn",
                "task_mode": scenario["task_mode"],
                "approval_required": scenario["approval_required"],
                "risk_categories": scenario["risk_categories"],
                "hard_gate_preserved": scenario["approval_required"],
            }
            for repeat in range(1, REPEATS + 1):
                cases.append(
                    {
                        "id": f"{scenario['id']}-{variant}-{repeat}",
                        "scenario": scenario["id"],
                        "intent_variant": variant,
                        "repeat": repeat,
                        "prompt": scenario["prompt"] + _suffix(variant),
                        "expected": expected,
                    }
                )
    return {
        "version": VERSION,
        "description": "Shoal 1.6.0 review-intent and hard-gate preservation Matrix.",
        "question": "Can explicit turn-scoped intent change optional review without changing task mode or mandatory authority gates?",
        "dimensions": {
            "scenario_families": [scenario["id"] for scenario in SCENARIOS],
            "intent_variants": list(INTENTS),
            "repeats": REPEATS,
        },
        "cases": cases,
    }


def validate_matrix(matrix: Any) -> dict[str, Any]:
    if not isinstance(matrix, dict) or matrix.get("version") != VERSION:
        raise ValueError("intent Matrix version is invalid")
    cases = matrix.get("cases")
    expected_count = len(SCENARIOS) * len(INTENTS) * REPEATS
    if not isinstance(cases, list) or len(cases) != expected_count:
        raise ValueError("intent Matrix case count is invalid")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {
            "id", "scenario", "intent_variant", "repeat", "prompt", "expected"
        }:
            raise ValueError("intent Matrix case shape is invalid")
        if case["id"] in ids:
            raise ValueError("intent Matrix case IDs must be unique")
        ids.add(case["id"])
        if case["scenario"] not in {item["id"] for item in SCENARIOS}:
            raise ValueError("intent Matrix scenario is invalid")
        if case["intent_variant"] not in INTENTS or case["repeat"] not in range(1, REPEATS + 1):
            raise ValueError("intent Matrix dimensions are invalid")
        expected = case["expected"]
        required = {
            "review_intent", "review_intent_source", "review_intent_scope",
            "optional_review", "task_mode", "approval_required", "risk_categories",
            "hard_gate_preserved",
        }
        if not isinstance(expected, dict) or set(expected) != required:
            raise ValueError("intent Matrix expected shape is invalid")
        if expected["review_intent"] not in {"fast", "default", "strict"}:
            raise ValueError("intent Matrix review intent is invalid")
        if expected["review_intent_scope"] != "turn":
            raise ValueError("intent Matrix intent scope must be turn")
        if expected["optional_review"] not in {"skip", "existing_policy", "expanded"}:
            raise ValueError("intent Matrix optional review is invalid")
        if not isinstance(expected["risk_categories"], list):
            raise ValueError("intent Matrix risk categories are invalid")
        if type(expected["approval_required"]) is not bool or type(expected["hard_gate_preserved"]) is not bool:
            raise ValueError("intent Matrix gate values are invalid")
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    matrix = validate_matrix(build_matrix())
    args.output.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
