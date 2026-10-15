#!/usr/bin/env python3
"""Create and validate the frozen role-fitness fixture/ledger bundle.

The public repository receives hashes and case metadata only.  Plan text,
rubrics, and the risk ledger are written to an explicitly supplied private
root so the model cannot receive the answer key during a live review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from benchmark_role_fitness import BenchmarkContractError, fixture_commitment


VERSION = "role-fitness-fixtures-v1"
COHORT_COUNTS = {"plan_review": 12, "mechanical_execution": 12, "split_workflow": 6}
PLAN_CLEAN_CONTROLS = 4
SEVERITIES = {"P0", "P1", "P2"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_private_root(path: Path) -> None:
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise BenchmarkContractError("private fixture root must be an unused absolute path")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)


def _plan_text(case_id: str, clean: bool, cohort: str = "plan_review") -> str:
    if clean:
        return (
            f"# {case_id}\n\n"
            "Update a non-production documentation index in one repository.\n\n"
            "The change is reversible, has no data migration, no external dependency, "
            "and includes a local acceptance check."
        )
    if cohort == "split_workflow":
        return (
            f"# {case_id}\n\n"
            "Migrate a production orders table from integer IDs to UUIDs across three services.\n\n"
            "The Plan includes foreign-key discovery and validation, bounded backfill batches, "
            "replication-lag thresholds, named owners, deployment prerequisites, stop conditions, "
            "and a tested acceptance checklist. It omits only an explicit dual-write period and "
            "the tested rollback artifact needed before the irreversible identifier cutover."
        )
    return (
        f"# {case_id}\n\n"
        "Migrate a production orders table from integer IDs to UUIDs across three services.\n\n"
        "Sequence: deploy the new schema, backfill in place, switch all services, then "
        "drop the integer ID column immediately. Constraints are no planned downtime, "
        "one deploy window, and rollback must be possible. The proposal omits a "
        "dual-write period, foreign-key validation, backfill batching, replication-lag "
        "checks, and a tested rollback artifact."
    )


def _ledger(case_id: str, clean: bool) -> list[dict[str, Any]]:
    if clean:
        return []
    return [
        {
            "id": f"{case_id}-migration-safety",
            "severity": "P1",
            "weight": 1,
            "anchor": "dual-write period",
            "revision_id": f"{case_id}-dual-write",
        },
        {
            "id": f"{case_id}-rollback",
            "severity": "P1",
            "weight": 1,
            "anchor": "tested rollback artifact",
            "revision_id": f"{case_id}-rollback",
        },
    ]


def _acceptance(case_id: str, cohort: str) -> tuple[str, bytes] | None:
    if cohort == "mechanical_execution":
        return "acceptance", _canonical(
            {
                "case_id": case_id,
                "allowed_paths": ["result.json"],
                "required_artifact": {"case_id": case_id, "accepted": True},
            }
        )
    if cohort == "split_workflow":
        return "revisions", _canonical(
            {
                "case_id": case_id,
                "revision_fragments": [
                    {"revision_id": f"{case_id}-dual-write", "text": "Add an explicit dual-write period and compatibility mapping."},
                    {"revision_id": f"{case_id}-rollback", "text": "Add a tested rollback artifact and a reversible cutover step."},
                ],
            }
        )
    return None


def _rubric(case_id: str, clean: bool, acceptance_hash: str | None) -> dict[str, Any]:
    return {
        "rubric_id": f"rubric-{case_id}",
        "case_id": case_id,
        "clean_control": clean,
        "acceptance_hash": acceptance_hash,
        "required_output": ["decision", "findings", "rationale"],
        "source_anchors": [] if clean else ["dual-write period", "tested rollback artifact"],
    }


def _case_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for cohort, count in COHORT_COUNTS.items():
        for number in range(1, count + 1):
            case_id = f"{cohort.replace('_', '-')}-{number:02d}"
            clean = cohort == "plan_review" and number <= PLAN_CLEAN_CONTROLS
            records.append({"case_id": case_id, "cohort": cohort, "clean_control": clean})
    return records


def _write_private(path: Path, value: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(value)
    os.chmod(path, mode)


def create_bundle(private_root: Path, *, salt: bytes | None = None) -> dict[str, Any]:
    """Create one immutable private bundle and return its public projection."""
    _safe_private_root(private_root)
    private_root.mkdir(mode=0o700)
    os.chmod(private_root, 0o700)
    salt = salt or os.urandom(32)
    if len(salt) < 16:
        raise BenchmarkContractError("fixture salt is too short")
    _write_private(private_root / "salt.bin", salt)
    manifest_cases: list[dict[str, Any]] = []
    ledgers: dict[str, list[dict[str, Any]]] = {}
    rubrics: dict[str, dict[str, Any]] = {}
    for record in _case_records():
        case_id = record["case_id"]
        clean = record["clean_control"]
        acceptance = _acceptance(case_id, record["cohort"])
        acceptance_hash = _sha256(acceptance[1]) if acceptance else None
        fixture_suffix = "md"
        fixture_bytes = _plan_text(case_id, clean, record["cohort"]).encode("utf-8")
        if record["cohort"] == "mechanical_execution":
            fixture_suffix = "json"
            fixture_bytes = _canonical(
                {
                    "fixture_version": "1",
                    "case_id": case_id,
                    "task": "produce the declared result artifact in the isolated worktree",
                    "input": {"operation": "update", "target": case_id},
                }
            )
        ledger = _ledger(case_id, clean)
        rubric = _rubric(case_id, clean, acceptance_hash)
        ledger_bytes = _canonical(ledger)
        rubric_bytes = _canonical(rubric)
        _write_private(private_root / "fixtures" / f"{case_id}.{fixture_suffix}", fixture_bytes)
        if acceptance:
            _write_private(private_root / acceptance[0] / f"{case_id}.json", acceptance[1])
        ledgers[case_id] = ledger
        rubrics[case_id] = rubric
        manifest_cases.append(
            {
                **record,
                "fixture_hash": _sha256(fixture_bytes),
                "ledger_hash": _sha256(ledger_bytes),
                "rubric_hash": _sha256(rubric_bytes),
                "ledger_commitment": fixture_commitment(salt, _sha256(fixture_bytes), ledger_bytes, rubric_bytes),
            }
        )
    _write_private(private_root / "ledgers.json", _canonical(ledgers))
    _write_private(private_root / "rubrics.json", _canonical(rubrics))
    private_manifest = {"version": VERSION, "cases": manifest_cases}
    _write_private(private_root / "manifest.json", _canonical(private_manifest))
    return public_projection(private_manifest)


def public_projection(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return hashes and case metadata without answer-key contents."""
    if manifest.get("version") != VERSION or not isinstance(manifest.get("cases"), list):
        raise BenchmarkContractError("fixture manifest is invalid")
    cases = []
    for case in manifest["cases"]:
        if not isinstance(case, dict) or set(case) != {
            "case_id", "cohort", "clean_control", "fixture_hash", "ledger_hash", "rubric_hash", "ledger_commitment"
        }:
            raise BenchmarkContractError("fixture manifest case shape is invalid")
        cases.append(dict(case))
    return {"version": VERSION, "case_count": len(cases), "cases": cases, "manifest_hash": _sha256(_canonical(manifest))}


