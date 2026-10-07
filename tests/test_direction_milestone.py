"""M2 and M2b of docs/specs/milestone-direction-check: the milestone direction block is rendered verbatim."""
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


def m2b_block() -> str:
    part = CLAUSES.read_text(encoding="utf-8").split("## M2b")[1]
    return part.split("```text\n")[1].split("```")[0].rstrip("\n")


class MilestoneDirectionTests(unittest.TestCase):
    def test_m2_block_verbatim_and_old_text_gone(self) -> None:
        block = m2_block()
        for path in SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(block, text, path.name)
            self.assertNotIn("may send the `verifier`", text, path.name)
            self.assertNotIn("may receive the", text, path.name)

    def test_m2b_block_verbatim_with_one_stop_list(self) -> None:
        block = m2b_block()
        for path in SURFACES:
            self.assertIn(block, path.read_text(encoding="utf-8"), path.name)
        self.assertNotIn("commit, push", block)
        self.assertNotIn("commit/push", block)
        self.assertIn("material change", block)
        self.assertIn("PAUSED_VERIFICATION", block)
        core = (ROOT / "core/policy/extensions.toml").read_text(encoding="utf-8")
        self.assertIn('id = "cost-unbounded-continuation"', core)
        self.assertIn(block, core)
        legacy = ROOT / "hosts/claude/src/skills/shoal-orchestration/references/workflow-extensions.md"
        self.assertIn(block, legacy.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
