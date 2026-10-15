#!/usr/bin/env python3
"""Run the deterministic v2 Luna-first/Sol-second-opinion route matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
import shoal_autoroute_gate as gate  # noqa: E402


VERSION = "role-fitness-routing-matrix-v2"
SCENARIOS = [
    {"id": "routine", "categories": [], "luna_uncertain": False, "unresolved_critical": False},
    {"id": "single_data", "categories": ["data"], "luna_uncertain": False, "unresolved_critical": False},
    {"id": "security_boundary", "categories": ["security"], "luna_uncertain": False, "unresolved_critical": False},
    {"id": "multi_risk", "categories": ["data", "irreversible"], "luna_uncertain": False, "unresolved_critical": False},
    {"id": "uncertain_single_data", "categories": ["data"], "luna_uncertain": True, "unresolved_critical": False},
    {"id": "external_release", "categories": ["external", "release"], "luna_uncertain": False, "unresolved_critical": False},
]
POLICIES = ("always_sol", "selective_v2", "selective_v2_uncertainty")


def _route(policy: str, scenario: dict[str, Any]) -> tuple[str, str]:
    if policy == "always_sol":
        return "sol_high", "always_sol_control"
    categories = tuple(scenario["categories"])
    reason = gate.route_reason(
        categories,
        luna_uncertain=scenario["luna_uncertain"] if policy == "selective_v2_uncertainty" else False,
        unresolved_critical=scenario["unresolved_critical"],
    )
    return ("sol_high", reason) if reason != "luna_default" else ("luna_first", reason)


def run_matrix() -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        for policy in POLICIES:
            route, reason = _route(policy, scenario)
            cells.append({"scenario": scenario["id"], "policy": policy, "route": route, "reason": reason})
    aggregates = {
        policy: {
            "scenarios": len(SCENARIOS),
            "sol_routes": sum(cell["route"] == "sol_high" for cell in cells if cell["policy"] == policy),
            "luna_routes": sum(cell["route"] == "luna_first" for cell in cells if cell["policy"] == policy),
        }
        for policy in POLICIES
    }
    return {
        "version": VERSION,
        "formal_claim": False,
        "hypothesis": "Luna handles default work; Sol is reserved for security, multiple risks, or Luna uncertainty.",
        "scenarios": SCENARIOS,
        "policies": list(POLICIES),
        "cells": cells,
        "aggregates": aggregates,
        "interpretation": "The selective policy reduces unnecessary Sol routes while retaining security and compound-risk escalation; this matrix proves routing shape only, not model quality.",
    }


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    result = run_matrix()
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        if len(argv) != 2 or argv[0] != "--output":
            raise SystemExit("usage: role_fitness_routing_matrix.py [--output PATH]")
        path = Path(argv[1])
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    json.dump(main(), sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
