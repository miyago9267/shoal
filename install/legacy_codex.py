"""Recognize and remove the pre-2.0.0 Codex install (the old product names).

docs/specs/shoal-rebrand N5/N8.  shoal 2.0.0 renamed everything the Codex installer
puts into a home.  The 2.0.0 installer (install/install.py) and tools/sync_global.py
call this module first: it recognizes what an earlier release installed (exact hook
groups, the install state's recorded script hash, marker blocks, config tables that
point at this repository's plugin/ directory), removes or renames only that, and
leaves every other byte alone.  The normal installer then installs the new names.

Every pre-2.0.0 name lives in a LEGACY_ constant below (or in
hook_registration.py); the rename scan (tools/scan_legacy_names.py) skips them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from hook_registration import (
    HookRegistrationError,
    LEGACY_GATE_SCRIPT,
    legacy_autoroute_locations,
    load_registration,
    remove_legacy_autoroute,
)

# ---- LEGACY_: names used before shoal 2.0.0 ----
LEGACY_STATE_SUFFIX = ".pilotfish-install-state.json"
LEGACY_STATE_PENDING_SUFFIX = ".json.pending"
LEGACY_GATE_RELATIVE = "hooks/" + LEGACY_GATE_SCRIPT
LEGACY_MARKER_BEGIN = "<!-- pilotfish-codex:begin -->"
LEGACY_MARKER_END = "<!-- pilotfish-codex:end -->"
LEGACY_MARKETPLACE = "pilotfish-codex"
LEGACY_TABLE_RENAMES = (
    ("[marketplaces.pilotfish-codex]", "[marketplaces.shoal-codex]"),
    (
        '[plugins."pilotfish-codex@pilotfish-codex"]',
        '[plugins."shoal-codex@shoal-codex"]',
    ),
    (
        '[plugins."pilotfish-jev-router@pilotfish-codex"]',
        '[plugins."shoal-jev-router@shoal-codex"]',
    ),
)
LEGACY_CACHE_RELATIVE = "plugins/cache/pilotfish-codex"
LEGACY_JEV_DIR = "pilotfish-jev"

# ---- current names ----
GUARD_RELATIVE = "hooks/shoal_guard.py"
MARKER_BEGIN = "<!-- shoal-codex:begin -->"
MARKER_END = "<!-- shoal-codex:end -->"
JEV_DIR = "shoal-jev"
BACKUP_INFIX = ".pre-shoal-"
POLICY_FILES = ("AGENTS.md", "AGENTS.override.md")


class LegacyMigrationError(Exception):
    """The legacy install cannot be migrated safely; nothing has been written."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def legacy_state_path(home: Path) -> Path:
    return home.with_name(f"{home.name}{LEGACY_STATE_SUFFIX}")


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.realpath(str(left))) == os.path.normcase(
        os.path.realpath(str(right))
    )


@dataclass
class Findings:
    """What a pre-2.0.0 install left in a Codex home (read-only inspection)."""

    home: Path
    state_path: Path | None = None
    state: dict | None = None
    gate_path: Path | None = None
    gate_proven: bool = (
        False  # the script still equals the hash the install state recorded
    )
    hooks_projection_ids: list[str] = field(default_factory=list)
    policy_files: list[Path] = field(default_factory=list)
    config_tables: list[str] = field(
        default_factory=list
    )  # legacy headers that will be renamed
    config_foreign: list[str] = field(default_factory=list)  # legacy headers left alone
    cache_dir: Path | None = None
    jev_dir: Path | None = None
    jev_blocked: bool = False  # both the legacy and the new dir exist
    proven_guard_sha256: str | None = None

    @property
    def found(self) -> bool:
        return bool(
            self.state_path
            or self.gate_path
            or self.hooks_projection_ids
            or self.policy_files
            or self.config_tables
            or self.cache_dir
            or self.jev_dir
        )

    def plan(self) -> list[str]:
        """Human-readable remove-old actions (the install-new half is the normal installer)."""
        lines: list[str] = []
        if self.hooks_projection_ids:
            lines.append(
                "remove legacy hooks.json groups: "
                + ", ".join(self.hooks_projection_ids)
            )
        if self.gate_path is not None:
            lines.append(
                f"remove {LEGACY_GATE_RELATIVE}"
                if self.gate_proven
                else f"unregister modified {LEGACY_GATE_RELATIVE} and keep it as a {BACKUP_INFIX}<ts> backup"
            )
        for path in self.policy_files:
            lines.append(f"replace legacy marker block in {path.name}")
        if self.config_tables:
            lines.append("rename config.toml tables: " + ", ".join(self.config_tables))
        if self.config_foreign:
            lines.append(
                "leave config.toml tables that do not point at this repository: "
                + ", ".join(self.config_foreign)
            )
        if self.cache_dir is not None:
            lines.append(f"remove stale plugin cache {LEGACY_CACHE_RELATIVE}")
        if self.jev_dir is not None:
            lines.append(
                f"leave {LEGACY_JEV_DIR}/ (the new {JEV_DIR}/ already exists)"
                if self.jev_blocked
                else f"rename {LEGACY_JEV_DIR}/ to {JEV_DIR}/"
            )
        if self.state_path is not None:
            lines.append(f"archive install state {self.state_path.name}")
        return lines


