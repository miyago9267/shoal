#!/usr/bin/env python3
"""Claude host stage adapter for the role-fitness content runner.

Implements claude-eval-parity R4-R6 behind ``StageAdapter``: one ``claude -p``
process per stage in a private root that is deleted before the stage returns,
dispatch evidence read from the stream, a frozen-manifest guard and the
cumulative cost admission.

Nothing here has been checked against a live ``claude`` run yet.  The stream
shapes, the token variable name, and the effect of the isolation and budget
flags are repo-external facts that AC-CE-018 still has to confirm; every parser
path therefore fails closed on a shape it does not recognise.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from role_fitness_fixtures import BenchmarkContractError, validate_bundle
from role_fitness_stage import (
    DispatchEvidence,
    StageAdapter,
    StageEvidenceError,
    StageOutcome,
    StageRequest,
    StageSetupError,
    StageTimeout,
)


ROOT = Path(__file__).resolve().parents[1]
DIST_AGENTS = ROOT / "hosts" / "claude" / "dist" / "agents"

# UNVERIFIED: the name of the variable `claude` reads a `claude setup-token`
# subscription token from has not been confirmed by a live call (SPEC Open
# question 5, AC-CE-018).  This constant is the only place that names it.
SUBSCRIPTION_TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"

# `manifest_hash` of docs/benchmarks/role-fitness-v1-fixtures-manifest-v2.json.
FROZEN_MANIFEST_V2_HASH = (
    "7ef0ac3299c5be0a016cf240cc428f95339d9adadedaad8e23d311deb309b3e2"
)

# Settled stop point of one run (SPEC "Live run 與成本").
RUN_COST_CAP_USD = Decimal("30")

DISPATCH_TOOL = "Agent"
DISPATCH_OK = "NATIVE_OK"
DISPATCH_FAILED = "NATIVE_DISPATCH_FAILED"

# Informational event seen in live runs (CLI 2.1.289, 2026-10-05).  Observed
# `rate_limit_info`: `status` ("allowed_warning" in every run so far),
# `rateLimitType`, `isUsingOverage` (false), `resetsAt`, `utilization`,
# `unifiedWindows`.  A rejected quota has never been observed: the stop rule
# below is inferred from the `allowed*` values, not from a seen rejection.
RATE_LIMIT_EVENT = "rate_limit_event"
RATE_LIMIT_ALLOWED_PREFIX = "allowed"
# A top-level type marker in a line that is not valid JSON (text nested in a
# message would carry escaped quotes and does not match).
_BROKEN_RATE_LIMIT_RE = re.compile(r'(?<!\\)"type"\s*:\s*"rate_limit_event"')
USAGE_LIMIT_REPORTED = "usage limit reported by the host"
USAGE_STATE_UNKNOWN = "usage state could not be read"

# A dispatching stream holds more than one `result` event: the Agent task runs
# in the background and the parent is woken once more when it completes (that
# result carries `origin.kind == "task-notification"`).  Two live runs of the
# same stage (CLI 2.1.289, 2026-10-05) put the results and the second
# `system/init` in different positions, so nothing here depends on where they
# sit; only the last event must be a result.  One dispatch explains two
# results; one more is slack.
MAX_STAGE_ROUNDS = 3
WAKE_ORIGIN = "task-notification"
TASK_COMPLETED = "completed"
_MODEL_USAGE_KEYS = {
    "input_tokens": "inputTokens",
    "cache_creation_input_tokens": "cacheCreationInputTokens",
    "cache_read_input_tokens": "cacheReadInputTokens",
    "output_tokens": "outputTokens",
}

# StageRequest.sandbox -> permission mode.  Prompts are never answered
# (`--permission-prompts none`), so anything the mode does not allow is denied.
_PERMISSION_MODES = {"read-only": "manual", "workspace-write": "acceptEdits"}

# The child gets an allowlisted environment, not the caller's: an inherited API
# key or provider switch would silently replace the subscription login, and
# unrelated secrets have no business in a model-driven process.
_PASSTHROUGH_ENV = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
)

# Bounds of the post-stage workdir scan; a tree beyond them fails the stage.
WORKDIR_SCAN_MAX_FILES = 1000
WORKDIR_SCAN_MAX_FILE_BYTES = 1024 * 1024
WORKDIR_SCAN_MAX_BYTES = 32 * 1024 * 1024

_ROLE_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
# A model alias or full name; it is passed as one argv element.
_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\[\]-]{0,79}")
_RESULT_USAGE_KEYS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)


class StageCleanupError(Exception):
    """Stage-private data could not be deleted; the stage has failed."""


class StageRateLimited(StageEvidenceError):
    """The host reported a usage limit that is not plainly allowed (AC-CE-032).

    ``detail`` is ``rate_limit_not_allowed``, ``rate_limit_status_unknown`` or
    ``rate_limit_overage``.  The run must not start another stage.
    """


class StageNotAdmitted(StageSetupError):
    """The cumulative cost admission refused to start the stage."""


@dataclass(frozen=True)
class StageObservation:
    """What a finished child left behind, shown to an observer before deletion.

    ``stdout`` and ``stderr`` are the raw in-memory output: an observer must
    reduce them to shapes and must not store or write them.  ``private`` holds
    the stage's ``config``, ``home`` and ``tmp`` directories; they and the
    staged ``.claude`` under ``workdir`` are deleted right after the observer
    returns.  An observer is never called when the output carries the token.
    """

    returncode: int
    stdout: str
    stderr: str
    private: Path
    workdir: Path


def _usd(value: Any, what: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise BenchmarkContractError(f"{what} must be a dollar amount")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise BenchmarkContractError(f"{what} must be a dollar amount") from exc
    if not amount.is_finite() or amount <= 0 or amount > RUN_COST_CAP_USD:
        raise BenchmarkContractError(f"{what} must be positive and at most the run cap")
    return amount


def require_frozen_manifest(private_root: Path) -> dict[str, Any]:
    """Validate the private bundle and reject anything but the frozen manifest v2."""
    projection = validate_bundle(private_root)
    if projection.get("manifest_hash") != FROZEN_MANIFEST_V2_HASH:
        raise BenchmarkContractError("fixture manifest is not the frozen v2 manifest")
    return projection


def claude_dispatch_prompt(*, role: str, task_name: str, message: str) -> str:
    """Ask the parent session to hand ``message`` to one named subagent."""
    return (
        f"Call the {DISPATCH_TOOL} tool exactly once with subagent_type='{role}' and "
        f"description='{task_name}', passing the following message unchanged as its prompt:\n\n"
        + message
        + f"\n\nWhen the {DISPATCH_TOOL} tool returns, stop. Do not do the work yourself, do not "
        f"call the {DISPATCH_TOOL} tool a second time, and do not use any other subagent_type."
    )


def claude_native_review_prompt(plan: str) -> str:
    """Claude form of the native plan-verifier review; the inner message matches Codex."""
    from run_role_fitness_content import _native_review_message

    return claude_dispatch_prompt(
        role="plan-verifier",
        task_name="role_fitness_plan_review",
        message=_native_review_message(plan),
    )


def _subscription_token() -> str:
    """Read the token from the environment only; never fall back to stored logins."""
    token = os.environ.get(SUBSCRIPTION_TOKEN_ENV)
    if (
        not token
        or token != token.strip()
        or any(character.isspace() for character in token)
    ):
        raise StageSetupError(
            f"subscription token is not available in {SUBSCRIPTION_TOKEN_ENV}"
        )
    return token


def _account_home() -> Path:
    """The user's home from the OS account record, not from the environment."""
    home: str | None = None
    try:
        if os.name == "nt":
            import ctypes

            buffer = ctypes.create_unicode_buffer(1024)
            # CSIDL_PROFILE: the profile directory of the calling account.
            if ctypes.windll.shell32.SHGetFolderPathW(None, 40, None, 0, buffer) == 0:
                home = buffer.value
        else:
            import pwd

            home = pwd.getpwuid(os.getuid()).pw_dir
    except (OSError, KeyError, AttributeError, ImportError):
        home = None
    if not home or not os.path.isabs(home):
        raise StageSetupError("user home cannot be determined")
    return Path(home)


