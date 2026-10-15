#!/usr/bin/env python3
"""Validate and project shoal's advisory review-intent signal."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


SIGNAL_SCHEMA = 1
SIGNAL_KEYS = frozenset(
    {
        "schema",
        "session_id",
        "turn_id",
        "review_intent",
        "source",
        "scope",
        "confidence",
        "risk_categories",
        "optional_review",
    }
)
INTENTS = frozenset({"fast", "default", "strict"})
OPTIONAL_REVIEWS = frozenset({"skip", "existing_policy", "expanded"})
RISK_CATEGORIES = frozenset({"data", "external", "irreversible", "release", "security"})
IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")


class ReviewIntentContractError(ValueError):
    """The advisory signal is malformed or internally inconsistent."""


def validate_signal(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SIGNAL_KEYS:
        raise ReviewIntentContractError("review-intent signal shape is invalid")
    if value["schema"] != SIGNAL_SCHEMA:
        raise ReviewIntentContractError("review-intent signal schema is unsupported")
    for field in ("session_id", "turn_id"):
        if not isinstance(value[field], str) or IDENTIFIER.fullmatch(value[field]) is None:
            raise ReviewIntentContractError(f"review-intent {field} is invalid")
    if value["review_intent"] not in INTENTS:
        raise ReviewIntentContractError("review-intent mode is invalid")
    if value["source"] != "explicit" or value["scope"] != "turn" or value["confidence"] != "clear":
        raise ReviewIntentContractError("review-intent provenance is invalid")
    categories = value["risk_categories"]
    if (
        not isinstance(categories, list)
        or categories != sorted(set(categories))
        or any(category not in RISK_CATEGORIES for category in categories)
    ):
        raise ReviewIntentContractError("review-intent risk categories are invalid")
    expected_optional = {
        "fast": "skip",
        "default": "existing_policy",
        "strict": "expanded",
    }[value["review_intent"]]
    if value["optional_review"] != expected_optional:
        raise ReviewIntentContractError("review-intent optional review does not match mode")
    return value


def scheduler_projection(value: Any, *, mandatory_review: bool) -> dict[str, Any]:
    """Project a validated signal without selecting a role or model."""
    signal = validate_signal(value)
    if type(mandatory_review) is not bool:
        raise ReviewIntentContractError("mandatory review flag is invalid")
    categories = signal["risk_categories"]
    derived_mandatory = bool(categories) and (
        "security" in categories or len(categories) >= 2
    )
    if derived_mandatory and not mandatory_review:
        raise ReviewIntentContractError("mandatory review downgrade is not allowed")
    digest = hashlib.sha256(
        json.dumps(signal, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "deduplication_key": f"{signal['session_id']}:{signal['turn_id']}:{digest}",
        "mandatory_review": mandatory_review,
        "optional_review": signal["optional_review"],
        "preserve_approval": True,
        "preserve_role_binding": True,
    }