def _read_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LegacyMigrationError(f"legacy install state {path.name} is unreadable: {exc}") from exc
    if not isinstance(state, dict) or state.get("status") != "committed":
        raise LegacyMigrationError(f"legacy install state {path.name} is not a committed transaction")
    return state


def detect(home: Path, plugin_root: Path | None) -> Findings:
    """Inspect `home` without writing.  plugin_root is this repository's plugin/ directory."""
    findings = Findings(home=home)
    state_path = legacy_state_path(home)
    pending = state_path.with_suffix(LEGACY_STATE_PENDING_SUFFIX)
    if pending.exists():
        raise LegacyMigrationError(
            f"legacy install transaction is pending ({pending.name}); resolve the aborted install before migrating"
        )
    if state_path.is_file():
        findings.state_path = state_path
        findings.state = _read_state(state_path)
    fingerprints = (findings.state or {}).get("target_fingerprints")
    fingerprints = fingerprints if isinstance(fingerprints, dict) else {}

    gate = home / LEGACY_GATE_RELATIVE
    if gate.is_file() and not gate.is_symlink():
        findings.gate_path = gate
        findings.gate_proven = fingerprints.get(LEGACY_GATE_RELATIVE) == _sha256(
            gate.read_bytes()
        )
    guard = home / GUARD_RELATIVE
    if guard.is_file() and fingerprints.get(GUARD_RELATIVE) == _sha256(
        guard.read_bytes()
    ):
        findings.proven_guard_sha256 = fingerprints[GUARD_RELATIVE]

    hooks = home / "hooks.json"
    if hooks.is_file():
        try:
            document = load_registration(
                hooks.read_bytes(), source="existing hooks.json"
            )
        except HookRegistrationError:
            document = None  # the installer rejects malformed hooks.json itself
        if document is not None and legacy_autoroute_locations(document):
            findings.hooks_projection_ids = remove_legacy_autoroute(document)[1]

    for name in POLICY_FILES:
        path = home / name
        if path.is_file() and LEGACY_MARKER_BEGIN in path.read_text(
            encoding="utf-8", errors="replace"
        ):
            findings.policy_files.append(path)

    config = home / "config.toml"
    owned = False
    text = config.read_text(encoding="utf-8", errors="replace") if config.is_file() else ""
    headers = [
        old
        for old, _new in LEGACY_TABLE_RENAMES
        if re.search(rf"(?m)^[ \t]*{re.escape(old)}[ \t]*(?:#.*)?$", text)
    ]
    if headers:  # config.toml is only parsed when it carries a legacy table
        try:
            parsed = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise LegacyMigrationError(f"config.toml is not valid TOML: {exc}") from exc
        market = parsed.get("marketplaces", {}).get(LEGACY_MARKETPLACE)
        source = market.get("source") if isinstance(market, dict) else None
        owned = (
            isinstance(source, str)
            and plugin_root is not None
            and _same_path(Path(source), plugin_root)
        )
        (findings.config_tables if owned else findings.config_foreign).extend(headers)

    cache = home / LEGACY_CACHE_RELATIVE
    if cache.is_dir() and not cache.is_symlink() and owned:
        findings.cache_dir = cache
    jev = home / LEGACY_JEV_DIR
    if jev.is_dir() and not jev.is_symlink() and owned:
        findings.jev_dir = jev
        findings.jev_blocked = (home / JEV_DIR).exists()
    return findings


