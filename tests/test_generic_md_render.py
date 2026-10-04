"""generic-md renderer（new-host 的 N1、N2）：[output] 宣告的五種編碼、路徑樣式、host 探索與驗證，
以及用宣告重現 Claude 與 agy 的 scout 輸出（逐位元組相同）。

機制測試用 temp 目錄的假 host（不放進 hosts/），core 沿用 repo 的 core。
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from render_helpers import ROOT, render, run_render

FIXTURES = ROOT / "tests" / "fixtures" / "generic-md"
CORE_ROLES = tuple(render.load_toml(ROOT / "core" / "roles.toml")["roles"])

FRONTMATTER = '''
[[output.frontmatter]]
key = "name"
source = "name"
encoding = "scalar"

[[output.frontmatter]]
key = "description"
source = "description"
encoding = "scalar"

[[output.frontmatter]]
key = "model"
source = "model"
encoding = "scalar"

[[output.frontmatter]]
key = "tools"
source = "tools"
encoding = "comma-list"
'''
PERMISSIONS = '''
[output.permissions.tools]
type = "list"

[output.permissions.mode]
type = "scalar"

[output.permissions.perm]
type = "map"
'''
ACCESS = '''
[access.read-only]
tools = ["read", "grep"]
mode = "ro"
perm = { edit = "deny", bash = "deny" }

[access.write]
mode = "rw"
perm = { edit = "allow" }

[access.verify]
tools = ["read", "grep", "run"]
mode = "run"

[capabilities.web]
tools = ["web"]
perm = { net = "allow" }
'''
DESCRIPTION = "Short text for {role}"


def binding_text(*, header: str = "", frontmatter: str = FRONTMATTER, permissions: str = PERMISSIONS,
                 access: str = ACCESS, path: str = "agents/{role}.md", roles: str | None = None,
                 extra: str = "") -> str:
    if roles is None:
        roles = "".join(f'\n[roles.{r}]\ndescription = "{DESCRIPTION.format(role=r)}"\n' for r in CORE_ROLES)
    return (
        'renderer = "generic-md"\nrole_text = "core"\n' + header
        + '\n[models]\n"anthropic/haiku" = "haiku"\n"anthropic/sonnet" = "sonnet"\n"anthropic/opus" = "opus"\n'
        + f'\n[output]\npath = "{path}"\n' + frontmatter + permissions + access + roles + extra
    )


class GenericRoot(unittest.TestCase):
    """temp repo 根目錄：複製 core，hosts/demo 由測試寫入。"""

    HOST = "demo"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
        self.host_dir = self.root / "hosts" / self.HOST
        self.host_dir.mkdir(parents=True)

    def write(self, rel: str, text: str) -> None:
        path = self.host_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def binding(self, **kwargs: object) -> None:
        self.write("binding.toml", binding_text(**kwargs))

    def files(self) -> dict[str, bytes]:
        return render.render_host(self.root, self.HOST)

    def text(self, role: str = "scout", rel: str | None = None) -> str:
        files = self.files()
        return files[rel or f"agents/{role}.md"].decode("utf-8")

    def head(self, role: str = "scout") -> str:
        text = self.text(role)
        return text[: text.index("\n---\n\n") + len("\n---\n\n")]

    def assert_rejected(self, *expected: str) -> None:
        result = run_render(self.HOST, self.root, "--check")
        self.assertEqual(result.returncode, 2, result.stderr)
        for needle in expected:
            self.assertIn(needle, result.stderr)


class EncodingTests(GenericRoot):
    def frontmatter(self, key: str, encoding: str, source: str = "", extra: str = "", value: str = "") -> str:
        pick = f'source = "{source}"' if source else f"value = {value}"
        return f'\n[[output.frontmatter]]\nkey = "{key}"\n{pick}\nencoding = "{encoding}"\n{extra}'

    def test_scalar_and_comma_list(self) -> None:
        self.binding()
        self.assertEqual(
            self.head(),
            "---\nname: scout\ndescription: Short text for scout\nmodel: sonnet\ntools: read, grep\n---\n\n",
        )

    def test_block_list_uses_the_indent_option(self) -> None:
        self.binding(frontmatter=self.frontmatter("tools", "block-list", "tools", "indent = 4\n"))
        self.assertEqual(self.head(), "---\ntools:\n    - read\n    - grep\n---\n\n")
        self.binding(frontmatter=self.frontmatter("tools", "block-list", "tools"))
        self.assertEqual(self.head(), "---\ntools:\n  - read\n  - grep\n---\n\n")

    def test_nested_map_is_one_level_of_key_values(self) -> None:
        self.binding(frontmatter=self.frontmatter("permission", "nested-map", "perm", "indent = 4\n"))
        self.assertEqual(self.head(), "---\npermission:\n    edit: deny\n    bash: deny\n---\n\n")

    def test_folded_keeps_source_lines_without_width(self) -> None:
        roles = '\n[roles.scout]\ndescription = """\nfirst line of text\nsecond line\n"""\n' + "".join(
            f'\n[roles.{r}]\ndescription = "x"\n' for r in CORE_ROLES if r != "scout"
        )
        self.binding(frontmatter=self.frontmatter("description", "folded", "description"), roles=roles)
        self.assertEqual(self.head(), "---\ndescription: >\n  first line of text\n  second line\n---\n\n")

    def test_folded_with_width_rewraps_including_the_indent(self) -> None:
        long = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        roles = "".join(f'\n[roles.{r}]\ndescription = "{long}"\n' for r in CORE_ROLES)
        self.binding(frontmatter=self.frontmatter("description", "folded", "description", "width = 24\nindent = 4\n"),
                     roles=roles)
        lines = self.head().splitlines()[1:-2]
        self.assertEqual(lines[0], "description: >")
        self.assertTrue(all(len(line) <= 24 and line.startswith("    ") for line in lines[1:]), lines)
        self.assertEqual(" ".join(line.strip() for line in lines[1:]), long)

    def test_fixed_value_and_missing_permission_field_is_skipped(self) -> None:
        fm = self.frontmatter("effort", "scalar", value='"low"') + self.frontmatter("mode", "scalar", "mode")
        self.binding(frontmatter=fm)
        self.assertEqual(self.head("scout"), "---\neffort: low\nmode: ro\n---\n\n")
        # write 的對應表沒有 tools，但有 mode；這裡只確認缺少的欄位不輸出
        self.binding(frontmatter=self.frontmatter("tools", "comma-list", "tools") + self.frontmatter("mode", "scalar", "mode"))
        self.assertEqual(self.head("executor"), "---\nmode: rw\n---\n\n")

    def test_capability_merges_into_access_fields(self) -> None:
        fm = self.frontmatter("tools", "comma-list", "tools") + self.frontmatter("permission", "nested-map", "perm")
        self.binding(frontmatter=fm)
        self.assertEqual(self.head("security-reviewer"),
                         "---\ntools: read, grep, web\npermission:\n  edit: deny\n  bash: deny\n  net: allow\n---\n\n")

    def test_role_override_replaces_the_whole_field(self) -> None:
        roles = "".join(f'\n[roles.{r}]\ndescription = "x"\n' + ('tools = ["only"]\n' if r == "scout" else "")
                        for r in CORE_ROLES)
        self.binding(roles=roles)
        self.assertIn("tools: only\n", self.head("scout"))
        self.assertIn("tools: read, grep\n", self.head("plan-verifier"))

    def test_body_follows_frontmatter_and_frame_wraps_it(self) -> None:
        self.binding()
        self.write("frames/default.md", "# Title\n\n{{role_body}}")
        text = self.text()
        self.assertIn("---\n\n# Title\n\nYou are a fast, read-only scout", text)
        self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"))

    def test_output_path_pattern(self) -> None:
        self.binding(path="agents/{role}/agent.md")
        self.assertEqual(sorted(self.files()), sorted(f"agents/{r}/agent.md" for r in CORE_ROLES))


class ValidationTests(GenericRoot):
    def frontmatter(self, body: str) -> str:
        return "\n[[output.frontmatter]]\n" + body

    def test_unknown_source_names_role_and_field(self) -> None:
        self.binding(frontmatter=self.frontmatter('key = "x"\nsource = "nope"\nencoding = "scalar"\n'))
        self.assert_rejected("host demo", "scout", "欄位 x", "nope")

    def test_undeclared_permission_field_cannot_be_a_source(self) -> None:
        self.binding(frontmatter=self.frontmatter('key = "x"\nsource = "tools"\nencoding = "comma-list"\n'),
                     permissions="", access="\n[access.read-only]\n[access.write]\n[access.verify]\n[capabilities.web]\n")
        self.assert_rejected("欄位 x", "tools", "[output.permissions.<欄位>]")

    def test_unsupported_encoding(self) -> None:
        self.binding(frontmatter=self.frontmatter('key = "x"\nsource = "name"\nencoding = "json"\n'))
        self.assert_rejected("scout", "欄位 x", "json")

    def test_encoding_must_match_the_source_type(self) -> None:
        self.binding(frontmatter=self.frontmatter('key = "x"\nsource = "tools"\nencoding = "scalar"\n'))
        self.assert_rejected("欄位 x", "scalar", "list")
        self.binding(frontmatter=self.frontmatter('key = "x"\nsource = "name"\nencoding = "block-list"\n'))
        self.assert_rejected("欄位 x", "block-list")

    def test_source_and_value_are_exclusive_and_one_is_required(self) -> None:
        self.binding(frontmatter=self.frontmatter('key = "x"\nsource = "name"\nvalue = "y"\nencoding = "scalar"\n'))
        self.assert_rejected("欄位 x", "source 與 value")
        self.binding(frontmatter=self.frontmatter('key = "x"\nencoding = "scalar"\n'))
        self.assert_rejected("欄位 x", "source 與 value")

    def test_bad_entries(self) -> None:
        cases = {
            'key = "x y"\nsource = "name"\nencoding = "scalar"\n': "key",
            'key = "x"\nsource = "name"\nencoding = "scalar"\nbogus = 1\n': "bogus",
            'key = "x"\nsource = "name"\nencoding = "scalar"\nindent = 2\n': "indent",
            'key = "x"\nsource = "tools"\nencoding = "block-list"\nwidth = 3\n': "width",
            'key = "x"\nsource = "tools"\nencoding = "block-list"\nindent = 0\n': "indent",
        }
        for body, needle in cases.items():
            with self.subTest(needle=needle):
                self.binding(frontmatter=self.frontmatter(body))
                self.assert_rejected("欄位 x", needle)

    def test_duplicate_key_and_empty_frontmatter(self) -> None:
        one = self.frontmatter('key = "x"\nsource = "name"\nencoding = "scalar"\n')
        self.binding(frontmatter=one + one)
        self.assert_rejected("欄位 x", "重複")
        self.binding(frontmatter="")
        self.assert_rejected("frontmatter")

    def test_access_table_field_must_be_declared_with_a_type(self) -> None:
        self.binding(access=ACCESS.replace('mode = "ro"', 'mode = "ro"\nsurprise = "x"'))
        self.assert_rejected("[access.read-only]", "surprise")

    def test_permission_type_is_enforced_on_values(self) -> None:
        self.binding(access=ACCESS.replace('tools = ["read", "grep"]', 'tools = "read"', 1))
        self.assert_rejected("[access.read-only]", "tools", "字串陣列")
        self.binding(access=ACCESS.replace('mode = "ro"', "mode = 3"))
        self.assert_rejected("mode", "字串")

    def test_permission_declaration_is_validated(self) -> None:
        self.binding(permissions=PERMISSIONS.replace('type = "map"', 'type = "set"'))
        self.assert_rejected("[output.permissions.perm]", "type")
        self.binding(permissions=PERMISSIONS + '\n[output.permissions.model]\ntype = "scalar"\n')
        self.assert_rejected("[output.permissions.model]")

    def test_extra_roles_are_rejected_with_the_role_name(self) -> None:
        self.binding(extra='\n[extra_roles.Explore]\nmodel = "haiku"\naccess = "read-only"\n')
        self.assert_rejected("Explore", "host 專屬 role")

    def test_role_text_must_be_core(self) -> None:
        self.binding(header="")
        self.write("binding.toml", binding_text().replace('role_text = "core"', 'role_text = "legacy"', 1))
        self.assert_rejected("role_text", "core")
        roles = "".join(f'\n[roles.{r}]\ndescription = "x"\n' + ('role_text = "legacy"\n' if r == "scout" else "")
                        for r in CORE_ROLES)
        self.binding(roles=roles)
        self.assert_rejected("scout", "role_text")

    def test_unknown_role_key_is_rejected(self) -> None:
        roles = "".join(f'\n[roles.{r}]\ndescription = "x"\n' + ('effort = "low"\n' if r == "scout" else "")
                        for r in CORE_ROLES)
        self.binding(roles=roles)
        self.assert_rejected("scout", "effort")

    def test_description_is_required_only_when_used(self) -> None:
        roles = "".join(f"\n[roles.{r}]\n" for r in CORE_ROLES)
        self.binding(roles=roles)
        self.assert_rejected("scout", "description")
        self.binding(roles=roles, frontmatter=self.frontmatter('key = "name"\nsource = "name"\nencoding = "scalar"\n'))
        self.assertEqual(run_render(self.HOST, self.root, "--write").returncode, 0)

    def test_every_catalog_role_still_needs_a_binding(self) -> None:
        roles = "".join(f'\n[roles.{r}]\ndescription = "x"\n' for r in CORE_ROLES if r != "scout")
        self.binding(roles=roles)
        self.assert_rejected("scout")

    def test_path_pattern_is_validated(self) -> None:
        for path in ("agents/fixed.md", "agents/{role}/{role}.md", "agents/{other}.md", "/abs/{role}.md",
                     "../{role}.md", "agents/{role}.txt", "agents//{role}.md"):
            with self.subTest(path=path):
                self.binding(path=path)
                self.assert_rejected("path")

    def test_empty_or_unsafe_values_are_rejected(self) -> None:
        self.binding(access=ACCESS.replace('tools = ["read", "grep"]', "tools = []", 1))
        self.assert_rejected("scout", "tools", "空")
        roles = "".join(f'\n[roles.{r}]\ndescription = "{"a: b" if r == "scout" else "x"}"\n' for r in CORE_ROLES)
        self.binding(roles=roles)
        self.assert_rejected("scout", "description", "YAML")
        roles = "".join(f'\n[roles.{r}]\ndescription = "{"a\\nb" if r == "scout" else "x"}"\n' for r in CORE_ROLES)
        self.binding(roles=roles)
        self.assert_rejected("scout", "description")
        self.binding(access=ACCESS.replace('"grep"]\nmode = "ro"', '"g,rep"]\nmode = "ro"', 1))
        self.assert_rejected("scout", "tools", "逗號")

    def test_missing_models_asks_to_fill_models(self) -> None:
        text = re.sub(r'(?ms)^\[models\]\n.*?(?=^\[)', "", binding_text())
        self.write("binding.toml", text)
        self.assert_rejected("[models]", "hosts/demo/binding.toml")

    def test_model_must_be_in_the_catalog(self) -> None:
        self.write("binding.toml", binding_text().replace('"anthropic/opus"', '"anthropic/nope"'))
        self.assert_rejected("anthropic/nope")

    def test_renderer_value_is_required(self) -> None:
        self.write("binding.toml", binding_text().replace('renderer = "generic-md"\n', ""))
        with self.assertRaises(render.RenderError):
            self.files()


class DistAndExplainTests(GenericRoot):
    def test_write_then_check_and_drift(self) -> None:
        self.binding()
        self.assertEqual(run_render(self.HOST, self.root, "--check").returncode, 1)
        result = run_render(self.HOST, self.root, "--write")
        self.assertEqual(result.returncode, 0, result.stderr)
        dist = self.host_dir / "dist"
        self.assertEqual(sorted(p.name for p in (dist / "agents").iterdir()), sorted(f"{r}.md" for r in CORE_ROLES))
        self.assertEqual(run_render(self.HOST, self.root, "--check").returncode, 0)
        (dist / "stale.md").write_text("x", encoding="utf-8", newline="\n")
        scout = dist / "agents" / "scout.md"
        scout.write_bytes(scout.read_bytes() + b"x")
        result = run_render(self.HOST, self.root, "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("多出: stale.md", result.stderr)
        self.assertIn("內容不同: agents/scout.md", result.stderr)
        self.assertEqual(run_render(self.HOST, self.root, "--write").returncode, 0)
        self.assertEqual(run_render(self.HOST, self.root, "--check").returncode, 0)

    def test_explain_shows_derived_permissions(self) -> None:
        self.binding()
        result = run_render(self.HOST, self.root, "--explain")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("host: demo", result.stdout)
        self.assertIn('tools = ["read", "grep", "web"]', result.stdout)

    def test_explain_rejects_an_invalid_generic_binding(self) -> None:
        self.binding(extra='\n[extra_roles.Explore]\nmodel = "haiku"\naccess = "read-only"\n')
        result = run_render(self.HOST, self.root, "--explain")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Explore", result.stderr)


class DiscoveryTests(GenericRoot):
    def test_generic_hosts_are_discovered_from_the_binding(self) -> None:
        self.binding()
        self.write("../other/binding.toml", 'role_text = "core"\n')  # 沒有 renderer：不是 generic host
        self.assertEqual(render.discover_generic_hosts(self.root), ["demo"])

    def test_host_choice_accepts_discovered_hosts_and_the_builtin_five(self) -> None:
        self.binding()
        self.assertEqual(run_render(self.HOST, self.root, "--explain").returncode, 0)
        result = run_render("nosuch", self.root, "--check")
        self.assertEqual(result.returncode, 2)
        self.assertIn("demo", result.stderr)
        for host in ("claude", "codex", "agy", "grok", "opencode"):
            self.assertIn(host, result.stderr)

    def test_builtin_names_are_reserved_for_their_renderers(self) -> None:
        self.assertEqual(set(render.RENDERERS), {"claude", "codex", "agy", "grok", "opencode"})
        self.assertEqual(set(render.DIST_DIRS), set(render.RENDERERS))
        shutil.copytree(ROOT / "hosts" / "agy", self.root / "hosts" / "agy", ignore=shutil.ignore_patterns("plugin"))
        agy = self.root / "hosts" / "agy" / "binding.toml"
        agy.write_text('renderer = "generic-md"\n' + agy.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        self.assertEqual(render.discover_generic_hosts(self.root), [])
        self.assertEqual(run_render("agy", self.root, "--check").returncode, 0)

    def test_broken_binding_of_a_non_builtin_host_is_reported(self) -> None:
        self.write("binding.toml", "renderer = [broken\n")
        result = run_render("claude", self.root, "--check")
        self.assertEqual(result.returncode, 2)
        self.assertIn("binding.toml", result.stderr)

    def test_host_directory_name_is_validated(self) -> None:
        bad = self.root / "hosts" / "Bad_Name"
        bad.mkdir()
        (bad / "binding.toml").write_text('renderer = "generic-md"\n', encoding="utf-8", newline="\n")
        with self.assertRaises(render.RenderError):
            render.discover_generic_hosts(self.root)


def _compose(host: str, fragment: str, dest: Path) -> None:
    """把既有 host 的 binding 改寫成 generic-md：換 renderer、拿掉 generic 不支援的設定（effort、
    host 專屬 role），接上 [output] 宣告；models、access、addenda、frames 都沿用該 host 現有的資料。"""
    shutil.copytree(ROOT / "core", dest / "core")
    target = dest / "hosts" / "x"
    for sub in ("addenda", "frames"):
        if (ROOT / "hosts" / host / sub).is_dir():
            shutil.copytree(ROOT / "hosts" / host / sub, target / sub)
    text = (ROOT / "hosts" / host / "binding.toml").read_text(encoding="utf-8")
    text = re.sub(r"(?m)^supports_effort = false\n", "", text)
    text = re.sub(r"(?m)^effort = .*\n", "", text)
    text = re.sub(r"(?ms)^# host 專屬 role.*", "", text)
    text = 'renderer = "generic-md"\n' + text + "\n" + (FIXTURES / fragment).read_text(encoding="utf-8")
    target.mkdir(parents=True, exist_ok=True)
    (target / "binding.toml").write_text(text, encoding="utf-8", newline="\n")


class ReproduceExistingHostsTests(unittest.TestCase):
    """N2：宣告能表達真實格式，不需要 renderer 內的 host 專屬分支。"""

    def rendered(self, host: str, fragment: str) -> dict[str, bytes]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        _compose(host, fragment, Path(tmp.name))
        return render.render_host(Path(tmp.name), "x")

    def test_claude_scout_is_byte_identical(self) -> None:
        files = self.rendered("claude", "claude-output.toml")
        real = (ROOT / "hosts/claude/dist/agents/scout.md").read_bytes()
        self.assertEqual(files["agents/scout.md"], real)

    def test_claude_other_roles_differ_only_in_effort(self) -> None:
        # effort 沒有 role 層級的來源，宣告只能寫固定值 low；其餘（tools、disallowedTools、body）要完全相同。
        files = self.rendered("claude", "claude-output.toml")
        for role in CORE_ROLES:
            with self.subTest(role=role):
                real = (ROOT / f"hosts/claude/dist/agents/{role}.md").read_bytes()
                normalized = re.sub(rb"(?m)^effort: .*$", b"effort: low", real, count=1)
                self.assertEqual(files[f"agents/{role}.md"], normalized)

    def test_agy_scout_is_byte_identical(self) -> None:
        files = self.rendered("agy", "agy-output.toml")
        real = (ROOT / "hosts/agy/dist/agents/scout/agent.md").read_bytes()
        self.assertEqual(files["agents/scout/agent.md"], real)

    def test_agy_all_roles_are_byte_identical(self) -> None:
        files = self.rendered("agy", "agy-output.toml")
        dist = ROOT / "hosts" / "agy" / "dist" / "agents"
        self.assertEqual(sorted(files), sorted(p.relative_to(dist.parent).as_posix() for p in dist.rglob("*.md")))
        for rel, data in files.items():
            self.assertEqual(data, (dist.parent / rel).read_bytes(), rel)


if __name__ == "__main__":
    unittest.main()
