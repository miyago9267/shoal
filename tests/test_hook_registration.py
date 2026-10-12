"""Codex guard registration: shoal-guard-v1 (matcher without Bash) is upgraded to v2 in place."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import hook_registration as hr  # noqa: E402

SOURCE = (ROOT / "templates" / "hooks.json").read_bytes()
V1, V2 = hr.TRUSTED_PROJECTIONS[hr.GUARD_PROJECTION_ID_V1], hr.TRUSTED_PROJECTIONS[hr.GUARD_PROJECTION_ID]
AUTOROUTE = hr.TRUSTED_PROJECTIONS[hr.CURRENT_PROJECTION_ID]
USER_BASH = {"matcher": "Bash", "hooks": [{"type": "command", "command": "/opt/audit.sh", "timeout": 5}]}
USER_STOP = {"hooks": [{"type": "command", "command": "/opt/stop.sh"}]}


def registration(guard: dict) -> bytes:
    document = {
        "hooks": {
            "Stop": [USER_STOP, copy.deepcopy(AUTOROUTE["Stop"])],
            "UserPromptSubmit": [copy.deepcopy(AUTOROUTE["UserPromptSubmit"]), copy.deepcopy(guard["UserPromptSubmit"])],
            "PreToolUse": [USER_BASH, copy.deepcopy(guard["PreToolUse"])],
        }
    }
    return json.dumps(document, indent=2).encode() + b"\n"


class GuardProjectionTests(unittest.TestCase):
    def test_v2_matcher_adds_bash_and_stays_anchored(self) -> None:
        self.assertEqual(V1["PreToolUse"]["matcher"], "^(apply_patch|spawn_agent|collaborationspawn_agent)$")
        self.assertEqual(V2["PreToolUse"]["matcher"], "^(apply_patch|spawn_agent|collaborationspawn_agent|Bash)$")
        self.assertEqual(V1["UserPromptSubmit"], V2["UserPromptSubmit"])
        self.assertEqual(hr.GUARD_PROJECTION_ID, "shoal-guard-v2")

    def test_both_projection_states_validate_and_digests_differ(self) -> None:
        for projection_id in hr.GUARD_PROJECTION_IDS:
            self.assertEqual(hr.validate_projection_state(hr.projection_state(projection_id)), projection_id)
        self.assertNotEqual(hr.projection_digest(hr.GUARD_PROJECTION_ID_V1), hr.projection_digest(hr.GUARD_PROJECTION_ID))

    def test_state_with_a_forged_digest_is_rejected(self) -> None:
        state = hr.projection_state(hr.GUARD_PROJECTION_ID)
        state["projection_sha256"] = hr.projection_digest(hr.GUARD_PROJECTION_ID_V1)
        with self.assertRaises(hr.HookRegistrationError):
            hr.validate_projection_state(state)


class MergeTests(unittest.TestCase):
    def merge(self, current: bytes, owned_guard):
        return hr.merge_registration(
            current, SOURCE, owned_projection_id=hr.CURRENT_PROJECTION_ID, owned_guard_projection_id=owned_guard
        )

    def test_owned_v1_is_replaced_in_place_and_foreign_entries_are_untouched(self) -> None:
        payload, hook_id, guard_id = self.merge(registration(V1), hr.GUARD_PROJECTION_ID_V1)
        self.assertEqual((hook_id, guard_id), (hr.CURRENT_PROJECTION_ID, hr.GUARD_PROJECTION_ID))
        hooks = json.loads(payload)["hooks"]
        self.assertEqual(hooks["PreToolUse"], [USER_BASH, V2["PreToolUse"]])
        self.assertEqual(hooks["UserPromptSubmit"][1], V2["UserPromptSubmit"])
        self.assertEqual(hooks["Stop"][0], USER_STOP)
        hr.validate_owned_projection(json.loads(payload), hr.GUARD_PROJECTION_ID)
        # idempotent once upgraded
        again, _, _ = self.merge(payload, hr.GUARD_PROJECTION_ID)
        self.assertEqual(again, payload)

    def test_unowned_v1_from_install_hooks_is_adopted_and_upgraded(self) -> None:
        payload, _, guard_id = self.merge(registration(V1), None)
        self.assertEqual(guard_id, hr.GUARD_PROJECTION_ID)
        self.assertEqual(json.loads(payload)["hooks"]["PreToolUse"], [USER_BASH, V2["PreToolUse"]])

    def test_unowned_v2_is_adopted_unchanged(self) -> None:
        current = registration(V2)
        payload, _, guard_id = self.merge(current, None)
        self.assertEqual((payload, guard_id), (current, hr.GUARD_PROJECTION_ID))

    def test_a_foreign_group_equal_to_the_v2_group_blocks_the_upgrade(self) -> None:
        document = json.loads(registration(V1))
        document["hooks"]["PreToolUse"].append(copy.deepcopy(V2["PreToolUse"]))
        with self.assertRaises(hr.HookRegistrationError):
            self.merge(json.dumps(document).encode(), hr.GUARD_PROJECTION_ID_V1)

    def test_a_partial_v1_without_state_is_not_adopted(self) -> None:
        document = json.loads(registration(V1))
        del document["hooks"]["UserPromptSubmit"][1]
        with self.assertRaises(hr.HookRegistrationError):
            self.merge(json.dumps(document).encode(), None)


if __name__ == "__main__":
    unittest.main()
