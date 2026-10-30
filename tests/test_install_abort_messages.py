"""P0 characterization (docs/specs/code-restructure T0.4): the exact InstallAbort messages of install/install.py.

The inventory test freezes every message template (P4 must not add, drop or reword one); the behaviour tests
reproduce a representative set of aborts through the real functions and compare the full text.
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import install as installer  # noqa: E402

INVENTORY = ROOT / "tests" / "fixtures" / "install_abort_messages.json"


def _literal(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else ""
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    if isinstance(node, ast.BinOp):
        return _literal(node.left) + _literal(node.right)
    return ""


class AbortInventoryTests(unittest.TestCase):
    def test_message_templates_equal_the_frozen_inventory(self) -> None:
        tree = ast.parse((ROOT / "install" / "install.py").read_text(encoding="utf-8"))
        found = {
            _literal(n.args[0])
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "InstallAbort" and n.args
        }
        frozen = json.loads(INVENTORY.read_text(encoding="utf-8"))["messages"]
        self.assertEqual(sorted(found), frozen)
        self.assertGreaterEqual(len(frozen), 130)


class AbortMessageTests(unittest.TestCase):
    def assertAborts(self, message: str, fn, *args, **kwargs) -> None:
        with self.assertRaises(installer.InstallAbort) as ctx:
            fn(*args, **kwargs)
        self.assertEqual(str(ctx.exception), message)

    def test_merge_config_text(self) -> None:
        merge = installer.merge_config_text
        self.assertAborts("features must be a TOML table", merge, "features = 1\n")
        self.assertAborts("agents must be a TOML table", merge, "agents = 1\n")
        self.assertAborts("agents table has unsupported or unowned keys", merge, "[agents]\nfoo = 1\n")
        self.assertAborts("legacy features.multi_agent_v2 must be an exact table", merge,
                          "[features]\nmulti_agent_v2 = true\n")
        self.assertAborts("features.multi_agent_v2 uses inline or dotted TOML syntax that cannot be safely rewritten",
                          merge, "[features]\nmulti_agent_v2 = { enabled = true }\n")
        self.assertAborts("legacy V2 table has extra or unowned entries", merge,
                          "[features.multi_agent_v2]\nfoo = 1\n")
        self.assertAborts("legacy features.multi_agent_v2 is explicitly disabled", merge,
                          "[features.multi_agent_v2]\nenabled = false\nmax_concurrent_threads_per_session = 4\n")
        self.assertAborts("legacy V2 concurrency must be exactly 4", merge,
                          "[features.multi_agent_v2]\nenabled = true\nmax_concurrent_threads_per_session = 5\n")
        self.assertAborts("legacy V2 migration requires committed installer provenance", merge,
                          "[features.multi_agent_v2]\nenabled = true\nmax_concurrent_threads_per_session = 4\n")
        self.assertAborts("legacy_key_unowned: features.multi_agent", merge, "[features]\nmulti_agent = true\n")
        self.assertAborts(
            "legacy root max_concurrent_threads_per_session conflicts with native child concurrency 3",
            merge, "max_concurrent_threads_per_session = 9\n")
        self.assertAborts(
            "agents.max_concurrent_threads_per_session conflicts with native child concurrency 3",
            merge, "[agents]\nmax_concurrent_threads_per_session = 9\n")
        with self.assertRaises(installer.InstallAbort) as ctx:
            merge("not = [valid\n")
        self.assertTrue(str(ctx.exception).startswith("existing config.toml is invalid TOML: "))

    def test_merge_instruction_text(self) -> None:
        begin, end = installer.MARKER_BEGIN, installer.MARKER_END
        message = "instruction file has unmatched or multiple shoal-codex marker pairs"
        self.assertAborts(message, installer.merge_instruction_text, begin + "\n", "b")
        self.assertAborts(message, installer.merge_instruction_text, begin + end + begin + end, "b")

    def test_validate_committed_state_first_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home, policy = Path(tmp), Path(tmp) / "AGENTS.md"
            check = lambda state: installer._validate_committed_state(state, home=home, policy_path=policy, config_snapshot=None)
            for state in ({}, {"status": "pending"}, [], None):
                self.assertAborts("install state is not a committed transaction", check, state)
            for version in (None, 2, "3", True, 5):
                state = {"status": "committed"}
                if version is not None:
                    state["state_version"] = version
                self.assertAborts("install state predates shoal 3.0.0 or is malformed; reinstall", check, state)

    def test_agents_root_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            real = home / "real"
            real.mkdir()
            link = home / "agents"
            link.symlink_to(real)
            self.assertAborts("agents root must not be a symlink", installer._assert_agents_root, link, home)
            outside = Path(tmp) / "outside"
            outside.mkdir()
            self.assertAborts("agents root escapes Codex home", installer._assert_agents_root, outside, home)
            afile = home / "afile"
            afile.write_text("x", encoding="utf-8")
            self.assertAborts("agents path is not a directory", installer._assert_agents_root, afile, home)

    def test_policy_identity_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target = tmp_path / "real.md"
            target.write_text("x", encoding="utf-8")
            link = tmp_path / "AGENTS.md"
            link.symlink_to(target)
            capture = installer._capture_policy_identity
            self.assertAborts("active policy path is a symlink; explicit policy integration is required",
                              capture, link, follow_policy_symlink=False, policy_root=None)
            self.assertAborts("policy-root is required when following an active policy symlink",
                              capture, link, follow_policy_symlink=True, policy_root=None)
            self.assertAborts("configured policy root is unavailable",
                              capture, link, follow_policy_symlink=True, policy_root=tmp_path / "missing")
            self.assertAborts("configured policy root is not a directory",
                              capture, link, follow_policy_symlink=True, policy_root=target)


if __name__ == "__main__":
    unittest.main()
