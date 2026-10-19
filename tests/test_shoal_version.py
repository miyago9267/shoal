"""install/shoal_version.py：beta 與 stable 兩個 channel，先比 channel 再比數字。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import shoal_version as sv  # noqa: E402


class ChannelTests(unittest.TestCase):
    def test_channel_of_each_form(self) -> None:
        self.assertEqual(sv.channel("3.12.0-beta"), sv.BETA)
        self.assertEqual(sv.channel("3.11.1"), sv.BETA)  # legacy，沒有後綴
        self.assertEqual(sv.channel("1.4.2"), sv.BETA)
        self.assertEqual(sv.channel("1.0.0", stable_epoch=True), sv.STABLE)
        self.assertEqual(sv.channel("1.0.0-beta", stable_epoch=True), sv.BETA)
        self.assertEqual(sv.channel("3.11.2"), sv.STABLE)  # 超過 legacy 又沒後綴
        self.assertIsNone(sv.channel("3.11"))
        self.assertIsNone(sv.channel("v3.11.1"))

    def test_parse(self) -> None:
        self.assertEqual(sv.parse("3.12.0-beta"), ((3, 12, 0), "beta"))
        self.assertEqual(sv.parse("1.0.0"), ((1, 0, 0), None))
        self.assertIsNone(sv.parse("01.0.0"))


class CompareTests(unittest.TestCase):
    def test_legacy_lt_beta_lt_stable(self) -> None:
        self.assertEqual(sv.compare("3.11.1", "3.12.0-beta"), -1)
        self.assertEqual(sv.compare("3.12.0-beta", "1.0.0", b_stable=True), -1)
        self.assertEqual(sv.compare("3.11.1", "1.0.0", b_stable=True), -1)
        self.assertEqual(sv.compare("3.0.0", "3.11.1"), -1)
        ordered = sorted(
            [
                ("1.0.0", True),
                ("3.0.0", False),
                ("3.12.0-beta", False),
                ("3.11.1", False),
            ],
            key=lambda v: sv.key(v[0], stable_epoch=v[1]),
        )
        self.assertEqual(
            [v for v, _ in ordered], ["3.0.0", "3.11.1", "3.12.0-beta", "1.0.0"]
        )

    def test_beta_lt_stable_regardless_of_numbers(self) -> None:
        for beta in ("99.0.0-beta", "3.11.1", "9.9.9-beta", "1.0.1-beta"):
            self.assertEqual(sv.compare(beta, "1.0.0", b_stable=True), -1, beta)
            self.assertEqual(sv.compare("1.0.0", beta, a_stable=True), 1, beta)

    def test_same_channel_compares_numbers(self) -> None:
        self.assertEqual(sv.compare("3.12.0-beta", "3.13.0-beta"), -1)
        self.assertEqual(sv.compare("1.0.1", "1.0.0", a_stable=True, b_stable=True), 1)
        self.assertEqual(sv.compare("3.12.0-beta", "3.12.0-beta"), 0)

    def test_malformed_raises(self) -> None:
        with self.assertRaises(ValueError):
            sv.compare("3.12", "1.0.0")

    def test_channel_switch(self) -> None:
        self.assertTrue(
            sv.is_channel_switch("3.12.0-beta", "1.0.0", source_stable=True)
        )
        self.assertTrue(sv.is_channel_switch("3.11.1", "1.0.0", source_stable=True))
        self.assertFalse(sv.is_channel_switch("3.11.1", "3.12.0-beta"))
        self.assertFalse(sv.is_channel_switch("3.12.0-beta", "1.0.0"))


class FormatTests(unittest.TestCase):
    def test_validators_accept_beta_suffix(self) -> None:
        sys.path.insert(0, str(ROOT / "tools"))
        import render

        for version in ("3.12.0-beta", "1.0.0"):
            self.assertRegex(version, render.PRODUCT_VERSION)
            self.assertRegex(version, render.HOST_VERSION)
            self.assertRegex(f"<!-- shoal-claude v{version} -->", sv.VERSION_PATTERN)
        self.assertNotRegex("3.12.0-rc", render.PRODUCT_VERSION)


class MarkerTests(unittest.TestCase):
    def test_channel_file_decides_stable_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(sv.repo_is_stable(Path(tmp)))
            (Path(tmp) / "CHANNEL").write_text("stable\n")
            self.assertTrue(sv.repo_is_stable(Path(tmp)))
            (Path(tmp) / "CHANNEL").write_text("beta\n")
            self.assertFalse(sv.repo_is_stable(Path(tmp)))

    def test_repo_is_beta_today(self) -> None:
        self.assertFalse(sv.repo_is_stable(ROOT))


if __name__ == "__main__":
    unittest.main()
