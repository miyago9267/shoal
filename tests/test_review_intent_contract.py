from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))

from review_intent_contract import (  # noqa: E402
    ReviewIntentContractError,
    scheduler_projection,
    validate_signal,
)


def signal(intent: str = "fast") -> dict[str, object]:
    return {
        "schema": 1,
        "session_id": "session-1",
        "turn_id": "turn-1",
        "review_intent": intent,
        "source": "explicit",
        "scope": "turn",
        "confidence": "clear",
        "risk_categories": ["security"],
        "optional_review": {
            "fast": "skip",
            "default": "existing_policy",
            "strict": "expanded",
        }[intent],
    }


class ReviewIntentContractTests(unittest.TestCase):
    def test_valid_signal_projects_without_model_or_role_selection(self) -> None:
        projected = scheduler_projection(signal("strict"), mandatory_review=True)
        self.assertEqual(projected["optional_review"], "expanded")
        self.assertTrue(projected["mandatory_review"])
        self.assertTrue(projected["preserve_approval"])
        self.assertTrue(projected["preserve_role_binding"])
        self.assertNotIn("model", projected)
        self.assertNotIn("role", projected)

    def test_fast_signal_never_removes_mandatory_review(self) -> None:
        projected = scheduler_projection(signal("fast"), mandatory_review=True)
        self.assertEqual(projected["optional_review"], "skip")
        self.assertTrue(projected["mandatory_review"])

    def test_consumer_cannot_downgrade_security_signal(self) -> None:
        with self.assertRaises(ReviewIntentContractError):
            scheduler_projection(signal("fast"), mandatory_review=False)

    def test_malformed_signal_and_mode_mismatch_fail_closed(self) -> None:
        malformed = signal("fast")
        malformed["optional_review"] = "expanded"
        with self.assertRaises(ReviewIntentContractError):
            validate_signal(malformed)

        unknown = signal("fast")
        unknown["unexpected"] = True
        with self.assertRaises(ReviewIntentContractError):
            validate_signal(unknown)


if __name__ == "__main__":
    unittest.main()
