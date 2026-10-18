import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "codex"
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
        self.assertEqual((ROOT / "plugin" / entry["source"]["path"]).resolve(), PLUGIN.resolve())

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

    def test_skill_never_lets_main_implement_itself(self) -> None:
        text = (
            (PLUGIN / "skills" / "shoal-orchestration" / "SKILL.md").read_text().lower()
        )
        self.assertNotIn("implement directly", text)
        self.assertNotIn("cheap parent", text)
        self.assertIn("write-capable role", text)

    def test_skill_names_every_on_demand_reference(self) -> None:
        skill = PLUGIN / "skills" / "shoal-orchestration"
        text = (skill / "SKILL.md").read_text()
        references = sorted((skill / "references").glob("*.md"))
        self.assertTrue(references)
        for reference in references:
            self.assertIn(
                f"](references/{reference.name})",
                text,
                f"SKILL.md does not point at references/{reference.name}",
            )

    def test_root_marketplace_mirrors_legacy_one_at_new_locations(self) -> None:
        """The exported root manifest lists the same plugins at plugins/<name>.

        The legacy plugin/ marketplace keeps its old paths for one release; Codex
        cannot resolve ".." out of a marketplace root, so they are symlinks.
        """
        legacy = json.loads(
            (ROOT / "plugin" / ".agents" / "plugins" / "marketplace.json").read_text()
        )
        root = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
        self.assertEqual(root["name"], legacy["name"])
        self.assertEqual(
            [p["name"] for p in root["plugins"]], [p["name"] for p in legacy["plugins"]]
        )
        for new, old in zip(root["plugins"], legacy["plugins"]):
            self.assertEqual(
                (ROOT / new["source"]["path"]).resolve(),
                (ROOT / "plugin" / old["source"]["path"]).resolve(),
            )
            self.assertEqual(new["policy"], old["policy"])
            manifest = new["source"]["path"] + "/.codex-plugin/plugin.json"
            self.assertTrue((ROOT / manifest).is_file(), manifest)

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
            / "plugins"
            / "jev-router"
            / ".codex-plugin"
            / "plugin.json"
        )
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(entry["source"]["path"], "./plugins/shoal-jev-router")
        self.assertEqual(
            (ROOT / "plugin" / entry["source"]["path"]).resolve(), manifest_path.parents[1].resolve()
        )
        self.assertEqual(entry["name"], manifest["name"])
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")


if __name__ == "__main__":
    unittest.main()
