#!/usr/bin/env python3
"""Run a bounded Luna/xhigh versus Sol/medium matched diagnostic."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from role_fitness_fixtures import BenchmarkContractError, validate_bundle
from role_fitness_scorecard import score_switch_cohort
from run_role_fitness_content import _write_report, run_review_case


VERSION = "role-fitness-sol-effort-diagnostic-v1"


def run_case(*, private_root: Path, active_home: Path, codex_bin: str, case_id: str, timeout: int) -> list[dict[str, Any]]:
    baseline = run_review_case(
        private_root=private_root, active_home=active_home, codex_bin=codex_bin,
        case_id=case_id, candidate="luna_xhigh", timeout=timeout,
    )
    switched = run_review_case(
        private_root=private_root, active_home=active_home, codex_bin=codex_bin,
        case_id=case_id, candidate="sol_high", timeout=timeout,
        model_effort_override=("gpt-5.6-sol", "medium"),
    )
    return [baseline, switched]


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
        parser.error("Sol effort diagnostic requires both --live and --yes")
    validate_bundle(args.private_root)
    manifest = json.loads((args.private_root / "manifest.json").read_text(encoding="utf-8"))
    risk_case_ids = {item["case_id"] for item in manifest["cases"] if not item.get("clean_control", False)}
    rows = [row for case_id in args.case_id for row in run_case(private_root=args.private_root, active_home=args.active_codex_home, codex_bin=args.codex_bin, case_id=case_id, timeout=args.timeout)]
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        group = grouped.setdefault(row["case_id"], {})
        key = "baseline" if row["candidate"] == "luna_xhigh" else "switched"
        group[key] = {key2: row[key2] for key2 in ("supported_findings", "quality_score", "weighted_tokens", "wall_seconds", "status", "false_escalation", "risk_coverage")}
    matched = [{"case_id": case_id, **group} for case_id, group in sorted(grouped.items()) if set(group) == {"baseline", "switched"}]
    score = score_switch_cohort(matched, risk_case_ids=risk_case_ids) if len(matched) == len(args.case_id) else None
    report = {"version": VERSION, "formal_claim": False, "model_efforts": {"baseline": "gpt-5.6-luna/xhigh", "switched": "gpt-5.6-sol/medium"}, "rows": rows, "matched_cohort": matched, "switch_score": score}
    _write_report(args.output, report)
    return report


if __name__ == "__main__":
    try:
        json.dump(main(), sys.stdout, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
    except BenchmarkContractError as exc:
        print(f"sol_effort_diagnostic_failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
