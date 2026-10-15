import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))

from decision_checkpoint import (  # noqa: E402
    CheckpointError,
    SCHEMA,
    resolve_reply,
    resume_contract,
    validate_checkpoint,
)


def card() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "checkpoint_id": "task_scope_choice",
        "scope": "task decomposition and blocker handling",
        "current_interpretation": "One local task is blocked; two sibling tasks remain runnable.",
        "impact": "The choice changes which local tasks continue, not external authority.",
        "recommended_option": "finish_runnable",
        "options": [
            {
                "id": "finish_runnable",
                "label": "Finish runnable tasks first",
                "effect": "Continue only the two unblocked sibling tasks, then pause.",
            },
            {
                "id": "stop_all",
                "label": "Stop all tasks",
                "effect": "Pause immediately and wait for human intervention.",
            },
        ],
        "excluded_scope": ["credentials", "external_writes", "irreversible_changes"],
        "affected_task_ids": ["blocked_local", "runnable_a", "runnable_b"],
        "resume_point": "Re-evaluate blocked_local after the selected local slice.",
        "approval_boundary": "This card does not approve external, destructive, or irreversible work.",
    }


class DecisionCheckpointTests(unittest.TestCase):
    def test_valid_card_is_bounded_and_recommends_existing_option(self) -> None:
        normalized = validate_checkpoint(card())
        self.assertEqual(normalized["recommended_option"], "finish_runnable")
        self.assertEqual(len(normalized["options"]), 2)

    def test_exact_number_or_id_confirms_only_selected_option(self) -> None:
        self.assertEqual(
            resolve_reply(card(), "1"),
            {"status": "CONFIRMED", "option_id": "finish_runnable"},
        )
        self.assertEqual(
            resolve_reply(card(), "stop_all"),
            {"status": "CONFIRMED", "option_id": "stop_all"},
        )

    def test_rejection_and_ambiguous_reply_never_resume_as_approval(self) -> None:
        rejected = resolve_reply(card(), "拒絕")
        self.assertEqual(rejected["status"], "REJECTED")
        ambiguous = resolve_reply(card(), "我覺得先看看情況")
        self.assertEqual(ambiguous["status"], "AMBIGUOUS")
        with self.assertRaisesRegex(CheckpointError, "cannot resume"):
            resume_contract(card(), ambiguous)

    def test_resume_contract_preserves_scope_and_exact_resume_point(self) -> None:
        result = resume_contract(card(), resolve_reply(card(), "1"))
        self.assertEqual(result["status"], "CONFIRMED")
        self.assertEqual(result["selected_option"], "finish_runnable")
        self.assertEqual(result["affected_task_ids"], ["blocked_local", "runnable_a", "runnable_b"])
        self.assertIn("Re-evaluate blocked_local", result["resume_point"])

    def test_card_rejects_duplicate_or_unbounded_options(self) -> None:
        invalid = card()
        invalid["options"] = [card()["options"][0]] * 4  # type: ignore[index]
        with self.assertRaisesRegex(CheckpointError, "two or three"):
            validate_checkpoint(invalid)
        invalid = card()
        invalid["questions"] = [{"question": "follow-up detail"}]
        with self.assertRaisesRegex(CheckpointError, "fields are missing or unknown"):
            validate_checkpoint(invalid)
        invalid = card()
        invalid["recommended_option"] = "unknown"
        with self.assertRaisesRegex(CheckpointError, "recommended_option"):
            validate_checkpoint(invalid)


if __name__ == "__main__":
    unittest.main()
