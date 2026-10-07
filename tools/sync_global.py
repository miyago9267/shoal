#!/usr/bin/env python3
"""把 shoal committed HEAD 同步到 Codex、Grok、agy、OpenCode 的全域安裝（每日同步用）。

用法：
  python3 tools/sync_global.py [--host codex|grok|agy|opencode ...]       dry-run（預設），不寫入
  python3 tools/sync_global.py --apply [--host ...] [--strict]            實際更新

預設四個 host 都跑；每個 host 輸出一行摘要：
  <host>: up-to-date | updated (<what>) | skipped (<reason>) | failed (<reason>)
沒有 --apply 時 updated 行尾會加 [dry-run]（代表「會更新」）。exit 0，除非 --strict 且有 failed。

只更新 shoal 自己安裝的內容，來源一律是 repo 的 committed HEAD（不是工作樹）：
  codex     tools/install_hooks.py --host codex（dispatch guard 與 hook entry），加上
            templates/agents/*.toml 對 <CODEX_HOME 或 ~/.codex>/agents/ 的 role：已相同就略過；
            與 HEAD 不同但位元組等於該 template 的某個歷史版本才取代（temp file + rename）；
            其他（使用者改過、未知來源、symlink）一律不動並回報 drift。不跑 install/install.py。
  grok      tools/install_grok.py dry-run 回報有差異才 --apply（不帶 --fix-toggles，不動 config.toml）。
  agy       tools/install_hooks.py --host agy；agents/skill 是指向 hosts/agy/dist 的 symlink，
            只檢查 symlink 還指在那裡（回報，不修）。
  opencode  需要 bun。用 install_global.sh 同樣的步驟建出 HEAD 的 bundle，與全域 config dir 的
            plugin、roles、pilotfish/*.json 比對；有差異就 install.sh --global --disable 再 --enable。
            dotfile 裡的 harness copy 只回報是否相同，不寫入。
            已停用（manifest 不是 enabled）或從未安裝就略過，不替使用者重新啟用。

stdlib only；重複執行不會改變結果，沒有差異時不寫檔、不建備份。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Mapping, Optional

REPO = Path(__file__).resolve().parents[1]
HOSTS = ("codex", "grok", "agy", "opencode")
ROLE_DIR = "templates/agents"
OPENCODE_INSTALL = "hosts/opencode/plugin/install/install.sh"
DEFAULT_HARNESS = Path("dotfile/config/opencode-harness/plugins/pilotfish-opencode.js")

Result = tuple[str, str]  # (status, detail)


class SyncError(Exception):
    """該 host 同步失敗（摘要為 failed）。"""


class Ctx:
    def __init__(
        self, repo: Path, ref: str, apply: bool, env: Mapping[str, str]
    ) -> None:
        self.repo, self.ref, self.apply, self.env = repo, ref, apply, dict(env)

    @property
    def home(self) -> Path:
        return Path(self.env.get("HOME") or Path.home())

    def abs_env(self, key: str, default: Path) -> Path:
        value = self.env.get(key)
        return Path(value).expanduser() if value else default


# ---- 共用 ----
def one_line(text: str) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return (lines[-1] if lines else "no output")[:200]


def run(
    cmd: list[str], ctx: Ctx, cwd: Optional[Path] = None, timeout: int = 600
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            env=ctx.env,
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SyncError(f"{Path(cmd[0]).name} 無法執行: {exc}") from exc


def git(ctx: Ctx, *args: str, check: bool = True) -> bytes:
    cmd = ["git", "-c", "core.autocrlf=false", "-C", str(ctx.repo), *args]
    try:
        proc = subprocess.run(cmd, env=ctx.env, capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SyncError(f"git {args[0]} 無法執行: {exc}") from exc
    if proc.returncode != 0 and check:
        raise SyncError(
            f"git {' '.join(args[:2])} 失敗: "
            + one_line(proc.stderr.decode("utf-8", "replace"))
        )
    return proc.stdout if proc.returncode == 0 else b""


def atomic_replace(path: Path, data: bytes, mode: int) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.shoal-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def installer_changes(script: str, extra: list[str], ctx: Ctx) -> bool:
    """跑 install_hooks / install_grok 的 --json 計畫；回傳寫入前是否有差異。"""
    cmd = [
        sys.executable,
        str(REPO / "tools" / script),
        *extra,
        "--json",
        "--repo",
        str(ctx.repo),
        "--ref",
        ctx.ref,
    ]
    plan = run(cmd, ctx)
    if plan.returncode != 0:
        raise SyncError(
            f"{script} exit {plan.returncode}: {one_line(plan.stderr or plan.stdout)}"
        )
    changes = None
    for line in plan.stdout.splitlines():
        if line.startswith('{"changes"'):
            changes = json.loads(line)["changes"]
    if changes is None:
        raise SyncError(f"{script} 沒有輸出 --json 計畫")
    changed = bool(changes)
    if changed and ctx.apply:
        done = run(cmd + ["--apply"], ctx)
        if done.returncode != 0:
            raise SyncError(
                f"{script} --apply exit {done.returncode}: {one_line(done.stderr or done.stdout)}"
            )
    return changed


# ---- codex ----
def codex_home(ctx: Ctx) -> Path:
    return ctx.abs_env("CODEX_HOME", ctx.home / ".codex")


def template_history(ctx: Ctx, path: str) -> set[bytes]:
    revs = git(ctx, "rev-list", ctx.ref, "--", path).decode().split()
    out: set[bytes] = set()
    for rev in revs:
        blob = git(ctx, "show", f"{rev}:{path}", check=False)
        if blob:
            out.add(blob)
    return out


def sync_codex_roles(ctx: Ctx, home: Path) -> tuple[list[str], list[str], list[str]]:
    agents = home / "agents"
    if not agents.is_dir():
        return [], [], []
    listing = (
        git(ctx, "ls-tree", "--name-only", ctx.ref, f"{ROLE_DIR}/").decode().split()
    )
    updated: list[str] = []
    added: list[str] = []
    drift: list[str] = []
    for path in sorted(p for p in listing if p.endswith(".toml")):
        name = Path(path).name
        target = agents / name
        head = git(ctx, "show", f"{ctx.ref}:{path}")
        if target.is_symlink() or (target.exists() and not target.is_file()):
            drift.append(name)
            continue
        if not target.exists():
            added.append(name)
            if ctx.apply:
                atomic_replace(target, head, 0o644)
            continue
        current = target.read_bytes()
        if current == head:
            continue
        if current in template_history(ctx, path):
            updated.append(name)
            if ctx.apply:
                atomic_replace(target, head, stat.S_IMODE(target.stat().st_mode))
        else:
            drift.append(name)
    return updated, added, drift


def sync_codex(ctx: Ctx) -> Result:
    home = codex_home(ctx)
    if not home.is_dir():
        return "skipped", f"{home} 不存在"
    parts: list[str] = []
    if installer_changes("install_hooks.py", ["--host", "codex"], ctx):
        parts.append("guard hooks")
    updated, added, drift = sync_codex_roles(ctx, home)
    if updated:
        parts.append("roles: " + ", ".join(updated))
    if added:
        parts.append("new roles: " + ", ".join(added))
    drift_note = ("drift: " + ", ".join(drift)) if drift else ""
    if parts:
        return "updated", "; ".join(parts + ([drift_note] if drift_note else []))
    return "up-to-date", drift_note


# ---- grok ----
def sync_grok(ctx: Ctx) -> Result:
    home = ctx.abs_env("GROK_HOME", ctx.home / ".grok")
    if not home.is_dir():
        return "skipped", f"{home} 不存在"
    if installer_changes("install_grok.py", [], ctx):
        return "updated", "dist files"
    return "up-to-date", ""


# ---- agy ----
def agy_link_problems(ctx: Ctx) -> list[str]:
    config = ctx.home / ".gemini" / "config"
    problems: list[str] = []
    for kind in ("agents", "skills"):
        listing = (
            git(ctx, "ls-tree", "--name-only", ctx.ref, f"hosts/agy/dist/{kind}/")
            .decode()
            .split()
        )
        for path in sorted(listing):
            name = Path(path).name
            link = config / kind / name
            expected = os.path.realpath(ctx.repo / path)
            if not link.is_symlink():
                problems.append(f"{kind}/{name} 不是 symlink")
            elif os.path.realpath(link) != expected:
                problems.append(f"{kind}/{name} 沒指向 hosts/agy/dist")
    return problems


def sync_agy(ctx: Ctx) -> Result:
    home = ctx.home / ".gemini"
    if not home.is_dir():
        return "skipped", f"{home} 不存在"
    changed = installer_changes("install_hooks.py", ["--host", "agy"], ctx)
    problems = agy_link_problems(ctx)
    note = ("symlink drift: " + ", ".join(problems)) if problems else "symlinks ok"
    if changed:
        return "updated", f"guard hooks; {note}"
    return "up-to-date", note


# ---- opencode ----
def opencode_config_dir(ctx: Ctx) -> Path:
    base = ctx.abs_env("OPENCODE_CONFIG_DIR", ctx.home / ".config" / "opencode")
    return Path(os.path.realpath(base))


def opencode_manifest(ctx: Ctx) -> Path:
    state = ctx.abs_env("XDG_STATE_HOME", ctx.home / ".local" / "state")
    return state / "shoal" / "opencode-global" / "install.manifest"


def manifest_state(manifest: Path) -> Optional[str]:
    try:
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.startswith("state|"):
                return line.split("|", 1)[1]
    except OSError:
        pass
    return None


def build_opencode(ctx: Ctx, work: Path, bun: str) -> dict[str, Path]:
    """與 install_global.sh 相同：git archive HEAD 的 hosts/opencode，bun install、bun build。"""
    archive = subprocess.run(
        ["git", "-C", str(ctx.repo), "archive", ctx.ref, "hosts/opencode"],
        env=ctx.env,
        capture_output=True,
        timeout=120,
    )
    if archive.returncode != 0:
        raise SyncError(
            "git archive hosts/opencode 失敗: "
            + one_line(archive.stderr.decode("utf-8", "replace"))
        )
    untar = subprocess.run(
        ["tar", "-x", "-C", str(work)],
        input=archive.stdout,
        capture_output=True,
        timeout=120,
    )
    if untar.returncode != 0:
        raise SyncError("解開 hosts/opencode 失敗")
    src = work / "hosts" / "opencode"
    dist = src / "dist"
    if not (dist / "roles").is_dir():
        raise SyncError("HEAD 沒有 hosts/opencode/dist/roles")
    bundle = work / "pilotfish-opencode.js"
    plugin = src / "plugin"
    for step in (
        [bun, "install", "--frozen-lockfile"],
        [
            bun,
            "build",
            "src/plugin/pilotfish-opencode.ts",
            "--bundle",
            "--format",
            "esm",
            "--target",
            "bun",
            "--outfile",
            str(bundle),
        ],
    ):
        proc = run(step, ctx, cwd=plugin)
        if proc.returncode != 0:
            raise SyncError(
                f"bun {step[1]} 失敗: {one_line(proc.stderr or proc.stdout)}"
            )
    if not bundle.is_file() or bundle.stat().st_size == 0:
        raise SyncError("plugin build 沒有輸出")
    expected = {"plugins/pilotfish-opencode.js": bundle}
    for role in sorted((dist / "roles").glob("*.md")):
        expected[f"agents/{role.name}"] = role
    for name in ("catalog.json", "routing.json"):
        if not (dist / name).is_file():
            raise SyncError(f"HEAD 沒有 hosts/opencode/dist/{name}")
        expected[f"pilotfish/{name}"] = dist / name
    return expected


def digest(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def opencode_diffs(config: Path, expected: dict[str, Path]) -> list[str]:
    return [rel for rel, src in expected.items() if digest(config / rel) != digest(src)]


def sync_opencode(ctx: Ctx) -> Result:
    bun = shutil.which("bun", path=ctx.env.get("PATH", os.defpath))
    if not bun:
        return "skipped", "bun not found"
    config = opencode_config_dir(ctx)
    if not config.is_dir():
        return "skipped", f"{config} 不存在"
    state = manifest_state(opencode_manifest(ctx))
    if state != "enabled":
        return "skipped", "全域安裝未啟用" if state else "尚未全域安裝"
    install_sh = ctx.repo / OPENCODE_INSTALL
    if not install_sh.is_file():
        return "skipped", f"{OPENCODE_INSTALL} 不存在"
    with tempfile.TemporaryDirectory(prefix="shoal-sync-opencode-") as tmp:
        work = Path(tmp)
        expected = build_opencode(ctx, work, bun)
        diffs = opencode_diffs(config, expected)
        harness = ctx.abs_env("OPENCODE_HARNESS_PLUGIN", ctx.home / DEFAULT_HARNESS)
        note = ""
        if harness.is_file():
            same = digest(harness) == digest(expected["plugins/pilotfish-opencode.js"])
            note = f"harness copy {'matches' if same else 'differs'}"
        if not diffs:
            return "up-to-date", note
        what = ", ".join(diffs)
        if ctx.apply:
            base = ["sh", str(install_sh), "--global", "--config-dir", str(config)]
            for action in ("--disable", "--enable"):
                proc = run(base + [action], ctx)
                if proc.returncode != 0:
                    tail = (
                        "；已停用，需手動 install.sh --global --enable"
                        if action == "--enable"
                        else ""
                    )
                    raise SyncError(
                        f"install.sh {action} 失敗: {one_line(proc.stderr or proc.stdout)}{tail}"
                    )
            left = opencode_diffs(config, expected)
            if left:
                raise SyncError("安裝後仍不一致: " + ", ".join(left))
        return "updated", what + (f"; {note}" if note else "")


RUNNERS: dict[str, Callable[[Ctx], Result]] = {
    "codex": sync_codex,
    "grok": sync_grok,
    "agy": sync_agy,
    "opencode": sync_opencode,
}


def format_line(host: str, status: str, detail: str, apply: bool) -> str:
    line = f"{host}: {status}" + (f" ({detail})" if detail else "")
    return line + (" [dry-run]" if status == "updated" and not apply else "")


def main(
    argv: Optional[list[str]] = None, env: Optional[Mapping[str, str]] = None
) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], allow_abbrev=False
    )
    parser.add_argument("--host", nargs="+", choices=HOSTS, help="預設四個 host 全跑")
    parser.add_argument(
        "--apply", action="store_true", help="實際更新；沒有這個旗標一律 dry-run"
    )
    parser.add_argument(
        "--strict", action="store_true", help="有任何 host failed 就 exit 1"
    )
    parser.add_argument("--repo", type=Path, default=REPO, help="shoal repo（測試用）")
    parser.add_argument("--ref", default="HEAD", help="要同步的 ref，預設 HEAD")
    args = parser.parse_args(argv)
    ctx = Ctx(args.repo, args.ref, args.apply, os.environ if env is None else env)
    failed = False
    for host in dict.fromkeys(args.host or HOSTS):
        try:
            status, detail = RUNNERS[host](ctx)
        except SyncError as exc:
            status, detail = "failed", str(exc)
        except Exception as exc:  # 單一 host 的意外不能擋住其他 host
            status, detail = "failed", f"{type(exc).__name__}: {exc}"
        failed = failed or status == "failed"
        print(
            format_line(host, status, " ".join(detail.split()), args.apply), flush=True
        )
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
