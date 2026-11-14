"""local-role-model-overlay P1：本機覆寫檔替指定 role 換模型（S1.1–S1.7）。

沿用 test_shoal_update 的假 claude 與 temp 目錄；覆寫檔寫在 temp 的 XDG_CONFIG_HOME。
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from test_shoal_update import ROOT, UpdateBase

AGENTS = "plugins/claude/agents"


class OverlayTests(UpdateBase):
    def setUp(self) -> None:
        super().setUp()
        self.env["XDG_CONFIG_HOME"] = str(self.tmp / "config")
        self.overlay = Path(self.env["XDG_CONFIG_HOME"]) / "shoal" / "claude.local.toml"

    def write_overlay(self, text: str) -> None:
        self.overlay.parent.mkdir(parents=True, exist_ok=True)
        self.overlay.write_text(text)

    def head(self, rel: str) -> bytes:
        return subprocess.check_output(["git", "-C", str(ROOT), "show", f"HEAD:{rel}"])

    def assert_rejected(self, text: str) -> None:
        self.write_overlay(text)
        code, out, err = self.update("--apply")
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("failed", out)
        self.assertFalse(self.mp.exists(), "被拒絕的覆寫不可 swap marketplace")

    def test_overlay_rewrites_only_the_model_line(self) -> None:
        self.write_overlay('[roles.security-reviewer]\nmodel = "claude-mythos-5-2"\n')
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        rel = f"{AGENTS}/security-reviewer.md"
        want = self.head(rel).decode().replace("\nmodel: opus\n", "\nmodel: claude-mythos-5-2\n", 1)
        self.assertEqual((self.mp / rel).read_text(), want)
        listing = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", "HEAD", "--", ".claude-plugin", "plugins"],
            text=True,
        ).split()
        for other in listing:
            if other != rel and (self.mp / other).exists():
                self.assertEqual((self.mp / other).read_bytes(), self.head(other), other)

    def test_overlay_is_reported_and_verify_stays_up_to_date(self) -> None:
        self.write_overlay('[roles.security-reviewer]\nmodel = "claude-mythos-5-2"\n')
        self.update("--apply")
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertIn("overlay: applied (security-reviewer=claude-mythos-5-2)", out)
        rows = self.statuses(out)
        self.assertEqual(rows["marketplace"], "up-to-date")
        self.assertEqual(rows["verify marketplace"], "up-to-date")

    def test_unknown_role_is_rejected(self) -> None:
        self.assert_rejected('[roles.no-such-role]\nmodel = "opus"\n')

    def test_keys_other_than_role_model_are_rejected(self) -> None:
        self.assert_rejected('[roles.security-reviewer]\nmodel = "opus"\neffort = "low"\n')

    def test_top_level_keys_other_than_roles_are_rejected(self) -> None:
        self.assert_rejected('[tiers.strong]\nmodel = "opus"\n')

    def test_invalid_model_value_is_rejected(self) -> None:
        self.assert_rejected('[roles.security-reviewer]\nmodel = "opus\\nevil: 1"\n')

    def test_flagged_model_on_security_role_is_rejected(self) -> None:
        self.assert_rejected('[roles.security-reviewer]\nmodel = "fable"\n')

    def test_role_names_that_are_paths_are_rejected(self) -> None:
        outside = self.tmp / "outside.md"
        outside.write_text("---\nname: x\nmodel: opus\n---\nbody\n")
        for role in ("../agents/security-reviewer", "./security-reviewer", str(outside.with_suffix("")), "a/b"):
            with self.subTest(role=role):
                self.assert_rejected(f'[roles."{role}"]\nmodel = "fable"\n')
        self.assertIn("model: opus", outside.read_text())

    def test_dry_run_with_path_role_does_not_touch_outside_files(self) -> None:
        outside = self.tmp / "outside.md"
        outside.write_text("---\nmodel: opus\n---\n")
        self.write_overlay(f'[roles."{outside.with_suffix("")}"]\nmodel = "haiku"\n')
        code, out, err = self.update()
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("model: opus", outside.read_text())

    def test_flagged_model_variants_on_security_role_are_rejected(self) -> None:
        for role in ("security-reviewer", "security-executor"):
            for model in ("fable", "fable[1m]", "claude-fable-5-2"):
                with self.subTest(role=role, model=model):
                    self.assert_rejected(f'[roles.{role}]\nmodel = "{model}"\n')

    def test_model_values_that_change_yaml_type_are_rejected(self) -> None:
        for model in ("[1m]", "-", "]", "1.0", "0"):
            with self.subTest(model=model):
                self.assert_rejected(f'[roles.verifier]\nmodel = "{model}"\n')

    def test_model_with_context_suffix_is_allowed(self) -> None:
        self.write_overlay('[roles.verifier]\nmodel = "opus[1m]"\n')
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertIn("\nmodel: opus[1m]\n", (self.mp / f"{AGENTS}/verifier.md").read_text())

    def test_overlay_change_reinstalls_the_core_plugin(self) -> None:
        # 版本相同時 claude plugin update 不刷新 cache（2026-11-14 實測），只能先移除再裝
        manifest = json.loads(self.head(".claude-plugin/marketplace.json"))
        version = next(p["version"] for p in manifest["plugins"] if p["name"] == "shoal")
        (self.state / "claude.version").write_text(version)
        self.update("--apply")
        before = len(self.calls())
        self.write_overlay('[roles.security-reviewer]\nmodel = "claude-mythos-5-2"\n')
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        calls = self.calls()[before:]
        self.assertIn("plugin uninstall shoal@shoal", calls)
        self.assertIn("plugin install shoal@shoal", calls)

    def test_flagged_model_on_non_security_role_is_allowed(self) -> None:
        self.write_overlay('[roles.verifier]\nmodel = "fable"\n')
        code, out, err = self.update("--apply")
        self.assertEqual(code, 0, out + err)
        self.assertIn("\nmodel: fable\n", (self.mp / f"{AGENTS}/verifier.md").read_text())


if __name__ == "__main__":
    unittest.main()
