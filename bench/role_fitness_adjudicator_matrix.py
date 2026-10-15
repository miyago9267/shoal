#!/usr/bin/env python3
"""Build the offline matrix for Luna verification and one-shot Sol adjudication."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence


VERSION = "role-fitness-adjudicator-matrix-v1"
POLICIES = ("luna_only", "risk_gated_adjudication", "semantic_adjudication")

SCENARIOS = [
    {"id": "agree_clean", "disagreement": False, "deterministic_probe": "agree", "risk": [], "evidence": "complete"},
    {"id": "agree_risk", "disagreement": False, "deterministic_probe": "agree", "risk": ["data"], "evidence": "complete"},
    {"id": "semantic_compound", "disagreement": True, "deterministic_probe": "undecided", "risk": ["data", "irreversible"], "evidence": "complete"},
    {"id": "semantic_security", "disagreement": True, "deterministic_probe": "undecided", "risk": ["security"], "evidence": "complete"},
    {"id": "semantic_routine", "disagreement": True, "deterministic_probe": "undecided", "risk": [], "evidence": "complete"},
    {"id": "deterministic_conflict", "disagreement": True, "deterministic_probe": "conflict", "risk": ["security"], "evidence": "complete"},
    {"id": "missing_evidence", "disagreement": True, "deterministic_probe": "undecided", "risk": ["security"], "evidence": "missing"},
    {"id": "recovery_critical", "disagreement": True, "deterministic_probe": "undecided", "risk": ["external", "release"], "evidence": "complete"},
]


def _risk_gate(scenario: dict[str, Any]) -> bool:
    risks = set(scenario["risk"])
    return "security" in risks or len(risks) >= 2


def route(policy: str, scenario: dict[str, Any]) -> dict[str, Any]:
    if policy not in POLICIES:
        raise ValueError(f"unknown policy: {policy}")
    if scenario["evidence"] != "complete":
        return {"route": "inconclusive", "reason": "evidence_missing"}
    if scenario["deterministic_probe"] == "conflict":
        return {"route": "inconclusive", "reason": "deterministic_probe_wins"}
    if not scenario["disagreement"]:
        return {"route": "luna", "reason": "no_disagreement"}
    if policy == "luna_only":
        return {"route": "luna", "reason": "adjudication_disabled"}
    if policy == "risk_gated_adjudication" and not _risk_gate(scenario):
        return {"route": "luna", "reason": "risk_gate_not_met"}
    return {"route": "sol_adjudicator", "reason": "semantic_disagreement"}


def run_matrix() -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        for policy in POLICIES:
            decision = route(policy, scenario)
            cells.append({"scenario": scenario["id"], "policy": policy, **decision})
    aggregates = {
        policy: {
            "scenarios": len(SCENARIOS),
            "sol_adjudications": sum(
                cell["route"] == "sol_adjudicator"
                for cell in cells
                if cell["policy"] == policy
            ),
            "luna_routes": sum(
                cell["route"] == "luna"
                for cell in cells
                if cell["policy"] == policy
            ),
            "inconclusive": sum(
                cell["route"] == "inconclusive"
                for cell in cells
                if cell["policy"] == policy
            ),
        }
        for policy in POLICIES
    }
    return {
        "version": VERSION,
        "formal_claim": False,
        "contract": {
            "verifier": "luna_xhigh",
            "adjudicator": "sol_high",
            "max_adjudications_per_fingerprint": 1,
            "missing_evidence": "inconclusive",
            "deterministic_probe_conflict": "inconclusive",
            "rubric_mutation": False,
        },
        "policies": list(POLICIES),
        "scenarios": SCENARIOS,
        "cells": cells,
        "aggregates": aggregates,
        "interpretation": "This matrix proves only route shape. Adjudication earns quality credit only when its final output is scored by the unchanged hidden-ledger rubric.",
    }


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    result = run_matrix()
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        if len(args) != 2 or args[0] != "--output":
            raise SystemExit("usage: role_fitness_adjudicator_matrix.py [--output PATH]")
        path = Path(args[1])
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    json.dump(main(), sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
