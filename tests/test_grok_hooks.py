"""grok 原生 hooks 的測試（docs/specs/grok-workflow，AC-GW-010 至 AC-GW-027）。

腳本以 subprocess 執行 committed dist 裡的檔案，輸入輸出走 stdin/stdout，
與 Grok 實際呼叫 hook 的方式相同。測試只用 temp 目錄當 grok home。
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "hosts" / "grok" / "dist"
HOOKS = DIST / "hooks"
GATE = HOOKS / "pilotfish-grok" / "subagent_stop_gate.py"
GUARD = HOOKS / "pilotfish-grok" / "plan_mode_guard.py"
SHOAL_GUARD = HOOKS / "pilotfish-grok" / "shoal_guard.py"


def run(script: Path, stdin: str | bytes, *args: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    full_env = {k: v for k, v in os.environ.items() if k not in ("PILOTFISH_ROLE", "PILOTFISH_GROK_HOME", "GROK_HOME")}
    full_env.update(env or {})
    data = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
    done = subprocess.run([sys.executable, str(script), *args], input=data, capture_output=True,
                          env=full_env, timeout=30)
    return done.returncode, done.stdout.decode("utf-8")


def gate(role: str, message: object, **extra: object) -> tuple[int, str]:
    payload = {"hookEventName": "subagent_stop", "stopHookActive": False, "lastAssistantMessage": message, **extra}
    return run(GATE, json.dumps(payload), env={"PILOTFISH_ROLE": role})


def blocked(role: str, message: object) -> dict:
    code, out = gate(role, message)
    assert code == 0, code
    result = json.loads(out)
    assert result["decision"] == "block"
    return result


VERIFIER_OK = {
    "confirmed": "Checked both acceptance conditions.\n\nCONFIRMED - tests pass (evidence: run log).",
    "refuted": "REFUTED. Priority P1, Confidence high, Evidence: x, Expected: y, Actual: z, Recheck: w.",
    "inconclusive": "INCONCLUSIVE: the environment lacks a database; retry once one exists.",
    "checkpoint-continue": "Direction checkpoint result: `CONTINUE` because the evidence supports the intent.",
    "checkpoint-pivot": "disposition = PIVOT (the assumption is contradicted)",
    "checkpoint-rollback": "ROLLBACK to the last verified checkpoint.",
    "token-in-the-middle": "Long analysis...\nmore text\nVerdict below.\nCONFIRMED\nAdvisory P3: minor.\n",
}

REVISE_BLOCK = ("Blocker: the slice has no rollback\nEvidence: SPEC.md:40 lists none\n"
                "Minimum revision: add a rollback step\nAcceptance check: SPEC.md names the rollback command")

SECURITY_OK = {
    "severity-and-file-line": "Finding 1\nSeverity: High\nEvidence: src/auth.py:42 trusts the header.\nRemediation: validate.",
    "evidence-gap": "Severity: Medium\nAffected unit: U1\nEvidence gap: the token store is not in the repo.",
    "two-findings": ("1. Severity: P1 - hard-coded key at config/app.toml:7\n"
                     "2. Severity: Low - evidence gap, no access to the CI logs"),
    "no-findings": "I reviewed the trust boundaries of U1 and have no findings.",
    "no-security-findings": "No security findings. Assumption: the proxy strips X-Forwarded-For.",
    "findings-none": "Findings: none",
}


class HookConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads((HOOKS / "pilotfish-grok.json").read_text(encoding="utf-8"))["hooks"]

    def test_subagent_stop_has_three_anchored_entries(self) -> None:  # AC-GW-010
        entries = self.config["SubagentStop"]
        self.assertEqual([e["matcher"] for e in entries], ["^verifier$", "^plan-verifier$", "^security-reviewer$"])
        for entry, role in zip(entries, ("verifier", "plan-verifier", "security-reviewer")):
            (handler,) = entry["hooks"]
            self.assertEqual(handler["type"], "command")
            self.assertEqual(handler["env"], {"PILOTFISH_ROLE": role})
            self.assertEqual(handler["command"], "pilotfish-grok/subagent_stop_gate.py")
            self.assertTrue((HOOKS / handler["command"]).is_file())

    def test_anchored_matchers_do_not_cross_match(self) -> None:  # AC-GW-010
        import re
        matchers = [e["matcher"] for e in self.config["SubagentStop"]]
        hits = {name: [m for m in matchers if re.search(m, name)] for name in ("verifier", "plan-verifier")}
        self.assertEqual(hits, {"verifier": ["^verifier$"], "plan-verifier": ["^plan-verifier$"]})

    def test_plan_mode_guard_entry_matches_only_spawn_subagent(self) -> None:  # AC-GW-027
        entry = self.config["PreToolUse"][0]
        self.assertEqual(entry["matcher"], "^spawn_subagent$")
        self.assertEqual(entry["hooks"][0]["command"], "pilotfish-grok/plan_mode_guard.py")
        self.assertTrue((HOOKS / entry["hooks"][0]["command"]).is_file())

    def test_dispatch_guard_entries(self) -> None:  # dispatch-enforcement R7
        self.assertEqual(len(self.config["PreToolUse"]), 2)
        tool = self.config["PreToolUse"][1]
        self.assertEqual(tool["matcher"], "^(search_replace|write_file|spawn_subagent)$")
        (prompt,) = self.config["UserPromptSubmit"]
        self.assertNotIn("matcher", prompt)
        for entry in (tool, prompt):
            (handler,) = entry["hooks"]
            self.assertEqual(handler["command"], "pilotfish-grok/shoal_guard.py")
            self.assertEqual(handler["env"], {"SHOAL_GUARD_HOST": "grok"})
            self.assertTrue((HOOKS / handler["command"]).is_file())

    def test_scripts_import_only_the_standard_library(self) -> None:  # AC-GW-027
        for script in (GATE, GUARD, SHOAL_GUARD):
            tree = ast.parse(script.read_text(encoding="utf-8"))
            names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
            self.assertLessEqual(names, set(sys.stdlib_module_names), script.name)


@unittest.skipIf(os.name == "nt", "shoal guard is POSIX-only; it is a no-op on Windows")
class DispatchGuardRunsFromDistTests(unittest.TestCase):
    """dist 內的 shoal_guard.py 以 grok 的方式執行：路徑直接 exec，host 由 hook 的 env 提供。"""

    def test_dist_guard_denies_a_subagent_dispatch_with_grok_output(self) -> None:
        payload = {"hookEventName": "pre_tool_use", "sessionId": "gs-1", "promptId": "gp-1", "cwd": "/tmp",
                   "toolName": "spawn_subagent", "toolInput": {"subagent_type": "scout"},
                   "subagentType": "executor", "permissionMode": "default"}
        with tempfile.TemporaryDirectory() as home:
            code, out = run(SHOAL_GUARD, json.dumps(payload),
                            env={"SHOAL_GUARD_HOST": "grok", "SHOAL_GUARD": "enforce", "HOME": home,
                                 "XDG_STATE_HOME": str(Path(home) / "state")})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["decision"], "deny")


class FormatGateTests(unittest.TestCase):
    def test_verifier_accepts_every_documented_token(self) -> None:  # AC-GW-011
        for label, message in VERIFIER_OK.items():
            with self.subTest(label):
                self.assertEqual(gate("verifier", message), (0, ""))

    def test_verifier_blocks_a_reply_without_verdict(self) -> None:  # AC-GW-012
        for message in ("Looks fine to me.", "", "   \n", "confirmed", "The claim holds; READY."):
            with self.subTest(message):
                reason = blocked("verifier", message)["reason"]
                for token in ("CONFIRMED", "REFUTED", "INCONCLUSIVE", "CONTINUE", "PIVOT", "ROLLBACK"):
                    self.assertIn(token, reason)

    def test_plan_verifier_accepts_ready_and_complete_revise(self) -> None:  # AC-GW-013
        samples = {
            "bare-ready": "READY",
            "ready-with-newline": "READY\n",
            "ready-after-preamble": "Reviewed the unit.\nREADY",
            "ready-in-backticks": "`READY`",
            "revise-one-block": "REVISE\n\n" + REVISE_BLOCK,
            "revise-two-blocks": "REVISE\n" + REVISE_BLOCK + "\n\n" + REVISE_BLOCK.replace("rollback", "budget"),
            "revise-markdown-bullets": "REVISE\n- **Blocker:** a\n- **Evidence:** b\n- **Minimum revision:** c\n"
                                       "- **Acceptance check:** d",
        }
        for label, message in samples.items():
            with self.subTest(label):
                self.assertEqual(gate("plan-verifier", message), (0, ""))

    def test_plan_verifier_blocks_prose_and_incomplete_revise(self) -> None:  # AC-GW-013
        reason = blocked("plan-verifier", "The plan looks reasonable overall.")["reason"]
        self.assertIn("READY", reason)
        self.assertIn("no 'Blocker:' block", blocked("plan-verifier", "REVISE")["reason"])
        for field in ("Evidence", "Minimum revision", "Acceptance check"):
            partial = "\n".join(line for line in REVISE_BLOCK.splitlines() if not line.startswith(field))
            reason = blocked("plan-verifier", "REVISE\n" + partial)["reason"]
            self.assertIn(f"missing: {field}", reason)
        second_partial = REVISE_BLOCK + "\n\nBlocker: another\nEvidence: gap"
        reason = blocked("plan-verifier", "REVISE\n" + second_partial)["reason"]
        self.assertIn("block 2 is missing: Minimum revision, Acceptance check", reason)
        self.assertNotIn("block 1", reason)

    def test_security_reviewer_accepts_complete_findings(self) -> None:  # AC-GW-014
        for label, message in SECURITY_OK.items():
            with self.subTest(label):
                self.assertEqual(gate("security-reviewer", message), (0, ""))

    def test_security_reviewer_blocks_incomplete_findings(self) -> None:  # AC-GW-014
        cases = {
            "no-severity": ("Finding 1\nEvidence: src/auth.py:42 trusts the header.", "finding 1 has no severity"),
            "no-evidence": ("Finding 1\nSeverity: High\nThe header is trusted.", "finding 1 has neither"),
            "second-lacks-evidence": ("Severity: High\nsrc/a.py:1 is bad.\nSeverity: Low\nminor", "finding 2 has neither"),
            "neither": ("The code seems OK, I looked at several files.", "no finding with a severity"),
            "empty": ("", "no finding with a severity"),
        }
        for label, (message, expected) in cases.items():
            with self.subTest(label):
                self.assertIn(expected, blocked("security-reviewer", message)["reason"])

    def test_stop_hook_active_always_allows(self) -> None:  # AC-GW-015
        for role in ("verifier", "plan-verifier", "security-reviewer"):
            with self.subTest(role):
                self.assertEqual(gate(role, "nonsense", stopHookActive=True), (0, ""))

    def test_fails_open_on_unparseable_input(self) -> None:  # AC-GW-016
        env = {"PILOTFISH_ROLE": "verifier"}
        for stdin in ("{not json", "", "[]", "null", '"text"', "{}", '{"lastAssistantMessage": 7}',
                      '{"lastAssistantMessage": null}', b"\xff\xfe\x00bad"):
            with self.subTest(stdin):
                self.assertEqual(run(GATE, stdin, env=env), (0, ""))

    def test_fails_open_when_role_is_unknown_or_missing(self) -> None:  # AC-GW-016
        payload = json.dumps({"lastAssistantMessage": "nonsense"})
        self.assertEqual(run(GATE, payload, env={"PILOTFISH_ROLE": "executor"}), (0, ""))
        self.assertEqual(run(GATE, payload), (0, ""))
        self.assertEqual(run(GATE, payload, "ghost"), (0, ""))

    def test_role_argument_overrides_environment(self) -> None:  # AC-GW-010
        payload = json.dumps({"lastAssistantMessage": "READY"})
        self.assertEqual(run(GATE, payload, "plan-verifier", env={"PILOTFISH_ROLE": "verifier"}), (0, ""))
        code, out = run(GATE, payload, "verifier", env={"PILOTFISH_ROLE": "plan-verifier"})
        self.assertEqual((code, json.loads(out)["decision"]), (0, "block"))

    def test_gate_tokens_still_appear_in_agent_text(self) -> None:  # AC-GW-017
        agents = {n: " ".join((DIST / "agents" / f"{n}.md").read_text(encoding="utf-8").split())  # 折行不影響比對
                  for n in ("verifier", "plan-verifier", "security-reviewer")}
        for token in ("CONFIRMED", "REFUTED", "INCONCLUSIVE", "CONTINUE", "PIVOT", "ROLLBACK", "direction_checkpoint"):
            self.assertIn(token, agents["verifier"], token)
        for token in ("READY", "REVISE", "Blocker:", "Evidence:", "Minimum revision:", "Acceptance check:"):
            self.assertIn(token, agents["plan-verifier"], token)
        for token in ("severity", "file:line", "evidence gap"):
            self.assertIn(token, agents["security-reviewer"], token)


def spawn(mode: str | None = None, subagent_type: str | None = None, permission: str = "plan") -> str:
    tool_input: dict[str, object] = {"prompt": "do it", "description": "task"}
    if mode is not None:
        tool_input["capability_mode"] = mode
    if subagent_type is not None:
        tool_input["subagent_type"] = subagent_type
    return json.dumps({"hookEventName": "pre_tool_use", "permissionMode": permission,
                       "toolName": "spawn_subagent", "toolInput": tool_input})


class PlanModeGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        (self.home / "roles").mkdir()
        for role in (DIST / "roles").glob("*.toml"):
            (self.home / "roles" / role.name).write_bytes(role.read_bytes())

    def call(self, stdin: str, *args: str, env: dict[str, str] | None = None) -> tuple[int, str]:
        return run(GUARD, stdin, "--grok-home", str(self.home), *args, env=env)

    def assert_denied(self, stdin: str, *args: str, env: dict[str, str] | None = None) -> dict:
        code, out = self.call(stdin, *args, env=env)
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["decision"], "deny")
        return result

    def test_other_permission_modes_are_never_blocked(self) -> None:  # AC-GW-020
        for mode in ("default", "auto", "bypassPermissions"):
            with self.subTest(mode):
                self.assertEqual(self.call(spawn("all", "executor", permission=mode)), (0, ""))
        self.assertEqual(self.call(json.dumps({"toolInput": {"capability_mode": "all"}})), (0, ""))

    def test_explicit_capability_mode_decides(self) -> None:  # AC-GW-021
        self.assertEqual(self.call(spawn("read-only", "executor")), (0, ""))  # 即使 role 預設可寫入
        self.assertEqual(self.call(spawn("execute", "executor")), (0, ""))
        self.assert_denied(spawn("read-write", "scout"))  # 即使 role 預設唯讀
        self.assert_denied(spawn("all", "plan-verifier"))

    def test_role_default_capability_mode_is_used_without_override(self) -> None:  # AC-GW-022
        for role in ("scout", "plan-verifier", "security-reviewer", "verifier"):
            with self.subTest(role):
                self.assertEqual(self.call(spawn(None, role)), (0, ""))
        for role in ("executor", "mech-executor", "security-executor"):
            with self.subTest(role):
                self.assertIn("default_capability_mode=", self.assert_denied(spawn(None, role))["reason"])

    def test_builtin_types_without_role_file(self) -> None:  # AC-GW-023
        for subagent_type in ("explore", "plan"):
            self.assertEqual(self.call(spawn(None, subagent_type)), (0, ""))
        self.assert_denied(spawn(None, "general-purpose"))
        self.assert_denied(spawn(None, None))

    def test_deny_reason_says_to_leave_plan_mode(self) -> None:  # AC-GW-026
        reason = self.assert_denied(spawn("all"))["reason"]
        self.assertIn("exit_plan_mode", reason)
        self.assertIn("plan mode", reason.lower())

    def test_fails_open_when_it_cannot_decide(self) -> None:  # AC-GW-024
        (self.home / "roles" / "broken.toml").write_text("default_capability_mode = [", encoding="utf-8", newline="\n")
        (self.home / "roles" / "weird.toml").write_text('default_capability_mode = "sudo"\n', encoding="utf-8", newline="\n")
        (self.home / "roles" / "empty.toml").write_text('description = "x"\n', encoding="utf-8", newline="\n")
        cases = {
            "invalid json": "{nope",
            "empty stdin": "",
            "toolInput not an object": json.dumps({"permissionMode": "plan", "toolInput": "all"}),
            "no toolInput": json.dumps({"permissionMode": "plan"}),
            "unknown custom type": spawn(None, "custom-agent"),
            "broken role toml": spawn(None, "broken"),
            "unknown mode in role toml": spawn(None, "weird"),
            "role toml without mode": spawn(None, "empty"),
            "unknown explicit mode": spawn("sudo", "executor"),
            "path traversal": spawn(None, "../roles/executor"),
            "slash in type": spawn(None, "a/b"),
            "type not a string": json.dumps({"permissionMode": "plan", "toolInput": {"subagent_type": 7}}),
        }
        for label, stdin in cases.items():
            with self.subTest(label):
                self.assertEqual(self.call(stdin), (0, ""))

    def test_missing_grok_home_falls_back_to_builtin_rules(self) -> None:  # AC-GW-024
        ghost = str(self.home / "does-not-exist")
        self.assertEqual(run(GUARD, spawn(None, "explore"), "--grok-home", ghost), (0, ""))
        self.assertEqual(json.loads(run(GUARD, spawn(None, "general-purpose"), "--grok-home", ghost)[1])["decision"], "deny")
        self.assertEqual(run(GUARD, spawn(None, "executor"), "--grok-home", ghost), (0, ""))  # 無法判斷，放行

    def test_grok_home_priority(self) -> None:  # AC-GW-025
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        (Path(other.name) / "roles").mkdir()
        (Path(other.name) / "roles" / "executor.toml").write_text('default_capability_mode = "read-only"\n', encoding="utf-8", newline="\n")
        stdin = spawn(None, "executor")
        # 沒有參數時用環境變數；PILOTFISH_GROK_HOME 優先於 GROK_HOME
        self.assertEqual(run(GUARD, stdin, env={"GROK_HOME": other.name}), (0, ""))
        self.assertEqual(run(GUARD, stdin, env={"GROK_HOME": str(self.home), "PILOTFISH_GROK_HOME": other.name}), (0, ""))
        self.assertEqual(json.loads(run(GUARD, stdin, env={"PILOTFISH_GROK_HOME": str(self.home),
                                                           "GROK_HOME": other.name})[1])["decision"], "deny")
        # --grok-home（含 = 寫法）優先於環境變數
        self.assertEqual(run(GUARD, stdin, f"--grok-home={other.name}", env={"GROK_HOME": str(self.home)}), (0, ""))
        self.assertEqual(json.loads(run(GUARD, stdin, "--grok-home", str(self.home),
                                        env={"PILOTFISH_GROK_HOME": other.name})[1])["decision"], "deny")

    def test_default_home_is_dot_grok(self) -> None:  # AC-GW-025
        fake_home = tempfile.TemporaryDirectory()
        self.addCleanup(fake_home.cleanup)
        roles = Path(fake_home.name) / ".grok" / "roles"
        roles.mkdir(parents=True)
        (roles / "executor.toml").write_text('default_capability_mode = "read-only"\n', encoding="utf-8", newline="\n")
        self.assertEqual(run(GUARD, spawn(None, "executor"), env={"HOME": fake_home.name}), (0, ""))


if __name__ == "__main__":
    unittest.main()
