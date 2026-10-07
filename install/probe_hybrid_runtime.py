#!/usr/bin/env python3
"""Report Hybrid bootstrap, Plugin/Skill, and fresh-session activation evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install import (  # noqa: E402
    SHOAL_PLUGIN_NAME,
    SHOAL_PLUGIN_VERSION,
    _codex_cli,
    _plugin_is_installed,
    active_instruction_file,
)


MARKER_BEGIN = "<!-- shoal-codex:begin -->"
MARKER_END = "<!-- shoal-codex:end -->"
SESSION_SENTINEL = "SHOAL_HYBRID_SESSION_PROBE_7F3C"


def _bootstrap_status(codex_home: Path) -> str:
    try:
        policy = active_instruction_file(codex_home)
        text = policy.read_text(encoding="utf-8") if policy.is_file() else ""
    except (OSError, UnicodeError):
        return "unavailable"
    return "active" if MARKER_BEGIN in text and MARKER_END in text else "unavailable"


def _session_probe(
    codex_home: Path,
    project: Path,
    persona_token: str | None,
    recap_token: str | None,
) -> tuple[str, str, int]:
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(codex_home)
    requested_tokens = " ".join(
        token for token in (persona_token, recap_token) if token
    )
    prompt = (
        "Use the active shoal instructions without asking me to paste them. "
        f"If they are active, reply with {SESSION_SENTINEL}. "
        + (f"Also include these policy probe tokens: {requested_tokens}." if requested_tokens else "")
    )
    try:
        result = subprocess.run(
            [
                _codex_cli(), "exec", "--ephemeral", "--skip-git-repo-check",
                "--sandbox", "read-only", "--cd", str(project), prompt,
            ],
            capture_output=True, text=True, check=False, env=environment,
        )
    except OSError:
        return "unverified", "unverified", 127
    behavior = "verified" if result.returncode == 0 and SESSION_SENTINEL in result.stdout else "unverified"
    persona_recap = (
        "verified"
        if result.returncode == 0
        and all(token in result.stdout for token in (persona_token, recap_token) if token)
        else "unverified"
    )
    return behavior, persona_recap, result.returncode


def build_report(
    *, codex_home: Path, project: Path, run_session: bool,
    persona_token: str | None = None, recap_token: str | None = None,
) -> dict[str, object]:
    plugin = False
    try:
        plugin = _plugin_is_installed(source_root=Path(__file__).resolve().parents[1], codex_home=codex_home)
    except (OSError, ValueError):
        plugin = False
    report: dict[str, object] = {
        "bootstrap": _bootstrap_status(codex_home),
        "plugin": "installed" if plugin else "unavailable",
        "skill": "available" if plugin else "unavailable",
        "plugin_name": SHOAL_PLUGIN_NAME,
        "plugin_version": SHOAL_PLUGIN_VERSION,
        "shoal_behavior": "unverified",
        "persona_recap": "unverified",
    }
    if run_session:
        behavior, persona_recap, exit_code = _session_probe(
            codex_home, project, persona_token, recap_token
        )
        report["shoal_behavior"] = behavior
        report["persona_recap"] = persona_recap
        report["session_exit_code"] = exit_code
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--run-session", action="store_true")
    parser.add_argument("--persona-token")
    parser.add_argument("--recap-token")
    args = parser.parse_args(argv)
    project = args.project or args.codex_home
    print(json.dumps(
        build_report(
            codex_home=args.codex_home, project=project,
            run_session=args.run_session,
            persona_token=args.persona_token,
            recap_token=args.recap_token,
        ),
        ensure_ascii=False, sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
