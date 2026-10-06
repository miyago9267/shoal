#!/usr/bin/env python3
"""Offline tests for ``install/claude_live_probe.py`` (claude-eval-parity AC-CE-018).

Nothing here starts ``claude`` or touches the user's real config: the child
process is a stub, the user config is a temporary directory reached through the
patched ``user_config_dir`` and the token is an obvious placeholder.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))
import claude_live_probe as probe  # noqa: E402
import role_fitness_claude as claude  # noqa: E402
from role_fitness_fixtures import BenchmarkContractError  # noqa: E402
from role_fitness_stage import (  # noqa: E402
    StageEvidenceError,
    StageRequest,
    StageSetupError,
)

SCRIPT = ROOT / "install" / "claude_live_probe.py"
SAMPLES = ROOT / "tests" / "fixtures" / "claude_stream"
FAKE_TOKEN = "placeholder-probe-token-for-offline-tests"
TOKEN_ENV = claude.SUBSCRIPTION_TOKEN_ENV
FREE_TEXT = "SENTINEL model sentence that must never be reported"
STAGED = sorted(
    path.stem for path in (ROOT / "hosts" / "claude" / "dist" / "agents").iterdir()
)
ALL = "auth,dispatch,budget"


def _events(name: str) -> list[dict[str, Any]]:
    text = (SAMPLES / f"{name}.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def _stream(events: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(event) + "\n" for event in events)


def stage_events(
    stage: str,
    *,
    init: dict[str, Any] | None = None,
    cwd: str = "/synthetic",
    sample: str | None = None,
) -> list[dict[str, Any]]:
    """A synthetic stream for one probe stage, seeded with unreportable text."""
    events = _events(
        sample or ("dispatch-ok" if stage == "dispatch" else "no-agent-call")
    )
    events = json.loads(json.dumps(events).replace("plan-verifier", "scout"))
    for event in events:
        if event["type"] == "system" and event["subtype"] == "init":
            event.update(
                {
                    "agents": STAGED + ["general-purpose"],
                    "skills": [],
                    "slash_commands": ["init"],
                    "plugins": [],
                    "hooks": [],
                    "apiKeySource": "none",
                    "cwd": cwd,
                }
            )
            event.update(init or {})
        for key in ("description", "prompt", "summary", "output_file"):
            if event["type"] == "system" and key in event:
                event[key] = FREE_TEXT
        if event["type"] == "result":
            event["result"] = FREE_TEXT
    for event in events:
        content = event.get("message", {}).get("content")
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "text":
                block["text"] = FREE_TEXT
            if block.get("type") == "tool_use":
                block["input"]["prompt"] = FREE_TEXT
    events[-1]["result"] = FREE_TEXT
    if stage == "budget":
        events[-1].update({"subtype": "error_max_budget_usd", "is_error": True})
    return events


def stage_of(prompt: str) -> str:
    if "subagent_type" in prompt:
        return "dispatch"
    return "budget" if probe.BUDGET_INPUT_FILE in prompt else "auth"


class _Host:
    """Stands in for ``subprocess.run``; replays one stream per probe stage."""

    def __init__(
        self, *, transcript: bool = True, on_run: Any = None, **overrides: Any
    ) -> None:
        self.transcript = transcript
        self.on_run = on_run
        self.overrides = overrides
        self.calls: list[dict[str, Any]] = []

    def run(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        env = dict(kwargs["env"])
        config, cwd = Path(env["CLAUDE_CONFIG_DIR"]), Path(kwargs["cwd"])
        stage = stage_of(kwargs["input"])
        self.calls.append(
            {
                "stage": stage,
                "argv": list(argv),
                "env": env,
                "input": kwargs["input"],
                "cwd": cwd,
                "cwd_files": sorted(path.name for path in cwd.iterdir()),
                "staged_agents": sorted(
                    path.stem for path in (cwd / ".claude" / "agents").iterdir()
                ),
            }
        )
        if self.transcript:
            project = config / "projects" / probe._munge(str(cwd))
            project.mkdir(parents=True)
            (project / "00000000-0000-4000-8000-000000000009.jsonl").write_text(
                "x", encoding="utf-8"
            )
            (config / ".credentials.json").write_text("{}", encoding="utf-8")
        (Path(env["HOME"]) / ".claude.json").write_text("{}", encoding="utf-8")
        if self.on_run is not None:
            self.on_run(stage, cwd)
        override = self.overrides.get(stage, {})
        stdout = override.get("stdout")
        if stdout is None:
            stdout = _stream(
                override.get("events") or stage_events(stage, cwd=str(cwd))
            )
        returncode = override.get("returncode", 1 if stage == "budget" else 0)
        return subprocess.CompletedProcess(
            argv, returncode, stdout, override.get("stderr", "")
        )


class ProbeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="lp-case-")))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.home = self.root / "user-home"
        self.config = self.home / ".claude"
        for relative in (
            "settings.json",
            "AGENTS.md",
            "agents/scout.md",
            "agents/my-private-agent.md",
            "skills/my-skill/SKILL.md",
            "commands/my-command.md",
            "hooks/on-stop.sh",
            "rules/shared.md",
            "memories/MEMORY.md",
            "projects/-other-session/log.jsonl",
            "history.jsonl",
        ):
            path = self.config / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("user content sentinel", encoding="utf-8")
        self.tmp = self.root / "tmp"
        self.tmp.mkdir()
        self.roots: list[Path] = []

        def make_root() -> Path:
            self.roots.append(
                Path(tempfile.mkdtemp(prefix="claude-live-probe-", dir=self.tmp))
            )
            return self.roots[-1]

        for target, replacement in (
            (patch.object(probe, "user_config_dir", lambda: self.config), None),
            (patch.object(probe, "_make_root", make_root), None),
            (
                patch.dict(
                    os.environ,
                    {
                        "HOME": str(self.home),
                        "USERPROFILE": str(self.home),
                        TOKEN_ENV: FAKE_TOKEN,
                    },
                ),
                None,
            ),
        ):
            target.start()
            self.addCleanup(target.stop)
        for name in ("CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY"):
            os.environ.pop(name, None)

    def probe(
        self, *args: str, host: _Host | None = None
    ) -> tuple[int, dict[str, Any], _Host, str, str]:
        host = host or _Host()
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(claude.subprocess, "run", host.run),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = probe.main(["--claude-bin", "claude-stub", *args])
        text = out.getvalue()
        return (
            code,
            (json.loads(text) if text.strip() else {}),
            host,
            text,
            err.getvalue(),
        )

    def touch(self, relative: str, offset_seconds: int = 0) -> None:
        """Rewrite an entry's mtime: now (inside the child's lifetime) by default."""
        path = self.config / relative
        stamp = time.time_ns() + offset_seconds * 1_000_000_000
        os.utime(path, ns=(stamp, stamp))


class StageSelectionTests(ProbeCase):
    def test_default_runs_only_the_auth_stage(self) -> None:
        code, report, host, _, _ = self.probe()
        self.assertEqual([call["stage"] for call in host.calls], ["auth"])
        self.assertEqual(list(report["stages"]), ["auth"])
        self.assertEqual(report["stages_requested"], ["auth"])
        self.assertEqual(report["stages"]["auth"]["status"], "pass")
        self.assertEqual((code, report["probe_exit_code"]), (0, 0))

    def test_argv_and_environment_of_each_stage(self) -> None:
        _, report, host, _, _ = self.probe("--stages", ALL)
        self.assertEqual(
            [call["stage"] for call in host.calls], ["auth", "dispatch", "budget"]
        )
        budgets = {"auth": "0.25", "dispatch": "1.00", "budget": "0.001"}
        for call in host.calls:
            argv, env = call["argv"], call["env"]
            with self.subTest(call["stage"]):
                self.assertEqual(argv[:2], ["claude-stub", "-p"])
                for pair in (
                    ["--output-format", "stream-json"],
                    ["--setting-sources", "project"],
                    ["--max-budget-usd", budgets[call["stage"]]],
                    ["--permission-mode", "manual"],
                    ["--permission-prompts", "none"],
                    ["--model", "haiku"],
                ):
                    index = argv.index(pair[0])
                    self.assertEqual(argv[index : index + 2], pair)
                self.assertIn("--verbose", argv)
                self.assertIn("--strict-mcp-config", argv)
                for forbidden in (
                    "--dangerously-skip-permissions",
                    "bypassPermissions",
                    "--bare",
                    "--settings",
                    "--add-dir",
                ):
                    self.assertNotIn(forbidden, argv)
                self.assertNotIn(call["input"], argv)
                self.assertEqual(
                    [key for key, value in env.items() if FAKE_TOKEN in value],
                    [TOKEN_ENV],
                )
                self.assertFalse(any(FAKE_TOKEN in part for part in argv))
                self.assertNotIn("ANTHROPIC_API_KEY", env)
                self.assertNotEqual(env["HOME"], str(self.home))
                self.assertIn(self.tmp, Path(env["CLAUDE_CONFIG_DIR"]).parents)
                self.assertEqual(call["staged_agents"], STAGED)
                # The report repeats the flags but never the binary path.
                self.assertEqual(report["stages"][call["stage"]]["argv"], argv[1:])
        self.assertEqual(
            len({call["env"]["CLAUDE_CONFIG_DIR"] for call in host.calls}), 3
        )
        self.assertIn("subagent_type='scout'", host.calls[1]["input"])
        self.assertIn(probe.BUDGET_INPUT_FILE, host.calls[2]["cwd_files"])
        self.assertNotIn(probe.BUDGET_INPUT_FILE, host.calls[0]["cwd_files"])

    def test_model_and_budgets_can_be_overridden(self) -> None:
        _, report, host, _, _ = self.probe(
            "--stages",
            "auth,budget",
            "--model",
            "sonnet",
            "--auth-budget-usd",
            "0.10",
            "--budget-probe-usd",
            "0.002",
        )
        for call, amount in zip(host.calls, ("0.10", "0.002")):
            argv = call["argv"]
            self.assertEqual(argv[argv.index("--model") + 1], "sonnet")
            self.assertEqual(argv[argv.index("--max-budget-usd") + 1], amount)
        self.assertEqual(report["model_requested"], "sonnet")

    def test_out_of_bounds_options_are_refused_before_anything_runs(self) -> None:
        for args in (
            ("--total-budget-usd", "31"),
            ("--total-budget-usd", "0"),
            ("--auth-budget-usd", "3"),
            ("--dispatch-budget-usd", "30.01", "--total-budget-usd", "30"),
            ("--budget-probe-usd", "0.5"),
            ("--timeout", "181"),
            ("--timeout", "1"),
            ("--stages", "auth,live"),
            ("--stages", "auth,"),
            ("--stages", " auth"),
            ("--stages", "auth,auth"),
            ("--stages", ""),
            ("--model", "two words"),
            ("--model", "--bare"),
        ):
            with self.subTest(args), self.assertRaises(SystemExit) as raised:
                self.probe(*args)
            self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.roots, [])

    def test_a_failed_auth_stage_is_not_retried_and_stops_the_run(self) -> None:
        events = stage_events("auth")
        events[-1].update({"subtype": "error_during_execution", "is_error": True})
        code, report, host, _, _ = self.probe(
            "--stages", ALL, host=_Host(auth={"events": events, "returncode": 1})
        )
        self.assertEqual([call["stage"] for call in host.calls], ["auth"])
        self.assertEqual(
            report["stages"]["auth"]["checks"]["cli_result"],
            {"status": "fail", "reason": "result_error_during_execution"},
        )
        for skipped in ("dispatch", "budget"):
            self.assertEqual(
                report["stages"][skipped],
                {"status": "skipped", "reason": "auth_stage_did_not_pass"},
            )
        self.assertEqual(code, 1)

    def test_total_budget_stops_further_stages(self) -> None:
        code, report, host, _, _ = self.probe(
            "--stages",
            "auth,dispatch",
            "--dispatch-budget-usd",
            "0.28",
            "--total-budget-usd",
            "0.30",
        )
        self.assertEqual([call["stage"] for call in host.calls], ["auth"])
        self.assertEqual(
            report["stages"]["dispatch"],
            {"status": "skipped", "reason": "total_budget_reached"},
        )
        self.assertEqual(report["charged_usd"], "0.0421")
        self.assertEqual(code, 3)

    def test_cost_above_a_stage_reservation_stops_the_run(self) -> None:
        _, report, host, _, _ = self.probe(
            "--stages", "auth,dispatch", "--auth-budget-usd", "0.01"
        )
        self.assertEqual(len(host.calls), 1)
        self.assertEqual(report["stopped"], "stage_cost_exceeded_reservation")

    def test_unknown_cost_is_charged_the_full_reservation(self) -> None:
        _, report, _, _, _ = self.probe(
            host=_Host(auth={"stdout": "not json\n", "returncode": 1})
        )
        self.assertEqual(report["charged_usd"], "0.25")
        self.assertEqual(
            report["stages"]["auth"]["checks"]["cli_result"]["reason"],
            "no_result_event",
        )


class TokenTests(ProbeCase):
    def test_missing_token_fails_closed_with_nonzero_exit(self) -> None:
        for value in (None, "", "   ", "two words"):
            with self.subTest(repr(value)), patch.dict(os.environ):
                os.environ.pop(TOKEN_ENV, None)
                if value is not None:
                    os.environ[TOKEN_ENV] = value
                code, report, host, out, err = self.probe("--stages", ALL)
                self.assertEqual((code, report, out, host.calls), (2, {}, "", []))
                self.assertIn(TOKEN_ENV, err)
                if value and value.strip():
                    self.assertNotIn(value.strip(), err)
        self.assertEqual(self.roots, [])

    @unittest.skipIf(os.name == "nt", "POSIX file modes and symlinks; the live probe runs on macOS/Linux")
    def test_token_is_in_no_output(self) -> None:
        target = self.root / "report.json"
        code, _, host, out, err = self.probe("--stages", ALL, "--report", str(target))
        self.assertEqual(len(host.calls), 3)
        self.assertEqual(out, "")
        written = target.read_text(encoding="utf-8")
        for text in (written, err, repr(code)):
            self.assertNotIn(FAKE_TOKEN, text)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(written)["token_env"], TOKEN_ENV)
        leftovers = [
            path
            for path in self.root.rglob("*")
            if path.is_file() and self.config not in path.parents and path != target
        ]
        self.assertEqual(leftovers, [])

    def test_stream_that_echoes_the_token_leaves_no_trace(self) -> None:
        events = stage_events("auth")
        events[-1]["result"] = f"env dump {FAKE_TOKEN}"
        for index, host in enumerate(
            (
                _Host(auth={"events": events}),
                _Host(auth={"stderr": f"warn {FAKE_TOKEN}"}),
            )
        ):
            with self.subTest(index):
                code, report, _, out, err = self.probe(host=host)
                self.assertNotIn(FAKE_TOKEN, out + err)
                stage = report["stages"]["auth"]
                self.assertEqual(
                    stage["checks"]["cli_result"],
                    {"status": "fail", "reason": "evidence_credential_in_stream"},
                )
                self.assertIsNone(stage["shape"])
                self.assertEqual(stage["isolation"]["cleanup"]["status"], "pass")
                self.assertEqual(code, 1)

    def test_report_is_withheld_if_it_would_carry_forbidden_content(self) -> None:
        leaks = {"token": FAKE_TOKEN, "home_path": str(self.home / "x")}
        for kind, leak in leaks.items():
            real = probe.stream_shape

            def leaking(stdout: str, leak: str = leak) -> dict[str, Any]:
                return {**real(stdout), "models": [leak]}

            with self.subTest(kind), patch.object(probe, "stream_shape", leaking):
                code, report, _, out, err = self.probe()
            self.assertEqual(code, 2)
            self.assertEqual(report["error"], "report_withheld")
            self.assertEqual(report["forbidden_content"], [kind])
            self.assertNotIn(leak, out + err)

    def test_help_needs_no_token_and_the_script_is_executable(self) -> None:
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        self.assertEqual(
            SCRIPT.read_text(encoding="utf-8").splitlines()[0], "#!/usr/bin/env python3"
        )
        env = {key: value for key, value in os.environ.items() if key != TOKEN_ENV}
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
        self.assertEqual(done.returncode, 0)
        self.assertIn("--stages", done.stdout)

    def test_probe_names_the_token_variable_only_through_the_adapter(self) -> None:
        self.assertNotIn(TOKEN_ENV, SCRIPT.read_text(encoding="utf-8"))


class ReportContentTests(ProbeCase):
    def test_report_has_no_free_text_and_no_absolute_path(self) -> None:
        code, report, host, out, err = self.probe("--stages", ALL)
        self.assertEqual(len(host.calls), 3)
        for unwanted in (
            FREE_TEXT,
            "SENTINEL",
            "user content sentinel",
            str(self.home),
            str(self.root),
            os.path.expanduser("~"),
            "claude-stub",
            probe._ONE_WORD,
        ):
            self.assertNotIn(unwanted, out)
            self.assertNotIn(unwanted, err.replace("claude-live-probe", ""))
        self.assertEqual(code, report["probe_exit_code"])

    def test_shape_lists_types_keys_tools_and_numbers(self) -> None:
        _, report, _, _, _ = self.probe("--stages", "auth,dispatch")
        shape = report["stages"]["dispatch"]["shape"]
        self.assertEqual(
            shape["sequence"],
            [
                "system/init",
                "assistant",
                "assistant",
                "user",
                "user",
                "assistant",
                "rate_limit_event",
                "assistant",
                "result/success",
            ],
        )
        self.assertIn("parent_tool_use_id", shape["keys"]["assistant"])
        self.assertEqual(
            shape["keys"]["assistant"]["parent_tool_use_id"], ["null", "str"]
        )
        self.assertEqual(
            shape["tool_uses"][0],
            {
                "name": "Agent",
                "level": "parent",
                "input_keys": ["description", "prompt", "subagent_type"],
                "subagent_type": "scout",
            },
        )
        self.assertEqual(shape["tool_uses"][1]["level"], "child")
        self.assertEqual(shape["result"]["numbers"]["total_cost_usd"], 0.0421)
        self.assertEqual(shape["result"]["usage"]["cache_read_input_tokens"], 300)
        self.assertEqual(list(shape["result"]["model_usage"]), ["synthetic-model"])
        self.assertEqual(shape["init"]["scalars"]["apiKeySource"], "none")
        self.assertNotIn("cwd", shape["init"]["scalars"])
        self.assertEqual(report["stages"]["dispatch"]["cost_usd"], 0.0421)
        self.assertEqual(report["stages"]["dispatch"]["exit_code"], 0)

    def test_values_that_are_not_names_are_reduced(self) -> None:
        events = stage_events("auth")
        events[0]["agents"] = STAGED + ["a name with spaces", str(self.home / "agent")]
        events[0][FREE_TEXT] = 1
        events[-1]["modelUsage"] = {FREE_TEXT: {"costUSD": 1}}
        _, report, _, out, _ = self.probe(host=_Host(auth={"events": events}))
        self.assertNotIn("SENTINEL", out)
        self.assertIn(
            "<other>", report["stages"]["auth"]["shape"]["init"]["lists"]["agents"]
        )

    def test_difference_from_the_synthetic_sample_is_listed(self) -> None:
        events = stage_events("auth", init={"mcp_servers": []})
        del events[-1]["permission_denials"]
        events[-1]["brand_new_key"] = "off"
        events[-1]["duration_ms"] = 1.5
        events.insert(1, {"type": "system", "subtype": "status", "session_id": "s"})
        _, report, _, _, _ = self.probe(host=_Host(auth={"events": events}))
        stage = report["stages"]["auth"]
        diff = stage["synthetic_diff"]
        self.assertEqual(diff["sample"], "no-agent-call")
        self.assertEqual(diff["kinds_only_live"], ["system/status"])
        result = diff["keys"]["result/success"]
        self.assertEqual(result["missing_in_live"], ["permission_denials"])
        self.assertEqual(result["extra_in_live"], ["brand_new_key"])
        self.assertEqual(
            result["type_changed"],
            {"duration_ms": {"live": ["float"], "synthetic": ["int"]}},
        )
        self.assertEqual(diff["keys"]["system/init"]["extra_in_live"], ["hooks"])
        self.assertEqual(list(diff["keys"]), ["result/success", "system/init"])
        # The adapter accepts an unknown `system` subtype, so the stage still passes.
        self.assertEqual(stage["checks"]["adapter_parse"]["status"], "pass")

    def test_a_shape_the_adapter_rejects_is_still_reported(self) -> None:
        events = stage_events("auth")
        events.insert(1, {"type": "rate_limit_event", "session_id": "s"})
        code, report, _, _, _ = self.probe(host=_Host(auth={"events": events}))
        stage = report["stages"]["auth"]
        self.assertEqual(stage["checks"]["cli_result"]["status"], "pass")
        self.assertEqual(
            stage["checks"]["adapter_parse"],
            {"status": "fail", "reason": "evidence_unrecognized_stream_event"},
        )
        self.assertIn("rate_limit_event", stage["shape"]["kinds"])
        self.assertEqual(stage["adapter"]["outcome"], "raised")
        self.assertEqual(code, 1)


class IsolationTests(ProbeCase):
    def test_clean_run_passes_every_isolation_check(self) -> None:
        code, report, _, _, _ = self.probe()
        isolation = report["stages"]["auth"]["isolation"]
        self.assertEqual(
            {name: entry["status"] for name, entry in isolation.items()},
            dict.fromkeys(isolation, "pass"),
        )
        private = isolation["private_config"]
        self.assertEqual(private["transcript_like_count"], 1)
        self.assertEqual(
            private["files_by_area"],
            {"config/<root>": 1, "config/projects": 1, "home/<root>": 1},
        )
        self.assertEqual(private["files_by_extension"], {".json": 2, ".jsonl": 1})
        self.assertNotIn("names", private)
        self.assertEqual(isolation["user_config"]["reason"], "stable_items_unchanged")
        self.assertGreater(isolation["user_config"]["entries_compared"], 8)
        self.assertEqual(isolation["user_projects"]["matching_entries"], 0)
        self.assertTrue(report["probe_root_removed"])
        self.assertEqual(list(self.tmp.iterdir()), [])
        self.assertEqual(code, 0)

    def test_no_transcript_in_the_private_config_is_undetermined(self) -> None:
        code, report, _, _, _ = self.probe(host=_Host(transcript=False))
        private = report["stages"]["auth"]["isolation"]["private_config"]
        self.assertEqual(
            (private["status"], private["reason"]),
            ("undetermined", "no_transcript_seen"),
        )
        self.assertEqual(code, 3)

    def test_changes_to_stable_user_config_items_fail(self) -> None:
        def modify(stage: str, cwd: Path) -> None:
            self.touch("settings.json")
            (self.config / "agents" / "new agent.md").write_text("x", encoding="utf-8")
            (self.config / "commands" / "my-command.md").unlink()

        code, report, host, out, _ = self.probe(
            "--stages", ALL, host=_Host(on_run=modify)
        )
        user = report["stages"]["auth"]["isolation"]["user_config"]
        self.assertEqual(
            (user["status"], user["reason"]), ("fail", "user_config_changed")
        )
        self.assertEqual(
            (user["added_count"], user["removed_count"], user["modified_count"]),
            (1, 1, 3),
        )
        self.assertEqual(
            user["changed_by_item"],
            {
                "agents": {"added": 1, "modified": 1},
                "commands": {"modified": 1, "removed": 1},
                "settings.json": {"modified": 1},
            },
        )
        self.assertEqual(
            user["changed_by_extension"], {".json": 1, ".md": 2, "<none>": 2}
        )
        # Counts only: no file name of the user's config is reported.
        for name in ("new agent", "my-command"):
            self.assertNotIn(name, out)
        self.assertEqual(len(host.calls), 1)
        self.assertEqual(report["stopped"], "isolation_check_failed")
        self.assertEqual(code, 1)

    def test_symlinked_settings_are_followed_to_their_target(self) -> None:
        target = self.root / "dotfile" / "settings.json"
        target.parent.mkdir()
        target.write_text("{}", encoding="utf-8")
        (self.config / "settings.json").unlink()
        (self.config / "settings.json").symlink_to(target)

        def modify(stage: str, cwd: Path) -> None:
            os.utime(target, ns=(time.time_ns(), time.time_ns()))

        _, report, _, out, _ = self.probe(host=_Host(on_run=modify))
        user = report["stages"]["auth"]["isolation"]["user_config"]
        self.assertEqual(
            (user["status"], user["changed_by_item"]),
            ("fail", {"settings.json": {"modified": 1}}),
        )
        self.assertNotIn("dotfile", out)

    def test_churn_from_other_sessions_is_ignored(self) -> None:
        def churn(stage: str, cwd: Path) -> None:
            self.touch("history.jsonl")
            self.touch("projects/-other-session/log.jsonl")
            (self.config / "projects" / "-another-session").mkdir()
            (self.config / "sessions").mkdir()
            (self.config / "statsig-cache.json").write_text("{}", encoding="utf-8")

        code, report, _, _, _ = self.probe(host=_Host(on_run=churn))
        isolation = report["stages"]["auth"]["isolation"]
        self.assertEqual(isolation["user_config"]["status"], "pass")
        self.assertEqual(isolation["user_projects"]["status"], "pass")
        self.assertEqual(code, 0)

    def test_stage_project_appearing_in_the_user_config_fails(self) -> None:
        def leak(stage: str, cwd: Path) -> None:
            (self.config / "projects" / probe._munge(str(cwd))).mkdir()

        code, report, _, out, _ = self.probe(host=_Host(on_run=leak))
        projects = report["stages"]["auth"]["isolation"]["user_projects"]
        self.assertEqual(
            projects,
            {
                "status": "fail",
                "reason": "stage_project_in_user_config",
                "matching_entries": 1,
            },
        )
        self.assertNotIn("-other-session", out)
        self.assertEqual(code, 1)

    def test_unreadable_user_config_is_undetermined(self) -> None:
        with patch.object(
            probe, "snapshot_user_config", side_effect=PermissionError("denied")
        ):
            code, report, _, _, _ = self.probe()
        user = report["stages"]["auth"]["isolation"]["user_config"]
        self.assertEqual(
            (user["status"], user["reason"]), ("undetermined", "user_config_unreadable")
        )
        with patch.object(probe, "USER_SCAN_MAX_ENTRIES", 3):
            _, report, _, _, _ = self.probe()
        self.assertEqual(
            report["stages"]["auth"]["isolation"]["user_config"]["reason"],
            "user_config_scan_limit",
        )
        self.assertEqual(code, 3)

    def test_private_data_left_behind_fails(self) -> None:
        real = claude._remove_private

        def keep(*paths: Path) -> None:
            raise claude.StageCleanupError("claude stage cleanup failed")

        with patch.object(claude, "_remove_private", keep):
            code, report, _, _, _ = self.probe()
        self.assertTrue(callable(real))
        cleanup = report["stages"]["auth"]["isolation"]["cleanup"]
        self.assertEqual(
            (cleanup["status"], cleanup["reason"]), ("fail", "private_data_left_behind")
        )
        self.assertEqual(
            (cleanup["staged_config_left"], cleanup["leftover_count"]), (True, 2)
        )
        self.assertTrue(report["probe_root_removed"])
        self.assertEqual(code, 1)


class SettingSourcesTests(ProbeCase):
    def sources(
        self,
        init: dict[str, Any] | None = None,
        events: list[dict[str, Any]] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        events = events or stage_events("auth", init=init)
        code, report, _, _, _ = self.probe(host=_Host(auth={"events": events}))
        return code, report["stages"]["auth"]["isolation"]["setting_sources"]

    def test_only_the_staged_project_layer_passes(self) -> None:
        code, sources = self.sources()
        self.assertEqual(sources["status"], "pass")
        agents = sources["categories"]["agents"]
        self.assertEqual(
            (
                agents["staged_missing"],
                agents["user_layer_loaded"],
                agents["unattributed"],
            ),
            ([], [], []),
        )
        self.assertEqual(sources["categories"]["slash_commands"]["unattributed"], [])
        self.assertEqual(sources["builtin_names_observed"], "cli_2.1.289_2026-10-05")
        self.assertEqual(sources["not_observable"], ["memory"])
        self.assertEqual(code, 0)

    def test_missing_init_event_is_undetermined_not_a_pass(self) -> None:
        code, sources = self.sources(events=stage_events("auth")[1:])
        self.assertEqual(
            sources, {"status": "undetermined", "reason": "init_event_missing"}
        )
        self.assertEqual(code, 3)

    def test_unlisted_categories_are_undetermined(self) -> None:
        events = stage_events("auth")
        for key in ("skills", "hooks", "plugins", "slash_commands"):
            del events[0][key]
        code, sources = self.sources(events=events)
        self.assertEqual(sources["status"], "undetermined")
        self.assertEqual(sources["categories"]["agents"]["status"], "pass")
        self.assertEqual(
            sources["categories"]["skills"],
            {"status": "undetermined", "reason": "init_key_missing"},
        )
        self.assertEqual(
            sources["categories"]["hooks"],
            {"status": "undetermined", "reason": "hooks_not_listed"},
        )
        self.assertEqual(code, 3)

    def test_user_layer_content_fails(self) -> None:
        cases = {
            "agents": ({"agents": STAGED + ["my-private-agent"]}, "user_layer_loaded"),
            "skills": ({"skills": ["my-skill"]}, "user_layer_loaded"),
            "slash_commands": ({"slash_commands": ["my-command"]}, "user_layer_loaded"),
            "mcp_servers": (
                {"mcp_servers": [{"name": "user-server", "status": "connected"}]},
                "mcp_servers_present",
            ),
            "plugins": (
                {"plugins": [{"name": "user-plugin", "path": str(self.home)}]},
                "plugins_present",
            ),
            "hooks": ({"hooks": ["Stop"]}, "hooks_present"),
        }
        for category, (init, reason) in cases.items():
            with self.subTest(category):
                code, sources = self.sources(init)
                entry = sources["categories"][category]
                self.assertEqual((entry["status"], entry["reason"]), ("fail", reason))
                self.assertEqual((sources["status"], code), ("fail", 1))

    def test_hook_events_in_the_stream_fail(self) -> None:
        events = stage_events("auth")
        events.insert(
            1, {"type": "system", "subtype": "hook_started", "session_id": "s"}
        )
        _, sources = self.sources(events=events)
        self.assertEqual(
            sources["categories"]["hooks"]["events"], ["system/hook_started"]
        )
        self.assertEqual(sources["categories"]["hooks"]["status"], "fail")

    def test_staged_agents_that_did_not_load_fail(self) -> None:
        _, sources = self.sources({"agents": ["general-purpose"]})
        agents = sources["categories"]["agents"]
        self.assertEqual(
            (agents["status"], agents["reason"]), ("fail", "staged_not_loaded")
        )
        self.assertEqual(agents["staged_missing"], STAGED)

    def test_user_layer_that_cannot_be_told_apart_is_undetermined(self) -> None:
        (self.config / "agents" / "my-private-agent.md").unlink()
        shutil.rmtree(self.config / "skills")
        _, sources = self.sources()
        for category in ("agents", "skills"):
            entry = sources["categories"][category]
            self.assertEqual(
                (entry["status"], entry["reason"]),
                ("undetermined", "no_distinguishing_user_entries"),
            )


class DispatchStageTests(ProbeCase):
    def dispatch(self, **override: Any) -> tuple[int, dict[str, Any]]:
        code, report, _, _, _ = self.probe(
            "--stages", "dispatch", host=_Host(dispatch=override)
        )
        return code, report["stages"]["dispatch"]

    def test_one_scout_dispatch_passes(self) -> None:
        code, stage = self.dispatch()
        self.assertEqual(
            {name: entry["status"] for name, entry in stage["checks"].items()},
            dict.fromkeys(stage["checks"], "pass"),
        )
        self.assertEqual(
            sorted(stage["checks"]),
            [
                "adapter_evidence",
                "adapter_parse",
                "agent_tool_call",
                "child_message",
                "cli_result",
                "staged_agent_loaded",
            ],
        )
        evidence = stage["checks"]["adapter_evidence"]
        self.assertEqual(
            (evidence["reason"], evidence["dispatch_status"], evidence["model"]),
            ("ok", "NATIVE_OK", "synthetic-model"),
        )
        self.assertEqual(stage["synthetic_diff"]["sample"], "dispatch-results-last")
        self.assertEqual(code, 0)

    def test_no_agent_call_fails(self) -> None:
        code, stage = self.dispatch(events=stage_events("auth"))
        self.assertEqual(
            stage["checks"]["agent_tool_call"],
            {"status": "fail", "reason": "no_agent_call"},
        )
        self.assertEqual(stage["checks"]["adapter_evidence"]["reason"], "no_agent_call")
        self.assertEqual(code, 1)

    def test_wrong_subagent_type_fails(self) -> None:
        events = stage_events("dispatch")
        events[1]["message"]["content"][1]["input"]["subagent_type"] = "Explore"
        _, stage = self.dispatch(events=events)
        self.assertEqual(
            stage["checks"]["agent_tool_call"]["reason"], "unexpected_subagent_type"
        )
        self.assertEqual(
            stage["checks"]["adapter_evidence"]["reason"], "unexpected_subagent_type"
        )

    def test_scout_missing_from_the_init_event(self) -> None:
        _, stage = self.dispatch(
            events=stage_events("dispatch", init={"agents": ["general-purpose"]})
        )
        self.assertEqual(
            stage["checks"]["staged_agent_loaded"],
            {"status": "fail", "reason": "scout_not_listed"},
        )
        _, stage = self.dispatch(events=stage_events("dispatch")[1:])
        self.assertEqual(
            stage["checks"]["staged_agent_loaded"],
            {"status": "undetermined", "reason": "init_agents_missing"},
        )


class BudgetStageTests(ProbeCase):
    def budget(self, **override: Any) -> tuple[int, dict[str, Any], str]:
        code, report, host, out, _ = self.probe(
            "--stages", "budget", host=_Host(budget=override)
        )
        self.assertEqual(len(host.calls), 1)
        return code, report["stages"]["budget"], out

    def test_host_failure_on_budget_is_an_observation_not_a_probe_failure(self) -> None:
        code, stage, _ = self.budget()
        self.assertEqual(stage["status"], "observed")
        check = stage["checks"]["budget_enforcement"]
        self.assertEqual(
            (check["status"], check["reason"], check["enforced"], check["exit_code"]),
            ("observed", "result_error_max_budget_usd", True, 1),
        )
        self.assertEqual(
            (check["result_is_error"], check["cost_usd"], check["cost_over_cap"]),
            (True, 0.0421, True),
        )
        self.assertEqual(stage["adapter"]["returncode"], 1)
        self.assertEqual(stage["max_budget_usd"], "0.001")
        self.assertEqual(list(stage["checks"]), ["budget_enforcement"])
        self.assertEqual(code, 0)

    def test_budget_that_is_not_enforced_is_reported(self) -> None:
        events = stage_events("budget")
        events[-1].update({"subtype": "success", "is_error": False})
        code, stage, _ = self.budget(events=events, returncode=0)
        check = stage["checks"]["budget_enforcement"]
        self.assertEqual(
            (check["reason"], check["enforced"]), ("budget_not_enforced", False)
        )
        self.assertEqual((stage["status"], code), ("observed", 0))

    def test_abort_without_a_result_event(self) -> None:
        stderr = "Error: SENTINEL Budget of $0.001 exceeded"
        code, stage, out = self.budget(stdout="", stderr=stderr, returncode=1)
        check = stage["checks"]["budget_enforcement"]
        self.assertEqual(
            (check["status"], check["reason"], check["enforced"]),
            ("observed", "exit_nonzero_budget_stderr", True),
        )
        self.assertEqual(stage["stderr"]["keywords"], ["budget"])
        self.assertEqual(stage["adapter"]["reason"], "evidence_no_result_event")
        self.assertNotIn("SENTINEL", out)
        code, stage, _ = self.budget(stdout="", stderr="", returncode=1)
        self.assertEqual(
            stage["checks"]["budget_enforcement"]["status"], "undetermined"
        )
        self.assertEqual((stage["status"], code), ("undetermined", 3))

    def test_rejected_flag_is_named_from_stderr(self) -> None:
        stderr = "error: unknown option '--permission-prompts'"
        _, stage, _ = self.budget(stdout="", stderr=stderr, returncode=1)
        self.assertEqual(stage["stderr"]["mentions_flags"], ["--permission-prompts"])
        self.assertEqual(stage["stderr"]["keywords"], ["permission", "unknown option"])


class AdapterOptionTests(ProbeCase):
    """Optional adapter parameters added for the probe; defaults stay as before."""

    def request(self, role: str | None) -> StageRequest:
        scratch = Path(tempfile.mkdtemp(prefix="adapter-", dir=self.tmp))
        (scratch / "cwd").mkdir()
        return StageRequest(
            prompt="p",
            role=role,
            sandbox="read-only",
            workdir=scratch / "cwd",
            scratch=scratch,
            timeout=30,
        )

    def run_adapter(
        self, adapter: claude.ClaudeStageAdapter, role: str | None, host: _Host
    ) -> Any:
        with patch.object(claude.subprocess, "run", host.run):
            return adapter.run_stage(self.request(role))

    def test_model_flag_is_only_added_when_asked_for(self) -> None:
        default = claude.ClaudeStageAdapter(
            claude_bin="claude-stub", max_budget_usd="0.50"
        )
        request = self.request("scout")
        self.assertNotIn("--model", default._command(request))
        chosen = claude.ClaudeStageAdapter(
            claude_bin="claude-stub", max_budget_usd="0.50", model="haiku"
        )
        self.assertEqual(
            chosen._command(request), default._command(request) + ["--model", "haiku"]
        )
        for bad in ("", "two words", "--bare", "-x", "a" * 81, 5, "a/b"):
            with self.subTest(repr(bad)), self.assertRaises(BenchmarkContractError):
                claude.ClaudeStageAdapter(
                    claude_bin="claude-stub", max_budget_usd="0.50", model=bad
                )

    def test_single_agent_stage_is_opt_in(self) -> None:
        host = _Host()
        default = claude.ClaudeStageAdapter(
            claude_bin="claude-stub", max_budget_usd="0.50"
        )
        with self.assertRaises(StageSetupError):
            self.run_adapter(default, None, host)
        self.assertEqual(host.calls, [])
        adapter = claude.ClaudeStageAdapter(
            claude_bin="claude-stub", max_budget_usd="0.50", allow_single_agent=True
        )
        outcome = self.run_adapter(adapter, None, host)
        self.assertIsNone(outcome.evidence)
        self.assertEqual(outcome.messages, [FREE_TEXT])
        self.assertEqual((outcome.returncode, outcome.cost_usd), (0, 0.0421))
        with self.assertRaises(StageSetupError):
            self.run_adapter(adapter, "not-a-role", host)

    def test_observer_sees_the_stage_before_it_is_deleted(self) -> None:
        seen: list[Any] = []

        def observe(observation: claude.StageObservation) -> None:
            seen.append(
                (
                    observation,
                    sorted(path.name for path in observation.private.iterdir()),
                    (observation.workdir / ".claude").is_dir(),
                )
            )

        adapter = claude.ClaudeStageAdapter(
            claude_bin="claude-stub",
            max_budget_usd="0.50",
            allow_single_agent=True,
            observer=observe,
        )
        self.run_adapter(adapter, None, _Host())
        observation, private, staged = seen[0]
        self.assertEqual(
            (private, staged, observation.returncode),
            (["config", "home", "tmp"], True, 0),
        )
        self.assertIn('"type": "result"', observation.stdout)
        self.assertFalse(observation.private.exists())
        self.assertFalse((observation.workdir / ".claude").exists())

    def test_observer_is_not_shown_output_that_carries_the_token(self) -> None:
        seen: list[Any] = []
        adapter = claude.ClaudeStageAdapter(
            claude_bin="claude-stub",
            max_budget_usd="0.50",
            allow_single_agent=True,
            observer=seen.append,
        )
        for override in ({"stdout": f"{FAKE_TOKEN}\n"}, {"stderr": FAKE_TOKEN}):
            with (
                self.subTest(list(override)),
                self.assertRaises(StageEvidenceError) as raised,
            ):
                self.run_adapter(adapter, None, _Host(auth=override))
            self.assertEqual(raised.exception.detail, "credential_in_stream")
        self.assertEqual(seen, [])


class LiveCalibrationTests(ProbeCase):
    """Rules corrected from the live reports of 2026-10-05 (CLI 2.1.289)."""

    def sources(self, **init: Any) -> tuple[int, dict[str, Any]]:
        events = stage_events("auth", init=init)
        code, report, _, _, _ = self.probe(host=_Host(auth={"events": events}))
        return code, report["stages"]["auth"]["isolation"]["setting_sources"]

    def add_user_skill(self, name: str) -> None:
        (self.config / "skills" / name).mkdir()
        (self.config / "skills" / name / "SKILL.md").write_text("x", encoding="utf-8")

    def test_builtin_plugins_are_not_the_user_layer(self) -> None:
        builtin = ["cc-plugin-agents-md", "cc-plugin-plugin-authoring", "cc-plugin-telemetry"]
        code, sources = self.sources(plugins=builtin)
        self.assertEqual(
            sources["categories"]["plugins"],
            {"status": "pass", "reason": "only_builtin_plugins", "loaded": builtin},
        )
        self.assertEqual(code, 0)
        for foreign in ("my-plugin", "xcc-plugin-a", "CC-PLUGIN-A", "cc_plugin_a"):
            with self.subTest(foreign):
                code, sources = self.sources(plugins=builtin + [foreign])
                plugins = sources["categories"]["plugins"]
                self.assertEqual((plugins["status"], plugins["reason"]), ("fail", "plugins_present"))
                self.assertEqual(plugins["not_builtin"], [foreign])
                self.assertEqual(code, 1)

    def test_builtin_skill_shared_with_the_user_layer_is_not_a_failure(self) -> None:
        self.add_user_skill("code-review")
        builtin = sorted(probe.BUILTIN_SKILLS)
        self.assertEqual(len(builtin), 19)
        code, sources = self.sources(skills=builtin, slash_commands=sorted(probe.BUILTIN_SLASH_COMMANDS))
        skills = sources["categories"]["skills"]
        self.assertEqual((skills["status"], skills["reason"]), ("pass", "no_user_layer_entry_loaded"))
        self.assertEqual((skills["ambiguous"], skills["user_layer_loaded"], skills["unattributed"]), (["code-review"], [], []))
        self.assertEqual(skills["distinguishing_user_entries"], 1)
        commands = sources["categories"]["slash_commands"]
        self.assertEqual((commands["status"], commands["ambiguous"]), ("pass", ["code-review"]))
        self.assertEqual((sources["status"], code), ("pass", 0))

    def test_user_only_skill_still_fails(self) -> None:
        self.add_user_skill("code-review")
        code, sources = self.sources(skills=sorted(probe.BUILTIN_SKILLS) + ["my-skill"])
        skills = sources["categories"]["skills"]
        self.assertEqual((skills["status"], skills["reason"]), ("fail", "user_layer_loaded"))
        self.assertEqual(skills["user_layer_loaded"], ["my-skill"])
        self.assertEqual(code, 1)

    def test_unknown_new_names_are_undetermined_not_a_pass(self) -> None:
        for category in ("skills", "slash_commands", "agents"):
            loaded = {"skills": ["batch"], "slash_commands": ["init"], "agents": STAGED}[category]
            with self.subTest(category):
                code, sources = self.sources(**{category: loaded + ["brand-new-name"]})
                entry = sources["categories"][category]
                self.assertEqual((entry["status"], entry["reason"]), ("undetermined", "unknown_names_loaded"))
                self.assertEqual(entry["unattributed"], ["brand-new-name"])
                self.assertEqual((sources["status"], code), ("undetermined", 3))

    def test_only_builtin_named_user_skills_cannot_prove_isolation(self) -> None:
        shutil.rmtree(self.config / "skills")
        (self.config / "skills").mkdir()
        self.add_user_skill("verify")
        _, sources = self.sources(skills=["verify"])
        skills = sources["categories"]["skills"]
        self.assertEqual((skills["status"], skills["reason"]), ("undetermined", "no_distinguishing_user_entries"))

    def user_config(self, on_run: Any, **host: Any) -> tuple[int, dict[str, Any], dict[str, Any]]:
        code, report, _, _, _ = self.probe(host=_Host(on_run=on_run, **host))
        return code, report["stages"]["auth"]["isolation"]["user_config"], report

    def test_change_dated_inside_the_child_lifetime_fails(self) -> None:
        code, user, _ = self.user_config(lambda stage, cwd: self.touch("settings.json"))
        self.assertEqual((user["status"], user["reason"]), ("fail", "user_config_changed"))
        self.assertEqual((user["changed_during_child_or_undated"], user["changed_outside_child"]), (1, 0))
        self.assertEqual(user["timing_basis"], "mtime_vs_child_lifetime")
        self.assertEqual(code, 1)

    def test_change_dated_outside_the_child_lifetime_is_set_apart(self) -> None:
        for offset in (-60, 60):
            with self.subTest(offset):
                code, user, report = self.user_config(
                    lambda stage, cwd: self.touch("settings.json", offset)
                )
                self.assertEqual(
                    (user["status"], user["reason"]),
                    ("undetermined", "user_config_changed_outside_child_lifetime"),
                )
                self.assertEqual((user["changed_during_child_or_undated"], user["changed_outside_child"]), (0, 1))
                self.assertEqual(user["modified_count"], 1)
                # Not a pass, and not a reason to stop the run either.
                self.assertIsNone(report["stopped"])
                self.assertEqual(code, 3)

    def test_changes_within_the_slack_count_as_inside(self) -> None:
        _, user, _ = self.user_config(lambda stage, cwd: self.touch("settings.json", -1))
        self.assertEqual(user["status"], "fail")

    def test_one_inside_change_among_outside_ones_fails(self) -> None:
        def modify(stage: str, cwd: Path) -> None:
            self.touch("settings.json", -60)
            self.touch("AGENTS.md", -60)
            self.touch("rules/shared.md")

        _, user, _ = self.user_config(modify)
        self.assertEqual((user["status"], user["changed_during_child_or_undated"], user["changed_outside_child"]), ("fail", 1, 2))

    def test_removed_entry_cannot_be_dated_and_fails(self) -> None:
        def modify(stage: str, cwd: Path) -> None:
            (self.config / "rules" / "shared.md").unlink()
            self.touch("rules", -60)

        _, user, _ = self.user_config(modify)
        self.assertEqual((user["status"], user["removed_count"], user["changed_outside_child"]), ("fail", 1, 1))

    def test_compare_without_a_window_keeps_any_change_a_failure(self) -> None:
        before = {"settings.json": (1, 10)}
        after = {"settings.json": (1, 20)}
        self.assertEqual(probe.compare_user_config(before, after)["status"], "fail")
        self.assertEqual(probe.compare_user_config(before, after, (10**18, 2 * 10**18))["status"], "undetermined")
        self.assertEqual(probe.compare_user_config(before, before, (0, 1))["status"], "pass")
        retargeted = {"settings.json": (2, 10, "a", 5)}, {"settings.json": (2, 10, "b", 5)}
        self.assertEqual(probe.compare_user_config(*retargeted, (10**18, 2 * 10**18))["status"], "fail")

    def test_rate_limit_event_shape_is_reported_without_free_text(self) -> None:
        events = stage_events("auth")
        self.assertEqual(events[-2]["type"], "rate_limit_event")
        events[-2]["rate_limit_info"] = {
            "status": "allowed_warning",
            "rateLimitType": "five_hour",
            "resetsAt": 1790000000,
            "isUsingOverage": False,
            "note": FREE_TEXT,
            "Mixed": "NotACode",
        }
        code, report, _, out, _ = self.probe(host=_Host(auth={"events": events}))
        stage = report["stages"]["auth"]
        self.assertEqual(stage["checks"]["adapter_parse"]["status"], "pass")
        self.assertEqual(
            stage["shape"]["keys"]["rate_limit_event.rate_limit_info"]["resetsAt"], ["int"]
        )
        self.assertEqual(
            stage["shape"]["rate_limits"],
            [{"status": "allowed_warning", "rateLimitType": "five_hour", "isUsingOverage": False}],
        )
        self.assertNotIn("SENTINEL", out)
        self.assertEqual(stage["adapter"]["event_counts"]["rate_limit_event"], 1)
        self.assertEqual(code, 0)

    def test_stream_shaped_like_the_live_run_matches_the_calibrated_sample(self) -> None:
        events = stage_events("auth")
        del events[0]["hooks"]
        _, report, _, _, _ = self.probe(host=_Host(auth={"events": events}))
        stage = report["stages"]["auth"]
        self.assertEqual(
            stage["shape"]["sequence"],
            ["system/init", "system/thinking_tokens", "system/thinking_tokens", "assistant", "assistant", "rate_limit_event", "result/success"],
        )
        diff = stage["synthetic_diff"]
        self.assertEqual(
            {key: value for key, value in diff.items() if key != "sample"},
            {"kinds_only_live": [], "kinds_only_synthetic": [], "paths_only_live": [], "paths_only_synthetic": [], "keys": {}},
        )

    def test_samples_carry_the_key_sets_of_the_live_report(self) -> None:
        shape = probe.stream_shape((SAMPLES / "no-agent-call.jsonl").read_text(encoding="utf-8"))
        keys = shape["keys"]
        self.assertEqual(sorted(keys["rate_limit_event"]), ["rate_limit_info", "session_id", "type", "uuid"])
        self.assertEqual(len(keys["system/init"]), 26)
        self.assertEqual(len(keys["result/success"]), 25)
        self.assertEqual(len(keys["result.modelUsage[]"]), 12)
        self.assertEqual(len(keys["result.usage"]), 12)
        self.assertEqual(len(keys["assistant"]), 8)
        self.assertEqual(len(keys["assistant.message"]), 13)
        self.assertIn("assistant.message.content[thinking]", keys)
        for name in ("dispatch-two-rounds",):
            other = probe.stream_shape((SAMPLES / f"{name}.jsonl").read_text(encoding="utf-8"))
            for path in ("system/init", "result.usage", "result.modelUsage[]", "rate_limit_event", "assistant.message"):
                self.assertEqual(sorted(other["keys"][path]), sorted(keys[path]), (name, path))
        self.assertEqual(
            sorted(keys["rate_limit_event.rate_limit_info"]),
            ["isUsingOverage", "rateLimitType", "resetsAt", "status", "unifiedWindows", "utilization"],
        )
        unknown = probe.stream_shape((SAMPLES / "unknown-event.jsonl").read_text(encoding="utf-8"))
        self.assertIn("synthetic_unknown_event", unknown["kinds"])


class DispatchRoundsTests(ProbeCase):
    """Live dispatch shape of 2026-10-05: task bookkeeping events and two rounds."""

    def dispatch(self, events: list[dict[str, Any]], *args: str) -> tuple[int, dict[str, Any], dict[str, Any], str, _Host]:
        code, report, host, out, _ = self.probe(
            "--stages", "auth,dispatch,budget", *args, host=_Host(dispatch={"events": events})
        )
        return code, report["stages"]["dispatch"], report, out, host

    def events(self) -> list[dict[str, Any]]:
        events = stage_events("dispatch", sample="dispatch-two-rounds")
        del events[0]["hooks"], events[18]["hooks"]
        return events

    def test_two_round_dispatch_passes_and_matches_the_sample(self) -> None:
        code, stage, report, out, host = self.dispatch(self.events())
        self.assertEqual(
            {name: entry["status"] for name, entry in stage["checks"].items()},
            dict.fromkeys(stage["checks"], "pass"),
        )
        shape = stage["shape"]
        self.assertEqual((shape["round_count"], shape["event_count"]), (2, 24))
        self.assertEqual(shape["sequence"][17:19], ["result/success", "system/init"])
        self.assertEqual([entry["index"] for entry in shape["rounds"]], [17, 23])
        self.assertEqual(shape["rounds"][1]["origin"], {"kind": "task-notification"})
        self.assertEqual(
            shape["dispatch_trace"],
            {
                "tool_use_index": 4,
                "tool_result_index": 7,
                "tool_result_text_chars": 89,
                "child_assistant_events": 1,
                "first_child_assistant_index": 10,
                "last_child_assistant_index": 10,
                "last_child_text_chars": len(FREE_TEXT),
                "task_notification_index": 13,
            },
        )
        self.assertEqual(
            shape["task_events"],
            [
                {"kind": "system/task_started", "index": 6, "task_type": "local_agent", "is_backgrounded": True, "spawn_depth": 1},
                {"kind": "system/task_updated", "index": 12, "patch_status": "completed"},
                {"kind": "system/task_notification", "index": 13, "status": "completed"},
            ],
        )
        for path in ("system/task_started", "system/task_updated", "system/task_notification", "system/background_tasks_changed", "system/thinking_tokens", "result.origin"):
            self.assertIn(path, shape["keys"])
        diff = stage["synthetic_diff"]
        self.assertEqual((diff["sample"], diff["keys"], diff["kinds_only_live"], diff["paths_only_live"]), ("dispatch-results-last", {}, [], []))
        # Cost is the cumulative value of the last round, not the first one.
        self.assertEqual(stage["cost_usd"], 0.0421)
        self.assertEqual(report["charged_usd"], "0.1263")
        self.assertEqual(stage["adapter"]["event_counts"]["result"], 2)
        self.assertEqual([call["stage"] for call in host.calls], ["auth", "dispatch", "budget"])
        self.assertNotIn("SENTINEL", out)

    def test_results_last_order_passes_like_the_other_order(self) -> None:
        """Report 5: second init before either result, both results at the end."""
        events = stage_events("dispatch", sample="dispatch-results-last")
        for event in events:
            event.pop("hooks", None)
        self.assertEqual([event["type"] for event in events[-2:]], ["result", "result"])
        code, stage, report, out, host = self.dispatch(events)
        self.assertEqual(
            {name: entry["status"] for name, entry in stage["checks"].items()},
            dict.fromkeys(stage["checks"], "pass"),
        )
        self.assertEqual(stage["checks"]["child_message"]["reason"], "child_text_present")
        self.assertEqual(stage["checks"]["adapter_evidence"]["reason"], "ok")
        shape = stage["shape"]
        self.assertEqual([entry["index"] for entry in shape["rounds"]], [20, 21])
        self.assertEqual(
            [entry["origin"] for entry in shape["rounds"]], [{}, {"kind": "task-notification"}]
        )
        trace = shape["dispatch_trace"]
        self.assertEqual(
            (trace["tool_use_index"], trace["tool_result_index"], trace["first_child_assistant_index"], trace["task_notification_index"]),
            (4, 7, 13, 16),
        )
        self.assertGreater(trace["tool_result_text_chars"], trace["last_child_text_chars"])
        diff = stage["synthetic_diff"]
        self.assertEqual(
            (diff["sample"], diff["keys"], diff["kinds_only_live"], diff["paths_only_live"], diff["paths_only_synthetic"]),
            ("dispatch-results-last", {}, [], [], []),
        )
        self.assertEqual(stage["cost_usd"], 0.0421)
        self.assertEqual([call["stage"] for call in host.calls], ["auth", "dispatch", "budget"])
        self.assertNotIn("SENTINEL", out)

    def test_missing_child_message_fails_the_stage_and_stops_the_run(self) -> None:
        events = stage_events("dispatch", sample="dispatch-results-last-no-child-message")
        code, stage, report, _, host = self.dispatch(events)
        self.assertEqual(stage["checks"]["child_message"], {"status": "fail", "reason": "no_child_message"})
        evidence = stage["checks"]["adapter_evidence"]
        self.assertEqual((evidence["status"], evidence["reason"]), ("fail", "agent_call_without_child_message"))
        self.assertEqual(stage["checks"]["agent_tool_call"]["status"], "pass")
        self.assertNotIn("last_child_text_chars", stage["shape"]["dispatch_trace"])
        self.assertEqual(report["stopped"], "dispatch_stage_did_not_pass")
        self.assertEqual([call["stage"] for call in host.calls], ["auth", "dispatch"])
        self.assertEqual(code, 1)

    def test_stream_not_ending_in_a_result_fails(self) -> None:
        events = stage_events("dispatch", sample="dispatch-two-rounds-ends-without-result")
        code, stage, report, _, host = self.dispatch(events)
        self.assertEqual(stage["checks"]["cli_result"], {"status": "fail", "reason": "events_after_last_result"})
        self.assertEqual(stage["adapter"]["reason"], "evidence_no_result_event")
        self.assertEqual(len(host.calls), 2)

    def test_a_failed_round_fails_the_stage_and_stops_the_run(self) -> None:
        for index in (17, 23):
            events = self.events()
            events[index].update({"subtype": "error_during_execution", "is_error": True})
            with self.subTest(index):
                code, stage, report, _, host = self.dispatch(events)
                self.assertEqual(
                    stage["checks"]["cli_result"],
                    {"status": "fail", "reason": "result_error_during_execution"},
                )
                self.assertEqual(stage["adapter"]["returncode"], 1)
                self.assertEqual(report["stopped"], "dispatch_stage_did_not_pass")
                self.assertEqual([call["stage"] for call in host.calls], ["auth", "dispatch"])
                self.assertEqual(code, 1)

    def test_too_many_rounds_fail_closed(self) -> None:
        events = self.events()
        events += events[18:] + events[18:]
        self.assertEqual(sum(event["type"] == "result" for event in events), 4)
        code, stage, report, _, host = self.dispatch(events)
        self.assertEqual(stage["checks"]["cli_result"]["reason"], "too_many_rounds")
        self.assertEqual(stage["adapter"]["reason"], "evidence_too_many_rounds")
        self.assertEqual(report["stopped"], "dispatch_stage_did_not_pass")
        self.assertEqual(len(host.calls), 2)

    def test_round_costs_use_the_largest_and_flag_an_abnormal_one(self) -> None:
        events = self.events()
        events[17]["total_cost_usd"] = 0.2
        code, stage, report, _, host = self.dispatch(events)
        # Position carries no meaning: the largest total is the stage cost.
        self.assertIsNone(stage["adapter"]["reason"])
        self.assertEqual(stage["cost_usd"], 0.2)
        events = self.events()
        events[17]["total_cost_usd"] = -1
        code, stage, report, _, host = self.dispatch(events)
        self.assertEqual((stage["cost_usd"], stage["cost_anomalous"]), (None, True))
        self.assertEqual(report["charged_usd"], "1.0421")

    def test_task_events_are_not_dispatch_evidence(self) -> None:
        events = [
            event
            for event in self.events()
            if not any(block.get("type") in ("tool_use", "tool_result") for block in event.get("message", {}).get("content", []))
        ]
        self.assertIn("task_started", [event.get("subtype") for event in events])
        code, stage, _, _, _ = self.dispatch(events)
        self.assertEqual(stage["checks"]["agent_tool_call"], {"status": "fail", "reason": "no_agent_call"})
        self.assertEqual(stage["checks"]["adapter_evidence"]["reason"], "no_agent_call")
        self.assertEqual(stage["shape"]["dispatch_trace"], {})

    def test_rate_limit_that_is_not_allowed_stops_the_run(self) -> None:
        cases = {
            "rejected": "evidence_rate_limit_not_allowed",
            "": "evidence_rate_limit_status_unknown",
        }
        for status, reason in cases.items():
            events = stage_events("auth")
            events[-2]["rate_limit_info"]["status"] = status
            with self.subTest(status):
                code, report, host, _, _ = self.probe("--stages", ALL, host=_Host(auth={"events": events}))
                auth = report["stages"]["auth"]
                self.assertEqual(auth["checks"]["adapter_parse"], {"status": "fail", "reason": reason})
                self.assertEqual(auth["checks"]["cli_result"]["status"], "pass")
                self.assertEqual(report["stopped"], "auth_stage_did_not_pass")
                self.assertEqual([call["stage"] for call in host.calls], ["auth"])
                self.assertEqual(code, 1)
        events = stage_events("auth")
        events[-2]["rate_limit_info"].update({"status": "allowed_warning", "isUsingOverage": True})
        _, report, host, _, _ = self.probe("--stages", ALL, host=_Host(auth={"events": events}))
        self.assertEqual(report["stages"]["auth"]["adapter"]["reason"], "evidence_rate_limit_overage")
        self.assertEqual(len(host.calls), 1)
        events = stage_events("auth")
        events[-2]["rate_limit_info"]["status"] = "allowed_warning"
        code, report, _, _, _ = self.probe(host=_Host(auth={"events": events}))
        self.assertEqual((report["stages"]["auth"]["status"], code), ("pass", 0))


class StopAfterFailureTests(ProbeCase):
    """F1: a stage that did not fully pass is the last live call of the run."""

    def assert_stopped_after(
        self, host: _Host, calls: list[str], reason: str
    ) -> dict[str, Any]:
        code, report, host, _, _ = self.probe("--stages", ALL, host=host)
        self.assertEqual([call["stage"] for call in host.calls], calls)
        self.assertEqual(report["stopped"], reason)
        for stage in set(probe.STAGES) - set(calls):
            self.assertEqual(
                report["stages"][stage], {"status": "skipped", "reason": reason}
            )
        self.assertEqual(code, 1)
        return report

    def test_adapter_rejecting_the_auth_stream_stops_the_run(self) -> None:
        events = stage_events("auth")
        events.insert(1, {"type": "rate_limit_event", "session_id": "s"})
        report = self.assert_stopped_after(
            _Host(auth={"events": events}), ["auth"], "auth_stage_did_not_pass"
        )
        auth = report["stages"]["auth"]
        self.assertEqual(auth["checks"]["cli_result"]["status"], "pass")
        self.assertEqual(
            auth["checks"]["adapter_parse"]["reason"],
            "evidence_unrecognized_stream_event",
        )

    def test_token_written_into_the_workdir_stops_the_run(self) -> None:
        def leak(stage: str, cwd: Path) -> None:
            (cwd / "notes.txt").write_text(f"x {FAKE_TOKEN}", encoding="utf-8")

        report = self.assert_stopped_after(
            _Host(on_run=leak), ["auth"], "auth_stage_did_not_pass"
        )
        self.assertEqual(
            report["stages"]["auth"]["adapter"]["reason"],
            "evidence_credential_in_workdir",
        )

    def test_an_unexpected_error_in_the_auth_stage_stops_the_run(self) -> None:
        with patch.object(probe, "stream_shape", side_effect=ValueError("boom")):
            report = self.assert_stopped_after(
                _Host(), ["auth"], "auth_stage_did_not_pass"
            )
        self.assertEqual(
            report["stages"]["auth"]["adapter"]["reason"], "unexpected_ValueError"
        )

    def test_a_failed_dispatch_stage_stops_before_the_budget_stage(self) -> None:
        self.assert_stopped_after(
            _Host(dispatch={"events": stage_events("auth")}),
            ["auth", "dispatch"],
            "dispatch_stage_did_not_pass",
        )
        events = stage_events("dispatch")
        events.insert(1, {"type": "rate_limit_event", "session_id": "s"})
        self.assert_stopped_after(
            _Host(dispatch={"events": events}),
            ["auth", "dispatch"],
            "dispatch_stage_did_not_pass",
        )


class NameAllowlistTests(ProbeCase):
    """F2: only short conservative identifiers are reported."""

    def test_names_that_look_like_text_or_secrets_become_placeholders(self) -> None:
        rejected = (
            "sk-ant-oat01-" + "A" * 20,
            "ghp_" + "b" * 20,
            "aB3dE5fG7hJ9kL1mN0pQ",
            "0123456789abcdef0123456789abcdef",
            "QwErTyUiOpAsDfGhJkLz",
            "two words",
            "tab\tname",
            "a/b",
            "name@host",
            "x" * 65,
            "",
            None,
            7,
        )
        for value in rejected:
            with self.subTest(repr(value)):
                self.assertEqual(probe._name(value), "<other>")
        for value in (
            "scout",
            "general-purpose",
            "claude-haiku-4-5-20251001",
            "claude-opus-5-5[1m]",
            "cacheCreationInputTokens",
            "cache_creation_input_tokens",
            "mcp__claude_ai_Claude_Docs__batch",
            "anthropic-skills:pdf",
            "error_max_budget_usd",
            "2.1.0",
        ):
            with self.subTest(value):
                self.assertEqual(probe._name(value), value)

    def test_credential_shaped_values_in_the_stream_are_not_reported(self) -> None:
        secret = "sk-ant-oat01-" + "Zq9" * 12
        events = stage_events("auth")
        events[0]["agents"] = STAGED + [secret]
        events[0]["tools"] = [secret, "Read"]
        events[0]["model"] = secret
        events[-1]["modelUsage"] = {secret: {"costUSD": 1}}
        code, report, _, out, _ = self.probe(host=_Host(auth={"events": events}))
        self.assertNotIn(secret, out)
        self.assertNotIn("Zq9Zq9", out)
        lists = report["stages"]["auth"]["shape"]["init"]["lists"]
        self.assertEqual(lists["tools"], ["<other>", "Read"])
        # A reduced name is one nobody can attribute: not a pass.
        agents = report["stages"]["auth"]["isolation"]["setting_sources"]["categories"]["agents"]
        self.assertEqual((agents["status"], agents["reason"]), ("undetermined", "unknown_names_loaded"))
        self.assertEqual(code, 3)

    def test_a_fragment_of_the_token_withholds_the_report(self) -> None:
        for part in (FAKE_TOKEN[:-1], FAKE_TOKEN[1:], FAKE_TOKEN[5:20]):
            events = stage_events("auth")
            events[0]["agents"] = STAGED + [part]
            events[0]["tools"] = [part]
            with self.subTest(part):
                code, report, _, out, err = self.probe(
                    host=_Host(auth={"events": events})
                )
                self.assertNotIn(part, out + err)
                self.assertEqual(report["error"], "report_withheld")
                self.assertEqual(report["forbidden_content"], ["token_fragment"])
                self.assertEqual(code, 2)

    def test_private_file_names_are_counted_not_listed(self) -> None:
        names = (
            "free text MARKER sentence.txt",
            "sk-ant-oat01-" + "A" * 40,
            "MARKER.weirdext",
            f"{FAKE_TOKEN}.json",
        )

        def write(stage: str, cwd: Path) -> None:
            config = next(iter((cwd.parent / "scratch").glob("claude-stage-*"))) / "config"
            (config / "MARKER dir").mkdir()
            for name in names:
                (config / "MARKER dir" / name).write_text("x", encoding="utf-8")

        code, report, _, out, err = self.probe(host=_Host(on_run=write))
        private = report["stages"]["auth"]["isolation"]["private_config"]
        self.assertEqual(private["files_by_area"]["config/<other>"], 4)
        self.assertEqual(
            private["files_by_extension"],
            {".json": 3, ".jsonl": 1, ".txt": 1, "<none>": 1, "<other>": 1},
        )
        for unwanted in ("MARKER", "sk-ant", FAKE_TOKEN, "weirdext"):
            self.assertNotIn(unwanted, out + err)
        self.assertEqual(code, 0)


class ReportFileTests(ProbeCase):
    """F3: the report file is created new, owner-only, never through a symlink."""

    def refused(self, destination: Path) -> None:
        code, report, host, out, err = self.probe(
            "--stages", ALL, "--report", str(destination)
        )
        self.assertEqual((code, report, out, host.calls), (2, {}, "", []))
        self.assertEqual(self.roots, [])
        self.assertNotIn(str(destination), err)

    @unittest.skipIf(os.name == "nt", "POSIX file modes and symlinks; the live probe runs on macOS/Linux")
    def test_existing_file_is_refused_and_left_alone(self) -> None:
        target = self.root / "existing.json"
        target.write_text("keep me", encoding="utf-8")
        os.chmod(target, 0o644)
        self.refused(target)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)

    def test_symlink_is_refused_and_its_target_left_alone(self) -> None:
        target = self.root / "target.json"
        target.write_text("keep me", encoding="utf-8")
        link = self.root / "link.json"
        link.symlink_to(target)
        self.refused(link)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep me")
        self.assertTrue(link.is_symlink())

    @unittest.skipIf(os.name == "nt", "POSIX file modes and symlinks; the live probe runs on macOS/Linux")
    def test_dangling_symlink_is_refused_and_its_target_not_created(self) -> None:
        target = self.root / "absent.json"
        link = self.root / "dangling.json"
        link.symlink_to(target)
        self.refused(link)
        self.assertFalse(target.exists())
        self.assertTrue(link.is_symlink())

    @unittest.skipIf(os.name == "nt", "POSIX file modes and symlinks; the live probe runs on macOS/Linux")
    def test_new_file_is_owner_only_even_with_a_loose_umask(self) -> None:
        target = self.root / "new.json"
        previous = os.umask(0)
        try:
            code, _, _, out, _ = self.probe("--report", str(target))
        finally:
            os.umask(previous)
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["status"], "pass")

    def test_no_empty_report_is_left_when_the_run_dies(self) -> None:
        target = self.root / "died.json"
        with (
            patch.object(probe, "run_probe", side_effect=RuntimeError("boom")),
            self.assertRaises(RuntimeError),
        ):
            self.probe("--report", str(target))
        self.assertFalse(target.exists())


class CostAccountingTests(ProbeCase):
    """F4: a cost that is not a finite non-negative number is charged in full."""

    def test_abnormal_cost_is_charged_the_whole_reservation(self) -> None:
        for raw in ("-100", "-0.0001", "NaN", "Infinity", "1e999", "true", '"0.01"', "null", str(10**400)):
            events = stage_events("auth")
            line = json.dumps(events[-1]).replace('"total_cost_usd": 0.0421', f'"total_cost_usd": {raw}')
            self.assertIn(f'"total_cost_usd": {raw}', line)
            stdout = _stream(events[:-1]) + line + "\n"
            with self.subTest(raw):
                code, report, host, _, _ = self.probe(
                    "--stages", ALL, "--total-budget-usd", "1.2",
                    host=_Host(auth={"stdout": stdout}),
                )
                self.assertEqual(report["charged_usd"], "0.25")
                self.assertIsNone(report["stages"]["auth"]["cost_usd"])
                self.assertTrue(report["stages"]["auth"]["cost_anomalous"])
                self.assertEqual([call["stage"] for call in host.calls], ["auth"])
                self.assertEqual(code, 1)

    def test_total_cannot_be_lowered_by_a_reported_cost(self) -> None:
        def entry(stage: str, **_: Any) -> dict[str, Any]:
            return {
                "status": "pass" if stage != "budget" else "observed",
                "isolation_status": "pass",
                "adapter": {"outcome": "returned"},
                "cost_usd": -100,
            }

        ran: list[str] = []

        def fake(stage: str, **kwargs: Any) -> dict[str, Any]:
            ran.append(stage)
            return entry(stage)

        with patch.object(probe, "run_stage", fake):
            code, report, _, _, _ = self.probe(
                "--stages", ALL, "--dispatch-budget-usd", "0.25", "--total-budget-usd", "0.60"
            )
        self.assertEqual(ran, ["auth", "dispatch"])
        self.assertEqual(report["charged_usd"], "0.50")
        self.assertEqual(
            report["stages"]["budget"],
            {"status": "skipped", "reason": "total_budget_reached"},
        )
        self.assertEqual(code, 3)


class HardeningTests(ProbeCase):
    """F5: escaped forms, ASCII-only amounts and bounded numbers."""

    def leak(self, value: str) -> tuple[int, dict[str, Any], str]:
        real = probe.stream_shape

        def leaking(stdout: str) -> dict[str, Any]:
            return {**real(stdout), "models": [value]}

        with patch.object(probe, "stream_shape", leaking):
            code, report, _, out, err = self.probe()
        self.assertNotIn(value, out + err)
        self.assertNotIn(json.dumps(value)[1:-1], out + err)
        return code, report, out

    def test_token_with_characters_json_escapes_is_still_caught(self) -> None:
        for token in ('place"holder\\tok', "placeholder-\u00e9\u4e2d-tok", 'p"\\'):
            with self.subTest(token), patch.dict(os.environ, {TOKEN_ENV: token}):
                code, report, _ = self.leak(token)
                self.assertEqual(report["forbidden_content"], ["token"])
                self.assertEqual(code, 2)
                code, report, _ = self.leak(f"pre-{token[:-1]}" if len(token) > 8 else token)
                self.assertEqual(code, 2)

    def test_home_path_with_characters_json_escapes_is_still_caught(self) -> None:
        weird = self.root / 'h\u00f6"m\\e' / ".claude"
        with patch.object(probe, "user_config_dir", lambda: weird):
            code, report, _ = self.leak(str(weird.parent / "file"))
        self.assertEqual(report["forbidden_content"], ["home_path"])
        self.assertEqual(code, 2)

    def test_amounts_and_timeout_must_be_plain_ascii_decimals(self) -> None:
        for args in (
            ("--total-budget-usd", "\u0661"),
            ("--auth-budget-usd", "0.\u0662"),
            ("--total-budget-usd", "1_0"),
            ("--auth-budget-usd", "1e-1"),
            ("--auth-budget-usd", " 0.1"),
            ("--auth-budget-usd", "+0.1"),
            ("--auth-budget-usd", ".1"),
            ("--budget-probe-usd", "0.0000001"),
            ("--timeout", "1_0_0"),
            ("--timeout", "\u0661\u0662\u0660"),
            ("--timeout", "+60"),
        ):
            with self.subTest(args), self.assertRaises(SystemExit) as raised:
                self.probe(*args)
            self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.roots, [])

    def test_deep_or_huge_numbers_are_dropped_and_flagged(self) -> None:
        events = stage_events("auth")
        deep = '{"a":' * 600 + "1" + "}" * 600
        line = json.dumps(events[-1])
        line = line.replace('"num_turns": 1', f'"num_turns": {10**400}')
        line = line.replace('"output_tokens": 25', f'"output_tokens": 25, "deep": {deep}, "huge": {10**400}', 1)
        self.assertIn('"deep"', line)
        stdout = _stream(events[:-1]) + line + "\n"
        code, report, _, out, _ = self.probe(host=_Host(auth={"stdout": stdout}))
        result = report["stages"]["auth"]["shape"]["result"]
        self.assertEqual(result["numbers_dropped"], ["num_turns"])
        self.assertNotIn("num_turns", result["numbers"])
        self.assertEqual(result["usage"]["<dropped>"], 1)
        self.assertEqual(result["usage"]["deep"], {"<dropped>": 1})
        self.assertEqual(result["usage"]["output_tokens"], 25)
        self.assertLess(len(out), 64 * 1024)
        self.assertEqual(code, 0)

    def test_nested_numbers_keep_one_level_only(self) -> None:
        wide = {f"k{index}": index for index in range(probe.MAX_KEYS + 5)}
        self.assertEqual(probe._numbers(wide)["<dropped>"], 5)
        nested = probe._numbers({"a": {"b": 1, "c": {"d": 2}}, "e": float("inf"), "f": True, "g": "1"})
        self.assertEqual(nested, {"a": {"b": 1, "<dropped>": 1}, "<dropped>": 1})

    def test_oversized_report_is_withheld(self) -> None:
        with patch.object(probe, "MAX_REPORT_BYTES", 2000):
            code, report, _, out, _ = self.probe()
        self.assertEqual(report["forbidden_content"], ["report_too_large"])
        self.assertEqual(code, 2)
        self.assertLess(len(out), 2000)

    def test_unbounded_event_kinds_and_paths_are_capped(self) -> None:
        events = stage_events("auth")
        extra = [{"type": "system", "subtype": f"kind{index}", f"k{index}": 1} for index in range(1000)]
        code, report, _, out, _ = self.probe(host=_Host(auth={"events": events[:1] + extra + events[1:]}))
        shape = report["stages"]["auth"]["shape"]
        self.assertEqual(len(shape["keys"]), probe.MAX_PATHS)
        self.assertGreater(shape["paths_dropped"], 0)
        self.assertTrue(shape["kinds_truncated"] and shape["sequence_truncated"])
        self.assertLess(len(out), probe.MAX_REPORT_BYTES)


if __name__ == "__main__":
    unittest.main()
