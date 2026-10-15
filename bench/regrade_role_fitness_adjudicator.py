#!/usr/bin/env python3
"""Regrade a completed adjudicator report with the frozen risk-coverage gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from role_fitness_scorecard import score_switch_cohort


def main() -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    manifest = json.loads((args.private_root / "manifest.json").read_text(encoding="utf-8"))
    ledgers = json.loads((args.private_root / "ledgers.json").read_text(encoding="utf-8"))
    risk_case_ids = {item["case_id"] for item in manifest["cases"] if not item.get("clean_control", False)}
    matched = []
    for row in report["rows"]:
        case_id = row["case_id"]
        total_weight = sum(item["weight"] for item in ledgers[case_id])
        baseline = row["primary"]
        final = row["final"]
        switched = row["switched_arm"]
        def arm(metrics: dict, coverage_source: dict) -> dict:
            value = {key: metrics[key] for key in ("supported_findings", "quality_score", "weighted_tokens", "wall_seconds", "false_escalation")}
            value["status"] = "accepted"
            value["risk_coverage"] = coverage_source["supported_findings"] / total_weight if total_weight else 0
            return value
        matched.append({"case_id": case_id, "baseline": arm(baseline, baseline), "switched": arm(switched, final)})
    score = score_switch_cohort(matched, risk_case_ids=risk_case_ids)
    result = {
        "version": "role-fitness-adjudicator-live-v1-regrade",
        "source_report": str(args.report),
        "private_manifest_sha256": "3c69498312db023d2d2643edae33a1583bc92b6481b1c2c57f610c77f4810bf5",
        "risk_case_count": len(risk_case_ids & {row["case_id"] for row in matched}),
        "clean_control_count": len(matched) - len(risk_case_ids & {row["case_id"] for row in matched}),
        "score": score,
        "formal_claim": False,
        "interpretation": "Risk coverage is measured only on risk-bearing cases; all cases and full protocol costs remain in the paired cohort.",
    }
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    main()
