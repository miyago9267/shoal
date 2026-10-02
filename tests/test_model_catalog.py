"""模型目錄與 resolver：選法、同分排序、R4 排除、R5 覆寫順序、R6 inherit、R9 失敗、--explain、換模型 mutation。"""

from __future__ import annotations

import copy
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from render_helpers import ROOT, render, run_render

import resolve  # noqa: E402  render_helpers 已把 tools/ 放進 sys.path

HOSTS = ("claude", "codex", "agy", "grok", "opencode")
FLAG = resolve.SECURITY_EXCLUDE_FLAG


def make_core(
    models: dict[str, tuple[int, int]], flagged: tuple[str, ...] = ()
) -> dict:
    """合成的 core：models 是 {key: (capability, cost)}；tiers 規則與 core/tiers.toml 相同。"""
    return {
        "models": {
            k: {
                "vendor": k.split("/")[0],
                "capability": c,
                "cost": p,
                **({"flags": [FLAG]} if k in flagged else {}),
            }
            for k, (c, p) in models.items()
        },
        "tiers": render.load_toml(ROOT / "core" / "tiers.toml")["tiers"],
    }


def binding_of(*keys: str, **extra: object) -> dict:
    return {"models": {k: k.split("/")[1] for k in keys}, **extra}


class SelectionTests(unittest.TestCase):
    def pick(
        self, core: dict, binding: dict, tier: str, security: bool = False
    ) -> object:
        return resolve.resolve(core, binding, tier=tier, security=security).model

    def test_cheapest_picks_lowest_cost_above_threshold(self) -> None:
        core = make_core({"a/small": (1, 1), "a/mid": (3, 2), "a/big": (5, 5)})
        binding = binding_of("a/small", "a/mid", "a/big")
        self.assertEqual(self.pick(core, binding, "fast"), "mid")  # small 低於門檻 2
        self.assertEqual(self.pick(core, binding, "standard"), "mid")
        self.assertEqual(self.pick(core, binding, "strong"), "big")

    def test_cheapest_tie_prefers_lower_capability_then_key(self) -> None:
        core = make_core({"a/y": (3, 2), "a/x": (3, 2), "a/z": (4, 2)})
        self.assertEqual(
            self.pick(core, binding_of("a/y", "a/x", "a/z"), "standard"), "x"
        )  # key 字典序
        self.assertEqual(
            self.pick(core, binding_of("a/y", "a/z"), "standard"), "y"
        )  # 同 cost 取 capability 低者

    def test_frontier_picks_most_capable(self) -> None:
        core = make_core({"a/small": (1, 1), "a/big": (5, 5), "a/mid": (4, 2)})
        self.assertEqual(
            self.pick(core, binding_of("a/small", "a/big", "a/mid"), "frontier"), "big"
        )

    def test_frontier_tie_prefers_lower_cost_then_key(self) -> None:
        core = make_core({"a/b": (5, 4), "a/a": (5, 4), "a/c": (5, 3)})
        self.assertEqual(
            self.pick(core, binding_of("a/b", "a/a", "a/c"), "frontier"), "c"
        )
        self.assertEqual(self.pick(core, binding_of("a/b", "a/a"), "frontier"), "a")

    def test_result_does_not_depend_on_declaration_order(self) -> None:
        core = make_core({"a/p": (3, 2), "a/q": (3, 2), "a/r": (4, 3)})
        for keys in (("a/p", "a/q", "a/r"), ("a/r", "a/q", "a/p")):
            self.assertEqual(self.pick(core, binding_of(*keys), "standard"), "p")

    def test_only_models_in_the_host_set_are_considered(self) -> None:
        core = make_core({"a/cheap": (3, 1), "a/mid": (3, 2)})
        self.assertEqual(self.pick(core, binding_of("a/mid"), "standard"), "mid")

    def test_host_names_may_be_tables(self) -> None:
        core = make_core({"a/m": (3, 2)})
        binding = {"models": {"a/m": {"provider": "a", "model": "m"}}}
        self.assertEqual(
            self.pick(core, binding, "standard"), {"provider": "a", "model": "m"}
        )


