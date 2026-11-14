"""M2b of docs/specs/milestone-direction-check: the unbounded-continuation clause exists in core and its stop token is rendered.

The clause text itself is guarded by prompts/ as the single source, `render --check` and the prompt lock;
this test only keeps the structure (clause id, stop token on every rendered surface).
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SURFACES = (
    ROOT / "plugins/claude/skills/shoal-orchestration/references/workflow-extensions.md",
    ROOT / "templates/agents-md.extensions.md",
)


class MilestoneDirectionTests(unittest.TestCase):
    def test_unbounded_continuation_clause_and_stop_token_are_rendered(self) -> None:
        core = (ROOT / "prompts/policy/extensions.md").read_text(encoding="utf-8")
        self.assertIn("<!-- clause: cost-unbounded-continuation ", core)
        for path in SURFACES:
            self.assertIn("PAUSED_VERIFICATION", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
