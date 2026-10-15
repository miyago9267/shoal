from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "bench"))
import run_role_fitness_live as live  # noqa: E402
import verify_dispatch  # noqa: E402


class LiveHarnessTests(unittest.TestCase):
    def test_checkpoint_preserves_each_completed_repeat(self) -> None:
        verdict = verify_dispatch._verdict(
            "NATIVE_OK",
            "native_verified",
            phase="post-spawn",
            child_created="yes",
            role="scout",
            task_name="model_probe_scout",
            fork_turns="none",
            parent_ref="a" * 16,
            child_ref="b" * 16,
            model="gpt-5.6-luna",
            reasoning_effort="low",
            correlation_mode="spawn_activity",
        )
        payload = verify_dispatch.receipt_payload(
            verdict,
            codex_version="0.147.0-alpha.1.2",
            active={"config": "a" * 64, "role_manifest": "b" * 64, "policy": "c" * 64},
            target={"config": "a" * 64, "role_manifest": "b" * 64, "policy": "c" * 64},
        )
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            with patch.object(live, "run_stage", return_value=payload):
                summaries = live.run_repeats(
                    active_home=Path(directory) / "active",
                    codex_bin="codex",
                    repository_root=ROOT,
                    roles=("scout",),
                    repeats=2,
                    stages_per_role=1,
                    parent_model="gpt-5.6-luna",
                    timeout=1,
                    checkpoint_path=checkpoint,
                )
            checkpoint_data = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertEqual([item["run_id"] for item in summaries], ["R1", "R2"])
            self.assertEqual(checkpoint_data["aggregate"]["availability"], {"passed": 2, "total": 2})
            self.assertEqual(checkpoint_data["aggregate"]["stability"], {"passed": 2, "total": 2})


if __name__ == "__main__":
    unittest.main()