def _protected_config_dirs() -> list[str]:
    """The user's own Claude config locations a stage must stay out of.

    ``HOME`` can be pointed anywhere, so the account's real home is protected
    as well as whatever the environment currently names.
    """
    protected = [_account_home() / ".claude"]
    try:
        protected.append(Path.home() / ".claude")
    except RuntimeError:
        pass
    inherited = os.environ.get("CLAUDE_CONFIG_DIR")
    if inherited:
        protected.append(Path(inherited))
    return [os.path.realpath(path) for path in protected]


def _require_outside_user_config(path: Path) -> None:
    real = Path(os.path.realpath(path))
    for protected in _protected_config_dirs():
        if real == Path(protected) or Path(protected) in real.parents:
            raise StageSetupError("stage directory is inside the user's Claude config")


def _committed_agents() -> list[Path]:
    try:
        entries = sorted(DIST_AGENTS.iterdir())
    except OSError:
        raise StageSetupError("committed Claude agents are unreadable") from None
    if not entries or any(
        entry.is_symlink() or not entry.is_file() or entry.suffix != ".md"
        for entry in entries
    ):
        raise StageSetupError(
            "committed Claude agents directory has an unexpected entry"
        )
    return entries


def _role_models(value: Any, agents: list[Path]) -> dict[str, str]:
    """Validate per-role model overrides: committed roles, plain model names."""
    if value is None:
        return {}
    known = {entry.stem for entry in agents}
    if not isinstance(value, dict) or any(
        not isinstance(role, str)
        or role not in known
        or not isinstance(model, str)
        or not _MODEL_RE.fullmatch(model)
        for role, model in value.items()
    ):
        raise BenchmarkContractError(
            "role models must map committed Claude agents to model names"
        )
    return dict(value)


