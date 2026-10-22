"""cross-vendor-relay T1.2：tools/shoal_relay.py 端到端，以假 codex binary 執行（不呼叫真的 codex）。

每個測試在 temp 目錄建一份與 plugin 相同的版面（tools/、core/、hooks/），vendors.toml 只把 paths 換成
假 binary；HOME、TMPDIR 都是 temp。假 binary 把 argv、env、stdin 是否為 /dev/null 記到 calls.jsonl，
行為由同目錄的 mode.json 決定。涵蓋 S1.1–S1.7、S1.2a、S1.14、S1.14a、S1.15–S1.19。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import shoal_relay  # noqa: E402
from repo_fixtures import git  # noqa: E402

SECRET = "sk-fixture-SECRET-value-0123456789"
SECRET2 = "fixture-token-abcdef987654"
SCHEMA = json.loads(
    (ROOT / "core" / "contracts" / "handback.schema.json").read_text(encoding="utf-8")
)
ALLOWED_ENV = {
    "PATH",
    "HOME",
    "USER",
    "LANG",
    "TERM",
    "CODEX_HOME",
    "TMPDIR",
    "SHOAL_RELAY_ROLE",
    "SHOAL_RELAY_NONCE",
    "__CF_USER_TEXT_ENCODING",  # macOS 在 exec 時自行加入，不是 runner 傳的
}

FAKE = r"""
import json, os, signal, subprocess, sys, time
from pathlib import Path

here = Path(__file__).resolve().parent
mode = json.loads((here / "mode.json").read_text())
argv = sys.argv[1:]
null, st0 = os.stat("/dev/null"), os.fstat(0)
rec = {"argv": argv, "env": dict(os.environ), "cwd": os.getcwd(),
       "stdin_devnull": st0.st_rdev == null.st_rdev and st0.st_ino == null.st_ino,
       "tmpdir_exists": os.path.isdir(os.environ.get("TMPDIR", "/nonexistent"))}
nonce = os.environ.get("SHOAL_RELAY_NONCE")
if nonce:
    p = Path(os.environ["HOME"]) / ".local/state/shoal/guard" / ("relay-" + nonce)
    rec["nonce_path"] = str(p)
    rec["nonce_mode"] = oct(p.stat().st_mode & 0o777) if p.is_file() else None
    rec["nonce_body"] = json.loads(p.read_text()) if p.is_file() else None
with open(here / "calls.jsonl", "a") as fh:
    fh.write(json.dumps(rec) + "\n")
if argv[:1] == ["--version"]:
    print(mode.get("version", "codex-cli 0.160.1"))
    sys.exit(0)
if argv[:2] == ["login", "status"]:
    print("Logged in using ChatGPT")
    sys.exit(mode.get("login_rc", 0))
if argv[:2] == ["mcp", "list"]:
    print(json.dumps(mode.get("mcp", [])))
    sys.exit(0)
out, cwd = Path(argv[argv.index("-o") + 1]), Path(argv[argv.index("-C") + 1])
def event(obj):
    print(json.dumps(obj), flush=True)
event({"type": "thread.started", "thread_id": "thread-123"})
for text in mode.get("messages", []):
    event({"type": "item.completed", "item": {"type": "agent_message", "text": text}})
for line in mode.get("stderr", []):
    print(line, file=sys.stderr, flush=True)
for name in mode.get("write", []):
    (cwd / name).write_text("x")
for name, body in mode.get("files", {}).items():
    if body is None:
        (cwd / name).unlink()
        continue
    (cwd / name).parent.mkdir(parents=True, exist_ok=True)
    (cwd / name).write_bytes(bytes.fromhex(body[4:]) if body.startswith("hex:") else body.encode())
for name, target in mode.get("links", {}).items():
    os.symlink(target, cwd / name)
behavior = mode.get("exec", "ok")
if behavior == "sleep":
    time.sleep(120)
if behavior == "grandchild":
    gc = subprocess.Popen([sys.executable, "-c",
                           "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)"],
                          start_new_session=True)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (here / "pids.json").write_text(json.dumps({"child": os.getpid(), "grandchild": gc.pid}))
    time.sleep(120)
if behavior == "missing":
    sys.exit(0)
if behavior == "empty":
    out.write_bytes(b"")
    sys.exit(0)
if "raw" in mode:
    out.write_text(mode["raw"])
