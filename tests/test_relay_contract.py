"""cross-vendor-relay T1.1：hand-back schema、core/vendors.toml 與 runner 的純函式（S1.2、S1.17）。"""

from __future__ import annotations

import json
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import shoal_relay  # noqa: E402

SCHEMA = json.loads(
    (ROOT / "core" / "contracts" / "handback.schema.json").read_text(encoding="utf-8")
)
VENDORS = tomllib.loads((ROOT / "core" / "vendors.toml").read_text(encoding="utf-8"))[
    "vendors"
]
CODEX = VENDORS["codex"]


def _walk(schema, where="$"):
    yield where, schema
    for key, sub in schema.get("properties", {}).items():
        yield from _walk(sub, f"{where}.{key}")
    if "items" in schema:
        yield from _walk(schema["items"], f"{where}[]")


def _types(schema):
    t = schema.get("type")
    return [t] if isinstance(t, str) else (t or [])


def valid_handback():
    return {
        "status": "done",
        "summary": "ok",
        "changed_files": ["a.txt"],
        "checks": [{"cmd": "make test", "exit": 0, "decisive_line": "OK"}],
        "unverified": [],
        "vendor": "codex",
        "session_id": "t-1",
        "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 2},
        "reported_files": ["a.txt"],
        "files_mismatch": False,
        "reason": None,
        "exit_code": 0,
        "stderr_tail": None,
        "partial_output": None,
        "landing": None,
    }


class HandbackSchemaIsStrict(unittest.TestCase):
    def test_every_object_is_closed_and_fully_required(self):
        for where, node in _walk(SCHEMA):
            if "object" in _types(node):
                with self.subTest(where=where):
                    self.assertIs(node.get("additionalProperties"), False)
                    self.assertEqual(
                        sorted(node["required"]), sorted(node["properties"])
                    )

    def test_strings_and_arrays_are_bounded(self):
        for where, node in _walk(SCHEMA):
            with self.subTest(where=where):
                if "string" in _types(node) and "enum" not in node:
                    self.assertIn("maxLength", node)
                if "array" in _types(node):
                    self.assertIn("maxItems", node)

    def test_d4_fields_present(self):
        for field in (
            "status",
            "summary",
            "changed_files",
            "checks",
            "unverified",
            "vendor",
            "session_id",
            "usage",
        ):
            self.assertIn(field, SCHEMA["properties"])
        self.assertEqual(
            SCHEMA["properties"]["status"]["enum"], ["done", "blocked", "failed"]
        )

    def test_vendor_schema_is_strict_subset(self):
        check, strict = shoal_relay.vendor_schemas(SCHEMA)
        self.assertEqual(
            sorted(strict["properties"]), sorted(shoal_relay.VENDOR_FIELDS)
        )
        for where, node in _walk(strict):
            with self.subTest(where=where):
                self.assertLessEqual(set(node), shoal_relay.STRICT_KEYS)
                if "object" in _types(node):
                    self.assertIs(node["additionalProperties"], False)
                    self.assertEqual(
                        sorted(node["required"]), sorted(node["properties"])
                    )
        self.assertEqual(check["properties"]["summary"]["maxLength"], 4000)

    def test_s1_17_rejects_extra_fields_and_long_strings(self):
        self.assertIsNone(shoal_relay.schema_error(SCHEMA, valid_handback()))
        extra = {**valid_handback(), "note": "x"}
        self.assertIn("unexpected field", shoal_relay.schema_error(SCHEMA, extra))
        nested = valid_handback()
        nested["checks"][0]["extra"] = 1
        self.assertIn("unexpected field", shoal_relay.schema_error(SCHEMA, nested))
        long = {**valid_handback(), "summary": "x" * 4001}
        self.assertIn("longer than", shoal_relay.schema_error(SCHEMA, long))
        self.assertIn(
            "expected",
            shoal_relay.schema_error(SCHEMA, {**valid_handback(), "exit_code": True}),
        )
        missing = valid_handback()
        del missing["usage"]
        self.assertIn("missing field", shoal_relay.schema_error(SCHEMA, missing))

    def test_landing_is_runner_only_and_closed(self):
        landing = {"landed": False, "reason": "patch does not apply", "worktree": "/r/.claude/worktrees/a",
                   "head": None, "tree": None}
        landed = {**landing, "landed": True, "reason": None, "head": "a" * 40, "tree": "b" * 40}
        self.assertIsNone(shoal_relay.schema_error(SCHEMA, {**valid_handback(), "landing": landed}))
        self.assertIsNone(shoal_relay.schema_error(SCHEMA, {**valid_handback(), "landing": landing}))
        self.assertIn(
            "unexpected field",
            shoal_relay.schema_error(SCHEMA, {**valid_handback(), "landing": {**landing, "x": 1}}),
        )
        self.assertNotIn("landing", shoal_relay.vendor_schemas(SCHEMA)[1]["properties"])