def validate_mechanical_acceptance(case_id: str, value: Any) -> bool:
    """Validate the semantic contract consumed by the mechanical runner."""
    if not isinstance(value, dict) or set(value) != {"case_id", "allowed_paths", "required_artifact"}:
        raise BenchmarkContractError("mechanical acceptance schema is invalid")
    if value["case_id"] != case_id or value["allowed_paths"] != ["result.json"]:
        raise BenchmarkContractError("mechanical acceptance scope is invalid")
    artifact = value["required_artifact"]
    if not isinstance(artifact, dict) or set(artifact) != {"case_id", "accepted"} or artifact != {"case_id": case_id, "accepted": True}:
        raise BenchmarkContractError("mechanical acceptance artifact is invalid")
    return True


def validate_split_revisions(case_id: str, value: Any) -> bool:
    """Validate the deterministic revision fragment contract."""
    if not isinstance(value, dict) or set(value) != {"case_id", "revision_fragments"} or value["case_id"] != case_id:
        raise BenchmarkContractError("split revision schema is invalid")
    fragments = value["revision_fragments"]
    if not isinstance(fragments, list) or not fragments:
        raise BenchmarkContractError("split revision fragments are empty")
    seen: set[str] = set()
    for fragment in fragments:
        if not isinstance(fragment, dict) or set(fragment) != {"revision_id", "text"}:
            raise BenchmarkContractError("split revision fragment schema is invalid")
        revision_id, text = fragment["revision_id"], fragment["text"]
        if not isinstance(revision_id, str) or not revision_id or revision_id in seen or not isinstance(text, str) or not text.strip():
            raise BenchmarkContractError("split revision fragment value is invalid")
        seen.add(revision_id)
    return True


