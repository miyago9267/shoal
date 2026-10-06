"""Validate bounded changes to the repository's agent prompt surfaces."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


MANIFEST_RELATIVE = Path("docs/specs/prompt-document-lock/LOCK.json")
# Each surface names the version file of the host that owns it (Decision 6 of
# claude-eval-parity): a change to a protected surface only requires that
# host's version to change, never the repository-root VERSION.
HOST_VERSION_FILE = re.compile(r"hosts/[a-z0-9][a-z0-9-]*/VERSION")
REQUIRED_SURFACE_PATHS = frozenset(
    {
        "templates/agents-md.bootstrap.md",
        "templates/agents-md.orchestration.md",
        "plugin/plugins/pilotfish-codex/skills/pilotfish-orchestration/references/orchestration-policy.md",
        "plugin/plugins/pilotfish-codex/skills/pilotfish-orchestration/SKILL.md",
        "plugin/plugins/pilotfish-codex/skills/pilotfish-orchestration/agents/openai.yaml",
        "plugin/plugins/pilotfish-codex/.codex-plugin/plugin.json",
        "templates/agents/executor.toml",
        "templates/agents/mech-executor.toml",
        "templates/agents/plan-verifier.toml",
        "templates/agents/scout.toml",
        "templates/agents/sol-executor.toml",
        "templates/agents/security-executor.toml",
        "templates/agents/security-reviewer.toml",
        "templates/agents/verifier.toml",
        "templates/hooks.json",
        "INSTALL_PROMPT.md",
        "hosts/claude/dist/agents/executor.md",
        "hosts/claude/dist/agents/Explore.md",
        "hosts/claude/dist/agents/mech-executor.md",
        "hosts/claude/dist/agents/plan-verifier.md",
        "hosts/claude/dist/agents/scout.md",
        "hosts/claude/dist/agents/security-executor.md",
        "hosts/claude/dist/agents/security-reviewer.md",
        "hosts/claude/dist/agents/verifier.md",
        "hosts/claude/dist/skills/pilotfish-orchestration/SKILL.md",
        "hosts/claude/dist/skills/pilotfish-orchestration/references/orchestration-policy.md",
        "hosts/claude/dist/skills/pilotfish-orchestration/references/workflow-extensions.md",
    }
)
HARD_MAX_CHANGED_LINES = 32
HARD_MAX_CHANGED_CHARACTERS = 4000
HARD_MAX_CHANGE_RATIO = 0.35
HARD_MAX_BYTES = 60_000
MIGRATION_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,63}")
MIGRATION_KEYS = frozenset({"migration_id", "equivalence"})


class PromptLockError(ValueError):
    """Raised when a protected prompt surface violates the lock contract."""


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_relative_repo_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _validate_surface(surface: Any, index: int) -> None:
    if not isinstance(surface, dict):
        raise PromptLockError(f"surface {index}: expected an object")
    required = {
        "id",
        "path",
        "max_lines",
        "max_bytes",
        "max_changed_lines",
        "max_changed_characters",
        "max_change_ratio",
        "required_fragments",
        "version_file",
    }
    missing = required - surface.keys()
    if missing:
        raise PromptLockError(f"surface {index}: missing fields {sorted(missing)}")
    if not isinstance(surface["id"], str) or not surface["id"]:
        raise PromptLockError(f"surface {index}: id must be a non-empty string")
    if not _is_relative_repo_path(surface["path"]):
        raise PromptLockError(f"surface {surface['id']}: path must stay inside the repository")
    version_file = surface["version_file"]
    if not isinstance(version_file, str) or not HOST_VERSION_FILE.fullmatch(version_file):
        raise PromptLockError(
            f"surface {surface['id']}: version_file must be hosts/<host>/VERSION"
        )
    for field in ("max_lines", "max_bytes", "max_changed_lines", "max_changed_characters"):
        if not _is_positive_int(surface[field]):
            raise PromptLockError(f"surface {surface['id']}: {field} must be a positive integer")
    if surface["max_bytes"] > HARD_MAX_BYTES:
        raise PromptLockError(f"surface {surface['id']}: max_bytes exceeds the hard ceiling")
    if surface["max_changed_lines"] > HARD_MAX_CHANGED_LINES:
        raise PromptLockError(f"surface {surface['id']}: max_changed_lines exceeds the hard ceiling")
    if surface["max_changed_characters"] > HARD_MAX_CHANGED_CHARACTERS:
        raise PromptLockError(
            f"surface {surface['id']}: max_changed_characters exceeds the hard ceiling"
        )
    ratio = surface["max_change_ratio"]
    if not isinstance(ratio, (int, float)) or isinstance(ratio, bool) or not 0 < ratio <= HARD_MAX_CHANGE_RATIO:
        raise PromptLockError(f"surface {surface['id']}: max_change_ratio exceeds the hard ceiling")
    fragments = surface["required_fragments"]
    if not isinstance(fragments, list) or not fragments or not all(
        isinstance(fragment, str) and fragment for fragment in fragments
    ):
        raise PromptLockError(f"surface {surface['id']}: required_fragments must be non-empty strings")
    if "migration" in surface:
        _validate_migration(surface["id"], surface["migration"])


def _validate_migration(surface_id: str, migration: Any) -> None:
    """Check the shape of the optional one-time migration marker."""

    if not isinstance(migration, dict):
        raise PromptLockError(f"surface {surface_id}: migration must be an object")
    unknown = migration.keys() - MIGRATION_KEYS
    if unknown:
        raise PromptLockError(f"surface {surface_id}: migration has unknown keys {sorted(unknown)}")
    missing = MIGRATION_KEYS - migration.keys()
    if missing:
        raise PromptLockError(f"surface {surface_id}: migration is missing fields {sorted(missing)}")
    migration_id = migration["migration_id"]
    if not isinstance(migration_id, str) or not MIGRATION_ID.fullmatch(migration_id):
        raise PromptLockError(f"surface {surface_id}: migration_id must match {MIGRATION_ID.pattern}")
    if not _is_relative_repo_path(migration["equivalence"]):
        raise PromptLockError(f"surface {surface_id}: migration equivalence must stay inside the repository")


def _validate_lock_shape(lock: Any) -> dict[str, Any]:
    if not isinstance(lock, dict):
        raise PromptLockError("lock manifest must be an object")
    if lock.get("schema_version") != 2:
        raise PromptLockError("unsupported prompt lock schema")
    if lock.get("status") != "active":
        raise PromptLockError("prompt lock must be active")
    if lock.get("manifest_immutable") is not True:
        raise PromptLockError("prompt lock manifest must be immutable")
    if not isinstance(lock.get("update_protocol"), str) or "--allow-lock-update" not in lock["update_protocol"]:
        raise PromptLockError("prompt lock must declare its explicit update protocol")
    version_gate = lock.get("version_gate")
    if not isinstance(version_gate, dict):
        raise PromptLockError("prompt lock must declare the VERSION gate")
    if version_gate.get("require_change_for_protected_surfaces") is not True:
        raise PromptLockError("prompt lock VERSION gate must be enabled")
    surfaces = lock.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise PromptLockError("prompt lock must contain surfaces")
    ids: set[str] = set()
    paths: set[str] = set()
    for index, surface in enumerate(surfaces):
        _validate_surface(surface, index)
        if surface["id"] in ids:
            raise PromptLockError(f"duplicate prompt lock surface id: {surface['id']}")
        if surface["path"] in paths:
            raise PromptLockError(f"duplicate prompt lock surface path: {surface['path']}")
        ids.add(surface["id"])
        paths.add(surface["path"])
    missing_paths = REQUIRED_SURFACE_PATHS - paths
    if missing_paths:
        raise PromptLockError(f"prompt lock removed required surfaces: {sorted(missing_paths)}")
    mirrors = lock.get("mirrors")
    if not isinstance(mirrors, list) or not mirrors:
        raise PromptLockError("prompt lock must declare mirrored policy files")
    for index, mirror in enumerate(mirrors):
        if not isinstance(mirror, dict) or not _is_relative_repo_path(mirror.get("left")) or not _is_relative_repo_path(
            mirror.get("right")
        ):
            raise PromptLockError(f"mirror {index}: paths must stay inside the repository")
    return lock


def load_lock(root: Path) -> dict[str, Any]:
    """Load and validate the repository lock manifest."""

    path = root / MANIFEST_RELATIVE
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PromptLockError(f"missing lock manifest: {MANIFEST_RELATIVE}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise PromptLockError(f"invalid lock manifest: {MANIFEST_RELATIVE}") from exc
    return _validate_lock_shape(lock)


def _diff_metrics(before: str, after: str) -> dict[str, int | float]:
    old_lines = before.splitlines()
    new_lines = after.splitlines()
    line_matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    changed_lines = 0
    added_lines = 0
    removed_lines = 0
    for tag, old_start, old_end, new_start, new_end in line_matcher.get_opcodes():
        if tag == "equal":
            continue
        removed_lines += old_end - old_start
        added_lines += new_end - new_start
        changed_lines += (old_end - old_start) + (new_end - new_start)

    changed_characters = 0
    for tag, old_start, old_end, new_start, new_end in line_matcher.get_opcodes():
        if tag != "equal":
            changed_characters += sum(len(line) for line in old_lines[old_start:old_end])
            changed_characters += sum(len(line) for line in new_lines[new_start:new_end])
    total_characters = len(before) + len(after)
    return {
        "changed_lines": changed_lines,
        "added_lines": added_lines,
        "removed_lines": removed_lines,
        "changed_characters": changed_characters,
        "change_ratio": changed_characters / total_characters if total_characters else 0.0,
    }


def check_change_budget(surface: dict[str, Any], before: str, after: str) -> dict[str, int | float]:
    """Check one surface and return redacted diff metrics."""

    metrics = _diff_metrics(before, after)
    label = surface.get("id") or surface.get("path") or "surface"
    limits = (
        ("changed_lines", surface["max_changed_lines"]),
        ("changed_characters", surface["max_changed_characters"]),
        ("change_ratio", surface["max_change_ratio"]),
    )
    for metric, limit in limits:
        if metrics[metric] > limit:
            raise PromptLockError(
                f"{label}: change budget exceeded for {metric} "
                f"({metrics[metric]} > {limit})"
            )
    return metrics


def _git_show(root: Path, base_ref: str, relative_path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{relative_path}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _git_ref_exists(root: Path, ref: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.returncode == 0


def _default_base_ref(root: Path) -> str | None:
    configured = os.environ.get("PROMPT_LOCK_BASE", "").strip()
    if configured:
        return configured
    return "HEAD" if _git_ref_exists(root, "HEAD") else None


def _resolve_repo_file(root: Path, relative_path: str) -> Path:
    resolved_root = root.resolve()
    resolved_path = (root / relative_path).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise PromptLockError(f"surface path escapes the repository: {relative_path}") from exc
    if not resolved_path.is_file():
        raise PromptLockError(f"protected surface is missing: {relative_path}")
    return resolved_path


def _validate_surface_content(root: Path, surface: dict[str, Any]) -> str:
    relative_path = surface["path"]
    path = _resolve_repo_file(root, relative_path)
    try:
        raw = path.read_bytes()
        content = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PromptLockError(f"protected surface is unreadable: {relative_path}") from exc
    if len(raw) > surface["max_bytes"]:
        raise PromptLockError(f"{surface['id']}: absolute size limit exceeded")
    if len(content.splitlines()) > surface["max_lines"]:
        raise PromptLockError(f"{surface['id']}: absolute line limit exceeded")
    normalized_content = " ".join(content.split()).casefold()
    for index, fragment in enumerate(surface["required_fragments"], start=1):
        if " ".join(fragment.split()).casefold() not in normalized_content:
            raise PromptLockError(f"{surface['id']}: required fragment {index} is missing")
    return content


def _validate_mirrors(root: Path, lock: dict[str, Any]) -> None:
    for index, mirror in enumerate(lock["mirrors"], start=1):
        left = _resolve_repo_file(root, mirror["left"])
        right = _resolve_repo_file(root, mirror["right"])
        if left.read_bytes() != right.read_bytes():
            raise PromptLockError(f"mirror {index} diverged: {mirror['left']} and {mirror['right']}")


def _base_migration_ids(base_manifest: str) -> dict[str, str]:
    """Return {surface id: migration_id} recorded in the base manifest."""

    try:
        surfaces = json.loads(base_manifest).get("surfaces", [])
    except (json.JSONDecodeError, AttributeError):
        return {}
    ids: dict[str, str] = {}
    for surface in surfaces if isinstance(surfaces, list) else []:
        if isinstance(surface, dict) and isinstance(surface.get("migration"), dict):
            migration_id = surface["migration"].get("migration_id")
            if isinstance(migration_id, str):
                ids[str(surface.get("id"))] = migration_id
    return ids


def _check_equivalence(root: Path, surface: dict[str, Any]) -> None:
    relative_path = surface["migration"]["equivalence"]
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise PromptLockError(f"{surface['id']}: migration equivalence escapes the repository") from exc
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else None
    except (OSError, UnicodeDecodeError) as exc:
        raise PromptLockError(f"{surface['id']}: migration equivalence is unreadable") from exc
    if text is None:
        raise PromptLockError(f"{surface['id']}: migration equivalence file is missing")
    if not text.strip():
        raise PromptLockError(f"{surface['id']}: migration equivalence file is empty")


def validate_lock(
    root: Path,
    base_ref: str | None = None,
    *,
    allow_lock_update: bool = False,
    allow_migration: bool = True,
) -> dict[str, Any]:
    """Validate current surfaces and, when available, their Git diff budget.

    A surface may carry a one-time `migration` marker. It waives only the change
    budget, and only while `allow_lock_update` is set and the base manifest's
    same surface lacks the same `migration_id`. With `allow_migration=False`
    (the pull-request label path) an active marker is an error.
    """

    root = root.resolve()
    lock = load_lock(root)
    contents = {
        surface["path"]: _validate_surface_content(root, surface)
        for surface in lock["surfaces"]
    }
    _validate_mirrors(root, lock)

    base_ref = base_ref or _default_base_ref(root)
    if base_ref and not base_ref.strip("0"):
        base_ref = "HEAD^" if _git_ref_exists(root, "HEAD^") else None
    if not base_ref:
        return {
            "status": "ok",
            "surface_count": len(contents),
            "base_diff": "skipped-no-base",
            "surfaces": [],
        }

    base_manifest = _git_show(root, base_ref, MANIFEST_RELATIVE.as_posix())
    if base_manifest is None:
        return {
            "status": "ok",
            "surface_count": len(contents),
            "base_diff": "skipped-new-lock",
            "surfaces": [],
        }

    current_manifest = (root / MANIFEST_RELATIVE).read_text(encoding="utf-8")
    if current_manifest != base_manifest and not allow_lock_update:
        raise PromptLockError(
            "LOCK.json changed; use --allow-lock-update only for an explicitly approved policy renewal"
        )

    base_migrations = _base_migration_ids(base_manifest)
    reports: list[dict[str, Any]] = []
    for surface in lock["surfaces"]:
        relative_path = surface["path"]
        before = _git_show(root, base_ref, relative_path)
        if before is None:
            if not allow_lock_update:
                raise PromptLockError(
                    f"{surface['id']}: new protected surface requires --allow-lock-update"
                )
            reports.append(
                {
                    "id": surface["id"],
                    "path": relative_path,
                    "added": True,
                    "changed_lines": 0,
                    "added_lines": 0,
                    "removed_lines": 0,
                    "changed_characters": 0,
                    "change_ratio": 0.0,
                }
            )
            continue
        marker = surface.get("migration")
        if (
            marker
            and allow_lock_update
            and base_migrations.get(surface["id"]) != marker["migration_id"]
        ):
            if not allow_migration:
                raise PromptLockError(
                    f"{surface['id']}: migration is not accepted on this path"
                )
            _check_equivalence(root, surface)
            metrics = _diff_metrics(before, contents[relative_path])
            reports.append(
                {
                    "id": surface["id"],
                    "path": relative_path,
                    "migration": marker["migration_id"],
                    **metrics,
                }
            )
            continue
        metrics = check_change_budget(surface, before, contents[relative_path])
        reports.append({"id": surface["id"], "path": relative_path, **metrics})
    # Each changed surface requires a change of its own host's version file.
    changed_by_version_file: dict[str, list[str]] = {}
    for surface, report in zip(lock["surfaces"], reports):
        if report["changed_characters"]:
            changed_by_version_file.setdefault(surface["version_file"], []).append(surface["id"])
    for version_file, surface_ids in sorted(changed_by_version_file.items()):
        current_version = _resolve_repo_file(root, version_file).read_text(encoding="utf-8").strip()
        base_version = (_git_show(root, base_ref, version_file) or "").strip()
        if not base_version or current_version == base_version:
            raise PromptLockError(
                f"protected prompt changed without a VERSION update: {version_file} "
                f"(changed surfaces: {', '.join(surface_ids)})"
            )
    return {
        "status": "ok",
        "surface_count": len(contents),
        "base_diff": "checked",
        "surfaces": reports,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base-ref", default=None)
    parser.add_argument("--allow-lock-update", action="store_true")
    parser.add_argument(
        "--no-migration",
        action="store_true",
        help="reject surface migration markers (pull-request label path)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        report = validate_lock(
            args.root,
            base_ref=args.base_ref or None,
            allow_lock_update=args.allow_lock_update,
            allow_migration=not args.no_migration,
        )
    except PromptLockError as exc:
        print(f"prompt-document-lock: error: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "prompt-document-lock: ok "
            f"surfaces={report['surface_count']} base_diff={report['base_diff']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
