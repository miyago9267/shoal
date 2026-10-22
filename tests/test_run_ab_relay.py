from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "ab"))
import run_ab  # noqa: E402


def tool_result(payload: object) -> dict:
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": json.dumps(payload)}]}}


class ArmPluginTests(unittest.TestCase):
    def test_relay_arm_has_own_plugin_dir_and_control_stays_off(self) -> None:
        """S1.13a"""
        with tempfile.TemporaryDirectory() as tmp:
            dirs, _ = run_ab.arm_plugins(Path(tmp), ["shoal", "shoal-relay"])
            self.assertNotEqual(dirs["shoal"], dirs["shoal-relay"])
            self.assertFalse(run_ab.relay_enabled(dirs["shoal"]))
            self.assertTrue(run_ab.relay_enabled(dirs["shoal-relay"]))

    def test_dry_run_reports_relay_per_arm(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_ab.main(["--arms", "shoal,shoal-relay", "--dry-run", "--model", "m", "--tasks-dir", str(ROOT / "bench/ab/tasks-v2")])
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("shoal: relay=off", text)
        self.assertIn("shoal-relay: relay=on", text)
        self.assertEqual(len({l for l in text.splitlines() if l.strip().startswith("plugin-dirs:")}), 2)

    def test_committed_binding_has_no_relay(self) -> None:
        self.assertNotIn("[relay", (ROOT / "hosts/claude/binding.toml").read_text(encoding="utf-8"))


class UsageTests(unittest.TestCase):
    def test_codex_usage_sums_handbacks_separately(self) -> None:
        events = [
            tool_result({"status": "done", "vendor": "codex", "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 3}}),
            tool_result({"status": "failed", "vendor": "codex", "usage": None, "session_id": "s1"}),
            tool_result({"status": "done", "vendor": "other", "usage": {"input_tokens": 99, "cached_input_tokens": 0, "output_tokens": 0}}),
            {"type": "user", "message": {"content": "plain"}},
            {"type": "result", "total_cost_usd": 0.1},
        ]
        usage = run_ab.codex_usage(run_ab.split_handbacks(run_ab.relay_handbacks(events))[0])
        self.assertEqual((usage["calls"], usage["input_tokens"], usage["cached_input_tokens"], usage["output_tokens"]), (2, 10, 4, 3))
        self.assertEqual(usage["calls_without_usage"], 1)

    def test_parse_accepts_json_array_and_stream_lines(self) -> None:
        result = {"type": "result", "total_cost_usd": 0.5}
        self.assertEqual(run_ab.parse_claude_output(json.dumps(result))[0], result)
        self.assertEqual(run_ab.parse_claude_output(json.dumps([{"type": "system"}, result]))[0], result)
        stream = "\n".join(json.dumps(e) for e in [{"type": "system"}, result])
        self.assertEqual(run_ab.parse_claude_output(stream)[0], result)
        with self.assertRaises(ValueError):
            run_ab.parse_claude_output("not json")


def text_result(text: str, parent: str | None = "toolu_main") -> dict:
    return {"type": "user", "parent_tool_use_id": parent, "message": {"content": [{"type": "tool_result", "content": [{"type": "text", "text": text}]}]}}


def tool_use(name: str, tool_input: dict, parent: str | None = None) -> dict:
    return {"type": "assistant", "parent_tool_use_id": parent, "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}}


# Shapes recorded from relay-v2 runs: runner exit 1 prefixes the JSON; a worktree refusal never starts Codex.
RAN = {"status": "done", "vendor": "codex", "session_id": "01a1", "usage": {"input_tokens": 75227, "cached_input_tokens": 59392, "output_tokens": 203}}
FILES_MISMATCH = {"status": "blocked", "vendor": "codex", "session_id": "01a2", "usage": {"input_tokens": 393636, "cached_input_tokens": 300000, "output_tokens": 900}, "files_mismatch": True, "reason": None}
NOT_WORKTREE = {"status": "blocked", "vendor": "codex", "reason": "cwd is not a linked worktree", "summary": "refused", "session_id": None, "usage": None}


class HandbackCountingTests(unittest.TestCase):
    def test_exit_code_prefix_is_stripped(self) -> None:
        """(a) f-refactor-split: `Exit code 1\\n{json}` used to fail json.loads and vanish."""
        events = [text_result("Exit code 1\n" + json.dumps(FILES_MISMATCH)), text_result(json.dumps(RAN))]
        self.assertEqual([h["session_id"] for h in run_ab.relay_handbacks(events)], ["01a2", "01a1"])

    def test_prefix_strip_ignores_other_text(self) -> None:
        self.assertEqual(run_ab.relay_handbacks([text_result("Exit code 2\nTraceback: boom"), text_result("not json")]), [])

    def test_only_vendor_runs_count_as_calls(self) -> None:
        """(b) the worktree refusal is blocked, not a call; files_mismatch ran Codex so it is a call."""
        events = [text_result(json.dumps(NOT_WORKTREE)), text_result("Exit code 1\n" + json.dumps(FILES_MISMATCH)), text_result(json.dumps(RAN))]
        ran, blocked = run_ab.split_handbacks(run_ab.relay_handbacks(events))
        usage = run_ab.codex_usage(ran)
        self.assertEqual((usage["calls"], usage["statuses"]), (2, ["blocked", "done"]))
        self.assertEqual(usage["input_tokens"], 393636 + 75227)
        self.assertEqual(blocked, [{"status": "blocked", "reason": "cwd is not a linked worktree"}])

    def test_blocked_without_reason_falls_back_to_summary(self) -> None:
        _, blocked = run_ab.split_handbacks([{"status": "failed", "vendor": "codex", "summary": "no hand-back"}])
        self.assertEqual(blocked, [{"status": "failed", "reason": "no hand-back"}])


class DispatchTests(unittest.TestCase):
    def test_main_dispatches_by_subagent_type_ignore_subagent_events(self) -> None:
        """(c) only events without parent_tool_use_id are main's."""
        events = [
            tool_use("Agent", {"subagent_type": "shoal:scout"}),
            tool_use("Agent", {"subagent_type": "shoal:applier"}),
            tool_use("Task", {"subagent_type": "shoal:applier"}),
            tool_use("Agent", {"subagent_type": "shoal:executor"}, parent="toolu_x"),
            tool_use("Edit", {"file_path": "a.py"}),
            tool_use("Edit", {"file_path": "b.py"}, parent="toolu_x"),
            tool_use("Bash", {"command": "ls"}),
        ]
        self.assertEqual(run_ab.main_activity(events), {"dispatches": {"shoal:scout": 1, "shoal:applier": 2}, "main_edits": 1})

    def test_no_dispatch_flag(self) -> None:
        def flag(**record: object) -> object:
            run_ab.flag_no_dispatch(record)
            return record.get("no_dispatch")

        self.assertTrue(flag(files_changed=3, dispatches={"shoal:scout": 1}))  # changed files, only read roles
        self.assertTrue(flag(files_changed=0, main_edits=2, dispatches={}))  # main edited itself, diff came back empty
        self.assertFalse(flag(files_changed=3, dispatches={"shoal:executor": 1}))
        self.assertFalse(flag(files_changed=3, dispatches={"security-executor": 1}))
        self.assertFalse(flag(files_changed=0, main_edits=0, dispatches={}))  # nothing changed, nothing to dispatch
        self.assertIsNone(flag(files_changed=3))  # no event data (error run)


class SummarizeTests(unittest.TestCase):
    def summarize(self, runs: list[dict]) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(json.dumps({"schema": run_ab.SCHEMA, "runs": runs}), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(run_ab.summarize(path), 0)
            return out.getvalue()

    def run_record(self, task: str, arm: str, passed: bool, dispatches: dict, **extra: object) -> dict:
        record = {"task": task, "category": "c", "arm": arm, "rep": 1, "pass": passed, "wall_s": 10.0, "total_cost_usd": 0.1,
                  "files_changed": 1, "dispatches": dispatches, **extra}
        run_ab.flag_no_dispatch(record)
        return record

    def test_subset_counts_only_pairs_where_both_arms_dispatched(self) -> None:
        """(d) t2: relay main edited directly (no_dispatch) so the pair drops out of the subset."""
        write = {"shoal:applier": 1}
        runs = [
            self.run_record("t1", "shoal", True, write),
            self.run_record("t1", "shoal-relay", True, write, codex={"calls": 1, "statuses": ["done"], "input_tokens": 5, "cached_input_tokens": 1, "output_tokens": 2, "calls_without_usage": 0},
                            relay_blocked=[{"status": "blocked", "reason": "cwd is not a linked worktree"}]),
            self.run_record("t2", "shoal", True, write),
            self.run_record("t2", "shoal-relay", False, {}, codex={"calls": 0, "statuses": [], "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "calls_without_usage": 0}, relay_blocked=[]),
        ]
        text = self.summarize(runs)
        self.assertIn("pairs where every shoal arm dispatched a write role: 1", text)
        subset = [l for l in text.splitlines() if "(both dispatched)" in l]
        self.assertEqual(len(subset), 2)
        self.assertTrue(all(l.split()[-8] == "1" for l in subset), subset)  # n column
        self.assertIn("relay calls 1", text)
        self.assertIn("blocked hand-backs 1", text)
        self.assertIn("blocked x1  blocked: cwd is not a linked worktree", text)
        self.assertIn("shoal-relay 1/2", text)  # no_dispatch count

    def test_old_results_without_dispatch_data_skip_the_subset(self) -> None:
        text = self.summarize([{"task": "t", "category": "c", "arm": "shoal", "rep": 1, "pass": True, "wall_s": 1.0, "total_cost_usd": 0.1}])
        self.assertIn("subset: n/a", text)


if __name__ == "__main__":
    unittest.main()
