#!/usr/bin/env python3
"""證明兩個 git ref 的 render 輸出逐位元組相同。

用法：python3 tools/render_equiv.py --base origin/main --head HEAD

對每個 ref 做 git archive，在 temp root 內用該 ref 自己的 tools/render.py 對六個 host 執行 --write；
另做一份 relay root，以 tests/fixtures/relay/relay.binding.toml 為 overlay 執行 claude-plugin --write，
輸出以 `relay:` 前綴併入比對。最後對 head 的 working tree 執行 render --check。有任何差異即非 0。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOSTS = ("claude", "codex", "agy", "grok", "opencode", "claude-plugin")
OVERLAY = "tests/fixtures/relay/relay.binding.toml"
# --write 會寫入的路徑（目錄或單檔，相對 repo 根）：五個 dist、claude-plugin 與 codex 的 mirror 目標。
OUTPUTS = (
    "hosts/claude/dist",
    "templates",
    "hosts/agy/dist",
    "hosts/grok/dist",
    "hosts/opencode/dist",
    "plugins/claude",
    "plugins/claude-guard",
    ".claude-plugin/marketplace.json",
    "plugins/codex/skills/shoal-orchestration/references/orchestration-policy.md",
    "plugins/codex/skills/shoal-orchestration/references/workflow-extensions.md",
)
RELAY_OUTPUTS = (
    "plugins/claude",
    "plugins/claude-guard",
    ".claude-plugin/marketplace.json",
)


def archive(repo: Path, ref: str, dest: Path) -> None:
    # 關閉 autocrlf，避免 Windows 的全域設定讓 git archive 輸出 CRLF
    data = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(repo), "archive", ref],
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data") if hasattr(
            tarfile, "data_filter"
        ) else tar.extractall(dest)


def render(root: Path, host: str, *extra: str) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "render.py"),
            "--host",
            host,
            "--write",
            "--root",
            str(root),
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"render --write --host {host} 失敗 ({root}):\n{proc.stderr}{proc.stdout}"
        )


def collect(root: Path, outputs: tuple[str, ...], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for item in outputs:
        path = root / item
        files = (
            [path]
            if path.is_file()
            else sorted(p for p in path.rglob("*") if p.is_file())
            if path.is_dir()
            else []
        )
        for p in files:
            if "__pycache__" not in p.parts:
                out[prefix + p.relative_to(root).as_posix()] = hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
    return out


def render_ref(repo: Path, ref: str, work: Path, label: str) -> dict[str, str]:
    default, relay = work / label / "default", work / label / "relay"
    archive(repo, ref, default)
    archive(repo, ref, relay)
    for host in HOSTS:
        render(default, host)
    render(relay, "claude-plugin", "--overlay", str(relay / OVERLAY))
    return {**collect(default, OUTPUTS), **collect(relay, RELAY_OUTPUTS, "relay:")}


def total(hashes: dict[str, str], relay: bool) -> str:
    lines = (
        f"{p} {h}\n"
        for p, h in sorted(hashes.items())
        if p.startswith("relay:") == relay
    )
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def check_tree(repo: Path) -> list[str]:
    failed = []
    for host in HOSTS:
        proc = subprocess.run(
            [
                sys.executable,
                str(repo / "tools" / "render.py"),
                "--host",
                host,
                "--check",
                "--root",
                str(repo),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            failed.append(f"render --check --host {host}:\n{proc.stderr}")
    return failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument(
        "--repo", type=Path, default=REPO, help="git repo 根目錄（測試用）"
    )
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="略過對 head working tree 的 render --check（測試用）",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="render-equiv-") as tmp:
        base = render_ref(args.repo, args.base, Path(tmp), "base")
        head = render_ref(args.repo, args.head, Path(tmp), "head")
    problems = [f"缺少: {p}" for p in sorted(base.keys() - head.keys())]
    problems += [f"多出: {p}" for p in sorted(head.keys() - base.keys())]
    problems += [
        f"內容不同: {p}"
        for p in sorted(base.keys() & head.keys())
        if base[p] != head[p]
    ]
    problems += [] if args.no_check else check_tree(args.repo)
    default_n = sum(not p.startswith("relay:") for p in head)
    summary = (
        f"base={args.base} head={args.head} default={total(head, False)} ({default_n} files) "
        f"relay={total(head, True)} ({len(head) - default_n} files)"
    )
    if problems:
        print("render_equiv: FAIL " + summary, file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("render_equiv: OK " + summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
