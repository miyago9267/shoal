"""M2 and M2b of docs/specs/milestone-direction-check: the milestone direction block is rendered verbatim."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUSES = ROOT / "docs" / "specs" / "milestone-direction-check" / "CLAUSES.md"
SURFACES = (
    ROOT / "hosts/claude/dist/skills/shoal-orchestration/references/workflow-extensions.md",
    ROOT / "plugins/claude/skills/shoal-orchestration/references/workflow-extensions.md",
    ROOT / "templates/agents-md.extensions.md",
)


# shared-rules B5: the core clause (rendered on Claude and Codex surfaces) adds this sentence after "review intent.".
# Codex carries it in the on-demand extensions document (templates/agents-md.extensions.md), not the always-on policy.
WRAPUP = (
    "At the wrap-up of multi-slice work, main also sends its draft final report to that checkpoint and "
    "corrects the report before sending it to the user."
)
CORE_SURFACES = SURFACES


def squash(text: str) -> str:
    return " ".join(text.split())


def m2_block() -> str:
    return CLAUSES.read_text(encoding="utf-8").split("```text\n")[1].split("```")[0].rstrip("\n")


def m2b_block() -> str:
    part = CLAUSES.read_text(encoding="utf-8").split("## M2b")[1]
    return part.split("```text\n")[1].split("```")[0].rstrip("\n")


class MilestoneDirectionTests(unittest.TestCase):
    def test_m2_block_verbatim_and_old_text_gone(self) -> None:
        block = m2_block()
        with_wrapup = squash(block).replace("review intent. Before closing", "review intent. " + WRAPUP + " Before closing")
        self.assertNotEqual(with_wrapup, squash(block))
        for path in SURFACES:
            text = path.read_text(encoding="utf-8")
            self.assertIn(with_wrapup, squash(text), path.name)
            self.assertNotIn("may send the `verifier`", text, path.name)
            self.assertNotIn("may receive the", text, path.name)

    def test_m2b_block_verbatim_with_one_stop_list(self) -> None:
        block = m2b_block()
        for path in SURFACES:
            self.assertIn(squash(block), squash(path.read_text(encoding="utf-8")), path.name)
        self.assertNotIn("commit, push", block)
        self.assertNotIn("commit/push", block)
        self.assertIn("material change", block)
        self.assertIn("PAUSED_VERIFICATION", block)
        core = (ROOT / "core/policy/extensions.toml").read_text(encoding="utf-8")
        self.assertIn('id = "cost-unbounded-continuation"', core)
        self.assertIn(block, core)
        dist = ROOT / "hosts/claude/dist/skills/shoal-orchestration/references/workflow-extensions.md"
        self.assertIn(block, dist.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
