"""shoal_install.py --doctor（T1.5、S1.12）：假 vendor binary，不呼叫真的 codex。"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import shoal_install  # noqa: E402

FAKE = """#!/bin/sh
here="$(dirname "$0")"
env > "$here/seen-env"
case "$1" in
  --version) echo "codex-cli $(cat "$here/version")" ;;
  login) cat "$here/login-out"; exit "$(cat "$here/login-rc")" ;;
esac
"""
SECRET = "sk-live-AbCdEf0123456789"


@unittest.skipIf(sys.platform == "win32", "fake vendor binary is a sh script")
class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="relay-doctor-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        (self.home / ".codex").mkdir(parents=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "codex").write_text(FAKE, encoding="utf-8")
        (self.bin / "codex").chmod(0o755)
        self.set_fake("0.160.1", "Logged in using ChatGPT\n")
        self.vendors = self.tmp / "vendors.toml"
        self.write_vendors(f'paths = ["{self.bin / "codex"}"]')
        self.env = {
            "HOME": str(self.home),
            "PATH": os.environ["PATH"],
            "OPENAI_API_KEY": "",
            "CODEX_HOME": str(self.home / ".codex"),
        }

    def set_fake(self, version: str, login: str, rc: int = 0) -> None:
        (self.bin / "version").write_text(version, encoding="utf-8")
        (self.bin / "login-out").write_text(login, encoding="utf-8")
        (self.bin / "login-rc").write_text(str(rc), encoding="utf-8")

    def write_vendors(self, paths_line: str) -> None:
        self.vendors.write_text(
            "[vendors.codex]\n"
            'min_version = "0.160.1"\n'
            'binary = "codex"\n'
            f"{paths_line}\n"
            "search_path = false\n"
            'version_args = ["--version"]\n'
            'login_args = ["login", "status"]\n'
            'env = ["PATH", "HOME", "CODEX_HOME"]\n',
            encoding="utf-8",
        )

    def doctor(self) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = shoal_install.do_doctor(self.env, self.vendors)
        return rc, out.getvalue(), err.getvalue()

    def test_reports_path_version_and_login(self) -> None:
        rc, out, _ = self.doctor()
        self.assertEqual(rc, 0, out)
        self.assertIn(f"binary: {os.path.realpath(self.bin / 'codex')}", out)
        self.assertIn("version: 0.160.1 (min 0.160.1) ok", out)
        self.assertIn("login: ChatGPT subscription", out)

    def test_version_below_minimum_fails(self) -> None:
        self.set_fake("0.159.9", "Logged in using ChatGPT\n")
        rc, out, _ = self.doctor()
        self.assertEqual(rc, 1)
        self.assertIn("0.159.9 (min 0.160.1) TOO OLD", out)

    def test_newer_version_passes(self) -> None:
        self.set_fake("0.162.1", "Logged in using ChatGPT\n")
        self.assertEqual(self.doctor()[0], 0)

    def test_missing_binary_fails(self) -> None:
        self.write_vendors(f'paths = ["{self.tmp / "nowhere" / "codex"}"]')
        rc, out, _ = self.doctor()
        self.assertEqual(rc, 1)
        self.assertIn("binary: MISSING", out)

    def test_not_logged_in_fails(self) -> None:
        self.set_fake("0.160.1", "Not logged in\n", rc=1)
        rc, out, _ = self.doctor()
        self.assertEqual(rc, 1)
        self.assertIn("login: not logged in", out)

    def test_raw_login_output_is_never_echoed(self) -> None:
        self.set_fake("0.160.1", f"Logged in using an API key - {SECRET}\n")
        rc, out, err = self.doctor()
        self.assertEqual(rc, 0)
        self.assertIn("login: API key (billed per use)", out)
        self.assertNotIn(SECRET, out + err)
        self.assertNotIn("Logged in using", out)

    def test_api_key_variables_are_reported_by_name_only(self) -> None:
        self.env.update(
            {
                "OPENAI_API_KEY": SECRET,
                "CODEX_API_KEY": SECRET,
                "ANTHROPIC_API_KEY": SECRET,
            }
        )
        _, out, err = self.doctor()
        for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "ANTHROPIC_API_KEY"):
            self.assertIn(f"warn: {name} is set", out)
        self.assertNotIn(SECRET, out + err)

    def test_no_warning_without_api_keys(self) -> None:
        self.assertNotIn("warn:", self.doctor()[1])

    def test_vendor_child_env_has_no_api_keys(self) -> None:
        self.env.update(
            {
                "OPENAI_API_KEY": SECRET,
                "CODEX_API_KEY": SECRET,
                "ANTHROPIC_API_KEY": SECRET,
            }
        )
        self.doctor()
        seen = (self.bin / "seen-env").read_text(encoding="utf-8")
        self.assertNotIn("API_KEY", seen)
        self.assertNotIn(SECRET, seen)

    def test_lists_trust_entries_that_point_at_worktrees_without_editing(self) -> None:
        linked = self.tmp / "wt"
        linked.mkdir()
        (linked / ".git").write_text(
            "gitdir: /main/.git/worktrees/wt\n", encoding="utf-8"
        )
        submodule = self.tmp / "sub"
        submodule.mkdir()
        (submodule / ".git").write_text(
            "gitdir: /main/.git/modules/sub\n", encoding="utf-8"
        )
        plain = self.tmp / "plain"
        (plain / ".git").mkdir(parents=True)
        claude_wt = self.tmp / "repo" / ".claude" / "worktrees" / "agent-1"
        config = self.home / ".codex" / "config.toml"
        config.write_text(
            'model = "x"\n'
            + "".join(
                f'\n[projects."{p}"]\ntrust_level = "trusted"\n'
                for p in (linked, submodule, plain, claude_wt)
            ),
            encoding="utf-8",
        )
        before = config.read_bytes()
        rc, out, _ = self.doctor()
        self.assertEqual(rc, 0)
        self.assertIn(f"{linked} (trusted)", out)
        self.assertIn(f"{claude_wt} (trusted)", out)
        self.assertNotIn(str(submodule), out)
        self.assertNotIn(str(plain), out)
        self.assertEqual(config.read_bytes(), before)

    def test_missing_or_broken_config_lists_nothing(self) -> None:
        self.assertNotIn("trust entries", self.doctor()[1])
        (self.home / ".codex" / "config.toml").write_text(
            "not [valid toml", encoding="utf-8"
        )
        self.assertNotIn("trust entries", self.doctor()[1])

    def test_default_vendors_file_is_the_repo_one(self) -> None:
        self.assertEqual(shoal_install.VENDORS_FILE, ROOT / "core" / "vendors.toml")


class LoginMethodTests(unittest.TestCase):
    def test_classification(self) -> None:
        cases = [
            (0, "Logged in using ChatGPT", "ChatGPT subscription"),
            (0, "Logged in using an API key - sk-abc***", "API key (billed per use)"),
            (1, "Not logged in", "not logged in"),
            (0, "Not logged in", "not logged in"),
            (1, "Logged in using ChatGPT", "not logged in"),
            (0, "something new", "unknown"),
        ]
        for rc, text, expected in cases:
            self.assertEqual(shoal_install.login_method(rc, text), expected, text)


class CliTests(unittest.TestCase):
    def test_doctor_dispatches_and_exits_with_its_code(self) -> None:
        with mock.patch.object(shoal_install, "do_doctor", return_value=1) as doctor:
            self.assertEqual(
                shoal_install.main(["--doctor"], env={"HOME": "/nonexistent"}), 1
            )
        doctor.assert_called_once()

    def test_doctor_cannot_be_combined(self) -> None:
        for extra in (["--host", "claude"], ["--list"], ["--update"], ["--apply"]):
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as caught,
            ):
                shoal_install.main(["--doctor", *extra], env={})
            self.assertEqual(caught.exception.code, 2, extra)


if __name__ == "__main__":
    unittest.main()
