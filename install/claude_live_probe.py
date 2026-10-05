#!/usr/bin/env python3
"""Minimal live probe for the repo-external facts of the Claude stage adapter.

claude-eval-parity AC-CE-018 (TASKS Phase B2, last item): one small, approved
live run that checks what offline tests cannot - the token variable under a
fresh ``CLAUDE_CONFIG_DIR``, the ``-p --output-format stream-json --verbose``
combination, the real stream shapes, the isolation of the user's config and
what ``--max-budget-usd`` does when the budget is exceeded.

Every stage goes through ``ClaudeStageAdapter``; this module never passes the
token itself.  The only product is a JSON shape report: verdicts with reason
codes, event type sequences, key names, numbers and names.  It carries no model
output, no file content, no token and no absolute path; the raw stream is
reduced in memory and never written.

Exit status: 0 every selected stage passed; 1 a check failed; 2 the probe did
not start or withheld its report; 3 nothing failed but something could not be
determined (a skipped stage counts).  This module does not retry.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import stat
import sys
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import role_fitness_claude as claude
from role_fitness_fixtures import BenchmarkContractError
from role_fitness_stage import (
    StageEvidenceError,
    StageRequest,
    StageSetupError,
    StageTimeout,
)


SCHEMA = "claude-live-probe-v1"
STAGES = ("auth", "dispatch", "budget")
SAMPLES = claude.ROOT / "tests" / "fixtures" / "claude_stream"
# Synthetic sample each stage's real shape is compared with.
BASELINES = {
    "auth": "no-agent-call",
    "dispatch": "dispatch-two-rounds",
    "budget": "no-agent-call",
}

# Cheapest alias: the probe checks plumbing, not answer quality.  The dispatched
# scout still runs on the model its committed agent file names.
DEFAULT_MODEL = "haiku"
DEFAULT_AUTH_BUDGET_USD = "0.25"
DEFAULT_DISPATCH_BUDGET_USD = "1.00"
# Far below the cost of a single turn, so the budget is certainly exceeded.
DEFAULT_BUDGET_PROBE_USD = "0.001"
# What the budget stage may really cost: the CLI can only stop after a turn.
DEFAULT_BUDGET_RESERVE_USD = "0.25"
DEFAULT_TOTAL_BUDGET_USD = "2.00"
DEFAULT_TIMEOUT = 180
MAX_TIMEOUT = 180

DISPATCH_ROLE = "scout"
DISPATCH_TASK = "live_probe_dispatch"
_ONE_WORD = "Reply with the single word READY. Do not call any tools."
BUDGET_INPUT_FILE = "probe-input.txt"
_BUDGET_PROMPT = (
    f"Use the Read tool to read the file {BUDGET_INPUT_FILE} in the current "
    "directory, then reply with the single word DONE."
)

# Items of the user's config that no other running session rewrites.
STABLE_ITEMS = (
    "settings.json",
    "AGENTS.md",
    "agents",
    "hooks",
    "skills",
    "rules",
    "commands",
    "memories",
)
USER_SCAN_MAX_ENTRIES = 200_000
MAX_SEQUENCE = 400
MAX_NAMES = 300
MAX_KEYS = 60
MAX_TOOL_USES = 50

PASS, FAIL, UNDETERMINED, OBSERVED, SKIPPED = (
    "pass",
    "fail",
    "undetermined",
    "observed",
    "skipped",
)

# Names are short conservative identifiers; anything else becomes a placeholder.
_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:\[\]-]{0,63}")
_ALNUM_RUN_RE = re.compile(r"[A-Za-z0-9]+")
_CREDENTIAL_PREFIXES = (
    "sk-",
    "sk_",
    "pk_",
    "rk_",
    "ghp_",
    "gho_",
    "ghu_",
    "ghs_",
    "ghr_",
    "github_pat_",
    "glpat-",
    "xox",
    "akia",
    "eyj",
    "aiza",
    "ya29.",
    "bearer",
)
_AMOUNT_RE = re.compile(r"[0-9]{1,4}(\.[0-9]{1,6})?", re.ASCII)
_KNOWN_EXTENSIONS = (
    ".jsonl",
    ".json",
    ".md",
    ".txt",
    ".log",
    ".lock",
    ".tmp",
    ".sh",
    ".db",
    ".toml",
    ".yaml",
    ".yml",
)
_KNOWN_AREAS = (
    "projects",
    "sessions",
    "todos",
    "shell-snapshots",
    "statsig",
    "plugins",
    "cache",
    "logs",
    "backups",
    "file-history",
    "debug",
    "session-env",
    "telemetry",
    "ide",
    "tasks",
)
# A run of this many consecutive token characters in the report withholds it.
TOKEN_FRAGMENT_LENGTH = 8
MAX_INTEGER = 2**53
MAX_PATHS = 200
MAX_REPORT_BYTES = 512 * 1024
_CODE_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_INIT_SCALARS = (
    "model",
    "permissionMode",
    "apiKeySource",
    "claude_code_version",
    "output_style",
)
# Fixed vocabulary looked for in stderr; stderr itself is never reported.
_STDERR_KEYWORDS = (
    "budget",
    "permission",
    "unknown option",
    "invalid",
    "unauthorized",
    "authentication",
    "login",
    "credit",
    "rate limit",
    "usage limit",
    "429",
    "not supported",
    "deprecated",
)


# Names the CLI ships itself, as loaded by a live run with a fresh config dir
# and `--setting-sources project` (CLI 2.1.289, observed 2026-10-05).  A user
# skill or command of the same name cannot be told apart from the built-in, so
# these names are never evidence of the user layer.
BUILTIN_SKILLS = frozenset(
    {
        "batch",
        "claude-api",
        "code-review",
        "dataviz",
        "debug",
        "deep-research",
        "design",
        "design-sync",
        "doctor",
        "fewer-permission-prompts",
        "loop",
        "plugin-authoring",
        "run",
        "run-skill-generator",
        "schedule",
        "simplify",
        "update-config",
        "verify",
        "workflow-authoring",
    }
)
BUILTIN_SLASH_COMMANDS = BUILTIN_SKILLS | frozenset(
    {
        "__remote-workflow",
        "advisor",
        "agents",
        "auto-mode-setup",
        "autocompact",
        "clear",
        "color",
        "compact",
        "config",
        "context",
        "design-consent",
        "design-revoke",
        "effort",
        "fast",
        "focus",
        "goal",
        "heapdump",
        "import",
        "init",
        "insights",
        "list-agents",
        "mcp",
        "model",
        "output-style",
        "recap",
        "reload-plugins",
        "reload-skills",
        "rename",
        "security-review",
        "skill-doctor",
        "team-onboarding",
        "ultrareview",
        "usage",
        "workflow-launch-exec",
    }
)
BUILTIN_AGENTS = frozenset({"Plan", "claude", "general-purpose", "statusline-setup"})
# Plugins bundled with the CLI carry this prefix (same observation).
BUILTIN_PLUGIN_PREFIX = "cc-plugin-"
# Slack around the child's lifetime when a change is dated by its mtime; file
# systems round timestamps, so a change this close counts as inside.
CHILD_WINDOW_SLACK_NS = 2_000_000_000


class _ScanLimit(Exception):
    """The user's config has more entries than the bounded scan allows."""