def validate_bundle(private_root: Path) -> dict[str, Any]:
    """Validate private bytes, commitments, counts, and answer-key boundaries."""
    if (
        not private_root.is_dir()
        or private_root.is_symlink()
        or (os.name != "nt" and stat.S_IMODE(private_root.stat().st_mode) & 0o077)
    ):
        raise BenchmarkContractError("private fixture root permissions are unsafe")
    try:
        salt = (private_root / "salt.bin").read_bytes()
        manifest = json.loads((private_root / "manifest.json").read_text(encoding="utf-8"))
        ledgers = json.loads((private_root / "ledgers.json").read_text(encoding="utf-8"))
        rubrics = json.loads((private_root / "rubrics.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkContractError("private fixture bundle is unreadable") from exc
    if public_projection(manifest)["case_count"] != sum(COHORT_COUNTS.values()):
        raise BenchmarkContractError("fixture count is incomplete")
    counts = {cohort: 0 for cohort in COHORT_COUNTS}
    p0_p1 = 0
    clean_controls = 0
    for case in manifest["cases"]:
        case_id = case["case_id"]
        cohort = case["cohort"]
        counts[cohort] += 1
        if case["clean_control"]:
            clean_controls += 1
        fixture_suffix = "json" if case["cohort"] == "mechanical_execution" else "md"
        fixture_bytes = (private_root / "fixtures" / f"{case_id}.{fixture_suffix}").read_bytes()
        ledger = ledgers.get(case_id)
        rubric = rubrics.get(case_id)
        if not isinstance(ledger, list) or not isinstance(rubric, dict):
            raise BenchmarkContractError("fixture answer key is incomplete")
        if _sha256(fixture_bytes) != case["fixture_hash"] or _sha256(_canonical(ledger)) != case["ledger_hash"] or _sha256(_canonical(rubric)) != case["rubric_hash"]:
            raise BenchmarkContractError("fixture hash mismatch")
        if fixture_commitment(salt, case["fixture_hash"], _canonical(ledger), _canonical(rubric)) != case["ledger_commitment"]:
            raise BenchmarkContractError("fixture commitment mismatch")
        acceptance_hash = rubric.get("acceptance_hash")
        if case["cohort"] == "mechanical_execution":
            acceptance = (private_root / "acceptance" / f"{case_id}.json")
            if not acceptance.is_file() or _sha256(acceptance.read_bytes()) != acceptance_hash:
                raise BenchmarkContractError("mechanical acceptance artifact is invalid")
            validate_mechanical_acceptance(case_id, json.loads(acceptance.read_text(encoding="utf-8")))
        elif case["cohort"] == "split_workflow":
            revisions = (private_root / "revisions" / f"{case_id}.json")
            if not revisions.is_file() or _sha256(revisions.read_bytes()) != acceptance_hash:
                raise BenchmarkContractError("split revision artifact is invalid")
            validate_split_revisions(case_id, json.loads(revisions.read_text(encoding="utf-8")))
        elif acceptance_hash is not None:
            raise BenchmarkContractError("plan rubric has an unexpected acceptance artifact")
        for finding in ledger:
            if finding.get("severity") in SEVERITIES - {"P2"}:
                p0_p1 += int(finding.get("weight", 0))
    if counts != COHORT_COUNTS or clean_controls != PLAN_CLEAN_CONTROLS or p0_p1 < 4:
        raise BenchmarkContractError("fixture acceptance gate is incomplete")
    return public_projection(manifest)


def score_plan_review(ledger: list[dict[str, Any]], output: dict[str, Any]) -> dict[str, Any]:
    """Score an anonymous review against the private source-rubric ledger."""
    if not isinstance(output, dict) or set(output) != {"decision", "findings", "rationale"}:
        raise BenchmarkContractError("review output shape is invalid")
    if output["decision"] not in {"READY", "REVISE"} or not isinstance(output["findings"], list) or not isinstance(output["rationale"], str) or not output["rationale"].strip():
        raise BenchmarkContractError("review output values are invalid")
    findings = output["findings"]
    matched: set[str] = set()
    true_findings = 0
    actionable = 0
    claimed_critical = 0
    supported_critical = 0
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {"severity", "title", "evidence", "revision_id"}:
            raise BenchmarkContractError("review finding shape is invalid")
        if finding["severity"] not in SEVERITIES or not all(isinstance(finding[key], str) and finding[key].strip() for key in ("title", "evidence")):
            raise BenchmarkContractError("review finding values are invalid")
        if finding["severity"] in {"P0", "P1"}:
            claimed_critical += 1
        haystack = f"{finding['title']} {finding['evidence']}".casefold()
        match = next((entry for entry in ledger if entry["id"] not in matched and entry["anchor"].casefold() in haystack), None)
        if match is None:
            continue
        matched.add(match["id"])
        true_findings += 1
        if finding["severity"] == match["severity"] and finding["revision_id"] == match["revision_id"]:
            actionable += 1
        if match["severity"] in {"P0", "P1"} and finding["severity"] == match["severity"]:
            supported_critical += 1
    total_weight = sum(int(entry["weight"]) for entry in ledger)
    critical_total = sum(int(entry["weight"]) for entry in ledger if entry["severity"] in {"P0", "P1"})
    clean_control = not ledger
    expected_decision = "READY" if clean_control else "REVISE"
    false_escalation = clean_control and (output["decision"] != "READY" or findings)
    return {
        "decision": output["decision"],
        "expected_decision": expected_decision,
        "risk_coverage": sum(int(entry["weight"]) for entry in ledger if entry["id"] in matched) / total_weight if total_weight else 1.0,
        "critical_precision": supported_critical / claimed_critical if claimed_critical else (1.0 if not critical_total else 0.0),
        "actionable_revision": actionable / len(ledger) if ledger else 1.0,
        "matched_findings": true_findings,
        "supported_findings": supported_critical,
        "claimed_findings": len(findings),
        "false_escalation": bool(false_escalation),
        "inconclusive": False,
        "passed": output["decision"] == expected_decision and not false_escalation,
    }


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--public-manifest", type=Path)
    args = parser.parse_args(argv)
    if args.create == args.validate:
        parser.error("choose exactly one of --create or --validate")
    result = create_bundle(args.private_root) if args.create else validate_bundle(args.private_root)
    if args.public_manifest:
        args.public_manifest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        args.public_manifest.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    try:
        json.dump(main(), sys.stdout, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
    except BenchmarkContractError as exc:
        print(f"fixture_bundle_failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
