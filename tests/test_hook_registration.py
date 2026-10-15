"""Codex guard registration: shoal-guard-v1 (matcher without Bash), v2 (no Stop group) and v3 (no SubagentStart group)
and v4 (no PostToolUse group) are upgraded to v5 in place; `shoal-guard-v5` and `shoal-dispatch-guard-v1` (the shell-only
PostToolUse matcher, no SessionEnd) are upgraded to `shoal-dispatch-guard-v2` the same way."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))
import hook_registration as hr  # noqa: E402

SOURCE = (ROOT / "templates" / "hooks.json").read_bytes()
V1, V2, V3, V4, V6 = (hr.TRUSTED_PROJECTIONS[hr.LEGACY_GUARD_PROJECTION_ID_V1], hr.TRUSTED_PROJECTIONS[hr.LEGACY_GUARD_PROJECTION_ID_V2],
                      hr.TRUSTED_PROJECTIONS[hr.LEGACY_GUARD_PROJECTION_ID_V3], hr.TRUSTED_PROJECTIONS[hr.LEGACY_GUARD_PROJECTION_ID_V4],
                      hr.TRUSTED_PROJECTIONS[hr.GUARD_PROJECTION_ID])
V5 = hr.TRUSTED_PROJECTIONS[hr.GUARD_PROJECTION_ID_V1]  # shoal-dispatch-guard-v1: the groups of the legacy shoal-guard-v5
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
    if "SubagentStart" in guard:
        document["hooks"]["SubagentStart"] = [copy.deepcopy(guard["SubagentStart"])]
    if "PostToolUse" in guard:
        document["hooks"]["PostToolUse"] = [copy.deepcopy(guard["PostToolUse"])]
    if "SessionEnd" in guard:
        document["hooks"]["SessionEnd"] = [copy.deepcopy(guard["SessionEnd"])]
    if "SessionEnd" in guard:
        document["hooks"]["SessionEnd"] = [copy.deepcopy(guard["SessionEnd"])]
    return json.dumps(document, indent=2).encode() + b"\n"


class GuardProjectionTests(unittest.TestCase):
    def test_v2_matcher_adds_bash_and_stays_anchored(self) -> None:
        self.assertEqual(V1["PreToolUse"]["matcher"], "^(apply_patch|spawn_agent|collaborationspawn_agent)$")
        self.assertEqual(V2["PreToolUse"]["matcher"], "^(apply_patch|spawn_agent|collaborationspawn_agent|Bash)$")
        self.assertEqual(V1["UserPromptSubmit"], V2["UserPromptSubmit"])
        self.assertEqual(V2["PreToolUse"], V6["PreToolUse"])

    def test_v4_adds_a_subagent_start_group_without_matcher(self) -> None:
        self.assertEqual(sorted(V4), ["PreToolUse", "Stop", "SubagentStart", "UserPromptSubmit"])
        self.assertEqual(sorted(V3), ["PreToolUse", "Stop", "UserPromptSubmit"])
        self.assertNotIn("matcher", V4["SubagentStart"])  # every agent_type; the guard filters by role
        (handler,) = V4["SubagentStart"]["hooks"]
        self.assertIn("shoal_guard.py", handler["command"])
        self.assertIn("--host codex", handler["command"])
        self.assertEqual(handler["timeout"], 10)
        for event in ("UserPromptSubmit", "Stop", "PreToolUse"):
            self.assertEqual(V4[event], V3[event])  # the three groups already approved keep their bytes

    def test_v5_adds_a_post_tool_use_group_for_the_shell_tool_only(self) -> None:
        self.assertEqual(hr.TRUSTED_PROJECTIONS["shoal-guard-v5"], V5)  # legacy v5 and shoal-dispatch-guard-v1 are byte-identical
        self.assertEqual(sorted(V5), ["PostToolUse", "PreToolUse", "Stop", "SubagentStart", "UserPromptSubmit"])
        self.assertEqual(V5["PostToolUse"]["matcher"], "^Bash$")  # the shell tool, anchored: no other tool's result
        (handler,) = V5["PostToolUse"]["hooks"]
        self.assertIn("shoal_guard.py", handler["command"])
        self.assertIn("--host codex", handler["command"])
        self.assertEqual(handler["timeout"], 10)
        self.assertIn("commandWindows", handler)
        for event in ("UserPromptSubmit", "Stop", "PreToolUse", "SubagentStart"):
            self.assertEqual(V5[event], V4[event])  # the four groups already approved keep their bytes

    def test_v2_current_widens_post_tool_use_and_adds_session_end(self) -> None:
        # issue miyago9267/shoal#3: chain members get edits (apply_patch) and SessionEnd on Codex
        self.assertEqual(hr.GUARD_PROJECTION_ID, "shoal-dispatch-guard-v2")
        self.assertEqual(
            hr.GUARD_PROJECTION_IDS,
            ("shoal-guard-v1", "shoal-guard-v2", "shoal-guard-v3", "shoal-guard-v4", "shoal-guard-v5",
             "shoal-dispatch-guard-v1", "shoal-dispatch-guard-v2"),  # all but the last are old ids, kept so an old state validates
        )
        self.assertEqual(sorted(V6), ["PostToolUse", "PreToolUse", "SessionEnd", "Stop", "SubagentStart", "UserPromptSubmit"])
        self.assertEqual(V6["PostToolUse"]["matcher"], "^(Bash|apply_patch)$")
        self.assertNotIn("matcher", V6["SessionEnd"])
        (handler,) = V6["SessionEnd"]["hooks"]
        self.assertIn("--host codex", handler["command"])
        self.assertEqual(handler["timeout"], 10)
        for event in ("UserPromptSubmit", "Stop", "PreToolUse", "SubagentStart"):
            self.assertEqual(V6[event], V5[event])  # the groups already approved keep their bytes

    def test_v3_adds_a_stop_group_for_the_guard_only(self) -> None:
        self.assertEqual(sorted(V2), ["PreToolUse", "UserPromptSubmit"])
        (handler,) = V6["Stop"]["hooks"]
        self.assertIn("shoal_guard.py", handler["command"])
        self.assertIn("--host codex", handler["command"])
        self.assertEqual(handler["timeout"], 10)
        self.assertIn("commandWindows", handler)
        self.assertNotEqual(V6["Stop"], AUTOROUTE["Stop"])  # the autoroute gate keeps its own Stop group

    def test_both_projection_states_validate_and_digests_differ(self) -> None:
        for projection_id in hr.GUARD_PROJECTION_IDS:
            self.assertEqual(hr.validate_projection_state(hr.projection_state(projection_id)), projection_id)
        digests = {hr.projection_digest(projection_id) for projection_id in hr.GUARD_PROJECTION_IDS}
        self.assertEqual(len(digests), len(hr.GUARD_PROJECTION_IDS) - 1)  # legacy v5 and shoal-dispatch-guard-v1 share their groups

    def test_state_with_a_forged_digest_is_rejected(self) -> None:
        state = hr.projection_state(hr.GUARD_PROJECTION_ID)
        state["projection_sha256"] = hr.projection_digest(hr.LEGACY_GUARD_PROJECTION_ID_V1)
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
        self.assertEqual(hooks["PreToolUse"], [USER_BASH, V6["PreToolUse"]])
        self.assertEqual(hooks["UserPromptSubmit"][1], V6["UserPromptSubmit"])
        # the user's Stop entry and the autoroute gate's Stop group stay in place; the guard's is appended
        self.assertEqual(hooks["Stop"], [USER_STOP, AUTOROUTE["Stop"], V6["Stop"]])
        self.assertEqual(hooks["SubagentStart"], [V6["SubagentStart"]])
        self.assertEqual(hooks["PostToolUse"], [V6["PostToolUse"]])
        self.assertEqual(hooks["SessionEnd"], [V6["SessionEnd"]])
        hr.validate_owned_projection(document, hr.GUARD_PROJECTION_ID)
        hr.validate_owned_projection(document, hr.CURRENT_PROJECTION_ID)
        return document

    def test_owned_v1_is_replaced_in_place_and_foreign_entries_are_untouched(self) -> None:
        payload, hook_id, guard_id = self.merge(registration(V1), hr.LEGACY_GUARD_PROJECTION_ID_V1)
        self.assert_upgraded(payload, hook_id, guard_id)
        again, _, _ = self.merge(payload, hr.GUARD_PROJECTION_ID)  # idempotent once upgraded
        self.assertEqual(again, payload)

    def test_owned_v2_gains_the_stop_group_and_nothing_else_moves(self) -> None:
        before = json.loads(registration(V2))
        payload, hook_id, guard_id = self.merge(registration(V2), hr.LEGACY_GUARD_PROJECTION_ID_V2)
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

    def test_owned_v3_gains_the_subagent_start_group_and_nothing_else_moves(self) -> None:
        before = json.loads(registration(V3))
        payload, hook_id, guard_id = self.merge(registration(V3), hr.LEGACY_GUARD_PROJECTION_ID_V3)
        after = self.assert_upgraded(payload, hook_id, guard_id)
        for event in ("PreToolUse", "UserPromptSubmit", "Stop"):
            self.assertEqual(after["hooks"][event], before["hooks"][event])
        again, _, _ = self.merge(payload, hr.GUARD_PROJECTION_ID)
        self.assertEqual(again, payload)

    def test_unowned_v3_from_install_hooks_is_adopted_and_upgraded(self) -> None:
        payload, hook_id, guard_id = self.merge(registration(V3), None)
        self.assert_upgraded(payload, hook_id, guard_id)

    def test_a_subagent_start_group_equal_to_the_guard_group_but_not_owned_blocks_the_v3_upgrade(self) -> None:
        document = json.loads(registration(V3))
        document["hooks"]["SubagentStart"] = [copy.deepcopy(V6["SubagentStart"])]  # a canonical group we did not place
        with self.assertRaises(hr.HookRegistrationError):
            self.merge(json.dumps(document).encode(), hr.LEGACY_GUARD_PROJECTION_ID_V3)

    def test_owned_v4_gains_the_post_tool_use_group_and_nothing_else_moves(self) -> None:
        # a machine that installed the earlier (unreleased) v4 is upgraded in place, not rejected
        before = json.loads(registration(V4))
        payload, hook_id, guard_id = self.merge(registration(V4), hr.LEGACY_GUARD_PROJECTION_ID_V4)
        after = self.assert_upgraded(payload, hook_id, guard_id)
        for event in ("PreToolUse", "UserPromptSubmit", "Stop", "SubagentStart"):
            self.assertEqual(after["hooks"][event], before["hooks"][event])
        self.assertEqual(after["hooks"]["PostToolUse"], [V6["PostToolUse"]])
        again, _, _ = self.merge(payload, hr.GUARD_PROJECTION_ID)
        self.assertEqual(again, payload)

    def test_unowned_v4_from_install_hooks_is_adopted_and_upgraded(self) -> None:
        payload, hook_id, guard_id = self.merge(registration(V4), None)
        self.assert_upgraded(payload, hook_id, guard_id)

    def test_a_post_tool_use_group_equal_to_the_guard_group_but_not_owned_blocks_the_v4_upgrade(self) -> None:
        document = json.loads(registration(V4))
        document["hooks"]["PostToolUse"] = [copy.deepcopy(V6["PostToolUse"])]  # a canonical group we did not place
        with self.assertRaises(hr.HookRegistrationError):
            self.merge(json.dumps(document).encode(), hr.LEGACY_GUARD_PROJECTION_ID_V4)

    def test_unowned_current_is_adopted_unchanged(self) -> None:
        current = registration(V6)
        payload, _, guard_id = self.merge(current, None)
        self.assertEqual((payload, guard_id), (current, hr.GUARD_PROJECTION_ID))

    def test_owned_dispatch_guard_v1_and_legacy_v5_migrate_in_place_to_v2(self) -> None:
        for owned in (hr.GUARD_PROJECTION_ID_V1, hr.LEGACY_GUARD_PROJECTION_ID_V5):
            with self.subTest(owned=owned):
                before = json.loads(registration(V5))
                payload, hook_id, guard_id = self.merge(registration(V5), owned)
                after = self.assert_upgraded(payload, hook_id, guard_id)
                for event in ("PreToolUse", "UserPromptSubmit", "Stop", "SubagentStart"):
                    self.assertEqual(after["hooks"][event], before["hooks"][event])
                self.assertEqual(after["hooks"]["SessionEnd"], [V6["SessionEnd"]])
                again, _, _ = self.merge(payload, hr.GUARD_PROJECTION_ID)  # idempotent
                self.assertEqual(again, payload)

    def test_unowned_dispatch_guard_v1_from_an_older_install_is_adopted_and_upgraded(self) -> None:
        payload, hook_id, guard_id = self.merge(registration(V5), None)
        self.assert_upgraded(payload, hook_id, guard_id)

    def test_a_user_post_tool_use_entry_survives_the_v1_migration(self) -> None:
        document = json.loads(registration(V5))
        document["hooks"]["PostToolUse"].insert(0, copy.deepcopy(USER_BASH))
        payload, _, _ = self.merge(json.dumps(document).encode(), hr.GUARD_PROJECTION_ID_V1)
        self.assertEqual(json.loads(payload)["hooks"]["PostToolUse"], [USER_BASH, V6["PostToolUse"]])

    def test_a_session_end_group_equal_to_the_guard_group_but_not_owned_blocks_the_migration(self) -> None:
        document = json.loads(registration(V5))
        document["hooks"]["SessionEnd"] = [copy.deepcopy(V6["SessionEnd"])]  # a canonical group we did not place
        with self.assertRaises(hr.HookRegistrationError):
            self.merge(json.dumps(document).encode(), hr.GUARD_PROJECTION_ID_V1)

    def test_fresh_install_registers_the_five_guard_groups_next_to_the_autoroute_gate(self) -> None:
        payload, hook_id, guard_id = hr.merge_registration(
            None, SOURCE, owned_projection_id=None, owned_guard_projection_id=None
        )
        document = json.loads(payload)
        self.assertEqual(document["hooks"]["Stop"], [AUTOROUTE["Stop"], V6["Stop"]])
        hr.validate_owned_projection(document, hr.GUARD_PROJECTION_ID)
        self.assertEqual((hook_id, guard_id), (hr.CURRENT_PROJECTION_ID, hr.GUARD_PROJECTION_ID))

    def test_a_stop_group_equal_to_the_guard_group_but_not_owned_blocks_the_v2_upgrade(self) -> None:
        document = json.loads(registration(V2))
        document["hooks"]["Stop"].append(copy.deepcopy(V6["Stop"]))  # a canonical group we did not place
        with self.assertRaises(hr.HookRegistrationError):
            self.merge(json.dumps(document).encode(), hr.LEGACY_GUARD_PROJECTION_ID_V2)

    def test_a_foreign_group_equal_to_the_v2_group_blocks_the_upgrade(self) -> None:
        document = json.loads(registration(V1))
        document["hooks"]["PreToolUse"].append(copy.deepcopy(V6["PreToolUse"]))
        with self.assertRaises(hr.HookRegistrationError):
            self.merge(json.dumps(document).encode(), hr.LEGACY_GUARD_PROJECTION_ID_V1)

    def test_a_partial_v1_without_state_is_not_adopted(self) -> None:
        document = json.loads(registration(V1))
        del document["hooks"]["UserPromptSubmit"][1]
        with self.assertRaises(hr.HookRegistrationError):
            self.merge(json.dumps(document).encode(), None)


if __name__ == "__main__":
    unittest.main()
