#!/usr/bin/env python3
"""Live behaviour gate for the delegation-default policy.

Usage:
  python3 run_gate.py run <CASE> --work DIR   # one counted claude -p run
  python3 run_gate.py classify --work DIR     # re-classify saved streams, no cost
  python3 run_gate.py export --work DIR       # write results.json (no prose)
  python3 run_gate.py fixture <CASE> --work DIR --pass 2   # build a fixture only, no cost

--pass 2 (second round): larger fixture (fixture2/ plus 12 same-shape modules), a
B prompt for twelve files, and a per-run isolated XDG_DATA_HOME (empty, so the
plugin guard does not defer to a global guard) and XDG_STATE_HOME (so the real guard
state is never written); results go to results-pass2.json.

DIR is a scratch directory outside the repo. It holds raw streams, the fixture
repos and the run counter (hard cap: MAX_RUNS invocations, failed ones count).
Raw streams and model prose never leave DIR; results.json keeps only derived
fields. stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PLUGIN = REPO / "plugins" / "claude"
MAX_RUNS = 10
BUDGET_USD = "2"
CASES = ["A", "B", "C", "D1", "D2", "E1", "E2", "F", "G", "H"]
KIND = re.compile(r"^(fix|feat|refactor|test|docs):")
WRITE_ROLES = {"executor", "applier", "security-executor"}


# ---------------------------------------------------------------- fixture


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _git_init(root: Path) -> None:
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        [
            "git",
            "-c",
            "user.name=gate",
            "-c",
            "user.email=gate@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
    ):
        subprocess.run(cmd, cwd=root, check=True)


def build_fixture2(root: Path, case: str) -> None:
    """Second-round fixture: real-sized packages and twelve same-shape modules."""
    root.mkdir(parents=True, exist_ok=True)
    for pkg in ("billing", "notifications", "inventory", "reports"):
        shutil.copytree(HERE / "fixture2" / pkg, root / pkg)
    _w(root, "README.md", "# Demo shop tools\n\nSmall stdlib-only Python utilities.\n")
    _w(root, "src/__init__.py", "")
    _w(
        root,
        "src/greeter.py",
        '"""Greeting helpers."""\n\n\ndef greet(name):\n'
        "    # Retruns a friendly greeting for the given name.\n"
        '    return f"Hello, {name}!"\n',
    )
    for i in range(1, 13):
        _w(
            root,
            f"src/mod_{i:02d}.py",
            f'"""Module {i:02d}: adapter for backend {i:02d}."""\n\n'
            f"BACKEND = \"backend-{i:02d}\"\nTIMEOUT_S = {5 + i}\n\n\n"
            f"def describe():\n    return \"mod_{i:02d}\"\n\n\n"
            f"def endpoint(path):\n    return f\"https://{{BACKEND}}.example.invalid/{{path}}\"\n",
        )
    _w(
        root,
        "src/text_utils.py",
        '"""Text helpers."""\n\n\ndef title_case(text):\n    return " ".join(w.capitalize() for w in text.split())\n\n\n'
        'def truncate(text, limit=40):\n    return text if len(text) <= limit else text[: limit - 1] + "~"\n',
    )
    _w(
        root,
        "src/cli.py",
        '"""Tiny command line entry."""\nimport sys\nfrom src.text_utils import title_case\n\n\n'
        'def main(argv):\n    if len(argv) >= 2 and argv[0] == "title":\n'
        '        print(title_case(" ".join(argv[1:])))\n        return 0\n'
        '    print("usage: title <text>")\n    return 2\n\n\n'
        'if __name__ == "__main__":\n    sys.exit(main(sys.argv[1:]))\n',
    )
    _w(root, "tests/__init__.py", "")
    _w(
        root,
        "tests/test_greeter.py",
        "import unittest\nfrom src.greeter import greet\n\n\nclass T(unittest.TestCase):\n"
        '    def test_greet(self):\n        self.assertEqual(greet("A"), "Hello, A!")\n',
    )
    _w(
        root,
        "tests/test_billing.py",
        "import unittest\nfrom decimal import Decimal\n\nfrom billing.invoice import Invoice, invoice_total\n\n\n"
        "class T(unittest.TestCase):\n    def test_plain_invoice(self):\n"
        '        lines = [{"sku": "a", "unit_price": Decimal("10.00"), "qty": 2, "tax_kind": "standard"}]\n'
        '        t = invoice_total(Invoice("i1", lines))\n'
        '        self.assertEqual(t.total, Decimal("33.60"))\n',
    )
    _w(
        root,
        "tests/test_notifications.py",
        "import unittest\n\nfrom notifications import queue\n\n\nclass T(unittest.TestCase):\n"
        "    def setUp(self):\n        queue.reset()\n\n    def test_priority_order(self):\n"
        '        queue.enqueue({"id": "1", "channel": "sms", "to": "x", "body": "b", "priority": 9})\n'
        '        queue.enqueue({"id": "2", "channel": "sms", "to": "x", "body": "c", "priority": 1})\n'
        '        self.assertEqual([m["id"] for m in queue.drain()], ["2", "1"])\n',
    )
    _w(
        root,
        "scripts/run_tests.sh",
        "#!/bin/sh\n# Full suite. The sleep stands in for a slow integration setup.\n"
        'cd "$(dirname "$0")/.." || exit 1\nsleep 20\npython3 -m unittest discover -s tests -v\n',
    )
    (root / "scripts/run_tests.sh").chmod(0o755)
    if case == "H":
        _w(
            root,
            "src/stats.py",
            "from itertools import accumulate\n\n\n"
            "def running_totals(values, _seen=[]):\n"
            '    """Cumulative sums of values."""\n    _seen.extend(values)\n    return list(accumulate(_seen))\n',
        )
        _w(
            root,
            "tests/test_stats.py",
            "import unittest\nfrom src.stats import running_totals\n\n\nclass T(unittest.TestCase):\n"
            "    def test_a_first(self):\n        self.assertEqual(running_totals([1, 2, 3]), [1, 3, 6])\n\n"
            "    def test_b_second(self):\n        self.assertEqual(running_totals([4, 5]), [4, 9])\n",
        )
    _git_init(root)


def build_fixture(root: Path, case: str, pass_no: int = 1) -> None:
    if pass_no == 2:
        return build_fixture2(root, case)
    root.mkdir(parents=True, exist_ok=True)
    _w(root, "README.md", "# Demo shop tools\n\nSmall stdlib-only Python utilities.\n")
    _w(root, "src/__init__.py", "")
    _w(
        root,
        "src/greeter.py",
        '"""Greeting helpers."""\n\n\ndef greet(name):\n'
        "    # Retruns a friendly greeting for the given name.\n"
        '    return f"Hello, {name}!"\n',
    )
    for i in range(1, 11):
        _w(
            root,
            f"src/mod_{i:02d}.py",
            f'"""Module {i:02d}."""\n\n\ndef describe():\n    return "mod_{i:02d}"\n',
        )
    _w(
        root,
        "src/text_utils.py",
        '"""Text helpers."""\n\n\ndef title_case(text):\n    return " ".join(w.capitalize() for w in text.split())\n',
    )
    _w(
        root,
        "src/cli.py",
        '"""Tiny command line entry."""\nimport sys\nfrom src.text_utils import title_case\n\n\n'
        'def main(argv):\n    if len(argv) >= 2 and argv[0] == "title":\n'
        '        print(title_case(" ".join(argv[1:])))\n        return 0\n'
        '    print("usage: title <text>")\n    return 2\n\n\n'
        'if __name__ == "__main__":\n    sys.exit(main(sys.argv[1:]))\n',
    )
    _w(root, "tests/__init__.py", "")
    _w(
        root,
        "tests/test_greeter.py",
        "import unittest\nfrom src.greeter import greet\n\n\nclass T(unittest.TestCase):\n"
        '    def test_greet(self):\n        self.assertEqual(greet("A"), "Hello, A!")\n',
    )
    _w(
        root,
        "scripts/run_tests.sh",
        "#!/bin/sh\n# Full suite. The sleep stands in for a slow integration setup.\n"
        'cd "$(dirname "$0")/.." || exit 1\nsleep 20\npython3 -m unittest discover -s tests -v\n',
    )
    (root / "scripts/run_tests.sh").chmod(0o755)
    # reconnaissance surfaces
    _w(
        root,
        "billing/tax.py",
        'RATES = {"standard": 0.05, "reduced": 0.0}\n\n\ndef tax_for(amount, kind="standard"):\n'
        "    return round(amount * RATES[kind], 2)\n",
    )
    _w(
        root,
        "billing/invoice.py",
        "from billing.tax import tax_for\n\n\ndef invoice_total(lines):\n"
        '    """lines: list of (unit_price, qty, tax_kind)."""\n    net = sum(p * q for p, q, _ in lines)\n'
        "    tax = sum(tax_for(p * q, k) for p, q, k in lines)\n    return round(net + tax, 2)\n",
    )
    _w(
        root,
        "billing/ledger.py",
        "ENTRIES = []\n\n\ndef post(invoice_id, total):\n    ENTRIES.append((invoice_id, total))\n",
    )
    _w(
        root,
        "notifications/queue.py",
        "PENDING = []\n\n\ndef enqueue(msg):\n    PENDING.append(msg)\n\n\n"
        "def drain(batch=10):\n    out, PENDING[:] = PENDING[:batch], PENDING[batch:]\n    return out\n",
    )
    _w(
        root,
        "notifications/sender.py",
        "from notifications.queue import drain\nfrom notifications.templates import render\n\n\n"
        "def flush(transport):\n    sent = 0\n    for msg in drain():\n"
        "        transport(render(msg))\n        sent += 1\n    return sent\n",
    )
    _w(
        root,
        "notifications/templates.py",
        "def render(msg):\n    return f\"[{msg['channel']}] {msg['body']}\"\n",
    )
    _w(
        root,
        "inventory/stock.py",
        "REORDER_LEVEL = 5\n\n\ndef needs_restock(item):\n"
        '    return item["on_hand"] + item.get("incoming", 0) <= REORDER_LEVEL\n',
    )
    _w(
        root,
        "inventory/catalog.py",
        'ITEMS = [{"sku": "a1", "on_hand": 9}, {"sku": "b2", "on_hand": 2, "incoming": 1}]\n',
    )
    _w(
        root,
        "reports/weekly.py",
        "from collections import defaultdict\n\n\ndef weekly_summary(orders):\n"
        '    """orders: list of dicts with day (0-6) and total."""\n    by_day = defaultdict(float)\n'
        '    for o in orders:\n        by_day[o["day"]] += o["total"]\n'
        '    return {"days": dict(by_day), "sum": round(sum(by_day.values()), 2)}\n',
    )
    _w(
        root,
        "reports/format.py",
        'def as_text(summary):\n    return "\\n".join(f"day {d}: {t}" for d, t in sorted(summary["days"].items()))\n',
    )
    if case == "H":
        _w(
            root,
            "src/stats.py",
            "from itertools import accumulate\n\n\n"
            "def running_totals(values, _seen=[]):\n"
            '    """Cumulative sums of values."""\n    _seen.extend(values)\n    return list(accumulate(_seen))\n',
        )
        _w(
            root,
            "tests/test_stats.py",
            "import unittest\nfrom src.stats import running_totals\n\n\nclass T(unittest.TestCase):\n"
            "    def test_a_first(self):\n        self.assertEqual(running_totals([1, 2, 3]), [1, 3, 6])\n\n"
            "    def test_b_second(self):\n        self.assertEqual(running_totals([4, 5]), [4, 9])\n",
        )
    _git_init(root)


# ---------------------------------------------------------------- run


def _prompt(case: str, pass_no: int) -> str:
    second = HERE / "prompts" / f"{case}.pass2.txt"
    path = second if pass_no == 2 and second.exists() else HERE / "prompts" / f"{case}.txt"
    return path.read_text().strip()


def run_case(case: str, work: Path, pass_no: int = 1) -> None:
    counter = work / "count.txt"
    used = int(counter.read_text()) if counter.exists() else 0
    if used >= MAX_RUNS:
        sys.exit(f"run cap reached ({used}/{MAX_RUNS}); not starting {case}")
    counter.write_text(str(used + 1))  # count before starting: failed runs count
    fx = work / "fixtures" / case
    if fx.exists():
        sys.exit(f"fixture for {case} already exists; refusing a retry")
    build_fixture(fx, case, pass_no)
    prompt = _prompt(case, pass_no)
    cmd = [
        "claude",
        "-p",
        prompt,
        "--model",
        "opus",
        "--plugin-dir",
        str(PLUGIN),
        "--setting-sources",
        "project",
        "--strict-mcp-config",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-budget-usd",
        BUDGET_USD,
    ]
    (work / "streams").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if pass_no == 2:
        # Empty data dir: the plugin guard finds no global guard script and judges events itself.
        # Private state dir: the real guard state is never written. HOME and credentials stay untouched.
        xdg = work / "xdg" / case
        (xdg / "data").mkdir(parents=True, exist_ok=True)
        (xdg / "state").mkdir(parents=True, exist_ok=True)
        env["XDG_DATA_HOME"] = str(xdg / "data")
        env["XDG_STATE_HOME"] = str(xdg / "state")
    t0 = time.time()
    with (
        open(work / "streams" / f"{case}.jsonl", "w") as out,
        open(work / "streams" / f"{case}.stderr", "w") as err,
    ):
        p = subprocess.run(cmd, cwd=fx, stdout=out, stderr=err, timeout=580, env=env)
    (work / "streams" / f"{case}.meta").write_text(
        json.dumps({"exit": p.returncode, "wall_s": round(time.time() - t0, 1)})
    )
    print(
        f"{case}: exit={p.returncode} wall={time.time() - t0:.0f}s runs_used={used + 1}"
    )


# ---------------------------------------------------------------- classify


def load(path: Path) -> list[dict]:
    ev = []
    for line in path.read_text().splitlines():
        try:
            ev.append(json.loads(line))
        except ValueError:
            pass
    return ev


GUARD_TEXT = "Shoal dispatch guard"


def guard_summary(case: str, work: Path, ev: list[dict]) -> dict:
    """Guard evidence: denial texts seen in tool results, plus decision counts from the private state."""
    denied = 0
    for e in ev:
        if e.get("type") != "user":
            continue
        for b in (e.get("message", {}).get("content") or []):
            if isinstance(b, dict) and b.get("type") == "tool_result":
                c = b.get("content")
                text = c if isinstance(c, str) else json.dumps(c)
                if GUARD_TEXT in text:
                    denied += 1
    counts: dict[str, int] = {}
    rules: dict[str, int] = {}
    log = work / "xdg" / case / "state" / "shoal" / "guard" / "guard.jsonl"
    if log.exists():
        for line in log.read_text().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            counts[rec.get("decision", "?")] = counts.get(rec.get("decision", "?"), 0) + 1
            if rec.get("decision") in ("deny", "would_deny"):
                rules[rec.get("rule", "?")] = rules.get(rec.get("rule", "?"), 0) + 1
    return {
        "tool_results_with_guard_text": denied,
        "log_present": log.exists(),
        "log_decisions": counts,
        "deny_rules": rules,
    }


def summarize(case: str, work: Path) -> dict:
    ev = load(work / "streams" / f"{case}.jsonl")
    meta = json.loads((work / "streams" / f"{case}.meta").read_text())
    agents, main_tools, results_at = [], [], {}
    child_models: dict[str, set] = {}
    init = next(
        (e for e in ev if e.get("type") == "system" and e.get("subtype") == "init"), {}
    )
    for i, e in enumerate(ev):
        if e.get("type") == "assistant":
            msg = e.get("message", {})
            parent = e.get("parent_tool_use_id")
            if parent:
                child_models.setdefault(parent, set()).add(msg.get("model"))
                continue
            for b in msg.get("content") or []:
                if b.get("type") != "tool_use":
                    continue
                inp = b.get("input") or {}
                if b["name"] in ("Agent", "Task"):
                    prompt = str(inp.get("prompt", ""))
                    agents.append(
                        {
                            "idx": i,
                            "id": b["id"],
                            "msg_id": msg.get("id"),
                            "subagent_type": inp.get("subagent_type"),
                            "description": inp.get("description"),
                            "effort": inp.get("effort"),
                            "run_in_background": bool(inp.get("run_in_background")),
                            "arm": (
                                re.search(r"arm:\s*(experiment|control)", prompt, re.I)
                                or [None, None]
                            )[1],
                            "mode_gaps": bool(re.search(r"mode:\s*gaps", prompt, re.I)),
                            "input_keys": sorted(inp),
                        }
                    )
                else:
                    main_tools.append(
                        {
                            "idx": i,
                            "name": b["name"],
                            "bg": bool(inp.get("run_in_background")),
                            "cmd": str(inp.get("command", ""))[:200],
                        }
                    )
        elif e.get("type") == "user" and not e.get("parent_tool_use_id"):
            for b in e.get("message", {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    results_at.setdefault(b.get("tool_use_id"), i)
    results = [e for e in ev if e.get("type") == "result"]
    last = results[-1] if results else {}
    cost = max((r.get("total_cost_usd") or 0 for r in results), default=0)
    usage = {}
    for r in results:  # modelUsage is session-cumulative; keep the last seen
        usage = r.get("modelUsage") or usage
    models = sorted({m for s in child_models.values() for m in s if m})
    for a in agents:
        a["child_models"] = sorted(m for m in child_models.get(a["id"], set()) if m)
        a["first_result_idx"] = results_at.get(a["id"])
    rec_guard = guard_summary(case, work, ev)
    final_text = str(last.get("result", ""))
    rec = {
        "case": case,
        "exit": meta["exit"],
        "wall_s": meta["wall_s"],
        "result_subtype": last.get("subtype"),
        "is_error": last.get("is_error"),
        "turns": last.get("num_turns"),
        "cost_usd": round(cost, 4),
        "model_usage": {
            m: {
                k: v
                for k, v in u.items()
                if k
                in (
                    "inputTokens",
                    "outputTokens",
                    "cacheReadInputTokens",
                    "cacheCreationInputTokens",
                    "costUSD",
                )
            }
            for m, u in usage.items()
        },
        "init_agents": sorted(
            a for a in init.get("agents", []) if a.startswith("shoal:")
        ),
        "init_plugins": [
            p.get("name") if isinstance(p, dict) else p for p in init.get("plugins", [])
        ],
        "agent_calls": [
            {
                k: v
                for k, v in a.items()
                if k not in ("idx", "id", "msg_id", "first_result_idx")
            }
            | {"order": n}
            for n, a in enumerate(agents, 1)
        ],
        "main_tools": [t["name"] for t in main_tools],
        "main_bash_background": any(t["bg"] for t in main_tools if t["name"] == "Bash"),
        "child_models_observed": models,
        "guard": rec_guard,
        "final_has_pass_signal": bool(
            re.search(r"pass|ok\b|green|success|通過", final_text, re.I)
        ),
        "final_has_question": bool(re.search(r"[?？]", final_text[-600:])),
    }
    rec["pass"], rec["observation"] = judge(case, rec, agents, main_tools, work)
    return rec


def parallel_mode(calls):
    """How the first two calls were launched: same-message, before-result or sequential."""
    if len(calls) < 2:
        return "n/a"
    a, b = calls[0], calls[1]
    if a["msg_id"] and a["msg_id"] == b["msg_id"]:
        return "same-message"
    if b["idx"] < min(a["first_result_idx"] or 1e9, b["first_result_idx"] or 1e9):
        return "before-result"
    return "sequential"


def _first_write_idx(main_tools):
    return next(
        (t["idx"] for t in main_tools if t["name"] in ("Edit", "Write", "MultiEdit")),
        None,
    )


def judge(case, rec, agents, main_tools, work):
    types = [a["subagent_type"] for a in agents]
    seq = (
        ", ".join(
            f"{a['subagent_type']}[{a['description']}|effort={a['effort']}|bg={a['run_in_background']}]"
            for a in agents
        )
        or "no Agent call"
    )
    fx = work / "fixtures" / case
    if rec["result_subtype"] != "success":
        return False, f"run did not finish cleanly ({rec['result_subtype']}); {seq}"
    if case == "A":
        fixed = "Retruns" not in (fx / "src/greeter.py").read_text()
        ok = not agents and fixed and any(t in rec["main_tools"] for t in ("Edit", "Write", "MultiEdit"))
        return ok, f"typo fixed={fixed}; {seq}"
    if case == "B":
        ok = (
            types == ["shoal:applier"]
            and bool(KIND.match(agents[0]["description"] or ""))
            and agents[0]["effort"] is not None
        )
        mods = sorted((fx / "src").glob("mod_*.py"))
        done = bool(mods) and all("def version()" in m.read_text() for m in mods)
        return ok, f"files done={done}; {seq}"
    if case == "C":
        w = [a for a in agents if a["subagent_type"] == "shoal:executor"]
        ok = (
            bool(agents)
            and types[0] == "shoal:executor"
            and all(
                KIND.match(a["description"] or "") and a["effort"] is not None
                for a in w
            )
        )
        return ok, seq
    if case in ("D1", "D2"):
        sc = [a for a in agents if a["subagent_type"] == "shoal:scout"]
        mode = parallel_mode(sc)
        par = len(sc) == 2 and mode in ("same-message", "before-result")
        ok = len(sc) == 2 and par and all(a["effort"] is not None for a in sc)
        return ok, f"parallel={mode}; {seq}"
    if case in ("E1", "E2"):
        w = [a for a in agents if a["subagent_type"] == "shoal:watcher"]
        ok = (
            bool(w)
            and w[0]["run_in_background"]
            and not rec["main_bash_background"]
            and rec["final_has_pass_signal"]
        )
        direct = [
            t for t in main_tools if t["name"] == "Bash" and "run_tests" in t["cmd"]
        ]
        return ok, f"main ran suite itself={bool(direct)}; {seq}"
    if case == "F":
        r = [a for a in agents if a["subagent_type"] == "shoal:researcher"]
        arms = sorted(a["arm"] or "none" for a in r)
        mode = parallel_mode(r)
        par = len(r) == 2 and mode in ("same-message", "before-result")
        ok = (
            len(r) == 2
            and arms == ["control", "experiment"]
            and par
            and all(a["effort"] is not None for a in r)
        )
        return ok, f"arms={arms} parallel={mode}; {seq}"
    if case == "G":
        wrote = _first_write_idx(main_tools) is not None or any(
            a["subagent_type"] in ("shoal:executor", "shoal:applier") for a in agents
        )
        crit = [
            a
            for a in agents
            if a["subagent_type"] == "shoal:plan-critic" and a["mode_gaps"]
        ]
        asked = "AskUserQuestion" in rec["main_tools"]
        txt = rec["final_has_question"]
        how = (
            "plan-critic gaps"
            if crit
            else "AskUserQuestion"
            if asked
            else "text questions"
            if txt
            else "none"
        )
        return (not wrote and how != "none"), f"path={how}; implemented={wrote}; {seq}"
    if case == "H":
        diag = next(
            (t["idx"] for t in main_tools if t["name"] in ("Read", "Bash", "Grep")),
            None,
        )
        early = [
            a
            for a in agents
            if a["subagent_type"] in ("shoal:scout", "shoal:executor", "shoal:applier")
            and (diag is None or a["idx"] < diag)
        ]
        scouts = [a for a in agents if a["subagent_type"] == "shoal:scout"]
        r = subprocess.run(
            ["python3", "-m", "unittest", "tests.test_stats"],
            cwd=fx,
            capture_output=True,
            text=True,
        )
        return (not early and not scouts), f"fixed={r.returncode == 0}; {seq}"
    return False, "unknown case"


# Facts about the second round that are not in the streams (recorded by hand after the run).
PASS2_META = {
    "invocations_used": 10,
    "cases_measured": 9,
    "unmeasured": ["A"],
    "invalid_runs": [
        {
            "case": "A",
            "cost_usd": 0.1008,
            "reason": "launched without --pass 2 (small fixture, global-guard deferral active); "
            "counted against the cap and excluded from the table",
            "result_under_that_config": "typo fixed directly, no Agent call",
        }
    ],
    "guard": {
        "plugin_guard_deferral": "disabled (empty XDG_DATA_HOME per run, private XDG_STATE_HOME per run)",
        "denials_total": 0,
        "r1_exercised": False,
        "r1_note": "fixtures lived under the system temp directory, which the guard exempts from edit rules, "
        "so R1 could not fire; only the dispatch, state and exempt paths were evaluated",
    },
    "fixture": {
        "loc_per_package": {"billing": 379, "notifications": 260, "inventory": 275, "reports": 240},
        "mechanical_files": 12,
        "test_command_sleep_s": 20,
    },
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "classify", "export", "fixture"])
    ap.add_argument("case", nargs="?")
    ap.add_argument("--work", required=True)
    ap.add_argument("--pass", dest="pass_no", type=int, choices=[1, 2], default=1)
    a = ap.parse_args()
    work = Path(a.work)
    if a.cmd == "run":
        run_case(a.case, work, a.pass_no)
        return
    if a.cmd == "fixture":
        build_fixture(work / "fixtures" / a.case, a.case, a.pass_no)
        print("fixture built")
        return
    recs = [
        summarize(c, work) for c in CASES if (work / "streams" / f"{c}.meta").exists()
    ]
    if a.cmd == "classify":
        for r in recs:
            print(
                r["case"],
                "PASS" if r["pass"] else "FAIL",
                r["observation"],
                f"${r['cost_usd']}",
                r["turns"],
                r["child_models_observed"],
            )
        return
    out = {
        **({"meta": PASS2_META} if a.pass_no == 2 else {}),
        "runs_used": len(recs),
        "total_cost_usd": round(sum(r["cost_usd"] for r in recs), 4),
        "records": recs,
    }
    name = "results-pass2.json" if a.pass_no == 2 else "results.json"
    (HERE / name).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {name}")


if __name__ == "__main__":
    main()
