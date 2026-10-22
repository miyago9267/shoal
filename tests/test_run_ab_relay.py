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
            tool_result({"status": "failed", "vendor": "codex", "usage": None}),
            tool_result({"status": "done", "vendor": "other", "usage": {"input_tokens": 99, "cached_input_tokens": 0, "output_tokens": 0}}),
            {"type": "user", "message": {"content": "plain"}},
            {"type": "result", "total_cost_usd": 0.1},
        ]
        usage = run_ab.codex_usage(run_ab.relay_handbacks(events))
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


if __name__ == "__main__":
    unittest.main()
