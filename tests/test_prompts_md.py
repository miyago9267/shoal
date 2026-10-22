"""prompts/*.md 的 marker 語法：條款、addendum、description 與 text 區塊的解析規則（text-first T2.2）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from render_helpers import ROOT, render

import contracts  # noqa: E402  (render_helpers 已把 tools/ 放進 sys.path)


def clauses(text: str, **kw) -> list[contracts.Clause]:
    return contracts.parse_markdown_contract(text, "t.md", **kw)


def addenda(text: str) -> list[contracts.Addendum]:
    return contracts.parse_markdown_addenda(text, "t.md")


class ClauseParseTests(unittest.TestCase):
    def test_leading_and_trailing_blank_lines_are_not_text(self) -> None:
        got = clauses(
            "\n\n<!-- clause: a kind=leaf -->\n\n\nA.\n\n\n<!-- clause: b kind=leaf -->\nB.\n\n"
        )
        self.assertEqual([c.text for c in got], ["A.", "B."])

    def test_inner_blank_lines_and_indentation_are_kept_verbatim(self) -> None:
        got = clauses("<!-- clause: a kind=leaf -->\nOne.\n\n  - two\n\nThree.\n")
        self.assertEqual(got[0].text, "One.\n\n  - two\n\nThree.")

    def test_sep_defaults_to_paragraph_and_required_is_a_flag(self) -> None:
        got = clauses(
            "<!-- clause: a kind=gate -->\nA.\n<!-- clause: b kind=gate sep=newline required -->\nB.\n",
            kinds=contracts.POLICY_KINDS,
            allow_required=True,
        )
        self.assertEqual(
            [(c.sep, c.required) for c in got],
            [("paragraph", False), ("newline", True)],
        )

    def test_required_is_rejected_for_role_clauses(self) -> None:
        with self.assertRaisesRegex(contracts.ContractError, "未知欄位 required"):
            clauses("<!-- clause: a kind=leaf required -->\nA.\n")

    def test_duplicate_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(contracts.ContractError, "id 重複"):
            clauses(
                "<!-- clause: a kind=leaf -->\nA.\n<!-- clause: a kind=leaf -->\nB.\n"
            )

    def test_content_before_the_first_marker_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            contracts.ContractError, "第 1 行.*第一個 marker 之前"
        ):
            clauses("preface\n<!-- clause: a kind=leaf -->\nA.\n")

    def test_marker_text_inside_a_line_is_ordinary_text(self) -> None:
        body = "See `<!-- clause: x kind=leaf -->` for the syntax."
        self.assertEqual(
            clauses(f"<!-- clause: a kind=leaf -->\n{body}\n")[0].text, body
        )

    def test_a_body_line_that_starts_like_a_marker_is_rejected(self) -> None:
        for line in (
            "<!-- clause: b kind=leaf --> trailing",
            "<!-- clause:b kind=leaf -->",
            "<!-- addendum: b at=end -->",
        ):
            with (
                self.subTest(line=line),
                self.assertRaisesRegex(contracts.ContractError, "marker"),
            ):
                clauses(f"<!-- clause: a kind=leaf -->\nA.\n{line}\nB.\n")

    def test_cr_is_rejected(self) -> None:
        with self.assertRaisesRegex(contracts.ContractError, "CR"):
            clauses("<!-- clause: a kind=leaf -->\r\nA.\r\n")

    def test_missing_kind_unknown_attribute_and_empty_text_are_rejected(self) -> None:
        cases = {
            "缺少欄位 kind": "<!-- clause: a -->\nA.\n",
            "未知欄位 color": "<!-- clause: a kind=leaf color=red -->\nA.\n",
            "屬性 kind 重複": "<!-- clause: a kind=leaf kind=scope -->\nA.\n",
            "非空字串": "<!-- clause: a kind=leaf -->\n\n",
            "至少要有": "\n\n",
        }
        for expected, text in cases.items():
            with (
                self.subTest(expected=expected),
                self.assertRaisesRegex(contracts.ContractError, expected),
            ):
                clauses(text)

    def test_leading_indentation_on_the_first_line_is_rejected(self) -> None:
        with self.assertRaisesRegex(contracts.ContractError, "頭尾不可有空白"):
            clauses("<!-- clause: a kind=leaf -->\n  A.\n")


class AddendumParseTests(unittest.TestCase):
    def test_at_sep_and_join_round_trip(self) -> None:
        got = addenda(
            "<!-- addendum: x at=after:one sep=space join=newline -->\nX.\n\n<!-- addendum: y at=end -->\nY.\n"
        )
        self.assertEqual(
            got,
            [
                contracts.Addendum("x", "after:one", "X.", "space", "newline"),
                contracts.Addendum("y", "end", "Y.", None, None),
            ],
        )

    def test_empty_file_means_no_addenda_and_missing_at_is_rejected(self) -> None:
        self.assertEqual(addenda(""), [])
        with self.assertRaisesRegex(contracts.ContractError, "缺少欄位 at"):
            addenda("<!-- addendum: x -->\nX.\n")

    def test_clause_marker_in_an_addendum_file_is_rejected(self) -> None:
        with self.assertRaisesRegex(contracts.ContractError, "只接受 `addendum`"):
            addenda("<!-- clause: x kind=leaf -->\nX.\n")


class BlockParseTests(unittest.TestCase):
    def test_description_blocks_keep_multiple_lines(self) -> None:
        got = contracts.parse_markdown_blocks(
            "<!-- description: scout -->\nLine one,\nline two.\n\n<!-- description: Explore -->\nE.\n",
            "d.md",
            "description",
        )
        self.assertEqual(got, {"scout": "Line one,\nline two.", "Explore": "E."})

    def test_duplicate_key_extra_attribute_and_bad_key_are_rejected(self) -> None:
        cases = {
            "key 重複": "<!-- text: a -->\nA.\n<!-- text: a -->\nB.\n",
            "只能有一個 key": "<!-- text: a b=c -->\nA.\n",
            "英數加連字號": "<!-- text: a_b -->\nA.\n",
        }
        for expected, text in cases.items():
            with (
                self.subTest(expected=expected),
                self.assertRaisesRegex(contracts.ContractError, expected),
            ):
                contracts.parse_markdown_blocks(text, "t.md", "text")

    def test_missing_file_means_no_blocks(self) -> None:
        self.assertEqual(
            contracts.load_blocks(Path("/nonexistent/text.md"), "text"), {}
        )


class HostBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "hosts" / "h").mkdir(parents=True)
        (self.root / "hosts" / "h" / "binding.toml").write_text(
            '[roles.scout]\n[roles.executor]\ndescription = "inline"\n[extra_roles.Odd]\nmodel = "m"\n',
            encoding="utf-8",
        )
        self.descriptions = self.root / "prompts" / "hosts" / "h" / "descriptions.md"
        self.descriptions.parent.mkdir(parents=True)

    def test_descriptions_fill_roles_and_extra_roles(self) -> None:
        self.descriptions.write_text(
            "<!-- description: scout -->\nS.\n<!-- description: Odd -->\nO.\n",
            encoding="utf-8",
        )
        binding = render.load_host_binding(self.root, "h")
        self.assertEqual(binding["roles"]["scout"]["description"], "S.")
        self.assertEqual(binding["extra_roles"]["Odd"]["description"], "O.")
        self.assertEqual(binding["roles"]["executor"]["description"], "inline")

    def test_unknown_role_and_duplicate_source_are_rejected(self) -> None:
        for expected, text in {
            "binding 沒有 role ghost": "<!-- description: ghost -->\nG.\n",
            "同時出現在 binding.toml": "<!-- description: executor -->\nE.\n",
        }.items():
            self.descriptions.write_text(text, encoding="utf-8")
            with (
                self.subTest(expected=expected),
                self.assertRaisesRegex(render.RenderError, expected),
            ):
                render.load_host_binding(self.root, "h")


class RepoPromptsTests(unittest.TestCase):
    """repo 內的 prompts 與 TOML 的分工：文字只在 prompts/，binding 不再有 description。"""

    def test_bindings_of_the_four_hosts_carry_no_description(self) -> None:
        for host in ("claude", "codex", "agy", "grok"):
            with self.subTest(host=host):
                binding = render.load_toml(ROOT / "hosts" / host / "binding.toml")
                for table in ("roles", "extra_roles"):
                    for name, spec in binding.get(table, {}).items():
                        self.assertNotIn("description", spec, f"{host} {name}")
                self.assertTrue(
                    (ROOT / "prompts" / "hosts" / host / "descriptions.md").is_file()
                )

    def test_every_text_key_used_by_render_exists(self) -> None:
        texts = render.load_texts(ROOT / "hosts" / "claude")
        self.assertEqual(
            sorted(texts),
            sorted(
                [
                    "relay-write-rules",
                    "relay-run-step",
                    "relay-description-suffix",
                    "relay-write-description-suffix",
                    "plugin-hooks-description",
                    "guard-hooks-description",
                    "plugin-description",
                    "guard-plugin-description",
                    "marketplace-description",
                    "marketplace-plugin-description",
                    "marketplace-guard-description",
                ]
            ),
        )

    def test_run_step_has_the_two_timing_placeholders_and_no_arithmetic(self) -> None:
        text = render.load_texts(ROOT / "hosts" / "claude")["relay-run-step"]
        self.assertEqual(
            contracts.placeholder_keys(text), {"timeout", "bash_timeout_ms"}
        )
        self.assertNotIn("*", text)
        self.assertNotIn("+", text)
        self.assertEqual(
            render.text_for({"k": text}, "k", render._relay_timing(540)),
            "Call Bash with `timeout: 600000` so it outlives the runner's 540s limit.",
        )


if __name__ == "__main__":
    unittest.main()
