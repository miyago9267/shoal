"""python-tests.yml 的靜態檢查與 lock 步驟的行為檢查（AC-CE-006、AC-CE-007）。"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "python-tests.yml").read_text(encoding="utf-8")


def trigger_block(name: str) -> str:
    match = re.search(rf"(?ms)^  {name}:\n(.*?)(?=^  \S|^\S)", WORKFLOW)
    assert match, name
    return match.group(1)


def lock_step_script() -> str:
    match = re.search(
        r"(?m)^      - name: Enforce prompt document lock\n(?:        [^\n]*\n)*?        run: \|\n((?:          [^\n]*\n|\n)+)",
        WORKFLOW,
    )
    assert match, "找不到 Enforce prompt document lock 的 run 區塊"
    return textwrap.dedent(match.group(1))


class WorkflowStaticTests(unittest.TestCase):
    def test_paths_cover_claude_host_for_pr_and_push(self) -> None:  # AC-CE-006
        for trigger in ("pull_request", "push"):
            self.assertIn('- "hosts/claude/**"', trigger_block(trigger), trigger)

    def test_pull_request_reacts_to_label_changes(self) -> None:  # AC-CE-007
        block = trigger_block("pull_request")
        self.assertRegex(block, r"types:\s*\[[^\]]*\blabeled\b[^\]]*\]")
        self.assertRegex(block, r"types:\s*\[[^\]]*\bunlabeled\b[^\]]*\]")

    def test_renewal_switches_are_present(self) -> None:  # AC-CE-007
        script = lock_step_script()
        self.assertIn("lock-renewal", WORKFLOW)
        self.assertIn("Lock-Renewal: approved", script)
        self.assertIn("--allow-lock-update", script)

    def test_commit_message_only_travels_through_env(self) -> None:  # AC-CE-007
        # run 區塊不得出現任何 ${{ }}：commit message 與 label 都經環境變數傳入
        self.assertNotIn("${{", lock_step_script())
        self.assertRegex(WORKFLOW, r"HEAD_COMMIT_MESSAGE: \$\{\{ github\.event\.head_commit\.message \}\}")


@unittest.skipUnless(shutil.which("bash") and sys.platform != "win32", "需要 POSIX bash")
class LockStepBehaviorTests(unittest.TestCase):
    """把 workflow 的 run 區塊原樣執行，python 換成只印參數的 stub。"""

    def run_step(self, **env: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "python"
            stub.write_text('#!/bin/sh\necho "ARGS: $*"\n', encoding="utf-8", newline="\n")
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
            result = subprocess.run(
                ["bash", "-c", lock_step_script()],
                capture_output=True, text=True, encoding="utf-8",
                env={"PATH": f"{tmp}{os.pathsep}{os.environ['PATH']}", "PROMPT_LOCK_BASE": "BASE",
                     "PR_HAS_RENEWAL_LABEL": "false", "HEAD_COMMIT_MESSAGE": "", **env},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_without_label_or_trailer_flag_is_absent(self) -> None:
        self.assertEqual(self.run_step(EVENT_NAME="pull_request"), "ARGS: install/validate_prompt_lock.py --base-ref BASE")
        self.assertEqual(
            self.run_step(EVENT_NAME="push", HEAD_COMMIT_MESSAGE="chore: x\n\nbody"),
            "ARGS: install/validate_prompt_lock.py --base-ref BASE",
        )

    def test_label_enables_flag_on_pull_request_only(self) -> None:
        expected = "ARGS: install/validate_prompt_lock.py --base-ref BASE --allow-lock-update"
        self.assertEqual(self.run_step(EVENT_NAME="pull_request", PR_HAS_RENEWAL_LABEL="true"), expected)
        self.assertNotIn("--allow-lock-update", self.run_step(EVENT_NAME="push", PR_HAS_RENEWAL_LABEL="true"))

    def test_trailer_must_be_its_own_line_on_push(self) -> None:
        expected = "ARGS: install/validate_prompt_lock.py --base-ref BASE --allow-lock-update"
        self.assertEqual(
            self.run_step(EVENT_NAME="push", HEAD_COMMIT_MESSAGE="feat: lock\n\nLock-Renewal: approved\n"), expected)
        self.assertEqual(
            self.run_step(EVENT_NAME="push", HEAD_COMMIT_MESSAGE="feat: lock\r\n\r\nLock-Renewal: approved\r\n"), expected)
        for message in ("Lock-Renewal: approved extra", "see Lock-Renewal: approved", "lock-renewal: approved"):
            self.assertNotIn("--allow-lock-update", self.run_step(EVENT_NAME="push", HEAD_COMMIT_MESSAGE=message), message)
        self.assertNotIn(
            "--allow-lock-update",
            self.run_step(EVENT_NAME="pull_request", HEAD_COMMIT_MESSAGE="Lock-Renewal: approved"),
        )

    def test_message_with_shell_metacharacters_is_not_executed(self) -> None:
        out = self.run_step(EVENT_NAME="push", HEAD_COMMIT_MESSAGE='x"; echo INJECTED; "$(echo INJECTED)`echo INJECTED`')
        self.assertNotIn("INJECTED", out)


if __name__ == "__main__":
    unittest.main()
