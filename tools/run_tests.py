#!/usr/bin/env python3
"""平行執行 tests/ 的 unittest，只用標準函式庫。

    python3 tools/run_tests.py                       # 全套，進程數 = CPU 數
    python3 tools/run_tests.py test_shoal_guard      # 指定 module（可多個）
    python3 tools/run_tests.py test_shoal_guard.VectorTests.test_shared_vectors
    python3 tools/run_tests.py -k relay -k overlay   # 測試 id 含關鍵字（任一）
    python3 tools/run_tests.py -j 4 -v               # 進程數、逐個 unit 輸出
    python3 tools/run_tests.py --list                # 只列出會跑的測試
    python3 tools/run_tests.py --write-timings       # 全套跑完後更新 tests/timings.json

切分：以 class 為單位，耗時超過 SPLIT_SECONDS 的 class 依 tests/timings.json 拆成多個 unit。
每個 unit 是一個獨立進程，有自己的 TMPDIR、TMP、TEMP 與 XDG_STATE_HOME，所以測試之間不共用臨時
路徑或 state。SERIAL_PREFIXES 內的測試無法平行，並行階段結束後逐個執行。
結束碼與 unittest 一致：全過 0、有失敗或錯誤 1、沒有測試 5。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
TIMINGS = TESTS / "timings.json"
SPLIT_SECONDS = 6.0
UNKNOWN_SECONDS = 0.05
UNIT_TIMEOUT = 900
KEEP_TIMING_OVER = 0.3
# 無法平行的測試：test id 的前綴（module、module.Class 或完整 id）。
# 這兩個斷言 subprocess 的延遲（和裸 python 比、或 1 秒內），CPU 滿載時會誤判。
SERIAL_PREFIXES = (
    "test_shoal_guard.ChainCliTests.test_event_nobody_needs_exits_fast_without_state_or_spawn",
    "test_shoal_guard.ChainCliTests.test_fifo_manifest_does_not_block_and_guard_stays_on",
)


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def normalize(name):
    name = name.replace("\\", "/")
    if name.endswith(".py"):
        name = name[:-3]
    name = name.replace("/", ".")
    return name[len("tests.") :] if name.startswith("tests.") else name


def load_tests(selectors):
    sys.path.insert(0, str(TESTS))
    loader = unittest.TestLoader()
    modules = sorted(p.stem for p in TESTS.glob("test*.py"))
    if selectors:
        wanted = {n.split(".")[0] for n in selectors}
        modules = [m for m in modules if m in wanted]
    tests = []
    for module in modules:
        tests.extend(flatten(loader.loadTestsFromName(module)))
    return tests


def matches(test_id, selectors, keywords):
    if selectors and not any(
        test_id == s or test_id.startswith(s + ".") for s in selectors
    ):
        return False
    return not keywords or any(k in test_id for k in keywords)


def is_serial(test_id):
    return any(test_id == p or test_id.startswith(p + ".") for p in SERIAL_PREFIXES)


def build_units(test_ids, timings):
    """回傳 [(weight, [test ids])]，依 weight 由大到小。"""
    by_class = {}
    for tid in test_ids:
        by_class.setdefault(tid.rsplit(".", 1)[0], []).append(tid)
    units = []
    for ids in by_class.values():
        cost = {t: timings.get(t, UNKNOWN_SECONDS) for t in ids}
        total = sum(cost.values())
        if total <= SPLIT_SECONDS:
            units.append((total, ids))
            continue
        bins = -(-int(total) // int(SPLIT_SECONDS)) or 1
        loads = [[0.0, []] for _ in range(max(bins, 2))]
        for tid in sorted(ids, key=lambda t: -cost[t]):
            target = min(loads, key=lambda b: b[0])
            target[0] += cost[tid]
            target[1].append(tid)
        units.extend((load, members) for load, members in loads if members)
    units.sort(key=lambda u: -u[0])
    return units


class TimedResult(unittest.TextTestResult):
    def startTest(self, test):
        self.started = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        self.durations[test.id()] = time.perf_counter() - self.started
        super().stopTest(test)


def worker(out_path, ids):
    import io

    sys.path.insert(0, str(TESTS))
    suite = unittest.TestLoader().loadTestsFromNames(ids)
    runner = unittest.TextTestRunner(
        stream=io.StringIO(), verbosity=0, resultclass=TimedResult
    )
    result = runner._makeResult()
    result.durations = {}
    start = time.perf_counter()
    suite(result)
    payload = {
        "ran": result.testsRun,
        "failures": [(t.id(), tb) for t, tb in result.failures],
        "errors": [(t.id(), tb) for t, tb in result.errors],
        "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": [t.id() for t in result.unexpectedSuccesses],
        "durations": result.durations,
        "seconds": time.perf_counter() - start,
    }
    Path(out_path).write_text(json.dumps(payload), encoding="utf-8")
    return 0


def run_unit(index, ids, base):
    unit_dir = base / f"u{index}"
    tmp, state = unit_dir / "t", unit_dir / "s"
    tmp.mkdir(parents=True)
    state.mkdir()
    out = unit_dir / "out.json"
    env = dict(
        os.environ,
        TMPDIR=str(tmp),
        TMP=str(tmp),
        TEMP=str(tmp),
        XDG_STATE_HOME=str(state),
    )
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", str(out), *ids]
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=UNIT_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return {
            "crash": f"unit 逾時（{UNIT_TIMEOUT}s）：{ids[0]} 等 {len(ids)} 個測試",
            "ids": ids,
        }
    if not out.is_file():
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        return {
            "crash": f"worker 異常結束（exit {proc.returncode}），{len(ids)} 個測試未完成：{ids[0]} ...\n{tail}",
            "ids": ids,
        }
    return json.loads(out.read_text(encoding="utf-8"))


def parse_args(argv):
    p = argparse.ArgumentParser(description="平行執行 tests/ 的 unittest。")
    p.add_argument(
        "targets",
        nargs="*",
        help="module、module.Class 或完整測試 id（tests/test_x.py 也可）",
    )
    p.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
        help="進程數（預設 CPU 數）",
    )
    p.add_argument(
        "-k",
        dest="keywords",
        action="append",
        default=[],
        help="測試 id 含此關鍵字才跑，可重複",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true", help="每個 unit 跑完輸出一行"
    )
    p.add_argument("--list", action="store_true", help="只列出會跑的測試 id")
    p.add_argument(
        "--write-timings",
        action="store_true",
        help="全套跑完且通過後更新 tests/timings.json",
    )
    return p.parse_args(argv)


def main(argv):
    if len(argv) > 1 and argv[0] == "--worker":
        return worker(argv[1], argv[2:])
    args = parse_args(argv)
    selectors = [normalize(t) for t in args.targets]
    started = time.perf_counter()
    loaded = load_tests(selectors)
    load_errors, ids = [], []
    for test in loaded:
        if type(test).__name__ == "_FailedTest":
            load_errors.append(test)
        elif matches(test.id(), selectors, args.keywords):
            ids.append(test.id())
    if args.list:
        print("\n".join(sorted(ids)))
        return 0

    timings = (
        json.loads(TIMINGS.read_text(encoding="utf-8")) if TIMINGS.is_file() else {}
    )
    parallel = [t for t in ids if not is_serial(t)]
    serial = [t for t in ids if is_serial(t)]
    units = build_units(parallel, timings)
    serial_units = [(0.0, [t]) for t in serial]

    base = Path(tempfile.mkdtemp(prefix="st-"))
    totals = {"ran": 0, "skipped": 0, "expected_failures": 0}
    problems, unexpected, durations = [], [], {}
    counter = iter(range(10**9))

    def absorb(unit_ids, r):
        if "crash" in r:
            problems.append(("ERROR", unit_ids[0], r["crash"]))
            print(f"ERROR: {r['crash'].splitlines()[0]}", flush=True)
            return
        for key in totals:
            totals[key] += r[key]
        problems.extend(("FAIL", tid, tb) for tid, tb in r["failures"])
        problems.extend(("ERROR", tid, tb) for tid, tb in r["errors"])
        unexpected.extend(r["unexpected_successes"])
        durations.update(r["durations"])
        bad = len(r["failures"]) + len(r["errors"])
        if args.verbose or bad:
            tag = "FAIL" if bad else "ok"
            print(
                f"[{tag}] {unit_ids[0].rsplit('.', 1)[0]} ({r['ran']} tests, {r['seconds']:.1f}s, 結束於 {time.perf_counter() - started:.0f}s)",
                flush=True,
            )

    def submit(pool, unit_list):
        futures = {
            pool.submit(run_unit, next(counter), m, base): m for _, m in unit_list
        }
        for fut in as_completed(futures):
            absorb(futures[fut], fut.result())

    try:
        with ThreadPoolExecutor(max_workers=max(args.jobs, 1)) as pool:
            submit(pool, units)
        if serial_units:
            with ThreadPoolExecutor(max_workers=1) as pool:
                submit(pool, serial_units)
    finally:
        shutil.rmtree(base, ignore_errors=True)

    for test in load_errors:
        result = unittest.TestResult()
        test.run(result)
        totals["ran"] += 1
        problems.extend(("ERROR", tid.id(), tb) for tid, tb in result.errors)

    elapsed = time.perf_counter() - started
    for kind, tid, tb in problems:
        print("=" * 70 + f"\n{kind}: {tid}\n" + "-" * 70 + f"\n{tb}")
    for tid in unexpected:
        print(f"UNEXPECTED SUCCESS: {tid}")
    print("-" * 70)
    print(
        f"Ran {totals['ran']} test{'s' if totals['ran'] != 1 else ''} in {elapsed:.3f}s (jobs={args.jobs})\n"
    )
    if totals["ran"] == 0:
        print("NO TESTS RAN")
        return 5
    extras = []
    if totals["skipped"]:
        extras.append(f"skipped={totals['skipped']}")
    if totals["expected_failures"]:
        extras.append(f"expected failures={totals['expected_failures']}")
    fails = sum(1 for k, *_ in problems if k == "FAIL")
    errors = sum(1 for k, *_ in problems if k == "ERROR")
    ok = not problems and not unexpected
    if ok:
        print("OK" + (f" ({', '.join(extras)})" if extras else ""))
    else:
        parts = [f"failures={fails}", f"errors={errors}"]
        if unexpected:
            parts.append(f"unexpected successes={len(unexpected)}")
        print("FAILED (" + ", ".join(parts + extras) + ")")
    if ok and args.write_timings and not (selectors or args.keywords):
        slow = {
            k: round(v, 1)
            for k, v in sorted(durations.items())
            if v >= KEEP_TIMING_OVER
        }
        TIMINGS.write_text(
            json.dumps(slow, indent=0, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"已寫入 {TIMINGS.relative_to(ROOT)}（{len(slow)} 筆）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
