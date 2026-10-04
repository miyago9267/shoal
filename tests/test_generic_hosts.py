"""generic-md host 的探索式測試（new-host 的 R7）：repo 內每個 `renderer = "generic-md"` 的 host
都檢查 `--check`，以及 core 條款逐字出現在輸出（role-contracts 的 R5）。

新增 generic-md host 不需要新增或修改測試檔。generic-md host 不使用 golden：
committed dist 加 `--check` 就是回歸基準。目前 repo 還沒有 generic-md host 時，這裡沒有任何檢查，仍然通過。
"""

from __future__ import annotations

import sys
import unittest

from render_helpers import ROOT, render, run_render

sys.path.insert(0, str(ROOT / "tools"))
import contracts  # noqa: E402


class GenericHostTests(unittest.TestCase):
    def hosts(self) -> list[str]:
        return render.discover_generic_hosts(ROOT)

    def test_check_passes_for_every_generic_host(self) -> None:
        for host in self.hosts():
            with self.subTest(host=host):
                result = run_render(host, ROOT, "--check")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_role_contains_every_unreplaced_clause(self) -> None:
        core = render.load_core(ROOT)
        for host in self.hosts():
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            files = render.render_host(ROOT, host)
            for name in render._bound_roles(core, binding):
                text = files[binding["output"]["path"].replace("{role}", name)].decode("utf-8")
                addenda = contracts.load_addenda(ROOT / "hosts" / host / "addenda" / f"{name}.toml")
                replaced = set(contracts.replaced_ids(addenda))
                for clause in core["contracts"][name]:
                    if clause.id not in replaced:
                        with self.subTest(host=host, role=name, clause=clause.id):
                            self.assertIn(clause.text, text)

    def test_generic_hosts_have_no_golden_and_a_dist_next_to_the_binding(self) -> None:
        for host in self.hosts():
            with self.subTest(host=host):
                self.assertFalse((ROOT / "tests" / "golden" / host).exists())
                self.assertEqual(render.dist_dir(host), f"hosts/{host}/dist")
                self.assertTrue((ROOT / "hosts" / host / "dist").is_dir())

    def test_builtin_hosts_are_never_discovered(self) -> None:
        self.assertFalse(set(self.hosts()) & set(render.RENDERERS))


if __name__ == "__main__":
    unittest.main()