if "handback" in mode:
    out.write_text(json.dumps(mode["handback"]))
event({"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 5}})
sys.exit(mode.get("rc", 0))
"""


def report(files=("a.txt",), **extra):
    return {
        "status": "done",
        "summary": "did it",
        "changed_files": list(files),
        "checks": [{"cmd": "make test", "exit": 0, "decisive_line": "OK"}],
        "unverified": [],
        **extra,
    }


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class RelayBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(os.path.realpath(self._tmp.name))
        self.root = self.tmp / "root"
        for rel in (
            "tools/shoal_relay.py",
            "core/contracts/handback.schema.json",
            "hooks/shoal_guard.py",
        ):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, self.root / rel)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.fake = self.bin / "codex"
        self.fake.write_text(f"#!{sys.executable}\n{FAKE}", encoding="utf-8")
        self.fake.chmod(0o755)
        self.write_vendors(str(self.fake))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.runner_tmp = self.tmp / "t"
        self.runner_tmp.mkdir()
        self.main = self.tmp / "main"
        self.main.mkdir()
        (self.main / "README").write_text("r")
        git(self.main, "init", "-q")
        git(self.main, "add", "README")
        git(self.main, "commit", "-q", "-m", "init")
        self.wt = self.tmp / "wt"
        git(self.main, "worktree", "add", "-q", "-b", "relay", str(self.wt))
        self.brief = self.tmp / "brief.md"
        self.brief.write_text("Implement the thing.\n", encoding="utf-8")
        self.set_mode(
            handback=report(),
            write=["a.txt"],
            mcp=[{"name": "srv-a"}, {"name": "node_repl"}],
        )

    def tearDown(self):
        self._tmp.cleanup()

    def write_vendors(self, binary: str):
        text = (ROOT / "core" / "vendors.toml").read_text(encoding="utf-8")
        text = re.sub(
            r"^paths = .*$", f"paths = [{json.dumps(binary)}]", text, flags=re.M
        )
        text = re.sub(r"^search_path = true$", "search_path = false", text, flags=re.M)
        (self.root / "core" / "vendors.toml").write_text(text, encoding="utf-8")

    def set_mode(self, **mode):
        (self.bin / "mode.json").write_text(json.dumps(mode), encoding="utf-8")

    def env(self):
        return {
            "PATH": os.environ["PATH"],
            "HOME": str(self.home),
            "LANG": "C.UTF-8",
            "TMPDIR": str(self.runner_tmp),
            "SHOAL_TEST_API_KEY": SECRET,
            "OPENAI_API_KEY": SECRET2,
            "XDG_STATE_HOME": str(self.tmp / "xdg"),
        }

    def argv(self, role="executor", cwd=None, brief=None, timeout=None):
        argv = [
            sys.executable,
            str(self.root / "tools" / "shoal_relay.py"),
            "--vendor",
            "codex",
            "--role",
            role,
            "--cwd",
            str(cwd or self.wt),
            "--brief",
            str(brief or self.brief),
        ]
        return argv + (["--timeout", str(timeout)] if timeout else [])

    def run_relay(self, **kw):
        done = subprocess.run(
            self.argv(**kw), env=self.env(), capture_output=True, text=True, timeout=60
        )
        return self.parse(done.stdout)

    def parse(self, stdout: str):
        lines = stdout.splitlines()
        self.assertEqual(len(lines), 1, stdout)
        hb = json.loads(lines[0])
        self.assertIsNone(shoal_relay.schema_error(SCHEMA, hb))
        self.assertNotIn(SECRET, stdout)
        self.assertNotIn(SECRET2, stdout)
        return hb

    def calls(self):
        path = self.bin / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def exec_calls(self):
        return [c for c in self.calls() if c["argv"][:1] == ["exec"]]

    def assert_no_spawn(self, hb, needle):
        self.assertEqual(hb["status"], "blocked", hb)
        self.assertIn(needle, hb["reason"])
        self.assertEqual(self.calls(), [])

    def assert_dead(self, *pids):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and any(alive(p) for p in pids):
            time.sleep(0.05)
        for pid in pids:
            self.assertFalse(alive(pid), f"pid {pid} survived")

    def wait_for_pids(self):
        path = self.bin / "pids.json"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if path.exists():
                try:
                    return json.loads(path.read_text())
                except ValueError:
                    pass
            time.sleep(0.05)
        self.fail("fake vendor never started its grandchild")


class RelayRunner(RelayBase):
    # S1.1 / S1.2 / S1.2a / S1.15
    def test_s1_1_command_shape_stdin_and_success(self):
        hb = self.run_relay()
        self.assertEqual(hb["status"], "done", hb)
        self.assertEqual(
            (hb["changed_files"], hb["reported_files"], hb["files_mismatch"]),
            (["a.txt"], ["a.txt"], False),
        )
        self.assertEqual(hb["session_id"], "thread-123")
        self.assertEqual(
            hb["usage"],
            {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 5},
        )
        self.assertEqual(hb["vendor"], "codex")
        [call] = self.exec_calls()
        argv = call["argv"]
        self.assertEqual(argv[:4], ["exec", "--json", "--ephemeral", "--strict-config"])
        for flag, value in (("--sandbox", "workspace-write"), ("-C", str(self.wt))):
            self.assertEqual(argv[argv.index(flag) + 1], value)
        for flag in ("--output-schema", "-o"):
            self.assertTrue(os.path.isabs(argv[argv.index(flag) + 1]))
        self.assertTrue(all(c["stdin_devnull"] for c in self.calls()))
        self.assertEqual(call["cwd"], str(self.wt))
        self.assertEqual(
            os.listdir(self.runner_tmp), []
        )  # private dir 與 TMPDIR 都已刪除

    def test_s1_2_fixed_pins_and_mcp_disabled(self):
        self.run_relay()
        argv = self.exec_calls()[0]["argv"]
        pins = [argv[i + 1] for i, tok in enumerate(argv) if tok == "-c"]
        for pin in shoal_relay._load_vendor("codex")["pins"]:
            self.assertIn(pin, pins)
        self.assertIn("mcp_servers.srv-a.enabled=false", pins)
        self.assertIn("mcp_servers.node_repl.enabled=false", pins)
        for call in self.calls():
            self.assertFalse(
                any(shoal_relay.FORBIDDEN_ARG.search(t) for t in call["argv"])
            )

    def test_s1_2a_brief_starts_with_role_marker(self):
        self.run_relay(role="applier")
        prompt = self.exec_calls()[0]["argv"][-1]
        self.assertTrue(
            prompt.startswith("You are the shoal named role `applier`"), prompt[:80]
        )
        self.assertIn("do not spawn subagents", prompt)
        self.assertTrue(prompt.endswith("Implement the thing.\n"))
        preamble = prompt.split("\n\n---\n\n", 1)[0]
        for rule in (
            "Do not run git commit, push, branch, stash",
            "writes to the git directory",
            "`blocked` only when the task cannot be done without information or permission you do not have",
            "return `done` and list the check under `unverified` with the reason",
            "`failed` when you attempted the change and could not complete it",
        ):
            self.assertIn(rule, preamble)

    def test_s1_15_env_allowlist_tmpdir_and_nonce(self):
        self.run_relay()
        for call in self.calls():
            self.assertLessEqual(
                set(call["env"]), ALLOWED_ENV, sorted(set(call["env"]) - ALLOWED_ENV)
            )
        call = self.exec_calls()[0]
        env, argv = call["env"], call["argv"]
        self.assertEqual(env["SHOAL_RELAY_ROLE"], "executor")
        self.assertRegex(env["SHOAL_RELAY_NONCE"], r"^[0-9a-f]{32}$")
        self.assertEqual(env["HOME"], str(self.home))
        self.assertTrue(call["tmpdir_exists"])
        tmpdir, out_dir = Path(env["TMPDIR"]), Path(argv[argv.index("-o") + 1]).parent
        self.assertNotEqual(tmpdir, out_dir)
        for path in (tmpdir, out_dir):
            self.assertNotIn(str(self.wt), str(path))
        self.assertEqual(call["nonce_mode"], "0o600")
        self.assertEqual(call["nonce_body"]["role"], "executor")
        self.assertTrue(
            call["nonce_path"].startswith(str(self.home / ".local/state/shoal/guard"))
        )
        self.assertFalse(os.path.exists(call["nonce_path"]))

    # S1.3
    def test_s1_3_exit_zero_without_valid_output_fails(self):
        cases = {
            "missing": ({"exec": "missing"}, "no output file"),
            "empty": ({"exec": "empty"}, "empty"),
            "bad json": ({"raw": "{not json"}, "not valid JSON"),
            "schema": ({"handback": {"status": "done"}}, "does not match the schema"),
        }
        for name, (mode, needle) in cases.items():
            with self.subTest(case=name):
                self.set_mode(**mode)
                hb = self.run_relay()
                self.assertEqual(hb["status"], "failed", hb)
                self.assertIn(needle, hb["reason"])

    # S1.4
    def test_s1_4_timeout_kills_and_keeps_partial_output(self):
        self.set_mode(exec="sleep", messages=["working on step 1"])
        start = time.monotonic()
        hb = self.run_relay(timeout=6)
        self.assertLess(time.monotonic() - start, 20)
        self.assertEqual((hb["status"], hb["reason"]), ("failed", "timeout"))
        self.assertIn("working on step 1", hb["partial_output"])

    # S1.5
    def test_s1_5_missing_binary_is_blocked(self):
        self.write_vendors(str(self.tmp / "nope" / "codex"))
        self.assert_no_spawn(self.run_relay(), "binary not found")

    def test_s1_5_not_logged_in_or_old_version_is_blocked(self):
        for mode, needle in (
            ({"login_rc": 1}, "not logged in"),
            ({"version": "codex-cli 0.150.0"}, "older than"),
        ):
            with self.subTest(needle=needle):
                (self.bin / "calls.jsonl").unlink(missing_ok=True)
                self.set_mode(**mode)
                hb = self.run_relay()
                self.assertEqual(hb["status"], "blocked", hb)
                self.assertIn(needle, hb["reason"])
                self.assertEqual(self.exec_calls(), [])

    def test_unsafe_mcp_id_is_blocked(self):
        self.set_mode(mcp=[{"name": "a.b"}], handback=report())
        hb = self.run_relay()
        self.assertEqual(hb["status"], "blocked")
        self.assertEqual(self.exec_calls(), [])

    # S1.6
    def test_s1_6_nonzero_exit_reports_code_and_stderr_tail(self):
        self.set_mode(rc=3, stderr=[f"line {i}" for i in range(1, 31)])
        hb = self.run_relay()
        self.assertEqual((hb["status"], hb["exit_code"]), ("failed", 3))
        self.assertEqual(
            hb["stderr_tail"].splitlines(), [f"line {i}" for i in range(11, 31)]
        )

    # S1.7 / S1.16
    def test_s1_16_secrets_are_redacted_everywhere(self):
        leak = f"key={SECRET} tok={SECRET2}"
        self.set_mode(rc=2, stderr=[leak], messages=[leak])
        hb = self.run_relay()
        self.assertIn("[REDACTED]", hb["stderr_tail"])
        self.assertIn("[REDACTED]", hb["partial_output"])
        self.set_mode(handback=report(summary=leak, unverified=[leak]), write=["a.txt"])
        hb = self.run_relay()
        self.assertEqual(hb["status"], "done")
        self.assertIn("[REDACTED]", hb["summary"])

    # S1.14 / S1.14a
    def test_s1_14_main_checkout_subdir_and_non_git_are_blocked(self):
        (self.wt / "sub").mkdir()
        plain = self.tmp / "plain"
        plain.mkdir()
        for cwd, needle in (
            (self.main, "not a linked worktree"),
            (self.wt / "sub", "root of the linked worktree"),
            (plain, "not inside a git repository"),
        ):
            with self.subTest(cwd=cwd.name):
                self.assert_no_spawn(self.run_relay(cwd=cwd), needle)

    def test_s1_14_only_executor_and_applier(self):
        for role in ("verifier", "security-executor", "scout", "main"):
            with self.subTest(role=role):
                self.assert_no_spawn(self.run_relay(role=role), "cannot be relayed")

    def test_s1_14a_codex_dir_anywhere_is_blocked(self):
        (self.wt / ".codex").mkdir()
        self.assert_no_spawn(self.run_relay(), ".codex")
        shutil.rmtree(self.wt / ".codex")
        (self.wt / "deep" / "er").mkdir(parents=True)
        (self.wt / "deep" / "er" / ".codex").write_text("x")
        self.assert_no_spawn(self.run_relay(), ".codex")
        shutil.rmtree(self.wt / "deep")
        (self.main / ".codex").mkdir()  # main checkout 根目錄（未追蹤）
        self.assert_no_spawn(self.run_relay(), ".codex")

    # S1.17
    def test_s1_17_changed_files_from_git_and_mismatch_flagged(self):
        self.set_mode(handback=report(files=["b.txt"]), write=["a.txt"])
        hb = self.run_relay()
        self.assertEqual(
            (hb["changed_files"], hb["reported_files"], hb["files_mismatch"]),
            (["a.txt"], ["b.txt"], True),
        )
        self.set_mode(handback=report(files=[str(self.wt / "a.txt")]), write=["a.txt"])
        self.assertFalse(self.run_relay()["files_mismatch"])

    # S1.17：自報路徑的註記、./、rename 寫法正規化後才比對；不一致只標出、不改 status
    def test_s1_17_annotated_paths_are_not_a_mismatch(self):
        (self.wt / "README").unlink()
        for files in (
            ["README (deleted)", "a.txt (new)"],
            ["./a.txt", "./README"],
            ["README -> a.txt"],
            ["a.txt (renamed from README)"],
            [str(self.wt / "a.txt") + " (modified)", "README (deleted)"],
        ):
            with self.subTest(files=files):
                self.set_mode(handback=report(files=files), write=["a.txt"])
                hb = self.run_relay()
                self.assertEqual(hb["status"], "done", hb)
                self.assertEqual(
                    (hb["changed_files"], hb["reported_files"], hb["files_mismatch"]),
                    (["README", "a.txt"], files, False),
                )

    def test_s1_17_mismatch_never_changes_status(self):
        for status in ("done", "failed", "blocked"):
            with self.subTest(status=status):
                self.set_mode(
                    handback=report(files=["b.txt (new)"], status=status),
                    write=["a.txt"],
                )
                hb = self.run_relay()
                self.assertEqual(hb["status"], status, hb)
                self.assertEqual(
                    (hb["changed_files"], hb["reported_files"], hb["files_mismatch"]),
                    (["a.txt"], ["b.txt (new)"], True),
                )

    def test_s1_17_vendor_extra_field_or_long_string_fails(self):
        for handback in (report(note="x"), report(summary="y" * 4001)):
            with self.subTest(keys=sorted(handback)):
                self.set_mode(handback=handback)
                hb = self.run_relay()
                self.assertEqual(hb["status"], "failed")
                self.assertIn("does not match the schema", hb["reason"])

    # S1.18
    def test_s1_18_timeout_kills_setsid_grandchild(self):
        self.set_mode(exec="grandchild")
        hb = self.run_relay(timeout=8)
        self.assertEqual(hb["reason"], "timeout")
        pids = json.loads((self.bin / "pids.json").read_text())
        self.assert_dead(pids["child"], pids["grandchild"])

    def test_s1_18_signals_kill_whole_tree(self):
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            with self.subTest(sig=sig.name):
                (self.bin / "pids.json").unlink(missing_ok=True)
                self.set_mode(exec="grandchild")
                proc = subprocess.Popen(
                    self.argv(), env=self.env(), stdout=subprocess.PIPE, text=True
                )
                pids = self.wait_for_pids()
                time.sleep(0.5)  # 讓 runner 掃描到孫程序
                proc.send_signal(sig)
                out, _ = proc.communicate(timeout=30)
                hb = self.parse(out)
                self.assertEqual(
                    (hb["status"], hb["reason"]),
                    ("failed", f"interrupted by {sig.name}"),
                )
                self.assert_dead(pids["child"], pids["grandchild"])

    def test_s1_18_parent_death_kills_whole_tree(self):
        self.set_mode(exec="grandchild")
        out = self.tmp / "relay.out"
        wrapper = (
            "import subprocess, sys, time, pathlib\n"
            "p = subprocess.Popen(sys.argv[2:], stdout=open(sys.argv[1], 'w'))\n"
            "print(p.pid, flush=True)\n"
            "pids = pathlib.Path(%r)\n"
            "while not pids.exists(): time.sleep(0.05)\n"
            "time.sleep(0.5)\n"
        ) % str(self.bin / "pids.json")
        done = subprocess.run(
            [sys.executable, "-c", wrapper, str(out), *self.argv()],
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        runner_pid = int(done.stdout.split()[0])
        pids = json.loads((self.bin / "pids.json").read_text())
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and alive(runner_pid):
            time.sleep(0.05)
        hb = self.parse(out.read_text())
        self.assertEqual(hb["reason"], "parent process exited")
        self.assert_dead(pids["child"], pids["grandchild"], runner_pid)

    # S1.19
    def test_s1_19_sandbox_failure_fails_without_retry(self):
        for rc in (1, 0):
            with self.subTest(rc=rc):
                (self.bin / "calls.jsonl").unlink(missing_ok=True)
                self.set_mode(
                    rc=rc,
                    stderr=["sandbox_apply: Operation not permitted"],
                    handback=report(),
                )
                hb = self.run_relay()
                self.assertEqual(hb["status"], "failed")
                self.assertIn("sandbox", hb["reason"])
                [call] = self.exec_calls()
                self.assertEqual(
                    call["argv"][call["argv"].index("--sandbox") + 1], "workspace-write"
                )

    def test_s1_19_unsafe_brief_is_refused(self):
        link = self.tmp / "link.md"
        link.symlink_to(self.brief)
        fifo = self.tmp / "fifo"
        os.mkfifo(fifo)
        big = self.tmp / "big.md"
        big.write_text("x" * (shoal_relay.MAX_BRIEF_BYTES + 1))
        empty = self.tmp / "empty.md"
        empty.write_text("  \n")
        for path, needle in (
            (link, "symlinks"),
            (fifo, "regular file"),
            (self.tmp, "regular file"),
            (big, "larger than"),
            (empty, "empty"),
        ):
            with self.subTest(brief=path.name):
                self.assert_no_spawn(self.run_relay(brief=path), needle)

    def test_bad_arguments_still_print_one_handback(self):
        done = subprocess.run(
            [
                sys.executable,
                str(self.root / "tools" / "shoal_relay.py"),
                "--role",
                "executor",
            ],
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        hb = self.parse(done.stdout)
        self.assertEqual(hb["status"], "blocked")
        self.assertEqual(done.returncode, 1)


    # 打包的 runner 先用同目錄的 tools/shoal_guard.py，沒有可用的再退回 hooks/shoal_guard.py；
    # 建 nonce 的任何失敗都回 blocked 且不呼叫 vendor。
    def sibling_guard(self, text: str):
        (self.root / "tools" / "shoal_guard.py").write_text(text, encoding="utf-8")

    def test_nonce_prefers_the_sibling_guard(self):
        real = (ROOT / "hooks" / "shoal_guard.py").read_text(encoding="utf-8")
        self.sibling_guard(real + "\n\ndef _open_private(path, flags):\n    raise RuntimeError('boom')\n")
        self.assert_no_spawn(self.run_relay(), "nonce")

    def test_nonce_falls_back_when_the_sibling_is_a_shim(self):
        shim = ROOT / "hosts" / "claude" / "plugin-src" / "shoal_guard_compat.py"
        self.sibling_guard(shim.read_text(encoding="utf-8"))
        self.assertEqual(self.run_relay()["status"], "done")

    def test_nonce_blocked_without_a_usable_guard(self):
        shim = ROOT / "hosts" / "claude" / "plugin-src" / "shoal_guard_compat.py"
        shutil.copy2(shim, self.root / "hooks" / "shoal_guard.py")
        self.assert_no_spawn(self.run_relay(), "guard")
        self.sibling_guard("raise SystemExit(3)\n")
        self.assert_no_spawn(self.run_relay(), "guard")
        (self.root / "hooks" / "shoal_guard.py").unlink()
        (self.root / "tools" / "shoal_guard.py").unlink()
        self.assert_no_spawn(self.run_relay(), "guard")

    def test_nonce_blocked_when_the_guard_dir_is_unusable(self):
        real = (ROOT / "hooks" / "shoal_guard.py").read_text(encoding="utf-8")
        self.sibling_guard(real + "\n\ndef _guard_dir(env, home):\n    raise OSError('boom')\n")
        self.assert_no_spawn(self.run_relay(), "guard state dir")


class RelayLanding(RelayBase):
    """fix/relay-landing：done 且有改動時，runner 把 worktree 的改動以 git apply 落到 primary checkout（不 commit）。"""

    BINARY = "00ff10807f0d0a00c3"

    def heads(self):
        return [git(p, "rev-parse", "HEAD").strip() for p in (self.main, self.wt)]

    def relay_files(self, files, links=None, status="done"):
        self.set_mode(
            handback=report(files=list(files) + list(links or {}), status=status),
            files=files,
            links=links or {},
        )
        before = self.heads()
        hb = self.run_relay()
        self.assertEqual(self.heads(), before)  # 兩邊都沒有 commit
        self.assertEqual(git(self.main, "diff", "--cached", "--name-only"), "")  # primary index 不動
        return hb

    def assert_landed(self, hb):
        self.assertEqual(hb["status"], "done", hb)
        self.assertEqual(hb["landing"], {"landed": True, "reason": None, "worktree": str(self.wt)})

    def assert_not_landed(self, hb, needle, status="done"):
        self.assertEqual(hb["status"], status, hb)
        self.assertIs(hb["landing"]["landed"], False, hb)
        self.assertEqual(hb["landing"]["worktree"], str(self.wt))
        self.assertIn(needle, hb["landing"]["reason"])

    def primary_status(self):
        return git(self.main, "status", "--porcelain", "--untracked-files=all")

    def test_tracked_edit_lands_in_primary(self):
        self.assert_landed(self.relay_files({"README": "edited\n"}))
        self.assertEqual((self.main / "README").read_text(), "edited\n")
        self.assertEqual(self.primary_status(), " M README\n")

    def test_new_text_and_binary_files_land_untracked(self):
        hb = self.relay_files({"pkg/new.py": "print('hi')\n", "img.bin": "hex:" + self.BINARY})
        self.assert_landed(hb)
        self.assertEqual((self.main / "pkg" / "new.py").read_text(), "print('hi')\n")
        self.assertEqual((self.main / "img.bin").read_bytes(), bytes.fromhex(self.BINARY))
        self.assertEqual(self.primary_status(), "?? img.bin\n?? pkg/new.py\n")

    def test_deleted_file_lands(self):
        self.assert_landed(self.relay_files({"README": None}))
        self.assertFalse((self.main / "README").exists())

    def test_refused_paths_are_not_landed(self):
        for files, links in (
            ({".claude/settings.json": "{}", "ok.txt": "ok"}, None),
            ({"sub/.Claude/x": "x"}, None),
            ({"deep/.codex/config.toml": "x"}, None),
            ({}, {"escape": "../../outside"}),
        ):
            with self.subTest(files=files, links=links):
                git(self.wt, "reset", "-q", "--hard")
                git(self.wt, "clean", "-qfdx")
                self.assert_not_landed(self.relay_files(files, links), "refused")
                self.assertEqual(self.primary_status(), "")

    def test_apply_conflict_keeps_done_and_leaves_primary_untouched(self):
        (self.main / "README").write_text("primary edit\n")
        marker = "CONTENT-MARKER-0f9e"
        self.set_mode(
            handback=report(files=["README", "new.txt"]),
            files={"README": marker + "\n", "new.txt": marker},
        )
        done = subprocess.run(self.argv(), env=self.env(), capture_output=True, text=True, timeout=60)
        hb = self.parse(done.stdout)
        self.assertEqual(done.returncode, 0)
        self.assert_not_landed(hb, "does not apply")
        self.assertNotIn(marker, done.stdout + done.stderr)  # 不轉印檔案內容
        self.assertEqual((self.main / "README").read_text(), "primary edit\n")
        self.assertFalse((self.main / "new.txt").exists())  # 全有或全無
        self.assertEqual((self.wt / "new.txt").read_text(), marker)  # 改動仍在 worktree

    def test_only_done_is_landed(self):
        for status in ("failed", "blocked"):
            with self.subTest(status=status):
                hb = self.relay_files({"README": "half\n"}, status=status)
                self.assert_not_landed(hb, f"status is {status}", status=status)
                self.assertEqual((self.main / "README").read_text(), "r")

    def test_no_changes_means_no_landing(self):
        self.set_mode(handback=report(files=[]))
        hb = self.run_relay()
        self.assertEqual(hb["status"], "done", hb)
        self.assertIsNone(hb["landing"])

    def test_blocked_before_run_has_no_landing(self):
        hb = self.run_relay(role="verifier")
        self.assertEqual(hb["status"], "blocked")
        self.assertIsNone(hb["landing"])


if __name__ == "__main__":
    unittest.main()