class SecurityExclusionTests(unittest.TestCase):
    CORE = make_core(
        {"a/mid": (3, 2), "a/opus": (4, 4), "a/fable": (5, 5)}, flagged=("a/fable",)
    )
    BINDING = binding_of("a/mid", "a/opus", "a/fable")

    def test_security_role_skips_flagged_model(self) -> None:
        res = resolve.resolve(self.CORE, self.BINDING, tier="frontier", security=True)
        self.assertEqual(res.model, "opus")

    def test_non_security_role_may_use_flagged_model(self) -> None:
        res = resolve.resolve(self.CORE, self.BINDING, tier="frontier", security=False)
        self.assertEqual(res.model, "fable")

    def test_exclusion_reason_is_reported(self) -> None:
        res = resolve.resolve(self.CORE, self.BINDING, tier="frontier", security=True)
        reasons = {c.key: c.excluded for c in res.candidates}
        self.assertIn(FLAG, reasons["a/fable"])
        self.assertIsNone(reasons["a/opus"])

    def test_security_role_fails_when_only_flagged_models_qualify(self) -> None:
        core = make_core({"a/fable": (5, 5)}, flagged=("a/fable",))
        with self.assertRaises(resolve.ResolveError):
            resolve.resolve(core, binding_of("a/fable"), tier="frontier", security=True)


class OverrideTests(unittest.TestCase):
    CORE = make_core({"a/mid": (3, 2), "a/big": (5, 5)})

    def test_role_pin_beats_tier_pin_and_rule(self) -> None:
        binding = binding_of("a/mid", "a/big", tiers={"standard": "tier-pin"})
        res = resolve.resolve(
            self.CORE, binding, tier="standard", pin=("role-pin", "[roles.x].model")
        )
        self.assertEqual(
            (res.model, res.source, res.detail), ("role-pin", "pin", "[roles.x].model")
        )

    def test_tier_pin_beats_rule(self) -> None:
        binding = binding_of("a/mid", "a/big", tiers={"standard": "tier-pin"})
        res = resolve.resolve(self.CORE, binding, tier="standard")
        self.assertEqual(
            (res.model, res.source, res.detail), ("tier-pin", "pin", "[tiers].standard")
        )
        self.assertEqual(
            resolve.resolve(self.CORE, binding, tier="strong").source, "rule"
        )  # 只覆寫該 tier

    def test_rule_is_used_without_pins(self) -> None:
        res = resolve.resolve(self.CORE, binding_of("a/mid", "a/big"), tier="standard")
        self.assertEqual((res.model, res.source, res.detail), ("mid", "rule", "a/mid"))

    def test_pin_wins_even_if_it_is_not_in_the_host_set(self) -> None:
        res = resolve.resolve(
            self.CORE,
            binding_of("a/mid"),
            tier="strong",
            pin=("custom", "[root].model"),
        )
        self.assertEqual(res.model, "custom")


class InheritTests(unittest.TestCase):
    def test_inherit_does_not_consult_the_catalog(self) -> None:
        res = resolve.resolve(
            {"models": {}, "tiers": {}},
            {"selection": "inherit"},
            tier="frontier",
            security=True,
        )
        self.assertEqual(
            (res.model, res.source, res.candidates), ("inherit", "inherit", ())
        )

    def test_pin_still_beats_inherit(self) -> None:
        res = resolve.resolve(
            {}, {"selection": "inherit"}, tier="fast", pin=("x", "[roles.a].model")
        )
        self.assertEqual(res.model, "x")

    def test_binding_validation(self) -> None:
        core = make_core({"a/m": (3, 2)})
        resolve.validate_binding(core, {"selection": "inherit"})
        resolve.validate_binding(core, binding_of("a/m"))
        for bad in (
            {},
            {"selection": "auto"},
            {"selection": "inherit", "models": {"a/m": "m"}},
            {"models": {"a/ghost": "g"}},
            {**binding_of("a/m"), "tiers": {"huge": "x"}},
        ):
            with self.assertRaises(resolve.ResolveError, msg=bad):
                resolve.validate_binding(core, bad)


class NoCandidateTests(unittest.TestCase):
    def test_no_model_meets_the_threshold(self) -> None:
        core = make_core({"a/small": (1, 1)})
        with self.assertRaisesRegex(resolve.ResolveError, "strong"):
            resolve.resolve(core, binding_of("a/small"), tier="strong")

    def test_empty_host_set_fails(self) -> None:
        with self.assertRaises(resolve.ResolveError):
            resolve.resolve(make_core({"a/m": (3, 2)}), {"models": {}}, tier="fast")


class CatalogValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = render.load_core(ROOT)

    def reject(self, mutate) -> None:
        core = copy.deepcopy(self.core)
        mutate(core)
        with self.assertRaises(resolve.ResolveError):
            resolve.validate_core(core)

    def test_shipped_catalog_is_valid(self) -> None:
        resolve.validate_core(self.core)

    def test_rejects_bad_models_and_tiers(self) -> None:
        self.reject(lambda c: c["models"]["anthropic/haiku"].update(capability=6))
        self.reject(lambda c: c["models"]["anthropic/haiku"].update(cost=0))
        self.reject(lambda c: c["models"]["anthropic/haiku"].update(vendor="openai"))
        self.reject(lambda c: c["models"]["anthropic/haiku"].update(flags="x"))
        self.reject(lambda c: c["tiers"].pop("frontier"))
        self.reject(lambda c: c["tiers"]["fast"].update(pick="random"))
        self.reject(lambda c: c["tiers"]["fast"].pop("min_capability"))

    def test_catalog_holds_no_host_specific_fields(self) -> None:
        for key, spec in self.core["models"].items():
            self.assertLessEqual(
                set(spec), {"vendor", "capability", "cost", "flags"}, key
            )

    def test_every_host_model_is_in_the_catalog(self) -> None:
        for host in HOSTS:
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            for key in binding.get("models", {}):
                self.assertIn(key, self.core["models"], f"{host}: {key}")


class CalibrationTests(unittest.TestCase):
    """現行配置（R8）：不寫任何 [tiers]，規則要重現目前各 host 的選模。"""

    EXPECTED = {
        "claude": {
            "scout": "sonnet",
            "mech-executor": "sonnet",
            "executor": "sonnet",
            "plan-verifier": "fable",
            "verifier": "opus",
            "security-reviewer": "opus",
            "security-executor": "opus",
        },
        "codex": {
            "scout": "gpt-6-luna",
            "mech-executor": "gpt-6-luna",
            "executor": "gpt-6-astra",
            "plan-verifier": "gpt-6-sol",
            "verifier": "gpt-6-sol",
            "security-reviewer": "gpt-6-sol",
            "security-executor": "gpt-6-sol",
        },
        "agy": {
            "scout": "flash",
            "mech-executor": "flash",
            "executor": "pro",
            "plan-verifier": "pro",
            "verifier": "pro",
            "security-reviewer": "pro",
            "security-executor": "pro",
        },
        "grok": {
            n: "inherit"
            for n in (
                "scout",
                "mech-executor",
                "executor",
                "plan-verifier",
                "verifier",
                "security-reviewer",
                "security-executor",
            )
        },
        "opencode": {
            "scout": "deepseek-v4-flash",
            "executor": "gpt-5.6-luna",
            "verifier": "gpt-5.6-sol",
            "security-reviewer": "gpt-5.6-sol",
            "security-executor": "gpt-5.6-sol",
        },
    }

    def test_rules_reproduce_current_models_without_tier_pins(self) -> None:
        core = render.load_core(ROOT)
        for host, expected in self.EXPECTED.items():
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            self.assertNotIn("tiers", binding, host)
            actual = {
                n: render.resolve_model(n, core, binding)
                for n in core["roles"]
                if n in expected
            }
            actual = {
                n: m["model"] if isinstance(m, dict) else m for n, m in actual.items()
            }
            self.assertEqual(actual, expected, host)