def _with_model(text: str, model: str) -> str:
    """Agent file text with the frontmatter ``model:`` line replaced.

    Only that one line changes: the role's prompt body and every other binding
    stay byte for byte what the committed dist holds.  A file without exactly
    one such line in a leading frontmatter block is refused.
    """
    end = text.find("\n---\n", 4)
    if not text.startswith("---\n") or end < 0:
        raise StageSetupError("staged agent has no frontmatter")
    head = text[4:end].split("\n")
    bound = [index for index, line in enumerate(head) if line.startswith("model:")]
    if len(bound) != 1:
        raise StageSetupError("staged agent has no single model binding")
    head[bound[0]] = f"model: {model}"
    return "---\n" + "\n".join(head) + text[end:]


def _remove_private(*paths: Path) -> None:
    """Delete stage-private trees; anything left behind fails the stage."""
    failed = False
    for path in paths:
        try:
            # A symlink here was not created by the adapter: do not follow it.
            if not path.is_symlink() and path.exists():
                shutil.rmtree(path)
        except OSError:
            failed = True
        if path.is_symlink() or path.exists():
            failed = True
    if failed:
        raise StageCleanupError("claude stage cleanup failed") from None


def _workdir_problem(workdir: Path, token: str) -> str | None:
    """Look for the token in what the stage left in the caller's workdir.

    Returns None when the bounded scan finds nothing.  When the token is found,
    or the tree cannot be scanned completely within the bounds, the workdir is
    emptied (the stage has failed, so its artifacts are void) and a short reason
    code is returned; ``workdir_cleanup_failed`` means it could not be emptied.
    The staged ``.claude`` is skipped here because it is deleted separately.
    """
    needle = token.encode("utf-8")
    problem: str | None = None
    try:
        pending = [entry for entry in os.scandir(workdir) if entry.name != ".claude"]
        files = scanned = 0
        while pending and problem is None:
            entry = pending.pop()
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                pending.extend(os.scandir(entry.path))
                continue
            size = entry.stat(follow_symlinks=False).st_size
            files += 1
            scanned += size
            if files > WORKDIR_SCAN_MAX_FILES or size > WORKDIR_SCAN_MAX_FILE_BYTES or scanned > WORKDIR_SCAN_MAX_BYTES:
                problem = "workdir_scan_limit"
            elif needle in Path(entry.path).read_bytes():
                problem = "credential_in_workdir"
    except OSError:
        problem = "workdir_scan_failed"
    if problem is None:
        return None
    try:
        for entry in list(os.scandir(workdir)):
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path)
            else:
                os.unlink(entry.path)
        if os.listdir(workdir):
            return "workdir_cleanup_failed"
    except OSError:
        return "workdir_cleanup_failed"
    return problem


def _bad_stream(detail: str) -> StageEvidenceError:
    return StageEvidenceError(detail)


