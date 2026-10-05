#!/usr/bin/env python3
"""Host-neutral contract for running one role-fitness content stage.

The content runner builds a prompt, hands it to a ``StageAdapter`` and scores
what comes back.  Everything host specific (argv, environment, session
materialization, transcript parsing, dispatch inspection) stays behind
``StageAdapter.run_stage``.  This module has no host imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class StageTimeout(Exception):
    """The host did not finish the stage within ``StageRequest.timeout``."""


class StageSetupError(Exception):
    """The host could not prepare an isolated stage; ``str()`` is its reason."""


class StageEvidenceError(Exception):
    """Dispatch/binding evidence could not be collected; ``detail`` names why."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class StageRequest:
    """One stage to run.

    ``role`` is None for a single-agent stage with no dispatch evidence;
    otherwise the named role the stage must dispatch to, with ``task_name`` the
    dispatch label the evidence must carry.  ``workdir`` is a clean directory
    the caller created (and may pre-populate or read back); ``scratch`` is the
    caller-owned directory for host-private state.  The caller removes both.
    """

    prompt: str
    role: str | None
    sandbox: str
    workdir: Path
    scratch: Path
    timeout: int
    task_name: str | None = None


@dataclass(frozen=True)
class DispatchEvidence:
    """Outcome of checking that the stage dispatched to the expected role."""

    ok: bool
    status: str
    reason_code: str
    model: str | None
    reasoning_effort: str | None


@dataclass(frozen=True)
class StageOutcome:
    """What a finished stage produced.

    ``messages`` and ``event_counts`` describe the stage's final agent (the
    dispatched child when there is one).  ``usage`` is the stage total;
    ``child_usage`` is the dispatched child alone and equals ``usage`` when
    nothing was dispatched.  ``events`` are host-native events kept only for
    bounded shape diagnostics.  ``wall_seconds`` is the unrounded host run time.
    """

    returncode: int
    messages: list[str]
    event_counts: dict[str, int]
    usage: dict[str, int]
    child_usage: dict[str, int]
    events: list[dict[str, Any]]
    wall_seconds: float
    evidence: DispatchEvidence | None


class StageAdapter(Protocol):
    """Runs one stage on one host.

    Raises ``StageSetupError`` before the host starts, ``StageTimeout`` when it
    overruns, and ``StageEvidenceError`` when a requested ``role`` leaves no
    usable dispatch evidence.  Other failures propagate unchanged.
    """

    def run_stage(self, request: StageRequest) -> StageOutcome: ...