class CliOverrideTests(unittest.TestCase):
    """R9：沒有模型滿足規則時 exit 2，並點名 host 與 role；R5：手動 pin 的 CLI 行為。"""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
        shutil.copytree(ROOT / "hosts" / "claude", self.root / "hosts" / "claude")
        self.binding = self.root / "hosts" / "claude" / "binding.toml"

    def check(self):
        return run_render("claude", self.root, "--check")

    def edit(self, path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def assert_rejected(self, expected: str) -> None:
        result = self.check()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(expected, result.stderr)

    def test_check_fails_and_names_host_and_role(self) -> None:
        # 只剩 haiku（capability 1），低於所有 tier 的門檻；frontier 以外的 role 都解不出來
        text = self.binding.read_text(encoding="utf-8")
        text = re.sub(r'(?m)^"anthropic/(sonnet|opus|fable)" = .*\n', "", text)
        self.binding.write_text(text, encoding="utf-8", newline="\n")
        result = self.check()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("host claude", result.stderr)
        self.assertIn("role scout", result.stderr)

    def test_explain_fails_the_same_way(self) -> None:
        self.edit(self.binding, '"anthropic/opus" = "opus"\n', "")
        self.edit(self.binding, '"anthropic/fable" = "fable"\n', "")
        self.edit(self.binding, '"anthropic/sonnet" = "sonnet"\n', "")
        result = run_render("claude", self.root, "--explain")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("host claude", result.stderr)

    def test_unknown_model_key_in_binding_is_rejected(self) -> None:
        self.edit(
            self.binding, '"anthropic/haiku" = "haiku"', '"anthropic/ghost" = "ghost"'
        )
        self.assert_rejected("anthropic/ghost")

    def test_pinned_security_role_to_flagged_model_is_rejected(self) -> None:
        # 手動 pin 優先於選模規則，但不能繞過 R4：security role pin 到帶旗標的模型要失敗
        self.edit(
            self.binding,
            "[roles.security-reviewer]\n",
            '[roles.security-reviewer]\nmodel = "fable"\n',
        )
        self.assert_rejected(FLAG)

    def test_pinned_security_role_to_unflagged_model_is_manual_override(self) -> None:
        # R5：pin 到沒有旗標的模型照常生效，--explain 標示手動指定
        self.edit(
            self.binding,
            "[roles.security-reviewer]\n",
            '[roles.security-reviewer]\nmodel = "sonnet"\n',
        )
        self.assertEqual(self.check().returncode, 1)  # dist 的 model 變了
        out = run_render("claude", self.root, "--explain").stdout
        block = out.split("security-reviewer  tier=strong")[1].split("\n\n")[0]
        self.assertIn("結果：sonnet（手動指定 [roles.security-reviewer].model）", block)

    def test_tier_pin_overrides_the_rule(self) -> None:
        self.edit(
            self.binding,
            "[roles.scout]\n",
            '[tiers]\nfast = "haiku"\n\n[roles.scout]\n',
        )
        self.assertEqual(self.check().returncode, 1)
        self.assertIn(
            b"\nmodel: haiku\n",
            render.RENDERERS["claude"](self.root)["agents/scout.md"],
        )
        self.assertIn(
            "手動指定 [tiers].fast", run_render("claude", self.root, "--explain").stdout
        )


class ExplainTests(unittest.TestCase):
    def explain(self, host: str) -> str:
        result = run_render(host, ROOT, "--explain")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_every_host_can_explain_every_role(self) -> None:
        core = render.load_core(ROOT)
        for host in HOSTS:
            out = self.explain(host)
            binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
            for name in render._bound_roles(core, binding):
                self.assertRegex(
                    out, rf"(?m)^{re.escape(name)}  tier=", f"{host}: {name}"
                )

    def test_claude_explain_shows_candidates_exclusions_and_result(self) -> None:
        out = self.explain("claude")
        scout = out.split("scout  tier=fast")[1].split("\n\n")[0]
        self.assertIn("capability 1 低於 fast 門檻 2", scout)
        self.assertRegex(scout, r"(?m)^  \* anthropic/sonnet +capability=3 cost=2$")
        self.assertIn("結果：sonnet（resolver 選出 anthropic/sonnet）", scout)
        security = out.split("security-reviewer  tier=strong  security=true")[1].split(
            "\n\n"
        )[0]
        self.assertRegex(
            security, rf"anthropic/fable +capability=5 cost=5  排除：帶有 {FLAG} 旗標"
        )
        self.assertIn("結果：opus", security)

    def test_host_specific_pin_is_marked_manual(self) -> None:
        self.assertIn(
            "結果：haiku（手動指定 [extra_roles.Explore].model）",
            self.explain("claude"),
        )
        out = self.explain("codex")
        self.assertIn(
            "結果：gpt-6-sol（手動指定 [extra_roles.sol-executor].model）", out
        )
        self.assertRegex(out, r"(?m)^\[root\]  tier=fast")

    def test_grok_explain_says_inherit(self) -> None:
        out = self.explain("grok")
        self.assertIn('selection = "inherit"', out)
        self.assertEqual(out.count("結果：inherit"), 7)

    def test_opencode_names_are_printed_as_json(self) -> None:
        out = self.explain("opencode")
        self.assertIn(
            '結果：{"provider": "deepseek", "model": "deepseek-v4-flash"}', out
        )
        self.assertNotIn("mech-executor", out)  # omitted_roles 不輸出

    def test_explain_does_not_touch_dist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "core", root / "core")
            shutil.copytree(ROOT / "hosts" / "claude", root / "hosts" / "claude")
            shutil.rmtree(root / "hosts" / "claude" / "dist")
            self.assertEqual(run_render("claude", root, "--explain").returncode, 0)
            self.assertFalse((root / "hosts" / "claude" / "dist").exists())


