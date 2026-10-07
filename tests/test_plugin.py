import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin" / "plugins" / "shoal-codex"
VERSION = (ROOT / "hosts" / "codex" / "VERSION").read_text(encoding="utf-8").strip()


class PluginPackageTests(unittest.TestCase):
    def test_marketplace_and_manifest_describe_the_same_plugin(self) -> None:
        marketplace = json.loads(
            (ROOT / "plugin" / ".agents" / "plugins" / "marketplace.json").read_text()
        )
        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual(entry["source"]["path"], "./plugins/shoal-codex")
        self.assertEqual(manifest["version"], VERSION)

    def test_skill_is_complete_and_references_exist(self) -> None:
        skill = PLUGIN / "skills" / "shoal-orchestration"
        text = (skill / "SKILL.md").read_text()
        self.assertIn("shoal-orchestration", text)
        self.assertNotIn("TODO", text)
        for reference in (
            "orchestration-policy.md",
            "role-contract.md",
            "verification-contract.md",
            "recovery-contract.md",
        ):
            self.assertTrue((skill / "references" / reference).is_file())
        self.assertTrue((skill / "agents" / "openai.yaml").is_file())

    def test_optional_jev_plugin_manifest_matches_marketplace_entry(self) -> None:
        marketplace = json.loads(
            (ROOT / "plugin" / ".agents" / "plugins" / "marketplace.json").read_text()
        )
        entry = next(
            plugin
            for plugin in marketplace["plugins"]
            if plugin["name"] == "shoal-jev-router"
        )
        manifest_path = (
            ROOT
            / "plugin"
            / "plugins"
            / "shoal-jev-router"
            / ".codex-plugin"
            / "plugin.json"
        )
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(entry["source"]["path"], "./plugins/shoal-jev-router")
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")

if __name__ == "__main__":
    unittest.main()