class LandingPaths(unittest.TestCase):
    """fix/relay-landing：diff-tree raw 輸出中任何一筆不安全，整份 patch 拒絕落地。"""

    OK = ":100644 100644 aaa bbb M"

    def check(self, *entries):
        return shoal_relay._check_landing_diff("".join(f"{m}\0{p}\0" for m, p in entries))

    def test_plain_paths_pass(self):
        self.check((self.OK, "src/a.py"), (":000000 100644 000 ccc A", "bin/run"), (":100644 000000 aaa 000 D", "old.txt"),
                   (":100755 100644 aaa bbb M", "was-exec.sh"), (self.OK, "docs/CLAUDE.txt"), (self.OK, "vscode/x"))

    def test_refused_names_and_paths_outside_the_repo(self):
        for path in (".git/config", "a/.GIT/hooks/x", ".codex/config.toml", "x/.Claude/settings.json",
                     "../outside", "/etc/passwd", "a//b", "./a"):
            with self.subTest(path=path), self.assertRaises(shoal_relay.NotLanded) as ctx:
                self.check((self.OK, "ok.txt"), (self.OK, path))
            self.assertIn("refused", str(ctx.exception))

    def test_h1_instruction_and_autorun_files_are_refused(self):
        for path in ("CLAUDE.md", "a/b/claude.MD", "CLAUDE.local.md", "AGENTS.md", "x/GEMINI.md",
                     "\uff21\uff27\uff25\uff2e\uff34\uff33.md", "CLAUDE\u200d.md", "\u200b.claude/x",
                     ".mcp.json", ".gitattributes", "a/.GitAttributes", ".gitmodules", ".envrc",
                     ".vscode/settings.json", "a/.Husky/pre-commit", ".githooks/pre-push", ".pre-commit-config.yaml"):
            with self.subTest(path=path), self.assertRaises(shoal_relay.NotLanded) as ctx:
                self.check((self.OK, "ok.txt"), (self.OK, path))
            self.assertTrue(str(ctx.exception).startswith("refused"))

    def test_h1_exec_bit_is_refused(self):
        for meta in (":000000 100755 000 ccc A", ":100644 100755 aaa aaa M", ":100644 100755 aaa ccc M"):
            with self.subTest(meta=meta), self.assertRaises(shoal_relay.NotLanded) as ctx:
                self.check((meta, "run.sh"))
            self.assertTrue(str(ctx.exception).startswith("refused"))

    def test_symlinks_and_submodules_are_refused(self):
        for meta in (":000000 120000 000 ccc A", ":100644 120000 aaa ccc T", ":000000 160000 000 ccc A", ":160000 000000 ccc 000 D"):
            with self.subTest(meta=meta), self.assertRaises(shoal_relay.NotLanded):
                self.check((meta, "link"))


class VendorsToml(unittest.TestCase):
    def test_codex_pins_from_t1_0(self):
        pins = set(CODEX["pins"])
        for pin in (
            'approval_policy="never"',
            "sandbox_workspace_write.writable_roots=[]",
            "sandbox_workspace_write.network_access=false",
            "sandbox_workspace_write.exclude_slash_tmp=true",
            'web_search="disabled"',
            "features.apps=false",
            "features.plugins=false",
            'shell_environment_policy.inherit="core"',
            "shell_environment_policy.ignore_default_excludes=false",
        ):
            self.assertIn(pin, pins)
        self.assertFalse(
            any("forced_login_method" in p for p in pins)
        )  # T1.0 後的決策：F6 不 pin

    def test_codex_command_and_policy(self):
        self.assertEqual(CODEX["min_version"], "0.160.1")
        self.assertEqual(
            CODEX["exec_args"], ["exec", "--json", "--ephemeral", "--strict-config"]
        )
        self.assertEqual(
            CODEX["sandbox"],
            {
                "read-only": "read-only",
                "write": "workspace-write",
                "verify": "workspace-write",
            },
        )
        self.assertEqual(
            CODEX["env"], ["PATH", "HOME", "USER", "LANG", "TERM", "CODEX_HOME"]
        )
        self.assertEqual(
            CODEX["mcp_disable"].format(id="x"), "mcp_servers.x.enabled=false"
        )
        self.assertTrue(all(p.startswith(("/", "~/")) for p in CODEX["paths"]))
        text = (ROOT / "core" / "vendors.toml").read_text(encoding="utf-8")
        for value in [*CODEX["pins"], *CODEX["exec_args"], *CODEX["sandbox"].values()]:
            self.assertIsNone(shoal_relay.FORBIDDEN_ARG.search(value))
        self.assertNotIn("danger-full-access =", text)

    def test_relay_roles_match_core_access(self):
        roles = tomllib.loads(
            (ROOT / "core" / "roles.toml").read_text(encoding="utf-8")
        )["roles"]
        for role, access in shoal_relay.RELAY_ROLES.items():
            self.assertEqual(roles[role]["access"], access)
            self.assertFalse(roles[role].get("security"))


class BuildArgv(unittest.TestCase):
    def build(self, access, cfg=CODEX):
        return shoal_relay.build_argv(
            "/abs/codex",
            cfg,
            access,
            Path("/p/s.json"),
            Path("/p/o.json"),
            Path("/wt"),
            "brief",
            ["srv-a"],
        )

    def test_s1_2_access_maps_to_sandbox(self):
        for access, mode in (
            ("read-only", "read-only"),
            ("write", "workspace-write"),
            ("verify", "workspace-write"),
        ):
            with self.subTest(access=access):
                argv = self.build(access)
                self.assertEqual(argv[argv.index("--sandbox") + 1], mode)
                self.assertIn("mcp_servers.srv-a.enabled=false", argv)
                for pin in CODEX["pins"]:
                    self.assertEqual(argv[argv.index(pin) - 1], "-c")
                self.assertFalse(any(shoal_relay.FORBIDDEN_ARG.search(t) for t in argv))
                self.assertEqual(argv[-1], "brief")

    def test_s1_2_refuses_bypass_flags_even_if_configured(self):
        for bad in (
            'sandbox_mode="danger-full-access"',
            "--dangerously-bypass-approvals-and-sandbox",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(shoal_relay.Blocked):
                    self.build("write", {**CODEX, "pins": [*CODEX["pins"], bad]})
        with self.assertRaises(shoal_relay.Blocked):
            self.build("write", {**CODEX, "sandbox": {"write": "danger-full-access"}})


if __name__ == "__main__":
    unittest.main()