class SwapModelMutationTests(unittest.TestCase):
    """M3：在 temp 複本的 catalog 與某個 host 的 [models] 加一個假模型，只有預期的 role 改變。"""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(ROOT / "core", self.root / "core")
        shutil.copytree(
            ROOT / "hosts",
            self.root / "hosts",
            ignore=shutil.ignore_patterns("plugin", "dist"),
        )

    def append(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.write_text(
            path.read_text(encoding="utf-8") + text, encoding="utf-8", newline="\n"
        )

    def add_model(self, key: str, capability: int, cost: int) -> None:
        vendor = key.split("/")[0]
        self.append(
            "core/models.toml",
            f'\n[models."{key}"]\nvendor = "{vendor}"\ncapability = {capability}\ncost = {cost}\n',
        )

    def changed(self, host: str) -> dict[str, tuple[bytes, bytes]]:
        before = render.RENDERERS[host](ROOT)
        after = render.RENDERERS[host](self.root)
        self.assertEqual(sorted(before), sorted(after))
        return {
            rel: (before[rel], after[rel])
            for rel in before
            if before[rel] != after[rel]
        }

    def test_catalog_only_model_changes_nothing(self) -> None:
        self.add_model("anthropic/zephyr", 4, 1)  # 沒有 host 宣告可用，所以沒有影響
        self.assertEqual(self.changed("claude"), {})

    def test_claude_new_strong_model_changes_only_strong_roles(self) -> None:
        self.add_model("anthropic/zephyr", 4, 3)  # 比 opus 便宜，達 strong 門檻
        binding = self.root / "hosts" / "claude" / "binding.toml"
        binding.write_text(
            binding.read_text(encoding="utf-8").replace(
                '"anthropic/haiku" = "haiku"\n',
                '"anthropic/haiku" = "haiku"\n"anthropic/zephyr" = "zephyr"\n',
                1,
            ),
            encoding="utf-8",
            newline="\n",
        )
        changed = self.changed("claude")
        self.assertEqual(
            set(changed),
            {
                "agents/verifier.md",
                "agents/security-reviewer.md",
                "agents/security-executor.md",
            },
        )
        for _, after in changed.values():
            self.assertIn(b"\nmodel: zephyr\n", after)

    def test_codex_new_model_obeys_tie_breaking(self) -> None:
        # 與 luna 同 cost、capability 較高：fast 同分取 capability 低的 luna，standard 改選更便宜的新模型
        self.add_model("openai/gpt-6-nova", 3, 1)
        binding = self.root / "hosts" / "codex" / "binding.toml"
        binding.write_text(
            binding.read_text(encoding="utf-8").replace(
                '"openai/gpt-6-sol" = "gpt-6-sol"\n',
                '"openai/gpt-6-sol" = "gpt-6-sol"\n"openai/gpt-6-nova" = "gpt-6-nova"\n',
                1,
            ),
            encoding="utf-8",
            newline="\n",
        )
        self.assertEqual(set(self.changed("codex")), {"agents/executor.toml"})
        self.assertIn(
            b'model = "gpt-6-nova"',
            render.RENDERERS["codex"](self.root)["agents/executor.toml"],
        )

    def test_opencode_new_model_is_written_as_provider_table(self) -> None:
        self.add_model(
            "deepseek/deepseek-v5-flash", 2, 1
        )  # 與現行 fast 同分，key 字典序在後，不改結果
        binding = self.root / "hosts" / "opencode" / "binding.toml"
        binding.write_text(
            binding.read_text(encoding="utf-8").replace(
                "[access.read-only]",
                '"deepseek/deepseek-v5-flash" = { provider = "deepseek", model = "deepseek-v5-flash" }\n\n[access.read-only]',
                1,
            ),
            encoding="utf-8",
            newline="\n",
        )
        # 新增的行接在 [models] 表尾端；結果不變，但新模型已被 resolver 納入候選
        self.assertEqual(self.changed("opencode"), {})
        routing = json.loads(render.RENDERERS["opencode"](self.root)["routing.json"])
        self.assertEqual(
            routing["roles"]["scout"]["candidates"][0]["model"], "deepseek-v4-flash"
        )


if __name__ == "__main__":
    unittest.main()
