"""tools/scan_legacy_names.py 的測試（docs/specs/shoal-rebrand RENAME「掃描範圍」）。

合成的舊名用 LEGACY_WORD 組出來，這個檔案本身不含舊名字串。
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import scan_legacy_names as scan  # noqa: E402

LEGACY_WORD = "pilot" + "fish"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class ScanFileTests(unittest.TestCase):
    def hits(self, path: str, text: str) -> list[int]:
        return [number for number, _ in scan.scan_file(path, text)]

    def test_plain_hit_is_case_insensitive(self) -> None:
        text = f"clean\nuses {LEGACY_WORD.capitalize()} here\nand {LEGACY_WORD.upper()}_X\n"
        self.assertEqual(self.hits("docs/guide.md", text), [2, 3])

    def test_upstream_names_and_history_paths_are_not_hits(self) -> None:
        text = (
            f"[Nanako0129/{LEGACY_WORD}](https://github.com/Nanako0129/{LEGACY_WORD}) and "
            f"Nanako0129/{LEGACY_WORD}-grok and miyago9267/{LEGACY_WORD}-codex\n"
            f"see docs/specs/hybrid-{LEGACY_WORD}-runtime/SPEC.md\n"
        )
        self.assertEqual(self.hits("README.md", text), [])
        self.assertEqual(
            self.hits("README.md", text + f"but {LEGACY_WORD} alone is\n"), [3]
        )

    def test_python_legacy_assignments_are_exempt_even_across_lines(self) -> None:
        text = (
            f'LEGACY_ONE = "{LEGACY_WORD}-one"\n'
            "LEGACY_MANY = (\n"
            f'    "{LEGACY_WORD}-a",\n'
            "    ('[', ')'),\n"
            f'    "{LEGACY_WORD}-b",\n'
            ")\n"
            f'plain = "{LEGACY_WORD}"\n'
            f'value = LEGACY_ONE + "{LEGACY_WORD}"\n'
        )
        self.assertEqual(
            self.hits("tools/x.py", text), [7]
        )  # 含 LEGACY_ 的第 8 行本身也豁免

    def test_other_languages_exempt_the_legacy_line_and_its_bracketed_block(
        self,
    ) -> None:
        text = (
            f'const LEGACY_NAMES = [\n  "{LEGACY_WORD}",\n  "x",\n];\n'
            f'const other = "{LEGACY_WORD}";\n'
            f'LEGACY_PLUGIN="{LEGACY_WORD}-opencode.js"\n'
        )
        self.assertEqual(self.hits("hosts/x.ts", text), [5])

    def test_changelog_scans_only_v2_and_newer_sections(self) -> None:
        text = (
            f"# Changelog\nintro mentions {LEGACY_WORD}\n\n## v2.0.0\nnew section {LEGACY_WORD}\n\n"
            f"## v1.5.0\nold section {LEGACY_WORD}\n\n## v1.0.0\nolder {LEGACY_WORD}\n"
        )
        self.assertEqual(self.hits("CHANGELOG.md", text), [2, 5])
        self.assertEqual(self.hits("hosts/codex/CHANGELOG.md", text), [2, 5])
        self.assertEqual(self.hits("docs/CHANGELOG.md", text), [2, 5, 8, 11])

    def test_readme_credit_section_is_skipped(self) -> None:
        text = f"# shoal\nbody {LEGACY_WORD}\n\n## 來源與致謝\n\ncredit {LEGACY_WORD}\n\n## 已知限制\n\nafter {LEGACY_WORD}\n"
        self.assertEqual(self.hits("README.md", text), [2, 10])
        self.assertEqual(self.hits("docs/other.md", text), [2, 6, 10])


class ScanRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.repo = Path(self.dir.name)
        git(self.repo, "init", "-q")

    def put(self, rel: str, text: str = "clean\n") -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_exempt_paths_and_hits(self) -> None:
        dirty = f"mentions {LEGACY_WORD}\n"
        for rel in (
            "docs/specs/old/SPEC.md",
            "docs/benchmarks/x.json",
            "docs/plans/p.md",
            "tests/golden/claude/x.md",
            "tests/fixtures/legacy_install/codex/state.json",
            "LICENSE",
            "upstream.lock",
            "install/evaluate_" + LEGACY_WORD + "_value_matrix.py",
            "tests/fixtures/grok/rules." + LEGACY_WORD + "-grok.upstream-v1.0.6.txt",
        ):
            self.put(rel, dirty)
        self.put("src/ok.py", "x = 1\n")
        self.put("src/bad.py", f"x = '{LEGACY_WORD}'\n")
        self.put(f"src/{LEGACY_WORD}-name.txt", "clean\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = scan.main(["--root", str(self.repo)])
        hits = out.getvalue().splitlines()
        self.assertEqual(code, 1)
        self.assertEqual(
            sorted(hits[:-1]),
            sorted(
                [
                    f"src/bad.py:1: x = '{LEGACY_WORD}'",
                    f"src/{LEGACY_WORD}-name.txt: file name contains a legacy name",
                ]
            ),
        )
        self.assertEqual(hits[-1], "legacy name scan: 2 hit(s)")

    def test_clean_repo_exits_zero(self) -> None:
        self.put("a.md", "hello\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(scan.main(["--root", str(self.repo)]), 0)
        self.assertEqual(out.getvalue().strip(), "legacy name scan: 0 hit(s)")

    def test_the_real_repository_is_clean(self) -> None:
        self.assertEqual(scan.scan(ROOT), [])


if __name__ == "__main__":
    unittest.main()
