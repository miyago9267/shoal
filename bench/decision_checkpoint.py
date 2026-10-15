"""Validate and resolve the general-mode decision checkpoint contract."""

from __future__ import annotations

import re
from typing import Any


SCHEMA = "shoal-decision-checkpoint-v1"
CHECKPOINT_STATUSES = frozenset({"PENDING", "CONFIRMED", "REJECTED", "AMBIGUOUS"})
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class CheckpointError(ValueError):
    """Raised when a decision card is unsafe or structurally ambiguous."""


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CheckpointError(f"{field} must be a non-empty string")
    return value.strip()


def _identifiers(value: Any, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise CheckpointError(f"{field} must be a non-empty list")
    if not all(isinstance(item, str) and IDENTIFIER.fullmatch(item) for item in value):
        raise CheckpointError(f"{field} contains an invalid identifier")
    if len(set(value)) != len(value):
        raise CheckpointError(f"{field} contains duplicates")
    return list(value)


def validate_checkpoint(card: Any) -> dict[str, Any]:
    """Validate a bounded, user-facing decision card and return a copy."""
    if not isinstance(card, dict):
        raise CheckpointError("checkpoint must be an object")
    required = {
        "schema", "checkpoint_id", "scope", "current_interpretation", "impact",
        "recommended_option", "options", "excluded_scope", "affected_task_ids",
        "resume_point", "approval_boundary",
    }
    if set(card) != required:
        raise CheckpointError("checkpoint fields are missing or unknown")
    if card["schema"] != SCHEMA:
        raise CheckpointError("checkpoint schema is unsupported")
    checkpoint_id = _string(card["checkpoint_id"], "checkpoint_id")
    if IDENTIFIER.fullmatch(checkpoint_id) is None:
        raise CheckpointError("checkpoint_id is invalid")
    options = card["options"]
    if not isinstance(options, list) or not 2 <= len(options) <= 3:
        raise CheckpointError("options must contain two or three choices")
    normalized_options: list[dict[str, str]] = []
    option_ids: set[str] = set()
    for option in options:
        if not isinstance(option, dict) or set(option) != {"id", "label", "effect"}:
            raise CheckpointError("each option must contain id, label, and effect")
        option_id = _string(option["id"], "option.id")
        if IDENTIFIER.fullmatch(option_id) is None or option_id in option_ids:
            raise CheckpointError("option id is invalid or duplicated")
        option_ids.add(option_id)
        normalized_options.append({
            "id": option_id,
            "label": _string(option["label"], "option.label"),
            "effect": _string(option["effect"], "option.effect"),
        })
    recommended = _string(card["recommended_option"], "recommended_option")
    if recommended not in option_ids:
        raise CheckpointError("recommended_option must name an option")
    return {
        "schema": SCHEMA,
        "checkpoint_id": checkpoint_id,
        "scope": _string(card["scope"], "scope"),
        "current_interpretation": _string(
            card["current_interpretation"], "current_interpretation"
        ),
        "impact": _string(card["impact"], "impact"),
        "recommended_option": recommended,
        "options": normalized_options,
        "excluded_scope": _identifiers(card["excluded_scope"], "excluded_scope", allow_empty=True),
        "affected_task_ids": _identifiers(card["affected_task_ids"], "affected_task_ids"),
        "resume_point": _string(card["resume_point"], "resume_point"),
        "approval_boundary": _string(card["approval_boundary"], "approval_boundary"),
    }


def resolve_reply(card: Any, reply: str) -> dict[str, str]:
    """Resolve only exact option ids/numbers or an explicit rejection."""
    normalized = validate_checkpoint(card)
    if not isinstance(reply, str) or not reply.strip():
        return {"status": "AMBIGUOUS", "option_id": ""}
    text = reply.strip().casefold()
    options = normalized["options"]
    for index, option in enumerate(options, start=1):
        if text in {option["id"].casefold(), str(index)}:
            return {"status": "CONFIRMED", "option_id": option["id"]}
    if text in {"reject", "rejected", "拒絕", "拒絕 checkpoint", "cancel", "取消"}:
        return {"status": "REJECTED", "option_id": ""}
    return {"status": "AMBIGUOUS", "option_id": ""}


def resume_contract(card: Any, resolution: dict[str, str]) -> dict[str, Any]:
    """Build the bounded resume payload after an unambiguous resolution."""
    normalized = validate_checkpoint(card)
    if resolution.get("status") not in {"CONFIRMED", "REJECTED"}:
        raise CheckpointError("ambiguous resolution cannot resume work")
    option_id = resolution.get("option_id", "")
    if resolution["status"] == "CONFIRMED" and option_id not in {
        option["id"] for option in normalized["options"]
    }:
        raise CheckpointError("selected option is not part of the checkpoint")
    return {
        "checkpoint_id": normalized["checkpoint_id"],
        "status": resolution["status"],
        "selected_option": option_id,
        "affected_task_ids": normalized["affected_task_ids"],
        "resume_point": normalized["resume_point"],
    }
