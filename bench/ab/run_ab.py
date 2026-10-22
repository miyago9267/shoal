#!/usr/bin/env python3
"""A/B benchmark runner: each task once with shoal, once without, same scoring.

Arms differ only in two ``--plugin-dir`` flags pointing at the shoal plugins
exported from the repo's committed HEAD.  Both arms are cut off from the
user's personal Claude setup (see README.md, "Isolation").

Python 3 stdlib only.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import threading
import fnmatch
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASKS_DIR = HERE / "tasks"
ARMS = ("shoal", "shoal-fast", "shoal-workflow", "baseline")
# shoal-fast: same plugins, prompt starts with `#fast` (main may edit small work directly).
FAST_PREFIX = "#fast\n\n"
# shoal-workflow: same plugins; the user explicitly asks for a Workflow whose agents are shoal roles.
WORKFLOW_PREFIX = (
    "Use a workflow to orchestrate this task: split it into independent slices and run them with the "
    "Workflow tool, giving each agent() call a shoal role via agentType (shoal:applier for mechanical "
    "slices, shoal:executor for slices that need judgment). Integrate and run the tests yourself at the end.\n\n"
)
PLUGIN_PATHS = ("plugins/claude", "plugins/claude-guard")
TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
TEST_TIMEOUT_S = 300
SCHEMA = "shoal-ab-v1"
# Stale bytecode from fixture authoring must never be reused.
NO_CACHE = shutil.ignore_patterns("__pycache__", "*.pyc")
# Minimal env passed through in token mode (fully private config + home).
PASSTHROUGH_ENV = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM")


# ---------------------------------------------------------------- tasks


def load_tasks(tasks_dir: Path, selected: str) -> list[dict[str, Any]]:
    """Read every task dir that follows the contract; filter by ``--tasks``."""
    tasks = []
    for meta_path in sorted(tasks_dir.glob("*/meta.json")):
        task_dir = meta_path.parent
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.setdefault("id", task_dir.name)
        meta.setdefault("category", "uncategorized")
        meta.setdefault("protected", [])
        meta.setdefault("timeout_s", 900)
        meta["dir"] = task_dir
        missing = [
            name
            for name in ("repo", "task.md", "hidden_tests/test_accept.py")
            if not (task_dir / name).exists()
        ]
        if missing:
            print(f"skip task {task_dir.name}: missing {missing}", file=sys.stderr)
            continue
        tasks.append(meta)
    if selected != "all":
        wanted = [name.strip() for name in selected.split(",") if name.strip()]
        known = {task["id"] for task in tasks}
        unknown = [name for name in wanted if name not in known]
        if unknown:
            raise SystemExit(f"unknown task ids: {unknown} (known: {sorted(known)})")
        tasks = [task for task in tasks if task["id"] in wanted]
    return tasks


# ---------------------------------------------------------------- git helpers


def git(cwd: Path, *args: str, check: bool = True) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if check and done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr.strip()[:300]}")
    return done.stdout


WORK_ROOT = Path(os.environ.get("SHOAL_AB_WORK_ROOT", Path.home() / "shoal-live-360" / "ab-runs"))


def init_workdir(task: dict[str, Any], parent: Path) -> Path:
    """Copy ``repo/`` into a fresh dir and commit it once."""
    work = parent / "work"
    shutil.copytree(task["dir"] / "repo", work, ignore=NO_CACHE)
    # Bytecode the agent creates by running tests is not a change to the project.
    git(work, "init", "-q")
    (work / ".git" / "info").mkdir(parents=True, exist_ok=True)
    (work / ".git" / "info" / "exclude").write_text("__pycache__/\n*.pyc\n")
    git(work, "config", "user.email", "bench@example.invalid")
    git(work, "config", "user.name", "bench")
    git(work, "config", "commit.gpgsign", "false")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "fixture")
    return work


def export_plugins(dest: Path) -> tuple[list[Path], str]:
    """Export the shoal plugins from committed HEAD (no WIP leaks into the arm)."""
    # SHOAL_AB_PLUGIN_REF: benchmark a branch's plugins without checking it out.
    ref = os.environ.get("SHOAL_AB_PLUGIN_REF", "HEAD")
    head = git(ROOT, "rev-parse", ref).strip()
    archive = subprocess.run(
        ["git", "archive", head, *PLUGIN_PATHS],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
    dirs = [dest / path for path in PLUGIN_PATHS]
    for path in dirs:
        if not (path / ".claude-plugin" / "plugin.json").is_file():
            raise RuntimeError(f"exported plugin has no manifest: {path}")
    return dirs, head


def diff_stats(work: Path) -> dict[str, Any]:
    """Changed files (tracked + untracked) and lines changed versus the fixture commit."""
    git(work, "add", "-A")
    names = [
        line
        for line in git(work, "diff", "--cached", "--name-only", "HEAD").splitlines()
        if line
    ]
    added = removed = 0
    for line in git(work, "diff", "--cached", "--numstat", "HEAD").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            added += int(parts[0])
            removed += int(parts[1])
    git(work, "reset", "-q")
    return {
        "changed_files": names,
        "files_changed": len(names),
        "lines_added": added,
        "lines_removed": removed,
    }


def is_test_file(name: str) -> bool:
    """Adding or editing tests is good practice, never a protected violation."""
    parts = name.split("/")
    return "tests" in parts[:-1] or parts[-1].startswith("test_")


def protected_hits(names: list[str], globs: list[str]) -> list[str]:
    hits = []
    for name in names:
        if is_test_file(name):
            continue
        for pattern in globs:
            prefix = pattern[:-3] if pattern.endswith("/**") else None
            if fnmatch.fnmatch(name, pattern) or (
                prefix and name.startswith(prefix + "/")
            ):
                hits.append(name)
                break
    return hits


# ---------------------------------------------------------------- scoring


def run_tests(work: Path, start_dir: str, override: str | None) -> dict[str, Any]:
    """unittest discovery from the project root; ``override`` is a shell command from meta."""
    if override:
        command: Any = override
        shell = True
    else:
        command = [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            start_dir,
            "-t",
            ".",
        ]
        shell = False
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        done = subprocess.run(
            command,
            cwd=work,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_S,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"passed": False, "rc": None, "tail": "test timeout"}
    tail = (done.stdout + done.stderr).strip().splitlines()[-5:]
    return {
        "passed": done.returncode == 0,
        "rc": done.returncode,
        "tail": "\n".join(tail),
    }


def score(task: dict[str, Any], work: Path) -> dict[str, Any]:
    """Diff first (so hidden tests never count as a change), then visible + hidden tests."""
    stats = diff_stats(work)
    hits = protected_hits(stats["changed_files"], task["protected"])
    visible = None
    if task.get("visible_cmd") or (work / "tests").is_dir():
        visible = run_tests(work, "tests", task.get("visible_cmd"))
    target = work / "hidden_tests"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(task["dir"] / "hidden_tests", target, ignore=NO_CACHE)
    hidden = run_tests(work, "hidden_tests", task.get("hidden_cmd"))
    visible_ok = visible is None or visible["passed"]
    return {
        **stats,
        "protected_violations": hits,
        "hidden": hidden,
        "visible": visible,
        "pass": hidden["passed"] and visible_ok and not hits,
    }


# ---------------------------------------------------------------- claude


def claude_command(args: argparse.Namespace, plugin_dirs: list[Path]) -> list[str]:
    command = [
        args.claude_bin,
        "-p",
        "--output-format",
        "json",
        "--model",
        args.model,
        "--permission-mode",
        "bypassPermissions",
        # No user/local settings: no personal hooks, enabledPlugins, output style.
        "--setting-sources",
        "project",
        "--strict-mcp-config",
    ]
    if args.max_budget_usd:
        command += ["--max-budget-usd", str(args.max_budget_usd)]
    for path in plugin_dirs:
        command += ["--plugin-dir", str(path)]
    return command


def claude_env(auth: str, private: Path) -> dict[str, str]:
    """Token mode: private config dir + home.  Keychain mode: user env, scrubbed."""
    if auth == "token":
        for name in ("config", "home", "tmp"):
            (private / name).mkdir(mode=0o700, exist_ok=True)
        return {
            **{key: os.environ[key] for key in PASSTHROUGH_ENV if key in os.environ},
            "HOME": str(private / "home"),
            "TMPDIR": str(private / "tmp"),
            "CLAUDE_CONFIG_DIR": str(private / "config"),
            TOKEN_ENV: os.environ[TOKEN_ENV],
        }
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CLAUDE_CODE_", "CLAUDECODE", "ANTHROPIC_"))
        and key != "CLAUDE_CONFIG_DIR"
    }
    # The user's shoal data dir registers guard-chain members; keep them out of both arms.
    (private / "data").mkdir(parents=True, exist_ok=True)
    env["XDG_DATA_HOME"] = str(private / "data")
    # Same as an installed shoal: hooks launch the recorded real interpreter (see plugins/claude-guard/hooks/run.sh).
    (private / "data" / "shoal").mkdir(parents=True, exist_ok=True)
    (private / "data" / "shoal" / "python").write_text(os.path.realpath(sys.executable) + "\n")
    return env


def resolve_auth(choice: str) -> str:
    if choice == "auto":
        return "token" if os.environ.get(TOKEN_ENV) else "keychain"
    if choice == "token" and not os.environ.get(TOKEN_ENV):
        raise SystemExit(f"--auth token needs {TOKEN_ENV} in the environment")
    return choice


def run_claude(
    args: argparse.Namespace,
    task: dict[str, Any],
    work: Path,
    plugin_dirs: list[Path],
    private: Path,
    arm: str = "",
) -> dict[str, Any]:
    prompt = (task["dir"] / "task.md").read_text(encoding="utf-8")
    if arm == "shoal-fast":
        prompt = FAST_PREFIX + prompt
    elif arm == "shoal-workflow":
        prompt = WORKFLOW_PREFIX + prompt
    command = claude_command(args, plugin_dirs)
    env = claude_env(args.auth_mode, private)
    out: dict[str, Any] = {"error": None}
    started = time.monotonic()
    proc = subprocess.Popen(
        command,
        cwd=work,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(prompt, timeout=task["timeout_s"])
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # take subagents/hooks down too
        except ProcessLookupError:
            pass
        stdout, stderr = proc.communicate()
        out["error"] = f"timeout after {task['timeout_s']}s"
    out["wall_s"] = round(time.monotonic() - started, 2)
    out["claude_rc"] = proc.returncode
    result: dict[str, Any] = {}
    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, list):  # tolerate the event-array shape
            parsed = next(
                (
                    e
                    for e in reversed(parsed)
                    if isinstance(e, dict) and e.get("type") == "result"
                ),
                {},
            )
        result = parsed if isinstance(parsed, dict) else {}
    except ValueError:
        if not out["error"]:
            out["error"] = (
                f"unparsable claude output (rc={proc.returncode}): {stderr.strip()[-300:]}"
            )
    for key in ("total_cost_usd", "duration_ms", "num_turns", "is_error", "subtype"):
        out[key] = result.get(key)
    if result.get("is_error") and not out["error"]:
        out["error"] = (
            f"claude {result.get('subtype')}: {str(result.get('result'))[:300]}"
        )
    return out


# ---------------------------------------------------------------- results file


def load_results(path: Path) -> dict[str, Any]:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("runs", [])
        return data
    return {"schema": SCHEMA, "runs": []}


def save_results(path: Path, data: dict[str, Any]) -> None:
    """Atomic rewrite after every run so a crash keeps finished runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


