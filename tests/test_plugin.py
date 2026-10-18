import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "codex"
VERSION = (ROOT / "hosts" / "codex" / "VERSION").read_text(encoding="utf-8").strip()


class PluginPackageTests(unittest.TestCase):
    def test_marketplace_and_manifest_describe_the_same_plugin(self) -> None:
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text()
        )
        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual(entry["source"]["path"], "./plugins/codex")
        self.assertEqual(manifest["version"], VERSION)

    def test_skill_is_complete_and_references_exist(self) -> None:
        skill = PLUGIN / "skills" / "shoal-orchestration"
        self.assertTrue((skill / "SKILL.md").is_file())
        references = sorted((skill / "references").glob("*.md"))
        self.assertTrue(references)
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        for reference in references:
            self.assertIn(
                f"](references/{reference.name})",
                text,
                f"SKILL.md does not point at references/{reference.name}",
            )

    def test_root_marketplace_lists_every_plugin_dir(self) -> None:
        root = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text()
        )
        self.assertEqual(root["name"], "shoal-codex")
        self.assertEqual(
            [p["name"] for p in root["plugins"]], ["shoal-codex", "shoal-jev-router"]
        )
        for entry in root["plugins"]:
            self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
            manifest = entry["source"]["path"] + "/.codex-plugin/plugin.json"
            self.assertTrue((ROOT / manifest).is_file(), manifest)

    def test_optional_jev_plugin_manifest_matches_marketplace_entry(self) -> None:
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text()
        )
        entry = next(
            plugin
            for plugin in marketplace["plugins"]
            if plugin["name"] == "shoal-jev-router"
        )
        manifest_path = (
            ROOT / "plugins" / "jev-router" / ".codex-plugin" / "plugin.json"
        )
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(entry["source"]["path"], "./plugins/jev-router")
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")


if __name__ == "__main__":
    unittest.main()