def _count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _result_texts(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        raise _bad_stream("unrecognized_tool_result")
    texts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or not isinstance(block.get("type"), str):
            raise _bad_stream("unrecognized_tool_result")
        if block["type"] == "text":
            if not isinstance(block.get("text"), str):
                raise _bad_stream("unrecognized_tool_result")
            texts.append(block["text"])
    return texts


def _require_rate_limit_allowed(event: dict[str, Any]) -> None:
    """Fail closed unless a rate limit event plainly allows the run to go on.

    Only a ``status`` starting with ``allowed`` continues; any other value, a
    missing status or active overage (extra cost) stops the stage.
    """
    info = event.get("rate_limit_info")
    if not isinstance(info, dict):
        raise _bad_stream("unrecognized_stream_event")
    status, overage = info.get("status"), info.get("isUsingOverage", False)
    if not isinstance(status, str) or not status:
        raise StageRateLimited("rate_limit_status_unknown")
    if not status.startswith(RATE_LIMIT_ALLOWED_PREFIX):
        raise StageRateLimited("rate_limit_not_allowed")
    if overage is not False:
        raise StageRateLimited("rate_limit_overage")


def _require_no_usage_limit(stdout: Any) -> None:
    """Raise ``StageRateLimited`` unless every usage report plainly allows the run.

    Runs before, and independently of, the completeness checks of
    ``parse_stream``: a rejected quota is exactly when the stream is likely to
    be cut short or malformed, and a timeout leaves only partial output.  Lines
    that are not JSON are skipped unless they are a broken rate limit event.
    A rate limit event that cannot be read (no ``rate_limit_info`` object, no
    string ``status``, or a damaged line) means the usage state is unknown,
    which also stops the run: ``rate_limit_status_unknown``.
    """
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    if not isinstance(stdout, str):
        return
    for line in stdout.splitlines():
        if RATE_LIMIT_EVENT not in line:
            continue
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            if _BROKEN_RATE_LIMIT_RE.search(line):
                raise StageRateLimited("rate_limit_status_unknown") from None
            continue
        if isinstance(event, dict) and event.get("type") == RATE_LIMIT_EVENT:
            try:
                _require_rate_limit_allowed(event)
            except StageRateLimited:
                raise
            except StageEvidenceError:
                raise StageRateLimited("rate_limit_status_unknown") from None


def _result_round(result: dict[str, Any]) -> dict[str, Any]:
    """Validate one ``result`` event and return what a round contributes."""
    usage, cost, models = (
        result.get("usage"),
        result.get("total_cost_usd"),
        result.get("modelUsage"),
    )
    if (
        not isinstance(result.get("subtype"), str)
        or not isinstance(result.get("is_error"), bool)
        or not isinstance(usage, dict)
        or not all(_count(usage.get(key)) for key in _RESULT_USAGE_KEYS)
        or isinstance(cost, bool)
        or not isinstance(cost, (int, float))
        or not math.isfinite(cost)
        or cost < 0
        or not isinstance(models, dict)
        or any(
            not isinstance(name, str) or not name or not isinstance(entry, dict)
            for name, entry in models.items()
        )
    ):
        raise _bad_stream("unrecognized_result_event")
    return {
        "usage": {key: usage[key] for key in _RESULT_USAGE_KEYS},
        "cost": float(cost),
        "models": models,
        "failed": result["is_error"] or result["subtype"] != "success",
        "text": result.get("result"),
        "wake": isinstance(result.get("origin"), dict)
        and result["origin"].get("kind") == WAKE_ORIGIN,
    }


def _stage_totals(rounds: list[dict[str, Any]]) -> tuple[dict[str, int], float]:
    """Raw usage and cost of a whole stage from its results; never undercounts.

    Cost: ``total_cost_usd`` is cumulative over the session.  In a live run
    both results reported the same total, and it equalled the sum of the
    ``modelUsage`` costs including the subagent's model.  The stage cost is the
    largest total of any result, wherever it sits.

    Usage: ``usage`` is per result and covers the parent only (live: the two
    results' fields added up to the parent model's ``modelUsage``);
    ``modelUsage`` is cumulative per model and includes the subagent.  Each
    field is the larger of the per-result sum and the largest per-model sum.
    """
    totals = {
        key: sum(entry["usage"][key] for entry in rounds) for key in _RESULT_USAGE_KEYS
    }
    for entry in rounds:
        per_model = list(entry["models"].values())
        if per_model and all(
            _count(model.get(name))
            for model in per_model
            for name in _MODEL_USAGE_KEYS.values()
        ):
            for key, name in _MODEL_USAGE_KEYS.items():
                totals[key] = max(totals[key], sum(model[name] for model in per_model))
    return totals, max(entry["cost"] for entry in rounds)


def parse_stream(stdout: str, role: str | None) -> dict[str, Any]:
    """Read one ``--output-format stream-json`` run.

    Returns the dispatched child's messages, event counts, usage normalised to
    the runner's keys, cost, model, dispatch evidence and whether the host
    reported the run as failed.  Raises ``StageEvidenceError`` with a short
    code (never stream content) for any event shape it does not recognise.
    With ``role`` None (a single-agent stage) there is no dispatch evidence and
    the message is the last result event's final text.

    Events are judged by their own fields, not by position.  The only
    positional rule is that the stream ends with a ``result``.  There must be
    one to ``MAX_STAGE_ROUNDS`` results and the stage has failed when any of
    them failed.  ``system`` events and ``rate_limit_event`` are informational.

    Dispatch evidence is the parent's single ``Agent`` tool call
    (``parent_tool_use_id`` null) with a tool result that is not an error.
    That tool result is only a launch receipt, so the child's messages are the
    text blocks of the assistant events whose ``parent_tool_use_id`` is the
    call's id, in stream order; without one the dispatch is not accepted.  A
    task event naming the call (``tool_use_id``) must not contradict it: a
    started task needs a notification, and a notification must say completed.
    """
    events: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            event = None
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise _bad_stream("unrecognized_stream_event")
        events.append(event)
    if not events or events[-1]["type"] != "result":
        raise _bad_stream("no_result_event")

    event_counts: dict[str, int] = {}
    calls: list[tuple[str, Any]] = []
    results: dict[str, tuple[bool, list[str]]] = {}
    seen_tool_ids: set[str] = set()
    rounds: list[dict[str, Any]] = []
    child_texts: dict[str, list[str]] = {}
    started: set[str] = set()
    notified: dict[str, list[str]] = {}
    for event in events:
        kind = event["type"]
        event_counts[kind] = event_counts.get(kind, 0) + 1
        if kind == "result":
            rounds.append(_result_round(event))
            if len(rounds) > MAX_STAGE_ROUNDS:
                raise _bad_stream("too_many_rounds")
            continue
        if kind == "system":
            subtype = event.get("subtype")
            if not isinstance(subtype, str):
                raise _bad_stream("unrecognized_stream_event")
            if subtype in {"task_started", "task_notification"}:
                # The two task events that name the tool call they belong to.
                tool_id = event.get("tool_use_id")
                if not isinstance(tool_id, str) or not tool_id:
                    raise _bad_stream("unrecognized_stream_event")
                if subtype == "task_started":
                    started.add(tool_id)
                elif not isinstance(event.get("status"), str):
                    raise _bad_stream("unrecognized_stream_event")
                else:
                    notified.setdefault(tool_id, []).append(event["status"])
            continue
        if kind == RATE_LIMIT_EVENT:
            _require_rate_limit_allowed(event)
            continue
        if kind not in {"assistant", "user"}:
            raise _bad_stream("unrecognized_stream_event")
        # Without an explicit parent marker a subagent's own tool call could be
        # mistaken for the parent's dispatch.
        if "parent_tool_use_id" not in event or not (
            event["parent_tool_use_id"] is None
            or isinstance(event["parent_tool_use_id"], str)
        ):
            raise _bad_stream("unrecognized_stream_event")
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if kind == "user" and isinstance(content, str):
            continue
        if not isinstance(content, list) or any(
            not isinstance(block, dict) or not isinstance(block.get("type"), str)
            for block in content
        ):
            raise _bad_stream("unrecognized_stream_event")
        if event["parent_tool_use_id"] is not None:
            if kind == "assistant":
                for block in content:
                    if block["type"] != "text":
                        continue
                    if not isinstance(block.get("text"), str):
                        raise _bad_stream("unrecognized_stream_event")
                    if block["text"].strip():
                        child_texts.setdefault(event["parent_tool_use_id"], []).append(
                            block["text"]
                        )
            continue
        for block in content:
            if kind == "assistant" and block["type"] == "tool_use":
                tool_id, name, tool_input = (
                    block.get("id"),
                    block.get("name"),
                    block.get("input"),
                )
                if (
                    not isinstance(tool_id, str)
                    or not tool_id
                    or not isinstance(name, str)
                    or not isinstance(tool_input, dict)
                    or tool_id in seen_tool_ids
                ):
                    raise _bad_stream("unrecognized_tool_use")
                seen_tool_ids.add(tool_id)
                if name == DISPATCH_TOOL:
                    calls.append((tool_id, tool_input.get("subagent_type")))
            elif kind == "user" and block["type"] == "tool_result":
                tool_id, is_error = (
                    block.get("tool_use_id"),
                    block.get("is_error", False),
                )
                if (
                    not isinstance(tool_id, str)
                    or tool_id in results
                    or not isinstance(is_error, bool)
                ):
                    raise _bad_stream("unrecognized_tool_result")
                results[tool_id] = (is_error, _result_texts(block.get("content")))

    # A result that says it was woken by a task needs a task that notified.
    wakes = sum(1 for entry in rounds if entry["wake"])
    if wakes > sum(len(statuses) for statuses in notified.values()):
        raise _bad_stream("wake_result_without_task_notification")
    usage, cost = _stage_totals(rounds)
    host_failed = any(entry["failed"] for entry in rounds)
    # Anthropic usage reports cache tokens outside input_tokens; the runner's
    # keys (and its weighted-token formula) expect them included.
    cache_read, cache_write = (
        usage["cache_read_input_tokens"],
        usage["cache_creation_input_tokens"],
    )
    normalized = {
        "input_tokens": usage["input_tokens"] + cache_read + cache_write,
        "cached_input_tokens": cache_read,
        "cache_write_input_tokens": cache_write,
        "output_tokens": usage["output_tokens"],
    }
    # The result event does not say which model served the subagent, so a model
    # is only reported when the whole stage used exactly one.
    models = {name for entry in rounds for name in entry["models"]}
    model = next(iter(models)) if len(models) == 1 else None

    if role is None:
        final = rounds[-1]["text"]
        return {
            "messages": [final] if isinstance(final, str) else [],
            "event_counts": event_counts,
            "usage": normalized,
            "cost_usd": cost,
            "host_failed": host_failed,
            "evidence": None,
        }
    messages: list[str] = []
    if not calls:
        reason = "no_agent_call"
    elif len(calls) > 1:
        reason = "multiple_agent_calls"
    elif calls[0][1] != role:
        reason = "unexpected_subagent_type"
    elif calls[0][0] not in results:
        reason = "agent_call_without_result"
    elif results[calls[0][0]][0]:
        reason = "agent_call_failed"
    elif any(status != TASK_COMPLETED for status in notified.get(calls[0][0], [])):
        reason = "agent_task_not_completed"
    elif calls[0][0] in started and calls[0][0] not in notified:
        reason = "agent_task_without_notification"
    elif not child_texts.get(calls[0][0]):
        # Never fall back to the tool result: it is a receipt, not an answer.
        reason = "agent_call_without_child_message"
    else:
        reason = "ok"
        messages = child_texts[calls[0][0]]
    ok = reason == "ok"
    return {
        "messages": messages,
        "event_counts": event_counts,
        "usage": normalized,
        "cost_usd": cost,
        "host_failed": host_failed,
        "evidence": DispatchEvidence(
            ok,
            DISPATCH_OK if ok else DISPATCH_FAILED,
            reason,
            model if ok else None,
            None,
        ),
    }


class ClaudeStageAdapter:
    """Run one dispatching stage through ``claude -p`` in a private root.

    Every stage gets a fresh private tree under ``request.scratch`` holding the
    config dir (``CLAUDE_CONFIG_DIR``), a throwaway home and a temp dir, and
    ``.claude/agents/`` staged into ``request.workdir`` from the committed
    dist.  All of it is deleted before ``run_stage`` returns or raises; the raw
    stream is only ever held in memory.

    Optional, all off by default: ``model`` adds ``--model`` for the parent
    session; ``allow_single_agent`` accepts ``StageRequest.role`` None (no
    dispatch evidence); ``observer`` is shown a ``StageObservation`` after the
    child exits and before the private tree is deleted; ``role_models`` maps a
    committed role to the model its staged copy is bound to for this adapter
    (an evaluation arm), leaving the committed file and the role text alone.
    """

    def __init__(
        self,
        *,
        claude_bin: str,
        max_budget_usd: Any,
        model: str | None = None,
        allow_single_agent: bool = False,
        observer: Callable[[StageObservation], None] | None = None,
        role_models: dict[str, str] | None = None,
    ) -> None:
        if model is not None and (
            not isinstance(model, str) or not _MODEL_RE.fullmatch(model)
        ):
            raise BenchmarkContractError("model must be a model alias or name")
        self.claude_bin = claude_bin
        self.max_budget_usd = _usd(max_budget_usd, "per-stage budget")
        self.model = model
        self.allow_single_agent = allow_single_agent
        self.observer = observer
        self.role_models = _role_models(role_models, _committed_agents())

    def with_role_models(self, role_models: dict[str, str]) -> "ClaudeStageAdapter":
        """The same adapter settings with different per-role model bindings."""
        return ClaudeStageAdapter(
            claude_bin=self.claude_bin,
            max_budget_usd=self.max_budget_usd,
            model=self.model,
            allow_single_agent=self.allow_single_agent,
            observer=self.observer,
            role_models=role_models,
        )

    def _command(self, request: StageRequest) -> list[str]:
        if request.sandbox not in _PERMISSION_MODES:
            raise StageSetupError("sandbox has no Claude permission mapping")
        # The prompt goes to stdin, so no variadic option can swallow it.
        command = [
            self.claude_bin,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--setting-sources",
            "project",
            "--max-budget-usd",
            format(self.max_budget_usd, "f"),
            "--permission-mode",
            _PERMISSION_MODES[request.sandbox],
            "--permission-prompts",
            "none",
            "--strict-mcp-config",
        ]
        if self.model is not None:
            command += ["--model", self.model]
        return command

    def _environment(self, token: str, private: Path) -> dict[str, str]:
        home, temp = str(private / "home"), str(private / "tmp")
        return {
            **{key: os.environ[key] for key in _PASSTHROUGH_ENV if key in os.environ},
            "HOME": home,
            "USERPROFILE": home,
            "TMPDIR": temp,
            "TEMP": temp,
            "TMP": temp,
            "CLAUDE_CONFIG_DIR": str(private / "config"),
            SUBSCRIPTION_TOKEN_ENV: token,
        }

    def run_stage(self, request: StageRequest) -> StageOutcome:
        token = _subscription_token()
        agents = _committed_agents()
        role = request.role
        if role is None:
            if not self.allow_single_agent:
                raise StageSetupError("stage role is not a committed Claude agent")
        elif not _ROLE_RE.fullmatch(role) or f"{role}.md" not in {
            entry.name for entry in agents
        }:
            raise StageSetupError("stage role is not a committed Claude agent")
        command = self._command(request)
        if token in request.prompt or any(token in part for part in command):
            raise StageSetupError("subscription token would be exposed to the stage")
        # Relative or `..` paths would hand the child relative isolation paths
        # and make deletion depend on the working directory.
        for path in (request.workdir, request.scratch):
            if not path.is_absolute() or ".." in path.parts:
                raise StageSetupError("stage directories must be absolute paths")
        _require_outside_user_config(request.workdir)
        _require_outside_user_config(request.scratch)
        staged = request.workdir / ".claude"
        if (
            not request.workdir.is_dir()
            or request.workdir.is_symlink()
            or staged.is_symlink()
            or staged.exists()
        ):
            raise StageSetupError("stage workdir is not a clean project directory")
        try:
            private = Path(
                tempfile.mkdtemp(prefix="claude-stage-", dir=request.scratch)
            )
        except OSError:
            raise StageSetupError("stage private root could not be created") from None
        try:
            try:
                for name in ("config", "home", "tmp"):
                    (private / name).mkdir(mode=0o700)
                (staged / "agents").mkdir(parents=True)
                for entry in agents:
                    target = staged / "agents" / entry.name
                    if entry.stem in self.role_models:
                        target.write_bytes(
                            _with_model(
                                entry.read_bytes().decode("utf-8"),
                                self.role_models[entry.stem],
                            ).encode("utf-8")
                        )
                    else:
                        shutil.copyfile(entry, target)
            except (OSError, UnicodeDecodeError):
                raise StageSetupError(
                    "stage directories could not be prepared"
                ) from None
            started = time.monotonic()
            # A host failure is raised after its handler has ended, so the new
            # exception has no cause or context: the original carries the
            # child's output.
            failure: Exception | None = None
            try:
                completed = subprocess.run(
                    command,
                    input=request.prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=self._environment(token, private),
                    cwd=str(request.workdir),
                    timeout=request.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as expired:
                failure = StageTimeout()
                # What arrived before the timeout is checked like a finished
                # stream: a leaked token first, then the usage state.
                partial = [
                    part.decode("utf-8", errors="replace")
                    if isinstance(part, bytes)
                    else part
                    for part in (expired.output, expired.stderr)
                    if isinstance(part, (bytes, str))
                ]
                if any(token in part for part in partial):
                    failure = StageEvidenceError("credential_in_stream")
                else:
                    try:
                        _require_no_usage_limit(
                            expired.output
                        )
                    except StageRateLimited as limited:
                        failure = StageRateLimited(limited.detail)
            except OSError:
                failure = StageSetupError("claude could not be started")
            if failure is not None:
                raise failure
            elapsed = time.monotonic() - started
            if token in completed.stdout or token in completed.stderr:
                raise StageEvidenceError("credential_in_stream")
            if self.observer is not None:
                self.observer(
                    StageObservation(
                        completed.returncode,
                        completed.stdout,
                        completed.stderr,
                        private,
                        request.workdir,
                    )
                )
            _require_no_usage_limit(completed.stdout)
            parsed = parse_stream(completed.stdout, role)
        finally:
            problem = _workdir_problem(request.workdir, token)
            _remove_private(private, staged)
            if problem == "workdir_cleanup_failed":
                raise StageCleanupError("claude stage cleanup failed")
            if problem is not None:
                raise StageEvidenceError(problem)
        # A run the host itself reports as failed must not read as a clean exit.
        returncode = completed.returncode or (1 if parsed["host_failed"] else 0)
        return StageOutcome(
            returncode,
            parsed["messages"],
            parsed["event_counts"],
            parsed["usage"],
            parsed["usage"],
            [],
            elapsed,
            parsed["evidence"],
            parsed["cost_usd"],
        )


class CostAdmission:
    """Cumulative stop: reserve the per-stage cap before each stage starts.

    A stage is admitted only while spent cost plus the reservation stays within
    the run cap (``RUN_COST_CAP_USD`` unless a lower ``run_cap_usd`` is given).
    A stage whose cost is unknown is charged its full
    reservation, and a stage that reports more than its reservation proves the
    per-stage cap is not enforced, which closes admission for the rest of the run.

    ``per_stage_cap_usd`` is the reservation, not necessarily the host's budget
    flag: the flag is only checked after a turn ends, so the reservation has to
    cover what a stage can really cost.
    """

    def __init__(self, *, per_stage_cap_usd: Any, run_cap_usd: Any = None) -> None:
        self.per_stage_cap_usd = _usd(per_stage_cap_usd, "per-stage cap")
        self.run_cap_usd = (
            RUN_COST_CAP_USD if run_cap_usd is None else _usd(run_cap_usd, "run cap")
        )
        self.spent_usd = Decimal("0")
        self._reserved = False
        self._closed: str | None = None

    def admit(self) -> None:
        if self._closed is not None:
            raise StageNotAdmitted(self._closed)
        if self._reserved:
            raise StageNotAdmitted("previous stage is not settled")
        if self.spent_usd + self.per_stage_cap_usd > self.run_cap_usd:
            raise StageNotAdmitted("cumulative cost cap reached")
        self._reserved = True

    def settle(self, cost_usd: float | None) -> None:
        if not self._reserved:
            raise BenchmarkContractError("no admitted stage to settle")
        self._reserved = False
        known = (
            not isinstance(cost_usd, bool)
            and isinstance(cost_usd, (int, float))
            and math.isfinite(cost_usd)
            and cost_usd >= 0
        )
        cost = Decimal(str(cost_usd)) if known else self.per_stage_cap_usd
        self.spent_usd += cost
        if cost > self.per_stage_cap_usd:
            self._closed = "per-stage cap was exceeded"

    def close(self, reason: str) -> None:
        """Refuse every later stage of the run (first reason wins)."""
        if self._closed is None:
            self._closed = reason

    @property
    def closed_reason(self) -> str | None:
        """Why no further stage will be admitted, or None while the run is open."""
        return self._closed


class AdmittedStageAdapter:
    """A ``StageAdapter`` that runs its inner adapter only after cost admission."""

    def __init__(self, inner: StageAdapter, admission: CostAdmission) -> None:
        self.inner = inner
        self.admission = admission

    def run_stage(self, request: StageRequest) -> StageOutcome:
        self.admission.admit()
        try:
            outcome = self.inner.run_stage(request)
        except StageSetupError:
            # Raised before the host starts: nothing was spent.
            self.admission.settle(0.0)
            raise
        except StageRateLimited as limited:
            # AC-CE-032: a usage limit ends the run; finished stages are kept.
            # So does a usage state that cannot be read.
            self.admission.settle(None)
            self.admission.close(
                USAGE_STATE_UNKNOWN
                if limited.detail == "rate_limit_status_unknown"
                else USAGE_LIMIT_REPORTED
            )
            raise
        except BaseException:
            self.admission.settle(None)
            raise
        self.admission.settle(outcome.cost_usd)
        return outcome


def open_claude_run(
    *,
    private_root: Path,
    claude_bin: str,
    per_stage_cap_usd: Any,
    reserve_usd: Any = None,
    run_cap_usd: Any = None,
    model: str | None = None,
    observer: Callable[[StageObservation], None] | None = None,
) -> AdmittedStageAdapter:
    """Stage adapter for one Claude run, after the frozen manifest check.

    ``per_stage_cap_usd`` is the ``--max-budget-usd`` flag.  ``reserve_usd`` is
    what admission sets aside per stage; it defaults to the flag value and may
    only be higher, because the flag is checked after a turn has been paid for.
    ``run_cap_usd`` lowers the run's stop point below ``RUN_COST_CAP_USD``.
    An arm with other role bindings shares the run through
    ``AdmittedStageAdapter(run.inner.with_role_models(...), run.admission)``.
    """
    require_frozen_manifest(private_root)
    inner = ClaudeStageAdapter(
        claude_bin=claude_bin,
        max_budget_usd=per_stage_cap_usd,
        model=model,
        observer=observer,
    )
    reserve = inner.max_budget_usd if reserve_usd is None else _usd(reserve_usd, "stage reservation")
    if reserve < inner.max_budget_usd:
        raise BenchmarkContractError("stage reservation is below the stage budget")
    return AdmittedStageAdapter(
        inner, CostAdmission(per_stage_cap_usd=reserve, run_cap_usd=run_cap_usd)
    )
