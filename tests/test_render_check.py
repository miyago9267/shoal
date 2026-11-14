"""輸出與來源的一致性：取代 tests/golden 的結構斷言（text-first P3a）。

文字回歸只由三道關卡承擔：`render --check`（輸出等於 prompts/ 與 binding 的 render 結果）、prompt lock
（預算與 required_fragments）、這裡的結構斷言。這裡不比對任何 prompt 的字句。
"""

from __future__ import annotations

import json
import re
import unittest

from render_helpers import ROOT, render, run_render

HOSTS = ("claude", "codex", "agy", "grok", "opencode", "claude-plugin")
# 每個 host 內某個 role 的輸出路徑（claude-plugin 是 claude 的 plugin 形態）。
ROLE_PATHS = {
    "claude": ("agents/{role}.md",),
    "codex": ("agents/{role}.toml",),
    "agy": ("agents/{role}/agent.md",),
    "grok": ("agents/{role}.md", "roles/{role}.toml"),
    "opencode": ("roles/{role}.md",),
    "claude-plugin": ("plugins/claude/agents/{role}.md",),
}
MARKER_LINE = re.compile(r"(?m)^<!-- shoal-(claude|agy|grok) v.+ -->$")
# 來源檔的 marker 與 frame 外殼不得出現在任何輸出。`${{ ... }}` 是 grok runtime 自己的樣板語法，不是殘留的 placeholder。
LEFTOVER_PLACEHOLDER = re.compile(rb"(?<!\$)\{\{")
SOURCE_MARKERS = (
    b"<!-- clause:",
    b"<!-- addendum:",
    b"<!-- description:",
    b"<!-- text:",
)
SOURCE_DIRS = ("frames", "policy-frames", "addenda", "policy-addenda", "relay")


def render_all() -> dict[str, dict[str, bytes]]:
    return {
        host: (
            render.render_claude_plugin(ROOT)
            if host == "claude-plugin"
            else render.render_host(ROOT, host)
        )
        for host in HOSTS
    }


def version(host: str) -> str:
    return (ROOT / "hosts" / host / "VERSION").read_text(encoding="utf-8").strip()


def normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


class RenderCheckTests(unittest.TestCase):
    """CI 的 `render --check` 步驟在本機的同一組 host。"""

    def test_every_host_matches_its_committed_output(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                result = run_render(host, ROOT, "--check")
                self.assertEqual(result.returncode, 0, result.stderr)


class StructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.outputs = render_all()
        cls.core = render.load_core(ROOT)

    def test_markers_equal_the_host_version(self) -> None:
        marker = lambda host, text: re.findall(
            rf"(?m)^<!-- shoal-{host} v.+ -->$", text
        )  # noqa: E731
        claude = self.outputs["claude"]
        expected = [f"<!-- shoal-claude v{version('claude')} -->"]
        self.assertEqual(
            marker(
                "claude", claude["skills/shoal-orchestration/SKILL.md"].decode("utf-8")
            ),
            expected,
        )
        self.assertEqual(
            claude["claude-md.bootstrap.md"].decode("utf-8").splitlines()[0],
            expected[0],
        )
        for host, rel in (
            ("agy", "rules/shoal-agy.md"),
            ("grok", "rules/shoal-grok.md"),
        ):
            with self.subTest(host=host):
                self.assertEqual(
                    marker(host, self.outputs[host][rel].decode("utf-8")),
                    [f"<!-- shoal-{host} v{version(host)} -->"],
                )

    def test_every_mirror_equals_its_source(self) -> None:
        mirrors = 0
        for host in ("claude", "codex", "agy", "grok", "opencode"):
            for rel, target in render.mirror_map(ROOT, host).items():
                mirrors += 1
                with self.subTest(host=host, mirror=target):
                    self.assertEqual(
                        (ROOT / target).read_bytes(), self.outputs[host][rel]
                    )
        self.assertGreaterEqual(mirrors, 1)  # codex 的 orchestration-policy

    def test_no_output_has_a_leftover_placeholder(self) -> None:
        for host, files in self.outputs.items():
            for rel, data in files.items():
                with self.subTest(host=host, path=rel):
                    self.assertIsNone(LEFTOVER_PLACEHOLDER.search(data))

    def test_every_core_role_has_an_output_where_the_host_provides_it(self) -> None:
        for host in HOSTS:
            binding = render.load_toml(
                ROOT
                / "hosts"
                / ("claude" if host == "claude-plugin" else host)
                / "binding.toml"
            )
            provided = set(self.core["roles"]) - set(binding.get("omitted_roles", []))
            self.assertTrue(provided, host)
            for role in sorted(provided):
                for template in ROLE_PATHS[host]:
                    with self.subTest(host=host, role=role):
                        self.assertIn(template.format(role=role), self.outputs[host])

    def test_frames_and_addenda_do_not_leak_into_the_output(self) -> None:
        for host, files in self.outputs.items():
            for rel, data in files.items():
                with self.subTest(host=host, path=rel):
                    self.assertFalse(set(rel.split("/")) & set(SOURCE_DIRS), rel)
                    for marker in SOURCE_MARKERS:
                        self.assertNotIn(marker, data)

    def test_every_lock_required_fragment_is_in_its_surface(self) -> None:
        lock = json.loads(
            (ROOT / "docs" / "specs" / "prompt-document-lock" / "LOCK.json").read_text(
                encoding="utf-8"
            )
        )
        checked = 0
        for surface in lock["surfaces"]:
            content = normalized((ROOT / surface["path"]).read_text(encoding="utf-8"))
            for fragment in surface["required_fragments"]:
                checked += 1
                with self.subTest(surface=surface["id"], fragment=fragment[:40]):
                    self.assertIn(normalized(fragment), content)
        self.assertGreater(checked, 100)


if __name__ == "__main__":
    unittest.main()
