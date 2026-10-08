"""Hook scripts run under whatever `python3` the host finds (macOS /usr/bin/python3 is 3.9).

This check does not need a 3.9 interpreter: ast.parse with feature_version rejects newer syntax
(match, parenthesised context managers, ...), and the future import keeps `X | None` annotations
from being evaluated at runtime on 3.9.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OLDEST = (3, 9)
SCRIPTS = sorted(
    [
        *(REPO / "hooks").glob("*.py"),
        *(REPO / "hosts" / "grok" / "src" / "hooks" / "shoal-grok").glob("*.py"),
    ]
)


class HookScriptsRunOnOldestPython(unittest.TestCase):
    def test_scripts_found(self) -> None:
        names = {p.name for p in SCRIPTS}
        self.assertLessEqual(
            {"shoal_guard.py", "shoal_autoroute_gate.py", "plan_mode_guard.py", "subagent_stop_gate.py"},
            names,
        )

    def test_syntax_is_valid_for_the_oldest_supported_python(self) -> None:
        for path in SCRIPTS:
            with self.subTest(path=path.name):
                ast.parse(path.read_text(encoding="utf-8"), str(path), feature_version=OLDEST)

    def test_annotations_are_not_evaluated_at_runtime(self) -> None:
        for path in SCRIPTS:
            with self.subTest(path=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
                futures = {
                    alias.name
                    for node in tree.body
                    if isinstance(node, ast.ImportFrom) and node.module == "__future__"
                    for alias in node.names
                }
                self.assertIn("annotations", futures)


if __name__ == "__main__":
    unittest.main()
