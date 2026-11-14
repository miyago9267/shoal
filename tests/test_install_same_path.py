from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "install"))

import install  # noqa: E402


class SamePathTests(unittest.TestCase):
    def test_plain_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(install._same_path(Path(tmp), Path(tmp) / "."))
            self.assertFalse(install._same_path(Path(tmp), Path(tmp) / "x"))

    @unittest.skipUnless(os.name == "nt", "Windows extended-length paths")
    def test_extended_length_prefix_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(install._same_path(Path("\\\\?\\" + tmp), Path(tmp)))
            self.assertTrue(install._same_path(Path(tmp.upper()), Path("\\\\?\\" + tmp)))


if __name__ == "__main__":
    unittest.main()