def user_config_dir() -> Path:
    """The user's own Claude config, from the OS account record."""
    return claude._account_home() / ".claude"


def _make_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="claude-live-probe-"))


def _name(value: Any) -> str:
    """A name safe to report: a short identifier, never a path, sentence or secret."""
    if (
        isinstance(value, str)
        and _NAME_RE.fullmatch(value)
        and not value.lower().startswith(_CREDENTIAL_PREFIXES)
        and not any(_looks_random(run) for run in _ALNUM_RUN_RE.findall(value))
    ):
        return value
    return "<other>"


def _looks_random(run: str) -> bool:
    """Whether one alphanumeric run reads like key material rather than a word."""
    if len(run) >= 32:
        return True
    pairs = list(zip(run, run[1:]))
    mixes = sum(1 for a, b in pairs if a.isdigit() != b.isdigit())
    flips = sum(
        1 for a, b in pairs if a.isalpha() and b.isalpha() and a.isupper() != b.isupper()
    )
    return (len(run) >= 10 and mixes >= 3) or (len(run) >= 16 and flips >= 0.4 * len(run))


def _names(values: Any) -> list[str]:
    """Names of a list of strings or of objects carrying a ``name``."""
    found: set[str] = set()
    for item in values if isinstance(values, list) else []:
        found.add(_name(item.get("name") if isinstance(item, dict) else item))
    return sorted(found)[:MAX_NAMES]


def _code(value: Any) -> str:
    return value if isinstance(value, str) and _CODE_RE.fullmatch(value) else "other"


