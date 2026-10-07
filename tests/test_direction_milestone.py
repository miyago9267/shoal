"""M2 of docs/specs/milestone-direction-check: the milestone direction block is rendered verbatim."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUSES = ROOT / "docs" / "specs" / "milestone-direction-check" / "CLAUSES.md"
SURFACES = (
    ROOT / "hosts/claude/dist/skills/shoal-orchestration/references/workflow-extensions.md",
    ROOT / "claude-plugin/skills/shoal-orchestration/references/workflow-extensions.md",
    ROOT / "templates/agents-md.orchestration.md",
    ROOT / "plugin/plugins/shoal-codex/skills/shoal-orchestration/references/orchestration-policy.md",
)


def m2_block() -> str:
    return CLAUSES.read_text(encoding="utf-8").split("```text\n")[1].split("```")[0].rstrip("\n")


class MilestoneDirectionTests(unittest.TestCase):
    def test_m2_block_verbatim_and_old_text_gone(self) -> None:
        block = m2_block()
        for path in SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(block, text, path.name)
            self.assertNotIn("may send the `verifier`", text, path.name)
            self.assertNotIn("may receive the", text, path.name)


if __name__ == "__main__":
    unittest.main()