def _backup_copy(path: Path, suffix: str) -> None:
    target = path.with_name(f"{path.name}{BACKUP_INFIX}{suffix}")
    n = 0
    while target.exists():
        n += 1
        target = path.with_name(f"{path.name}{BACKUP_INFIX}{suffix}-{n}")
    target.write_bytes(path.read_bytes())
    os.chmod(target, path.stat().st_mode & 0o777)


def _write_keep_mode(path: Path, data: bytes) -> None:
    mode = path.stat().st_mode & 0o777
    tmp = path.with_name(f".{path.name}.shoal-migrate")
    tmp.write_bytes(data)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def _convert_policy(text: str) -> str:
    begins, ends = text.count(LEGACY_MARKER_BEGIN), text.count(LEGACY_MARKER_END)
    if begins != ends or begins > 1:
        raise LegacyMigrationError(
            "instruction file has unmatched or multiple legacy marker pairs"
        )
    if text.count(MARKER_BEGIN) or text.count(MARKER_END):
        raise LegacyMigrationError(
            "instruction file carries both legacy and shoal-codex markers"
        )
    return text.replace(LEGACY_MARKER_BEGIN, MARKER_BEGIN).replace(
        LEGACY_MARKER_END, MARKER_END
    )


def apply(findings: Findings) -> list[str]:
    """Remove or rename the legacy artifacts.  Returns what was done (for the installer's notes).

    Every file that is edited gets a `<name>.pre-shoal-<ts>` copy first; nothing the
    legacy install did not provably own is touched.  A home that still has a pending
    legacy transaction is rejected by detect().
    """
    home, ts, done = findings.home, stamp(), []
    # Validate everything that can fail before the first write.
    new_policy = {
        path: _convert_policy(path.read_text(encoding="utf-8"))
        for path in findings.policy_files
    }
    config_text = None
    if findings.config_tables:
        config_text = (home / "config.toml").read_text(encoding="utf-8")
        for old, new in LEGACY_TABLE_RENAMES:
            if old in findings.config_tables and re.search(
                rf"(?m)^[ \t]*{re.escape(new)}", config_text
            ):
                raise LegacyMigrationError(
                    f"config.toml already has {new}; resolve the duplicate first"
                )

    if findings.hooks_projection_ids:
        hooks = home / "hooks.json"
        document = load_registration(hooks.read_bytes(), source="existing hooks.json")
        cleaned, _ids = remove_legacy_autoroute(document)
        _backup_copy(hooks, ts)
        _write_keep_mode(
            hooks,
            (json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        done.append(
            "removed legacy hooks.json groups: "
            + ", ".join(findings.hooks_projection_ids)
        )
    if findings.gate_path is not None:
        if findings.gate_proven:
            findings.gate_path.unlink()
            done.append(f"removed {LEGACY_GATE_RELATIVE}")
        else:
            kept = findings.gate_path.with_name(
                f"{findings.gate_path.name}{BACKUP_INFIX}{ts}"
            )
            os.replace(findings.gate_path, kept)
            done.append(f"kept the modified {LEGACY_GATE_RELATIVE} as {kept.name}")
    for path, text in new_policy.items():
        _backup_copy(path, ts)
        _write_keep_mode(path, text.encode("utf-8"))
        done.append(f"converted the legacy marker block in {path.name}")
    if config_text is not None:
        _backup_copy(home / "config.toml", ts)
        for old, new in LEGACY_TABLE_RENAMES:
            if old in findings.config_tables:
                config_text = re.sub(
                    rf"(?m)^([ \t]*){re.escape(old)}",
                    lambda m, n=new: m.group(1) + n,
                    config_text,
                )
        tomllib.loads(config_text)
        _write_keep_mode(home / "config.toml", config_text.encode("utf-8"))
        done.append("renamed config.toml tables: " + ", ".join(findings.config_tables))
    if findings.cache_dir is not None:
        import shutil

        shutil.rmtree(findings.cache_dir)
        done.append(f"removed stale plugin cache {LEGACY_CACHE_RELATIVE}")
    if findings.jev_dir is not None and not findings.jev_blocked:
        os.rename(findings.jev_dir, home / JEV_DIR)
        done.append(f"renamed {LEGACY_JEV_DIR}/ to {JEV_DIR}/")
    if findings.state_path is not None:
        archived = findings.state_path.with_name(
            f"{findings.state_path.name}{BACKUP_INFIX}{ts}"
        )
        os.replace(findings.state_path, archived)
        done.append(f"archived install state as {archived.name}")
    return done
