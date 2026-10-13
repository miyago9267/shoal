"""core policy 在 codex、grok、agy、opencode 上可用（但 repo 內仍全是 legacy，只有 claude 是 core）。

在 temp 副本的 binding 寫入最小 [policy]（placeholders、documents、trivial frame），驗證 core 輸出、
required 保護、placeholder 缺漏的錯誤與 legacy 的逐位元組不變。
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from render_helpers import ROOT, render, run_render

HOSTS = ("codex", "grok", "agy", "opencode")
BOOTSTRAP_PATH = {"codex": "agents-md.orchestration.md", "grok": "rules/shoal-policy.md",
                  "agy": "rules/shoal-policy.md", "opencode": "policy/bootstrap.md"}
BOOTSTRAP_TEXT = "never spawn subagents"
LEGACY_POLICY = re.compile(r'\[policy\]\npolicy_text = "legacy"\nomit = \[\]\n')


class HostPolicyCase(unittest.TestCase):
    def prepare(self, host: str) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.host = host
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
        shutil.copytree(ROOT / "hosts" / host, self.root / "hosts" / host,
                        ignore=shutil.ignore_patterns("plugin", "node_modules"))
        if host == "grok":
            (self.root / "hooks").mkdir()
            shutil.copy(ROOT / "hooks" / "shoal_guard.py", self.root / "hooks" / "shoal_guard.py")
        self.binding = self.root / "hosts" / host / "binding.toml"
        self.paths = {"bootstrap": BOOTSTRAP_PATH[host], "skill": "policy/skill.md",
                      "orchestration": "policy/orchestration.md", "extensions": "policy/extensions.md"}

    def policy_table(self, mode: str, *, drop_placeholder: str = "", extra: str = "") -> str:
        claude = render.load_toml(ROOT / "hosts" / "claude" / "binding.toml")["policy"]["placeholders"]
        lines = ["[policy]", f'policy_text = "{mode}"', "omit = []", "", "[policy.placeholders]"]
        lines += [f"{k} = {json.dumps(v)}" for k, v in claude.items() if k != drop_placeholder]
        lines += ["", "[policy.documents]"] + [f'{d} = "{p}"' for d, p in self.paths.items()]
        return "\n".join(lines) + "\n" + extra

    def configure(self, mode: str = "core", **kw: str) -> None:
        text = self.binding.read_text(encoding="utf-8")
        self.assertRegex(text, LEGACY_POLICY)
        text = LEGACY_POLICY.sub(lambda _m: self.policy_table(mode, **kw), text, count=1)
        self.binding.write_text(text, encoding="utf-8", newline="\n")
        frames = self.root / "hosts" / self.host / "policy-frames"
        frames.mkdir(exist_ok=True)
        (frames / "default.md").write_text("<!-- frame -->\n{{role_body}}", encoding="utf-8", newline="\n")

    def run_host(self, *flags: str):
        return run_render(self.host, self.root, *flags)


class CoreOnEveryHostTests(HostPolicyCase):
    def test_core_output_lands_at_the_mapped_paths(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.prepare(host)
                legacy = render.render_host(self.root, host)
                self.configure()
                core = render.render_host(self.root, host)
                self.assertIn(BOOTSTRAP_TEXT, core[self.paths["bootstrap"]].decode("utf-8"))
                self.assertTrue(core[self.paths["bootstrap"]].startswith(b"<!-- frame -->\n"))
                for path in self.paths.values():
                    self.assertIn(path, core)
                other = set(legacy) - set(self.paths.values())
                self.assertTrue(all(core[p] == legacy[p] for p in other), host)

    def test_required_clause_cannot_be_omitted(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.prepare(host)
                self.configure()
                text = self.binding.read_text(encoding="utf-8")
                self.binding.write_text(
                    text.replace("omit = []", 'omit = [{ id = "approval-gate", reason = "x" }]', 1),
                    encoding="utf-8", newline="\n")
                result = self.run_host("--check")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(f"host {host}", result.stderr)
                self.assertIn("approval-gate", result.stderr)

    def test_missing_placeholder_or_document_names_the_host(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.prepare(host)
                self.configure(drop_placeholder="shell_tool")
                result = self.run_host("--check")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(f"host {host}", result.stderr)
                self.assertIn("[policy.placeholders] 缺少 shell_tool", result.stderr)

    def test_missing_document_names_the_host(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.prepare(host)
                self.paths.pop("skill")
                self.configure()
                result = self.run_host("--check")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(f"host {host}", result.stderr)
                self.assertIn("[policy.documents] 缺少文件 skill", result.stderr)

    def test_legacy_with_policy_tables_is_byte_identical_to_the_committed_output(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.prepare(host)
                self.configure("legacy")
                self.assertEqual(render.render_host(self.root, host), render.render_host(ROOT, host))

    def test_explain_policy_and_preview_work(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.prepare(host)
                self.configure("legacy")
                explained = self.run_host("--explain-policy")
                self.assertEqual(explained.returncode, 0, explained.stderr)
                self.assertIn("approval-gate", explained.stdout)
                out = self.root / "preview"
                self.assertEqual(self.run_host("--policy-preview", str(out)).returncode, 0)
                self.assertTrue((out / self.paths["bootstrap"]).is_file())

    def test_a_document_can_be_left_out_by_omitting_every_clause(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.prepare(host)
                self.configure()
                clauses = render.load_core(self.root)["policy"]["docs"]["skill"]
                self.assertFalse(any(c.required for c in clauses), "skill 文件含 required 條款，這個測試要換文件")
                body = ", ".join(f'{{ id = "{c.id}", reason = "host has no skill" }}' for c in clauses)
                text = self.binding.read_text(encoding="utf-8")
                self.binding.write_text(text.replace("omit = []", f"omit = [{body}]", 1),
                                        encoding="utf-8", newline="\n")
                files = render.render_host(self.root, host)
                self.assertNotIn(self.paths["skill"], files)
                self.assertIn(self.paths["bootstrap"], files)


class MirrorTests(HostPolicyCase):
    def test_binding_can_declare_extra_mirrors(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.prepare(host)
                self.configure(extra=f'\n[policy.mirrors]\n"{self.paths["bootstrap"]}" = "mirror/bootstrap.md"\n')
                self.assertEqual(self.run_host("--write").returncode, 0)
                files = render.render_host(self.root, host)
                self.assertEqual((self.root / "mirror" / "bootstrap.md").read_bytes(),
                                 files[self.paths["bootstrap"]])
                self.assertEqual(self.run_host("--check").returncode, 0)
                (self.root / "mirror" / "bootstrap.md").write_text("stale", encoding="utf-8")
                self.assertEqual(self.run_host("--check").returncode, 1)

    def test_mirror_source_must_be_a_policy_document(self) -> None:
        self.prepare("grok")
        self.configure(extra='\n[policy.mirrors]\n"nope.md" = "mirror/x.md"\n')
        result = self.run_host("--check")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("host grok", result.stderr)
        self.assertIn("不是 [policy.documents] 的輸出路徑", result.stderr)

    def test_codex_builtin_mirror_follows_the_core_content(self) -> None:
        self.prepare("codex")
        self.configure(extra="")
        self.assertEqual(self.run_host("--write").returncode, 0)
        mirror = self.root / render.MIRRORS["codex"]["agents-md.orchestration.md"]
        self.assertIn(BOOTSTRAP_TEXT, mirror.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
