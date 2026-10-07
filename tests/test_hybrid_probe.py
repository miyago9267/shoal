import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import probe_hybrid_runtime as probe  # noqa: E402


class HybridProbeTests(unittest.TestCase):
    def test_report_separates_bootstrap_and_plugin_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "codex"
            home.mkdir()
            (home / "AGENTS.md").write_text(
                "<!-- shoal-codex:begin -->\n<!-- shoal-codex:end -->\n"
            )
            with mock.patch.object(probe, "_plugin_is_installed", return_value=True):
                with mock.patch.object(
                    probe, "_session_probe", return_value=("verified", "verified", 0)
                ):
                    report = probe.build_report(
                        codex_home=home, project=home, run_session=True
                    )
            self.assertEqual(report["bootstrap"], "active")
            self.assertEqual(report["plugin"], "installed")
            self.assertEqual(report["skill"], "available")
            self.assertEqual(report["shoal_behavior"], "verified")
            self.assertEqual(report["persona_recap"], "verified")

    def test_report_does_not_infer_skill_from_bootstrap_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "codex"
            home.mkdir()
            (home / "AGENTS.md").write_text(
                "<!-- shoal-codex:begin -->\n<!-- shoal-codex:end -->\n"
            )
            with mock.patch.object(probe, "_plugin_is_installed", return_value=False):
                report = probe.build_report(
                    codex_home=home, project=home, run_session=False
                )
            self.assertEqual(report["bootstrap"], "active")
            self.assertEqual(report["plugin"], "unavailable")
            self.assertEqual(report["skill"], "unavailable")
            self.assertEqual(report["shoal_behavior"], "unverified")


if __name__ == "__main__":
    unittest.main()
