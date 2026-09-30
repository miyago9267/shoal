from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import check_links  # noqa: E402


class LinkCheckTests(unittest.TestCase):
    def test_release_documents_have_no_broken_relative_links(self) -> None:
        self.assertEqual(check_links.check(ROOT, list(check_links.DEFAULT_FILES)), [])

    def test_reports_missing_target_and_ignores_anchor_external_and_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "exists.md").write_text("x", encoding="utf-8")
            (root / "a.md").write_text(
                "[ok](./exists.md#top) [web](https://example.com/x) [self](#h)\n"
                "[bad](./nope.md#h) <img src=\"./gone.svg\">\n"
                "```\n[in code](./ignored.md)\n```\n",
                encoding="utf-8",
            )
            missing = check_links.check(root, ["a.md"])
            self.assertEqual(missing, ["a.md:2: ./nope.md", "a.md:2: ./gone.svg"])

    def test_missing_source_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                check_links.check(Path(directory), ["absent.md"]), ["absent.md: 檔案不存在"]
            )


if __name__ == "__main__":
    unittest.main()
