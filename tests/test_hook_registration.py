"""Codex guard registration: shoal-guard-v1 (matcher without Bash) and v2 (no Stop group) are upgraded to v3 in place."""

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
V1, V2, V3 = (hr.TRUSTED_PROJECTIONS[hr.GUARD_PROJECTION_ID_V1], hr.TRUSTED_PROJECTIONS[hr.GUARD_PROJECTION_ID_V2],
              hr.TRUSTED_PROJECTIONS[hr.GUARD_PROJECTION_ID])
AUTOROUTE = hr.TRUSTED_PROJECTIONS[hr.CURRENT_PROJECTION_ID]
USER_BASH = {"matcher": "Bash", "hooks": [{"type": "command", "command": "/opt/audit.sh", "timeout": 5}]}
USER_STOP = {"hooks": [{"type": "command", "command": "/opt/stop.sh"}]}


def registration(guard: dict) -> bytes:
    document = {
        "hooks": {
            "Stop": [USER_STOP, copy.deepcopy(AUTOROUTE["Stop"])]
            + ([copy.deepcopy(guard["Stop"])] if "Stop" in guard else []),
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
        self.assertEqual(V2["PreToolUse"], V3["PreToolUse"])

    def test_v3_adds_a_stop_group_for_the_guard_only(self) -> None:
        self.assertEqual(hr.GUARD_PROJECTION_ID, "shoal-guard-v3")
        self.assertEqual(hr.GUARD_PROJECTION_IDS, ("shoal-guard-v1", "shoal-guard-v2", "shoal-guard-v3"))
        self.assertEqual(sorted(V3), ["PreToolUse", "Stop", "UserPromptSubmit"])
        self.assertEqual(sorted(V2), ["PreToolUse", "UserPromptSubmit"])
        (handler,) = V3["Stop"]["hooks"]
        self.assertIn("shoal_guard.py", handler["command"])
        self.assertIn("--host codex", handler["command"])
        self.assertEqual(handler["timeout"], 10)
        self.assertIn("commandWindows", handler)
        self.assertNotEqual(V3["Stop"], AUTOROUTE["Stop"])  # the autoroute gate keeps its own Stop group

    def test_both_projection_states_validate_and_digests_differ(self) -> None:
        for projection_id in hr.GUARD_PROJECTION_IDS:
            self.assertEqual(hr.validate_projection_state(hr.projection_state(projection_id)), projection_id)
        digests = {hr.projection_digest(projection_id) for projection_id in hr.GUARD_PROJECTION_IDS}
        self.assertEqual(len(digests), len(hr.GUARD_PROJECTION_IDS))

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

    def assert_upgraded(self, payload: bytes, hook_id: str, guard_id: str) -> dict:
        self.assertEqual((hook_id, guard_id), (hr.CURRENT_PROJECTION_ID, hr.GUARD_PROJECTION_ID))
        document = json.loads(payload)
        hooks = document["hooks"]
        self.assertEqual(hooks["PreToolUse"], [USER_BASH, V3["PreToolUse"]])
        self.assertEqual(hooks["UserPromptSubmit"][1], V3["UserPromptSubmit"])
        # the user's Stop entry and the autoroute gate's Stop group stay in place; the guard's is appended
        self.assertEqual(hooks["Stop"], [USER_STOP, AUTOROUTE["Stop"], V3["Stop"]])
        hr.validate_owned_projection(document, hr.GUARD_PROJECTION_ID)
        hr.validate_owned_projection(document, hr.CURRENT_PROJECTION_ID)
        return document

    def test_owned_v1_is_replaced_in_place_and_foreign_entries_are_untouched(self) -> None:
        payload, hook_id, guard_id = self.merge(registration(V1), hr.GUARD_PROJECTION_ID_V1)
        self.assert_upgraded(payload, hook_id, guard_id)
        again, _, _ = self.merge(payload, hr.GUARD_PROJECTION_ID)  # idempotent once upgraded
        self.assertEqual(again, payload)

    def test_owned_v2_gains_the_stop_group_and_nothing_else_moves(self) -> None:
        before = json.loads(registration(V2))
        payload, hook_id, guard_id = self.merge(registration(V2), hr.GUARD_PROJECTION_ID_V2)
        after = self.assert_upgraded(payload, hook_id, guard_id)
        self.assertEqual(after["hooks"]["PreToolUse"], before["hooks"]["PreToolUse"])
        self.assertEqual(after["hooks"]["UserPromptSubmit"], before["hooks"]["UserPromptSubmit"])
        again, _, _ = self.merge(payload, hr.GUARD_PROJECTION_ID)
        self.assertEqual(again, payload)

    def test_unowned_v1_from_install_hooks_is_adopted_and_upgraded(self) -> None:
        payload, hook_id, guard_id = self.merge(registration(V1), None)
        self.assert_upgraded(payload, hook_id, guard_id)

    def test_unowned_v2_from_install_hooks_is_adopted_and_upgraded(self) -> None:
        payload, hook_id, guard_id = self.merge(registration(V2), None)
        self.assert_upgraded(payload, hook_id, guard_id)

    def test_unowned_v3_is_adopted_unchanged(self) -> None:
        current = registration(V3)
        payload, _, guard_id = self.merge(current, None)
        self.assertEqual((payload, guard_id), (current, hr.GUARD_PROJECTION_ID))

    def test_fresh_install_registers_the_three_guard_groups_next_to_the_autoroute_gate(self) -> None:
        payload, hook_id, guard_id = hr.merge_registration(
            None, SOURCE, owned_projection_id=None, owned_guard_projection_id=None
        )
        document = json.loads(payload)
        self.assertEqual(document["hooks"]["Stop"], [AUTOROUTE["Stop"], V3["Stop"]])
        hr.validate_owned_projection(document, hr.GUARD_PROJECTION_ID)
        self.assertEqual((hook_id, guard_id), (hr.CURRENT_PROJECTION_ID, hr.GUARD_PROJECTION_ID))

    def test_a_stop_group_equal_to_the_guard_group_but_not_owned_blocks_the_v2_upgrade(self) -> None:
        document = json.loads(registration(V2))
        document["hooks"]["Stop"].append(copy.deepcopy(V3["Stop"]))  # a canonical group we did not place
        with self.assertRaises(hr.HookRegistrationError):
            self.merge(json.dumps(document).encode(), hr.GUARD_PROJECTION_ID_V2)

    def test_a_foreign_group_equal_to_the_v2_group_blocks_the_upgrade(self) -> None:
        document = json.loads(registration(V1))
        document["hooks"]["PreToolUse"].append(copy.deepcopy(V3["PreToolUse"]))
        with self.assertRaises(hr.HookRegistrationError):
            self.merge(json.dumps(document).encode(), hr.GUARD_PROJECTION_ID_V1)

    def test_a_partial_v1_without_state_is_not_adopted(self) -> None:
        document = json.loads(registration(V1))
        del document["hooks"]["UserPromptSubmit"][1]
        with self.assertRaises(hr.HookRegistrationError):
            self.merge(json.dumps(document).encode(), None)


if __name__ == "__main__":
    unittest.main()