def run_key(record: dict[str, Any]) -> tuple[str, str, int]:
    return (record["task"], record["arm"], int(record["rep"]))


# ---------------------------------------------------------------- modes


def plan(
    args: argparse.Namespace, tasks: list[dict[str, Any]], arms: list[str]
) -> list[tuple]:
    return [
        (task, arm, rep)
        for rep in range(1, args.reps + 1)
        for task in tasks
        for arm in arms
    ]


def benchmark(
    args: argparse.Namespace, tasks: list[dict[str, Any]], arms: list[str]
) -> int:
    out_path = Path(args.out)
    data = load_results(out_path)
    done = {
        run_key(r) for r in data["runs"] if not (args.retry_errors and r.get("error"))
    }
    data["runs"] = [r for r in data["runs"] if run_key(r) in done]
    todo = [
        (t, a, r) for t, a, r in plan(args, tasks, arms) if (t["id"], a, r) not in done
    ]
    print(f"{len(todo)} runs to do, {len(done)} already in {out_path}", file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="shoal-ab-plugins-") as plugin_root:
        shoal_dirs, head = export_plugins(Path(plugin_root))
        lock = threading.Lock()
        finished = [0]

        def one(task: dict[str, Any], arm: str, rep: int) -> None:
            record: dict[str, Any] = {
                "task": task["id"],
                "category": task["category"],
                "arm": arm,
                "rep": rep,
                "model": args.model,
                "auth": args.auth_mode,
                "shoal_head": head,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            # Not under /tmp or $TMPDIR: the shoal guard exempts those, so the shoal arm would be a no-op.
            WORK_ROOT.mkdir(parents=True, exist_ok=True)
            parent = Path(tempfile.mkdtemp(prefix=f"shoal-ab-{task['id']}-{arm}-", dir=WORK_ROOT))
            try:
                work = init_workdir(task, parent)
                record.update(
                    run_claude(
                        args,
                        task,
                        work,
                        shoal_dirs if arm in ("shoal", "shoal-fast", "shoal-workflow") else [],
                        parent / "private",
                        arm,
                    )
                )
                record.update(score(task, work))
                if record.get("error"):
                    record["pass"] = False
            except Exception as error:  # keep going; the record carries the failure
                record["error"] = f"runner: {type(error).__name__}: {error}"
                record["pass"] = False
            finally:
                if args.keep_workdirs:
                    record["workdir"] = str(parent)
                else:
                    shutil.rmtree(parent, ignore_errors=True)
            with lock:
                data["runs"].append(record)
                save_results(out_path, data)
                finished[0] += 1
                print(
                    f"[{finished[0]}/{len(todo)}] {task['id']} {arm} rep{rep} "
                    f"pass={record.get('pass')} cost={record.get('total_cost_usd')} "
                    f"wall={record.get('wall_s')} err={record.get('error')}",
                    file=sys.stderr,
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            for future in [pool.submit(one, t, a, r) for t, a, r in todo]:
                future.result()
    return 0


def self_test(args: argparse.Namespace, tasks: list[dict[str, Any]]) -> int:
    """No claude: untouched repo must fail hidden tests; repo + solution.patch must pass."""
    failures = 0
    for task in tasks:
        verdicts = {}
        for variant in ("untouched", "solution"):
            parent = Path(tempfile.mkdtemp(prefix=f"shoal-ab-selftest-{task['id']}-"))
            try:
                work = init_workdir(task, parent)
                if variant == "solution":
                    patch = task["dir"] / "solution.patch"
                    git(work, "apply", "--whitespace=nowarn", str(patch))
                verdicts[variant] = score(task, work)
            except Exception as error:
                verdicts[variant] = {
                    "pass": False,
                    "hidden": {"passed": False},
                    "error": str(error),
                }
            finally:
                shutil.rmtree(parent, ignore_errors=True)
        sol, raw = verdicts["solution"], verdicts["untouched"]
        ok = sol["pass"] and not raw["hidden"]["passed"]
        failures += not ok
        print(
            f"{'OK  ' if ok else 'FAIL'} {task['id']:<20} solution: pass={sol['pass']} "
            f"files={sol.get('files_changed')} +{sol.get('lines_added')}/-{sol.get('lines_removed')} "
            f"protected={sol.get('protected_violations')} | untouched hidden_passed={raw['hidden']['passed']}"
        )
        if not ok:
            for name, verdict in verdicts.items():
                detail = verdict.get("error") or verdict["hidden"].get("tail") or ""
                print(f"     {name}: {detail}")
                if verdict.get("visible") and not verdict["visible"]["passed"]:
                    print(f"     {name} visible: {verdict['visible']['tail']}")
    print(f"self-test: {len(tasks) - failures}/{len(tasks)} tasks OK")
    return 1 if failures or not tasks else 0


def summarize(path: Path) -> int:
    runs = load_results(path)["runs"]
    if not runs:
        print("no runs")
        return 1

    def row(label: str, group: list[dict[str, Any]]) -> str:
        costs = [
            r["total_cost_usd"]
            for r in group
            if isinstance(r.get("total_cost_usd"), (int, float))
        ]
        walls = [
            r["wall_s"] for r in group if isinstance(r.get("wall_s"), (int, float))
        ]
        passed = sum(1 for r in group if r.get("pass"))
        prot = sum(1 for r in group if r.get("protected_violations"))
        errors = sum(1 for r in group if r.get("error"))
        fmt = lambda v, p="{:.4f}": p.format(v) if v is not None else "-"
        return (
            f"{label:<28} {len(group):>4} {passed:>4} {fmt(passed / len(group), '{:.0%}'):>6} "
            f"{fmt(statistics.mean(costs) if costs else None):>9} "
            f"{fmt(statistics.median(costs) if costs else None):>9} "
            f"{fmt(statistics.mean(walls) if walls else None, '{:.1f}'):>8} {prot:>5} {errors:>4}"
        )

    header = f"{'group':<28} {'n':>4} {'pass':>4} {'rate':>6} {'cost_avg':>9} {'cost_med':>9} {'wall_s':>8} {'prot':>5} {'err':>4}"
    print(header)
    print("-" * len(header))
    arms = sorted({r["arm"] for r in runs})
    for arm in arms:
        print(row(arm, [r for r in runs if r["arm"] == arm]))
    print()
    for category in sorted({r.get("category", "?") for r in runs}):
        for arm in arms:
            group = [
                r
                for r in runs
                if r["arm"] == arm and r.get("category", "?") == category
            ]
            if group:
                print(row(f"{category} / {arm}", group))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tasks", default="all", help="comma list of task ids, or all")
    parser.add_argument("--arms", default="shoal,baseline")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument(
        "--model", help="model id for the parent session (required for live runs)"
    )
    parser.add_argument("--out", default=str(HERE / "results" / "ab.json"))
    parser.add_argument("--dry-run", action="store_true", help="print the plan only")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="score solution.patch instead of calling claude",
    )
    parser.add_argument(
        "--summarize", metavar="JSON", help="print the per-arm/per-category table"
    )
    parser.add_argument("--tasks-dir", default=str(TASKS_DIR))
    parser.add_argument("--jobs", type=int, default=1, help="runs in parallel")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument(
        "--auth",
        choices=("auto", "token", "keychain"),
        default="auto",
        help=f"token: {TOKEN_ENV} + private config dir; keychain: user login, settings cut to project",
    )
    parser.add_argument(
        "--max-budget-usd", type=float, help="per-run --max-budget-usd cap"
    )
    parser.add_argument(
        "--retry-errors", action="store_true", help="re-run records that have an error"
    )
    parser.add_argument("--keep-workdirs", action="store_true")
    args = parser.parse_args(argv)

    if args.summarize:
        return summarize(Path(args.summarize))
    tasks = load_tasks(Path(args.tasks_dir).resolve(), args.tasks)
    if args.self_test:
        return self_test(args, tasks)
    arms = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    if not arms or any(arm not in ARMS for arm in arms):
        raise SystemExit(f"--arms must be a subset of {ARMS}")
    if args.reps < 1:
        raise SystemExit("--reps must be >= 1")
    if args.dry_run:
        args.auth_mode = resolve_auth(args.auth)
        done = {run_key(r) for r in load_results(Path(args.out))["runs"]}
        print(
            "(shoal --plugin-dir paths are exported from git HEAD into a temp dir at run time)"
        )
        print(f"auth={args.auth_mode} model={args.model or '<missing>'} out={args.out}")
        for arm in arms:
            print(
                f"  {arm}: {' '.join(claude_command(args, [ROOT / p for p in PLUGIN_PATHS] if arm == 'shoal' else []))}"
            )
        for task, arm, rep in plan(args, tasks, arms):
            mark = "skip (in --out)" if (task["id"], arm, rep) in done else "run"
            print(
                f"  {task['id']:<20} {task['category']:<12} {arm:<9} rep{rep} timeout={task['timeout_s']}s {mark}"
            )
        return 0
    if not args.model:
        raise SystemExit("--model is required for live runs")
    if shutil.which(args.claude_bin) is None:
        raise SystemExit(f"claude binary not found: {args.claude_bin}")
    args.auth_mode = resolve_auth(args.auth)
    return benchmark(args, tasks, arms)


if __name__ == "__main__":
    sys.exit(main())
