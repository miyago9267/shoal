"""tools/render_equiv.py：兩個 ref 的 render 輸出只要差一個位元組就必須非 0。"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import render_equiv  # noqa: E402

# render 與 relay overlay 需要的最小樹。
SUBSET = ("core", "prompts", "hosts", "tools", "hooks", "VERSION", "tests/fixtures/relay")


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(repo),
            *args,
        ],
        check=True,
        capture_output=True,
    )


class RenderEquivTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="equiv-test-"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        cls.repo = cls.tmp / "repo"
        for item in SUBSET:
            src, dst = ROOT / item, cls.repo / item
            if src.is_dir():
                shutil.copytree(
                    src,
                    dst,
                    ignore=shutil.ignore_patterns("__pycache__", "dist"),
                )
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        git(cls.repo, "init", "-q", "-b", "main")
        git(cls.repo, "add", "-A")
        git(cls.repo, "commit", "-q", "-m", "base")

    def branch(self, name: str, rel: str, extra: bytes) -> None:
        git(self.repo, "checkout", "-q", "-b", name, "main")
        with (self.repo / rel).open("ab") as fh:
            fh.write(extra)
        git(self.repo, "commit", "-q", "-am", name)

    def run_equiv(self, base: str, head: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = render_equiv.main(
                ["--repo", str(self.repo), "--base", base, "--head", head, "--no-check"]
            )
        return code, out.getvalue() + err.getvalue()

    def test_same_ref_is_equal(self) -> None:
        code, text = self.run_equiv("main", "main")
        self.assertEqual(code, 0, text)
        self.assertIn("render_equiv: OK", text)

    def test_one_byte_in_default_output_fails(self) -> None:
        self.branch("default-byte", "hooks/shoal_guard.py", b"#")
        code, text = self.run_equiv("main", "default-byte")
        self.assertEqual(code, 1, text)
        self.assertIn("內容不同: plugins/claude-guard/hooks/shoal_guard.py", text)

    def test_one_byte_in_relay_only_output_fails(self) -> None:
        self.branch("relay-byte", "tools/shoal_relay.py", b"#")
        code, text = self.run_equiv("main", "relay-byte")
        self.assertEqual(code, 1, text)
        self.assertIn("內容不同: relay:plugins/claude/tools/shoal_relay.py", text)
        self.assertNotIn("內容不同: plugins/", text)


if __name__ == "__main__":
    unittest.main()