def _munge(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", text)


def _extension(file_name: str) -> str:
    """A file's extension class; the name itself is never reported."""
    extension = os.path.splitext(file_name)[1].lower()
    if not extension:
        return "<none>"
    return extension if extension in _KNOWN_EXTENSIONS else "<other>"


def _tally(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    for kind, label in (
        (int, "int"),
        (float, "float"),
        (str, "str"),
        (list, "list"),
        (dict, "dict"),
    ):
        if isinstance(value, kind):
            return label
    return "other"


def _number(value: Any) -> int | float | None:
    """A finite number of ordinary size, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, int):
        return value if abs(value) <= MAX_INTEGER else None
    return value if math.isfinite(value) else None


def _valid_cost(value: Any) -> bool:
    return _number(value) is not None and value >= 0


def _numbers(value: Any, depth: int = 1) -> dict[str, Any]:
    """Numeric leaves of a mapping, at most one level of nesting.

    Anything deeper, beyond ``MAX_KEYS`` or not an ordinary finite number is
    dropped and counted under ``<dropped>``.
    """
    found: dict[str, Any] = {}
    if not isinstance(value, dict):
        return found
    dropped = max(0, len(value) - MAX_KEYS)
    for key, item in list(value.items())[:MAX_KEYS]:
        if isinstance(item, dict):
            nested = _numbers(item, depth - 1) if depth > 0 else None
            if nested is None:
                dropped += 1
            elif nested:
                found[_name(key)] = nested
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            if _number(item) is None:
                dropped += 1
            else:
                found[_name(key)] = item
    if dropped:
        found["<dropped>"] = dropped
    return found


def _event_kind(event: dict[str, Any]) -> str:
    kind = _name(event.get("type")) if "type" in event else "<untyped>"
    if isinstance(event.get("subtype"), str):
        kind += "/" + _name(event["subtype"])
    return kind


def stream_shape(stdout: str) -> dict[str, Any]:
    """Reduce a raw stream to names, key sets, types and numbers.

    No string value of the stream survives unless it is a bounded name (event
    types, key names, tool names, model names, ``subagent_type``).
    """
    events: list[dict[str, Any]] = []
    unparsed = 0
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            event = None
        if isinstance(event, dict):
            events.append(event)
        else:
            unparsed += 1

    keys: dict[str, dict[str, set[str]]] = {}
    paths_dropped = 0

    def note(path: str, mapping: Any) -> None:
        nonlocal paths_dropped
        if not isinstance(mapping, dict):
            return
        if path not in keys and len(keys) >= MAX_PATHS:
            paths_dropped += 1
            return
        slot = keys.setdefault(path, {})
        for key, value in list(mapping.items())[:MAX_KEYS]:
            slot.setdefault(_name(key), set()).add(_json_type(value))

    sequence: list[str] = []
    tool_uses: list[dict[str, Any]] = []
    rate_limits: list[dict[str, Any]] = []
    task_events: list[dict[str, Any]] = []
    rounds: list[dict[str, Any]] = []
    # Where the first parent-level Agent call, its tool result, the child's
    # own messages and the task notification sit in the stream (positions and
    # text lengths only): enough to tell an answer from a launch receipt.
    trace: dict[str, Any] = {}
    dispatch_id: str | None = None
    models: set[str] = set()
    init: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    for index, event in enumerate(events):
        kind = _event_kind(event)
        sequence.append(kind)
        note(kind, event)
        if event.get("type") == "system" and kind.startswith("system/task_"):
            if len(task_events) < MAX_TOOL_USES:
                entry = {"kind": kind, "index": index}
                for key in ("status", "task_type"):
                    if isinstance(event.get(key), str):
                        entry[key] = _name(event[key])
                for key in ("is_backgrounded", "spawn_depth"):
                    if isinstance(event.get(key), bool) or _number(event.get(key)) is not None:
                        entry[key] = event[key]
                patch = event.get("patch")
                if isinstance(patch, dict) and isinstance(patch.get("status"), str):
                    entry["patch_status"] = _name(patch["status"])
                task_events.append(entry)
            note(f"{kind}.patch", event.get("patch"))
            note(f"{kind}.usage", event.get("usage"))
            if (
                kind == "system/task_notification"
                and dispatch_id is not None
                and event.get("tool_use_id") == dispatch_id
            ):
                trace.setdefault("task_notification_index", index)
        parent_id = event.get("parent_tool_use_id")
        if (
            dispatch_id is not None
            and parent_id == dispatch_id
            and event.get("type") == "assistant"
        ):
            trace["child_assistant_events"] = trace.get("child_assistant_events", 0) + 1
            trace.setdefault("first_child_assistant_index", index)
            trace["last_child_assistant_index"] = index
        message = event.get("message")
        if isinstance(message, dict):
            note(f"{kind}.message", message)
            note(f"{kind}.message.usage", message.get("usage"))
            if isinstance(message.get("model"), str):
                models.add(_name(message["model"]))
            content = message.get("content")
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                block_type = _name(block.get("type"))
                note(f"{kind}.message.content[{block_type}]", block)
                if dispatch_id is not None and parent_id == dispatch_id:
                    if block_type == "text" and isinstance(block.get("text"), str):
                        trace["last_child_text_chars"] = len(block["text"])
                if (
                    block_type == "tool_result"
                    and dispatch_id is not None
                    and parent_id is None
                    and block.get("tool_use_id") == dispatch_id
                    and "tool_result_index" not in trace
                ):
                    trace["tool_result_index"] = index
                    body = block.get("content")
                    if isinstance(body, str):
                        trace["tool_result_text_chars"] = len(body)
                    elif isinstance(body, list):
                        trace["tool_result_text_chars"] = sum(
                            len(part["text"])
                            for part in body
                            if isinstance(part, dict) and isinstance(part.get("text"), str)
                        )
                    if isinstance(block.get("is_error"), bool):
                        trace["tool_result_is_error"] = block["is_error"]
                if block_type != "tool_use":
                    continue
                if (
                    dispatch_id is None
                    and parent_id is None
                    and block.get("name") == claude.DISPATCH_TOOL
                    and isinstance(block.get("id"), str)
                ):
                    dispatch_id = block["id"]
                    trace["tool_use_index"] = index
                tool, tool_input = _name(block.get("name")), block.get("input")
                note(f"tool_use[{tool}].input", tool_input)
                if len(tool_uses) < MAX_TOOL_USES:
                    entry: dict[str, Any] = {
                        "name": tool,
                        "level": "parent"
                        if event.get("parent_tool_use_id") is None
                        else "child",
                        "input_keys": sorted(
                            _name(key)
                            for key in (
                                list(tool_input)[:MAX_KEYS]
                                if isinstance(tool_input, dict)
                                else []
                            )
                        ),
                    }
                    if isinstance(tool_input, dict) and "subagent_type" in tool_input:
                        entry["subagent_type"] = _name(tool_input["subagent_type"])
                    tool_uses.append(entry)
        if (
            event.get("type") == "system"
            and event.get("subtype") == "init"
            and init is None
        ):
            init = {
                "scalars": {
                    key: _name(event[key])
                    for key in _INIT_SCALARS
                    if isinstance(event.get(key), str)
                },
                "lists": {
                    _name(key): _names(value)
                    for key, value in list(event.items())[:MAX_KEYS]
                    if isinstance(value, list)
                },
            }
        if event.get("type") == "rate_limit_event":
            info = event.get("rate_limit_info")
            note("rate_limit_event.rate_limit_info", info)
            if isinstance(info, dict) and len(rate_limits) < MAX_TOOL_USES:
                # Only enum-like values (lower-case codes) and booleans.
                rate_limits.append(
                    {
                        _name(key): value
                        for key, value in list(info.items())[:MAX_KEYS]
                        if isinstance(value, bool)
                        or (isinstance(value, str) and _CODE_RE.fullmatch(value))
                    }
                )
        if event.get("type") == "result":
            note("result.usage", event.get("usage"))
            usage_by_model = event.get("modelUsage")
            for entry in (
                usage_by_model.values() if isinstance(usage_by_model, dict) else []
            ):
                note("result.modelUsage[]", entry)
            denials = event.get("permission_denials")
            numeric = ("num_turns", "duration_ms", "duration_api_ms", "total_cost_usd")
            result = {
                "subtype": _name(event.get("subtype")),
                "is_error": event.get("is_error")
                if isinstance(event.get("is_error"), bool)
                else None,
                "is_last_event": event is events[-1],
                "index": index,
                "text_chars": len(event["result"])
                if isinstance(event.get("result"), str)
                else None,
                "origin": {
                    key: _name(value)
                    for key, value in (
                        event["origin"].items()
                        if isinstance(event.get("origin"), dict)
                        else []
                    )
                    if key in ("kind", "type", "source") and isinstance(value, str)
                },
                "numbers": {
                    key: event[key]
                    for key in numeric
                    if _number(event.get(key)) is not None
                },
                "numbers_dropped": [
                    key
                    for key in numeric
                    if key in event and _number(event[key]) is None
                ],
                "usage": _numbers(event.get("usage")),
                "model_usage": {
                    _name(model): _numbers(entry)
                    for model, entry in (
                        list(usage_by_model.items())[:MAX_KEYS]
                        if isinstance(usage_by_model, dict)
                        else []
                    )
                },
                "permission_denials": {
                    "count": len(denials) if isinstance(denials, list) else None,
                    "tools": sorted(
                        {
                            _name(item.get("tool_name"))
                            for item in (denials if isinstance(denials, list) else [])
                            if isinstance(item, dict)
                        }
                    )[:MAX_NAMES],
                },
            }
            note("result.origin", event.get("origin"))
            rounds.append(result)
    return {
        "event_count": len(events),
        "unparsed_lines": unparsed,
        "kinds": sorted(set(sequence))[:MAX_NAMES],
        "kinds_truncated": len(set(sequence)) > MAX_NAMES,
        "paths_dropped": paths_dropped,
        "sequence": sequence[:MAX_SEQUENCE],
        "sequence_truncated": len(sequence) > MAX_SEQUENCE,
        "keys": {
            path: {key: sorted(types) for key, types in sorted(slot.items())}
            for path, slot in sorted(keys.items())
        },
        "tool_uses": tool_uses,
        "rate_limits": rate_limits,
        "task_events": task_events,
        "dispatch_trace": trace,
        "rounds": rounds[:MAX_TOOL_USES],
        "round_count": len(rounds),
        "models": sorted(models),
        "init": init,
        "result": result,
    }


def shape_diff(live: dict[str, Any], synthetic: dict[str, Any]) -> dict[str, Any]:
    """Where the live shape and a synthetic sample disagree (names only)."""
    live_keys, synthetic_keys = live["keys"], synthetic["keys"]
    differing: dict[str, Any] = {}
    for path in sorted(set(live_keys) & set(synthetic_keys)):
        here, there = live_keys[path], synthetic_keys[path]
        entry = {
            "missing_in_live": sorted(set(there) - set(here)),
            "extra_in_live": sorted(set(here) - set(there)),
            "type_changed": {
                key: {"live": here[key], "synthetic": there[key]}
                for key in sorted(set(here) & set(there))
                if here[key] != there[key]
            },
        }
        if any(entry.values()):
            differing[path] = entry
    return {
        "kinds_only_live": sorted(set(live["kinds"]) - set(synthetic["kinds"])),
        "kinds_only_synthetic": sorted(set(synthetic["kinds"]) - set(live["kinds"])),
        "paths_only_live": sorted(set(live_keys) - set(synthetic_keys)),
        "paths_only_synthetic": sorted(set(synthetic_keys) - set(live_keys)),
        "keys": differing,
    }


def _baseline_diff(stage: str, shape: dict[str, Any]) -> dict[str, Any]:
    sample = BASELINES[stage]
    try:
        text = (SAMPLES / f"{sample}.jsonl").read_text(encoding="utf-8")
    except OSError:
        return {"sample": sample, "status": UNDETERMINED, "reason": "sample_unreadable"}
    return {"sample": sample, **shape_diff(shape, stream_shape(text))}


def snapshot_user_config(config: Path) -> dict[str, tuple[Any, ...]]:
    """Names, types and mtimes of the stable items; no file is opened.

    A symlink is recorded with its target and the target's mtime, and a linked
    directory is walked.  Raises ``OSError`` or ``_ScanLimit``.
    """
    entries: dict[str, tuple[Any, ...]] = {}
    walked: set[str] = set()
    pending = [(config / item, (item,)) for item in reversed(STABLE_ITEMS)]
    while pending:
        path, parts = pending.pop()
        try:
            status = os.lstat(path)
        except FileNotFoundError:
            continue
        if len(entries) >= USER_SCAN_MAX_ENTRIES:
            raise _ScanLimit
        record: list[Any] = [stat.S_IFMT(status.st_mode), status.st_mtime_ns]
        is_dir = stat.S_ISDIR(status.st_mode)
        if stat.S_ISLNK(status.st_mode):
            record.append(os.readlink(path))
            try:
                target = os.stat(path)
            except OSError:
                record.append(None)
            else:
                record.append(target.st_mtime_ns)
                is_dir = stat.S_ISDIR(target.st_mode)
        entries["/".join(parts)] = tuple(record)
        if is_dir:
            real = os.path.realpath(path)
            if real in walked:
                continue
            walked.add(real)
            for name in sorted(os.listdir(path), reverse=True):
                pending.append((path / name, parts + (name,)))
    return entries


def _project_entries(config: Path, marker: str) -> int:
    """How many entries of the user's ``projects/`` belong to this probe run."""
    try:
        names = os.listdir(config / "projects")
    except FileNotFoundError:
        return 0
    return sum(1 for name in names if marker in _munge(name))


def _changed_in_window(
    name: str,
    before: dict[str, tuple[Any, ...]],
    after: dict[str, tuple[Any, ...]],
    window: tuple[int, int],
) -> bool:
    """Whether a changed entry's new mtime falls in the child's lifetime.

    An entry that is gone, or whose change left no new mtime to date it by,
    counts as inside: only a change positively dated outside is set apart.
    """
    if name not in after:
        return True
    old = before.get(name, ())
    # Positions 1 and 3 hold the entry's own mtime and a link target's mtime.
    stamps = [
        after[name][index]
        for index in (1, 3)
        if index < len(after[name])
        and (index >= len(old) or old[index] != after[name][index])
    ]
    if not stamps or any(not isinstance(stamp, int) for stamp in stamps):
        return True
    low, high = window[0] - CHILD_WINDOW_SLACK_NS, window[1] + CHILD_WINDOW_SLACK_NS
    return any(low <= stamp <= high for stamp in stamps)


def compare_user_config(
    before: dict[str, tuple[Any, ...]],
    after: dict[str, tuple[Any, ...]],
    window: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Counts of changed entries per stable item and extension; no file names.

    ``window`` is the child's lifetime in epoch nanoseconds.  A change dated
    inside it (or that cannot be dated) fails the check, because a write by the
    child and a concurrent write by another session look the same.  Only when
    every change is dated outside the window is the result ``undetermined``:
    mtimes can be set by the writer, so this is never a pass.
    """
    changes = {
        "added": set(after) - set(before),
        "removed": set(before) - set(after),
        "modified": {
            name for name in set(before) & set(after) if before[name] != after[name]
        },
    }
    by_item: dict[str, dict[str, int]] = {}
    by_extension: dict[str, int] = {}
    inside = 0
    for kind, names in changes.items():
        for name in names:
            parts = name.split("/")
            # The first component is always one of the fixed STABLE_ITEMS.
            _tally(by_item.setdefault(parts[0], {}), kind)
            _tally(by_extension, _extension(parts[-1]))
            if window is None or _changed_in_window(name, before, after, window):
                inside += 1
    total = sum(len(names) for names in changes.values())
    if not total:
        status, reason = PASS, "stable_items_unchanged"
    elif inside:
        status, reason = FAIL, "user_config_changed"
    else:
        status, reason = UNDETERMINED, "user_config_changed_outside_child_lifetime"
    return {
        "status": status,
        "reason": reason,
        "entries_compared": len(before),
        **{f"{kind}_count": len(names) for kind, names in changes.items()},
        "changed_by_item": {item: by_item[item] for item in sorted(by_item)},
        "changed_by_extension": dict(sorted(by_extension.items())),
        "timing_basis": "mtime_vs_child_lifetime" if window else "not_available",
        "changed_during_child_or_undated": inside,
        "changed_outside_child": total - inside,
    }


def user_layer_names(snapshot: dict[str, tuple[Any, ...]]) -> dict[str, set[str]]:
    """Agent, skill and command names of the user layer, from file names only."""
    names: dict[str, set[str]] = {"agents": set(), "skills": set(), "commands": set()}
    for entry in snapshot:
        parts = entry.split("/")
        if len(parts) < 2 or parts[0] not in names:
            continue
        leaf = parts[-1]
        if parts[0] == "skills":
            names["skills"].add(parts[1][:-3] if parts[1].endswith(".md") else parts[1])
        elif leaf.endswith(".md"):
            names[parts[0]].add(leaf[:-3])
    return names


def private_listing(private: Path) -> dict[str, Any]:
    """What the child wrote into its private config and home, as counts.

    Files are counted per area (a fixed vocabulary of directory names) and per
    extension class; no file name is reported.
    """
    counts = {"config": 0, "home": 0}
    by_area: dict[str, int] = {}
    by_extension: dict[str, int] = {}
    transcripts = 0
    for top in counts:
        for directory, _, files in os.walk(private / top):
            for file_name in files:
                parts = Path(directory, file_name).relative_to(private).parts
                counts[top] += 1
                if len(parts) == 2:
                    area = "<root>"
                else:
                    area = parts[1] if parts[1] in _KNOWN_AREAS else "<other>"
                _tally(by_area, f"{top}/{area}")
                _tally(by_extension, _extension(file_name))
                if top == "config" and (
                    file_name.endswith(".jsonl") or area in {"projects", "sessions"}
                ):
                    transcripts += 1
    return {
        "status": PASS if transcripts else UNDETERMINED,
        "reason": "transcript_in_private_config"
        if transcripts
        else "no_transcript_seen",
        "config_file_count": counts["config"],
        "home_file_count": counts["home"],
        "transcript_like_count": transcripts,
        "files_by_area": dict(sorted(by_area.items())),
        "files_by_extension": dict(sorted(by_extension.items())),
    }


def judge_setting_sources(
    shape: dict[str, Any] | None, staged: set[str], user: dict[str, set[str]] | None
) -> dict[str, Any]:
    """Whether only the staged project layer was loaded, per category.

    A category that the stream does not list, or that the user layer cannot
    distinguish, is ``undetermined``; it is never counted as a pass.
    """
    if shape is None or shape["init"] is None:
        return {
            "status": UNDETERMINED,
            "reason": "no_observation" if shape is None else "init_event_missing",
        }
    lists = shape["init"]["lists"]
    categories: dict[str, dict[str, Any]] = {}

    def verdict(status: str, reason: str, **extra: Any) -> dict[str, Any]:
        return {"status": status, "reason": reason, **extra}

    def user_layer(
        category: str,
        user_names: set[str] | None,
        own: set[str],
        builtin: frozenset[str],
    ) -> None:
        """Judge one name list against the staged, built-in and user layers.

        A loaded name that only the user layer explains fails.  A name shared
        by the user layer and the CLI's own set proves nothing (``ambiguous``).
        A name nobody explains is new: ``undetermined``, never a pass.
        """
        if category not in lists:
            categories[category] = verdict(UNDETERMINED, "init_key_missing")
            return
        loaded = set(lists[category])
        extra: dict[str, Any] = {"loaded": sorted(loaded)}
        missing = sorted(own - loaded)
        if own:
            extra["staged_missing"] = missing
        if user_names is None:
            categories[category] = verdict(
                FAIL if missing else UNDETERMINED,
                "staged_not_loaded" if missing else "user_layer_unknown",
                **extra,
            )
            return
        distinguishing = user_names - own - builtin
        from_user = sorted(_name(name) for name in loaded & distinguishing)
        unknown = sorted(loaded - own - builtin - user_names)
        extra["user_layer_loaded"] = from_user
        extra["ambiguous"] = sorted(
            _name(name) for name in loaded & user_names & builtin
        )
        extra["unattributed"] = unknown
        extra["distinguishing_user_entries"] = len(distinguishing)
        if missing:
            categories[category] = verdict(FAIL, "staged_not_loaded", **extra)
        elif from_user:
            categories[category] = verdict(FAIL, "user_layer_loaded", **extra)
        elif unknown:
            categories[category] = verdict(UNDETERMINED, "unknown_names_loaded", **extra)
        elif not distinguishing:
            categories[category] = verdict(
                UNDETERMINED, "no_distinguishing_user_entries", **extra
            )
        else:
            categories[category] = verdict(PASS, "no_user_layer_entry_loaded", **extra)

    user_layer(
        "agents", None if user is None else user["agents"], staged, BUILTIN_AGENTS
    )
    user_layer(
        "skills", None if user is None else user["skills"], set(), BUILTIN_SKILLS
    )
    user_layer(
        "slash_commands",
        None if user is None else user["commands"] | user["skills"],
        set(),
        BUILTIN_SLASH_COMMANDS,
    )
    if "mcp_servers" not in lists:
        categories["mcp_servers"] = verdict(UNDETERMINED, "init_key_missing")
    elif lists["mcp_servers"]:
        categories["mcp_servers"] = verdict(
            FAIL, "mcp_servers_present", loaded=lists["mcp_servers"]
        )
    else:
        categories["mcp_servers"] = verdict(PASS, "none_loaded")
    if "plugins" not in lists:
        categories["plugins"] = verdict(UNDETERMINED, "init_key_missing")
    else:
        foreign = [
            name
            for name in lists["plugins"]
            if not name.startswith(BUILTIN_PLUGIN_PREFIX)
        ]
        if foreign:
            categories["plugins"] = verdict(
                FAIL, "plugins_present", loaded=lists["plugins"], not_builtin=foreign
            )
        elif lists["plugins"]:
            categories["plugins"] = verdict(
                PASS, "only_builtin_plugins", loaded=lists["plugins"]
            )
        else:
            categories["plugins"] = verdict(PASS, "none_loaded")
    hook_events = sorted(kind for kind in shape["kinds"] if "/hook" in kind)
    if hook_events or lists.get("hooks"):
        categories["hooks"] = verdict(
            FAIL, "hooks_present", events=hook_events, loaded=lists.get("hooks", [])
        )
    elif "hooks" in lists:
        categories["hooks"] = verdict(PASS, "none_loaded")
    else:
        categories["hooks"] = verdict(UNDETERMINED, "hooks_not_listed")
    status = _worst(entry["status"] for entry in categories.values())
    return {
        "status": status,
        "reason": "see_categories",
        "basis": "init_event_names_vs_user_file_names",
        "builtin_names_observed": "cli_2.1.289_2026-10-05",
        "not_observable": ["memory"],
        "categories": categories,
    }


def _worst(statuses: Any) -> str:
    seen = set(statuses)
    if FAIL in seen:
        return FAIL
    if seen & {UNDETERMINED, SKIPPED}:
        return UNDETERMINED
    return PASS


def _check(status: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, **extra}


def _cli_result(observed: dict[str, Any], failure: str | None) -> dict[str, Any]:
    shape = observed.get("shape")
    if shape is None:
        return _check(FAIL, failure or "no_observation")
    result = _decisive_round(shape)
    if result is None:
        return _check(FAIL, "no_result_event")
    if result["subtype"] != "success" or result["is_error"] is not False:
        return _check(FAIL, "result_" + _code(result["subtype"]))
    if not shape["result"]["is_last_event"]:
        return _check(FAIL, "events_after_last_result")
    if shape["round_count"] > claude.MAX_STAGE_ROUNDS:
        return _check(FAIL, "too_many_rounds")
    if observed["returncode"] != 0:
        return _check(FAIL, "exit_nonzero")
    return _check(PASS, "result_success")


def _decisive_round(shape: dict[str, Any]) -> dict[str, Any] | None:
    """The first round that did not succeed, else the last round.

    A stage is as good as its worst round: one failed round fails the stage.
    """
    for entry in shape["rounds"]:
        if entry["subtype"] != "success" or entry["is_error"] is not False:
            return entry
    return shape["result"]


def _stage_cost(shape: dict[str, Any]) -> tuple[Any, bool]:
    """Stage cost over all rounds and whether any round's cost was abnormal.

    ``total_cost_usd`` is read as cumulative over the session (see the
    adapter's ``_stage_totals``); the largest value is the stage cost.
    """
    costs = [entry["numbers"].get("total_cost_usd") for entry in shape["rounds"]]
    anomalous = any(
        "total_cost_usd" in entry["numbers_dropped"] for entry in shape["rounds"]
    ) or any(cost is not None and not _valid_cost(cost) for cost in costs)
    valid = [cost for cost in costs if _valid_cost(cost)]
    return (None if anomalous or not valid else max(valid)), anomalous


def _budget_observation(
    observed: dict[str, Any], failure: str | None, cap: Decimal
) -> dict[str, Any]:
    """What the CLI did when the budget was exceeded; a host failure is expected."""
    shape = observed.get("shape")
    if shape is None:
        return _check(UNDETERMINED, failure or "no_observation")
    result = _decisive_round(shape)
    extra: dict[str, Any] = {"exit_code": observed["returncode"]}
    if result is None:
        mentioned = "budget" in observed["stderr"]["keywords"]
        if observed["returncode"] != 0 and mentioned:
            return _check(
                OBSERVED, "exit_nonzero_budget_stderr", enforced=True, **extra
            )
        return _check(UNDETERMINED, "no_result_event", **extra)
    cost = result["numbers"].get("total_cost_usd")
    cost = cost if _valid_cost(cost) else None
    extra.update(
        result_subtype=result["subtype"],
        result_is_error=result["is_error"],
        cost_usd=cost,
        cost_over_cap=None if cost is None else Decimal(str(cost)) > cap,
    )
    if result["subtype"] == "success" and result["is_error"] is False:
        return _check(OBSERVED, "budget_not_enforced", enforced=False, **extra)
    return _check(
        OBSERVED, "result_" + _code(result["subtype"]), enforced=True, **extra
    )


def _stderr_summary(stderr: str, argv: list[str]) -> dict[str, Any]:
    lowered = stderr.lower()
    return {
        "bytes": len(stderr.encode("utf-8", "replace")),
        "lines": len(stderr.splitlines()),
        "mentions_flags": sorted(
            {part for part in argv if part.startswith("--") and part in stderr}
        ),
        "keywords": [word for word in _STDERR_KEYWORDS if word in lowered],
    }


def _failure_code(error: BaseException) -> str:
    if isinstance(error, StageTimeout):
        return "timeout"
    if isinstance(error, claude.StageCleanupError):
        return "cleanup_failed"
    if isinstance(error, StageEvidenceError):
        return "evidence_" + _code(error.detail)
    if isinstance(error, StageSetupError):
        # Adapter setup messages are fixed strings; reduce them to a code.
        return "setup_" + re.sub(r"[^a-z0-9]+", "_", str(error).lower()).strip("_")[:60]
    return "unexpected_" + re.sub(r"[^A-Za-z0-9]", "", type(error).__name__)[:40]


def run_stage(
    stage: str, *, options: argparse.Namespace, budget: Decimal, root: Path
) -> dict[str, Any]:
    """Run one probe stage once and reduce everything it showed to a report entry."""
    marker = _munge(root.name)
    stage_root = root / stage
    workdir, scratch = stage_root / "work", stage_root / "scratch"
    workdir.mkdir(parents=True)
    scratch.mkdir()
    role = DISPATCH_ROLE if stage == "dispatch" else None
    if stage == "dispatch":
        prompt = claude.claude_dispatch_prompt(
            role=DISPATCH_ROLE, task_name=DISPATCH_TASK, message=_ONE_WORD
        )
    elif stage == "budget":
        (workdir / BUDGET_INPUT_FILE).write_text("probe\n", encoding="utf-8")
        prompt = _BUDGET_PROMPT
    else:
        prompt = _ONE_WORD
    request = StageRequest(
        prompt=prompt,
        role=role,
        sandbox="read-only",
        workdir=workdir,
        scratch=scratch,
        timeout=options.timeout,
        task_name=DISPATCH_TASK if role else None,
    )
    observed: dict[str, Any] = {}

    def observe(observation: claude.StageObservation) -> None:
        # Called right after the child exits: the end of its lifetime.
        observed["ended_ns"] = time.time_ns()
        observed["returncode"] = observation.returncode
        observed["stderr"] = _stderr_summary(observation.stderr, argv)
        observed["private"] = private_listing(observation.private)
        observed["shape"] = stream_shape(observation.stdout)

    adapter = claude.ClaudeStageAdapter(
        claude_bin=options.claude_bin,
        max_budget_usd=budget,
        model=options.model,
        allow_single_agent=True,
        observer=observe,
    )
    # Everything after the binary is a fixed flag or a validated value.
    argv = adapter._command(request)[1:]

    config = user_config_dir()
    before: dict[str, tuple[Any, ...]] | None
    try:
        before, scan_problem = snapshot_user_config(config), None
    except _ScanLimit:
        before, scan_problem = None, "user_config_scan_limit"
    except OSError:
        before, scan_problem = None, "user_config_unreadable"

    outcome, failure = None, None
    started_ns = time.time_ns()
    try:
        outcome = adapter.run_stage(request)
    except Exception as error:  # reduced to a code; the message is never reported
        failure = _failure_code(error)
    # Without an observation the child's end is unknown: take the later bound.
    window = (started_ns, observed.get("ended_ns") or time.time_ns())

    user_check: dict[str, Any]
    if before is None:
        user_check = _check(UNDETERMINED, scan_problem or "user_config_unreadable")
    else:
        try:
            user_check = compare_user_config(
                before, snapshot_user_config(config), window
            )
        except _ScanLimit:
            user_check = _check(UNDETERMINED, "user_config_scan_limit")
        except OSError:
            user_check = _check(UNDETERMINED, "user_config_unreadable")
    try:
        project_entries = _project_entries(config, marker)
        projects_check = _check(
            FAIL if project_entries else PASS,
            "stage_project_in_user_config"
            if project_entries
            else "no_stage_project_entry",
            matching_entries=project_entries,
        )
    except OSError:
        projects_check = _check(UNDETERMINED, "user_projects_unreadable")

    staged_left = (workdir / ".claude").is_symlink() or (workdir / ".claude").exists()
    leftovers = len(os.listdir(scratch)) + int(staged_left)
    shutil.rmtree(stage_root, ignore_errors=True)
    removed = not stage_root.exists()
    if failure == "cleanup_failed" or leftovers or not removed:
        cleanup = _check(
            FAIL,
            "private_data_left_behind",
            leftover_count=leftovers,
            staged_config_left=staged_left,
        )
    else:
        cleanup = _check(PASS, "private_tree_deleted")

    shape = observed.get("shape")
    try:
        staged = {entry.stem for entry in claude._committed_agents()}
    except StageSetupError:
        staged = set()
    isolation = {
        "private_config": observed.get("private")
        or _check(UNDETERMINED, failure or "no_observation"),
        "user_config": user_check,
        "user_projects": projects_check,
        "setting_sources": judge_setting_sources(
            shape, staged, None if before is None else user_layer_names(before)
        ),
        "cleanup": cleanup,
    }

    checks: dict[str, dict[str, Any]] = {}
    if stage == "budget":
        checks["budget_enforcement"] = _budget_observation(observed, failure, budget)
    else:
        checks["cli_result"] = _cli_result(observed, failure)
        checks["adapter_parse"] = (
            _check(FAIL, failure) if failure else _check(PASS, "stream_recognised")
        )
    if stage == "dispatch":
        calls = [
            call
            for call in (shape["tool_uses"] if shape else [])
            if call["level"] == "parent" and call["name"] == claude.DISPATCH_TOOL
        ]
        if shape is None:
            checks["agent_tool_call"] = _check(
                UNDETERMINED, failure or "no_observation"
            )
        elif len(calls) != 1:
            checks["agent_tool_call"] = _check(
                FAIL, "no_agent_call" if not calls else "multiple_agent_calls"
            )
        elif calls[0].get("subagent_type") != DISPATCH_ROLE:
            checks["agent_tool_call"] = _check(FAIL, "unexpected_subagent_type")
        else:
            checks["agent_tool_call"] = _check(PASS, "one_scout_dispatch")
        evidence = outcome.evidence if outcome is not None else None
        if evidence is None:
            checks["adapter_evidence"] = _check(FAIL, failure or "no_evidence")
        else:
            checks["adapter_evidence"] = _check(
                PASS if evidence.ok else FAIL,
                _code(evidence.reason_code),
                dispatch_status=_name(evidence.status),
                model=None if evidence.model is None else _name(evidence.model),
            )
        loaded = (
            None
            if shape is None or shape["init"] is None
            else shape["init"]["lists"].get("agents")
        )
        if loaded is None:
            checks["staged_agent_loaded"] = _check(UNDETERMINED, "init_agents_missing")
        else:
            checks["staged_agent_loaded"] = _check(
                PASS if DISPATCH_ROLE in loaded else FAIL,
                "scout_listed" if DISPATCH_ROLE in loaded else "scout_not_listed",
            )

    # A cost that is not a finite non-negative number is not a cost: the stage
    # is then charged its whole reservation.
    cost, cost_anomalous = None, False
    if shape is not None and shape["result"] is not None:
        cost, cost_anomalous = _stage_cost(shape)
    if cost is None and not cost_anomalous and outcome is not None:
        cost = outcome.cost_usd
    if cost is not None and not _valid_cost(cost):
        cost, cost_anomalous = None, True
    status = _worst(
        PASS if entry["status"] == OBSERVED else entry["status"]
        for entry in checks.values()
    )
    if stage == "budget" and status == PASS:
        status = OBSERVED
    entry = {
        "status": status,
        "isolation_status": _worst(item["status"] for item in isolation.values()),
        "checks": checks,
        "isolation": isolation,
        "argv": argv,
        "max_budget_usd": format(budget, "f"),
        "cost_usd": cost,
        "cost_anomalous": cost_anomalous,
        "exit_code": observed.get("returncode"),
        "adapter": {
            "outcome": "returned" if outcome is not None else "raised",
            "reason": failure,
            "returncode": None if outcome is None else outcome.returncode,
            "usage": None if outcome is None else _numbers(outcome.usage),
            "event_counts": None if outcome is None else _numbers(outcome.event_counts),
        },
        "stderr": observed.get("stderr"),
        "shape": shape,
        "synthetic_diff": None if shape is None else _baseline_diff(stage, shape),
    }
    return entry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Minimal live probe of the Claude stage adapter (claude-eval-parity "
            "AC-CE-018). Consumes subscription usage; run it only with approval, "
            f"with the token injected into {claude.SUBSCRIPTION_TOKEN_ENV} by the "
            "credential broker. Writes a JSON shape report that holds no model "
            "output, no token and no absolute path. Never retries."
        ),
        epilog=(
            "Exit status: 0 all selected stages passed; 1 a check failed; 2 the "
            "probe did not start or withheld its report; 3 nothing failed but "
            "something could not be determined."
        ),
    )
    parser.add_argument(
        "--stages",
        default="auth",
        help="comma-separated subset of auth,dispatch,budget (default: auth)",
    )
    parser.add_argument("--report", help="write the JSON report here (default: stdout)")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"model of the parent session (default: {DEFAULT_MODEL}, the cheapest alias)",
    )
    parser.add_argument(
        "--claude-bin", help="claude executable (default: found on PATH)"
    )
    parser.add_argument(
        "--auth-budget-usd",
        default=DEFAULT_AUTH_BUDGET_USD,
        help="--max-budget-usd of the auth stage (default: %(default)s)",
    )
    parser.add_argument(
        "--dispatch-budget-usd",
        default=DEFAULT_DISPATCH_BUDGET_USD,
        help="--max-budget-usd of the dispatch stage (default: %(default)s)",
    )
    parser.add_argument(
        "--budget-probe-usd",
        default=DEFAULT_BUDGET_PROBE_USD,
        help="--max-budget-usd of the budget stage, meant to be exceeded (default: %(default)s)",
    )
    parser.add_argument(
        "--budget-reserve-usd",
        default=DEFAULT_BUDGET_RESERVE_USD,
        help="what the budget stage may really cost before it is stopped (default: %(default)s)",
    )
    parser.add_argument(
        "--total-budget-usd",
        default=DEFAULT_TOTAL_BUDGET_USD,
        help=(
            "stop starting stages once spent plus the next reservation exceeds this "
            f"(default: %(default)s, at most {claude.RUN_COST_CAP_USD})"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=_seconds,
        default=DEFAULT_TIMEOUT,
        help=f"seconds per stage, 10 to {MAX_TIMEOUT} (default: %(default)s)",
    )
    return parser


def _seconds(text: str) -> int:
    if not re.fullmatch(r"[0-9]{1,4}", text, re.ASCII):
        raise argparse.ArgumentTypeError("must be a plain decimal number of seconds")
    return int(text)


def _amount(value: Any, what: str) -> Decimal:
    """A dollar amount written as plain ASCII decimal, within the run cap."""
    if not isinstance(value, str) or not _AMOUNT_RE.fullmatch(value):
        raise BenchmarkContractError(f"{what} must be a plain decimal dollar amount")
    return claude._usd(value, what)


def _plan(options: argparse.Namespace) -> tuple[list[str], dict[str, Decimal], Decimal]:
    """Validated stage order, per-stage amounts and the overall cap."""
    stages = options.stages.split(",")
    if not stages or len(set(stages)) != len(stages) or set(stages) - set(STAGES):
        raise BenchmarkContractError(
            "--stages must list each of auth,dispatch,budget at most once"
        )
    total = _amount(options.total_budget_usd, "--total-budget-usd")
    amounts = {
        "auth": _amount(options.auth_budget_usd, "--auth-budget-usd"),
        "dispatch": _amount(options.dispatch_budget_usd, "--dispatch-budget-usd"),
        "budget": _amount(options.budget_probe_usd, "--budget-probe-usd"),
        "budget_reserve": _amount(options.budget_reserve_usd, "--budget-reserve-usd"),
    }
    if amounts["budget"] > amounts["budget_reserve"]:
        raise BenchmarkContractError(
            "--budget-probe-usd must not exceed --budget-reserve-usd"
        )
    if any(amount > total for amount in amounts.values()):
        raise BenchmarkContractError("a stage amount exceeds --total-budget-usd")
    if not 10 <= options.timeout <= MAX_TIMEOUT:
        raise BenchmarkContractError(f"--timeout must be 10 to {MAX_TIMEOUT} seconds")
    return [stage for stage in STAGES if stage in stages], amounts, total


def run_probe(options: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    """Run the selected stages in order; returns the report and the deleted root."""
    stages, amounts, total = _plan(options)
    root = _make_root()
    spent = Decimal("0")
    stop: str | None = None
    entries: dict[str, Any] = {}
    try:
        for stage in stages:
            reserve = amounts["budget_reserve" if stage == "budget" else stage]
            if stop is None and spent + reserve > total:
                stop = "total_budget_reached"
            if stop is not None:
                entries[stage] = {"status": SKIPPED, "reason": stop}
                continue
            print(f"claude-live-probe: running stage {stage}", file=sys.stderr)
            entry = run_stage(stage, options=options, budget=amounts[stage], root=root)
            entries[stage] = entry
            cost = entry["cost_usd"]
            charged = Decimal(str(cost)) if _valid_cost(cost) else reserve
            spent += charged
            if charged > reserve:
                stop = "stage_cost_exceeded_reservation"
            elif stage != "budget" and (
                entry["status"] != PASS or entry["adapter"]["outcome"] != "returned"
            ):
                # Login or dispatch in doubt: no further live call.
                stop = f"{stage}_stage_did_not_pass"
            elif entry["isolation_status"] == FAIL:
                stop = "isolation_check_failed"
            print(
                f"claude-live-probe: stage {stage}: {entry['status']}", file=sys.stderr
            )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    statuses = [entry["status"] for entry in entries.values()] + [
        entry["isolation_status"]
        for entry in entries.values()
        if "isolation_status" in entry
    ]
    if root.exists():
        statuses.append(FAIL)
    worst = _worst(PASS if status == OBSERVED else status for status in statuses)
    report = {
        "schema": SCHEMA,
        "token_env": claude.SUBSCRIPTION_TOKEN_ENV,
        "model_requested": options.model,
        "stages_requested": stages,
        "budgets_usd": {
            **{key: format(amount, "f") for key, amount in amounts.items()},
            "total": format(total, "f"),
        },
        "charged_usd": format(spent, "f"),
        "stopped": stop,
        "probe_root_removed": not root.exists(),
        "status": worst,
        "probe_exit_code": {PASS: 0, FAIL: 1, UNDETERMINED: 3}[worst],
        "stages": entries,
    }
    return report, root


def _strings(node: Any) -> list[str]:
    """Every string in the report, keys included, before any JSON escaping."""
    found: list[str] = []
    pending = [node]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, (list, tuple, set)):
            pending.extend(item)
    return found


def _forbidden(report: dict[str, Any], text: str, root: Path) -> list[str]:
    """Kinds of content the report must never carry.

    Each value is looked for in the raw strings of the report and, in its JSON
    escaped forms, in the serialized text, so quotes, backslashes and non-ASCII
    characters cannot hide it.
    """
    raw = "\n".join(_strings(report))

    def present(needle: str) -> bool:
        if len(needle) < 2:
            return False
        escaped = {
            json.dumps(needle)[1:-1],
            json.dumps(needle, ensure_ascii=False)[1:-1],
        }
        return needle in raw or needle in text or any(form in text for form in escaped)

    found = []
    try:
        token = claude._subscription_token()
    except StageSetupError:
        found.append("token_unavailable")
    else:
        size = min(len(token), TOKEN_FRAGMENT_LENGTH)
        if present(token):
            found.append("token")
        elif any(
            present(token[start : start + size])
            for start in range(len(token) - size + 1)
        ):
            found.append("token_fragment")
    homes = {str(user_config_dir().parent)}
    try:
        homes.update({str(claude._account_home()), str(Path.home())})
    except (StageSetupError, RuntimeError):
        pass
    homes.update({os.path.realpath(home) for home in homes})
    if any(present(home) for home in homes):
        found.append("home_path")
    if any(present(path) for path in {str(root), os.path.realpath(root)}):
        found.append("temp_path")
    if len(text.encode("utf-8")) > MAX_REPORT_BYTES:
        found.append("report_too_large")
    return found


def _open_report(destination: str) -> int:
    """Create the report file: new, owner-only and never through a symlink."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    return os.open(destination, flags, 0o600)


def _emit(report: dict[str, Any], descriptor: int | None) -> None:
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if descriptor is None:
        sys.stdout.write(text)
        return
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    options = parser.parse_args(argv)
    try:
        _plan(options)
        if not isinstance(options.model, str) or not claude._MODEL_RE.fullmatch(
            options.model
        ):
            raise BenchmarkContractError("--model must be a model alias or name")
    except BenchmarkContractError as error:
        parser.error(str(error))
    # Fail closed before anything is created: no token, no probe.
    try:
        claude._subscription_token()
    except StageSetupError:
        print(
            f"claude-live-probe: subscription token is not available in "
            f"{claude.SUBSCRIPTION_TOKEN_ENV}; refusing to start",
            file=sys.stderr,
        )
        return 2
    if options.claude_bin is None:
        options.claude_bin = shutil.which("claude")
    if not options.claude_bin:
        print("claude-live-probe: claude executable not found", file=sys.stderr)
        return 2
    # The report file is claimed before any stage runs, so a path that exists
    # (file, symlink or dangling symlink) costs nothing and is left untouched.
    descriptor: int | None = None
    if options.report is not None:
        try:
            descriptor = _open_report(options.report)
        except OSError:
            print(
                "claude-live-probe: report path exists or cannot be created; "
                "refusing to start",
                file=sys.stderr,
            )
            return 2
    written = False
    try:
        report, root = run_probe(options)
        exit_code = report["probe_exit_code"]
        forbidden = _forbidden(report, json.dumps(report), root)
        if forbidden:
            report = {
                "schema": SCHEMA,
                "status": FAIL,
                "probe_exit_code": 2,
                "error": "report_withheld",
                "forbidden_content": forbidden,
            }
            exit_code = 2
        try:
            _emit(report, descriptor)
            written = True
        except OSError:
            print("claude-live-probe: report could not be written", file=sys.stderr)
            return 2
        return exit_code
    finally:
        if descriptor is not None and not written:
            # Only ever the empty file this run created itself.
            try:
                os.close(descriptor)
            except OSError:
                pass
            try:
                os.unlink(options.report)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
