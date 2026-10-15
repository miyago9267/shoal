#!/usr/bin/env python3
"""把 shoal 的 OpenCode role、plugin 與控制檔安裝到全域 config dir（stdlib only，macOS、Linux、Windows 相同）。

hosts/opencode/plugin/install/install_global.sh 的 Python 版（docs/specs/repo-layout D9）：行為與 manifest
格式相同，所以兩者可以互相接手。入口 `tools/shoal_install.py --host opencode` 與 `tools/sync_global.py` 都呼叫這裡。

用法：
  python3 tools/opencode_global.py [--config-dir DIR] (--enable|--disable|--rollback) [--dry-run]

寫入 <config-dir>：agents/*.md、plugins/shoal-opencode.js、shoal/{catalog,routing}.json
manifest 與備份放在 ${XDG_STATE_HOME:-$HOME/.local/state}/shoal/opencode-global（不進 config dir）。
外部 CLI 只有 git 與 bun（用 shutil.which 解析）；bun 用來把 plugin 打成單一 bundle。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Mapping, Optional

REPO = Path(__file__).resolve().parents[1]
LEGACY_PLUGIN_ENTRY = "plugins/pilotfish-opencode.js"  # 2.0.0 之前的舊名
LEGACY_CONTROL_PREFIX = "pilotfish/"


class OpenCodeError(Exception):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state_dir(env: Mapping[str, str]) -> Path:
    base = env.get("XDG_STATE_HOME") or str(
        Path(env.get("HOME") or Path.home()) / ".local" / "state"
    )
    return Path(base) / "shoal" / "opencode-global"


def config_input(env: Mapping[str, str], config_arg: Optional[str]) -> str:
    """與 plugin 的全域層一致：--config-dir，其次 OPENCODE_CONFIG_DIR，最後 ~/.config/opencode。"""
    if config_arg:
        return config_arg
    if env.get("OPENCODE_CONFIG_DIR"):
        return env["OPENCODE_CONFIG_DIR"]
    return str(Path(env.get("HOME") or Path.home()) / ".config" / "opencode")


# ---- manifest（pipe 分隔，與 install_global.sh 相同）----
def read_manifest(path: Path) -> list[list[str]]:
    try:
        return [
            line.split("|") for line in path.read_text(encoding="utf-8").splitlines()
        ]
    except OSError:
        return []


def manifest_value(rows: list[list[str]], key: str) -> str:
    for row in rows:
        if row[0] == key and len(row) > 1:
            return row[1]
    return ""


def check_relative(rel: str) -> None:
    parts = rel.replace("\\", "/").split("/")
    if (
        not rel
        or rel.startswith("/")
        or ".." in parts
        or (len(rel) > 1 and rel[1] == ":")
    ):
        raise OpenCodeError(f"invalid path in manifest: {rel}")


def _entries(rows: list[list[str]]) -> list[tuple[str, str, str]]:
    return [(r[1], r[2], r[3]) for r in rows if r[0] == "entry" and len(r) >= 4]


def set_state(manifest: Path, new_state: str) -> None:
    rows = read_manifest(manifest)
    for row in rows:
        if row[0] == "state":
            row[1] = new_state
    tmp = manifest.with_name(manifest.name + ".tmp")
    tmp.write_text("\n".join("|".join(r) for r in rows) + "\n", encoding="utf-8")
    os.replace(tmp, manifest)


def verify_manifest_files(
    rows: list[list[str]], config_dir: Path, verb: str, backup_dir: Optional[Path]
) -> None:
    for present, expected, rel in _entries(rows):
        check_relative(rel)
        installed = config_dir / rel
        if installed.exists() and sha256_file(installed) != expected:
            raise OpenCodeError(
                f"cannot {verb}: file changed after installation: {rel}"
            )
        if (
            verb == "rollback"
            and present == "1"
            and not (backup_dir and (backup_dir / rel).is_file())
        ):
            raise OpenCodeError(f"cannot rollback: backup file is missing: {rel}")


def remove_created_dirs(rows: list[list[str]], config_dir: Path) -> None:
    for row in rows:
        if row[0] != "mkdir" or len(row) < 2:
            continue
        check_relative(row[1])
        try:
            (config_dir / row[1]).rmdir()
        except OSError:
            pass


def resolve_recorded_config(rows: list[list[str]], config_arg: Optional[str]) -> Path:
    recorded = manifest_value(rows, "config")
    if not recorded:
        raise OpenCodeError("invalid install manifest: config directory is missing")
    if config_arg:
        if not Path(config_arg).is_dir():
            raise OpenCodeError(f"config directory does not exist: {config_arg}")
        requested = os.path.realpath(config_arg)
        if requested != recorded:
            raise OpenCodeError(
                f"manifest was installed into {recorded}, not {requested}"
            )
    return Path(recorded)


def do_disable(env: Mapping[str, str], config_arg: Optional[str]) -> int:
    state = state_dir(env)
    manifest = state / "install.manifest"
    if not manifest.is_file():
        print("shoal-opencode is disabled: no install manifest")
        return 0
    rows = read_manifest(manifest)
    config_dir = resolve_recorded_config(rows, config_arg)
    verify_manifest_files(rows, config_dir, "disable", None)
    for present, _, rel in _entries(rows):
        target = config_dir / rel
        if present == "0" and target.exists():
            target.unlink()
    remove_created_dirs(rows, config_dir)
    set_state(manifest, "disabled")
    print(
        f"shoal-opencode disabled; rollback backup kept at {state / manifest_value(rows, 'backup')}"
    )
    return 0


def do_rollback(env: Mapping[str, str], config_arg: Optional[str]) -> int:
    state = state_dir(env)
    manifest = state / "install.manifest"
    if not manifest.is_file():
        raise OpenCodeError("cannot rollback: no install manifest")
    rows = read_manifest(manifest)
    config_dir = resolve_recorded_config(rows, config_arg)
    backup_rel = manifest_value(rows, "backup")
    check_relative(backup_rel)
    backup_dir = state / backup_rel
    if not backup_dir.is_dir():
        raise OpenCodeError("cannot rollback: backup directory is missing")
    verify_manifest_files(rows, config_dir, "rollback", backup_dir)
    for present, _, rel in _entries(rows):
        target = config_dir / rel
        if present == "1":
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(backup_dir / rel, target)
        elif target.exists():
            target.unlink()
    remove_created_dirs(rows, config_dir)
    set_state(manifest, "rolled_back")
    print("shoal-opencode rollback restored")
    return 0


# ---- enable ----
def _extract_tar(data: bytes, dest: Path) -> None:
    root = os.path.realpath(dest)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            target = os.path.realpath(os.path.join(root, member.name))
            if os.path.commonpath([root, target]) != root or member.issym() or member.islnk():
                raise OpenCodeError(f"unsafe path in archive: {member.name}")
        tar.extractall(dest)


def git_archive(
    repo: Path, ref: str, paths: list[str], dest: Path, env: Mapping[str, str]
) -> None:
    git = shutil.which("git", path=env.get("PATH"))
    if not git:
        raise OpenCodeError("git is required to read the committed dist")
    proc = subprocess.run(
        [git, "-C", str(repo), "archive", ref, *paths],
        env=dict(env),
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise OpenCodeError(
            f"cannot read {' '.join(paths)} at {ref} of {repo}: {tail[-1] if tail else 'git archive failed'}"
        )
    _extract_tar(proc.stdout, dest)


def build_plan(
    repo: Path, ref: str, work: Path, env: Mapping[str, str], bun: Optional[str]
) -> dict[str, Path]:
    """回傳 {相對 config dir 的路徑: 來源檔}。bun 為 None 時不建 bundle（dry-run 預覽用）。"""
    git_archive(repo, ref, ["hosts/opencode"], work, env)
    src = work / "hosts" / "opencode"
    dist = src / "dist"
    if not (dist / "roles").is_dir():
        raise OpenCodeError(f"hosts/opencode/dist/roles is missing at {ref}")
    for name in ("catalog.json", "routing.json"):
        if not (dist / name).is_file():
            raise OpenCodeError(f"hosts/opencode/dist/{name} is missing at {ref}")
    plan: dict[str, Path] = {}
    for role in sorted((dist / "roles").glob("*.md")):
        plan[f"agents/{role.name}"] = role
    bundle = work / "shoal-opencode.js"
    if bun:
        plugin = src / "plugin"
        for step in (
            [bun, "install", "--frozen-lockfile"],
            [
                bun,
                "build",
                "src/plugin/shoal-opencode.ts",
                "--bundle",
                "--format",
                "esm",
                "--target",
                "bun",
                "--outfile",
                str(bundle),
            ],
        ):
            proc = subprocess.run(
                step,
                cwd=plugin,
                env=dict(env),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout).strip().splitlines()
                raise OpenCodeError(
                    f"bun {step[1]} failed: {tail[-1] if tail else 'no output'}"
                )
        if not bundle.is_file() or bundle.stat().st_size == 0:
            raise OpenCodeError("plugin build produced no output")
    plan["plugins/shoal-opencode.js"] = bundle
    for name in ("catalog.json", "routing.json"):
        plan[f"shoal/{name}"] = dist / name
    return plan


def find_conflicts(
    plan: dict[str, Path], config_dir: Path, manifest_rows: list[list[str]]
) -> list[Path]:
    """已存在的檔案只有兩種可以覆蓋：內容與來源相同，或 manifest 記錄過且 hash 仍相符（先前由本 installer 安裝）。"""
    recorded = {rel: h for _, h, rel in _entries(manifest_rows)}
    conflicts = []
    for rel, source in plan.items():
        installed = config_dir / rel
        if not (installed.exists() or installed.is_symlink()):
            continue
        if not source.is_file():  # dry-run 不建 bundle
            continue
        if installed.is_file() and sha256_file(installed) == sha256_file(source):
            continue
        if (
            installed.is_file()
            and recorded.get(rel)
            and recorded[rel] == sha256_file(installed)
        ):
            continue
        conflicts.append(installed)
    return conflicts


def check_providers(config_dir: Path) -> None:
    """routing.json 的候選 provider 必須在 opencode.json 宣告（只比 key 名稱，不讀也不印任何值）。"""
    opencode_json = config_dir / "opencode.json"
    if not opencode_json.is_file():
        print(
            f"warning: {opencode_json} not found; provider check skipped",
            file=sys.stderr,
        )
        return
    try:
        config = json.loads(opencode_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(
            "warning: cannot parse opencode.json as JSON (JSONC?); provider check skipped",
            file=sys.stderr,
        )
        return
    routing = json.loads(
        (config_dir / "shoal" / "routing.json").read_text(encoding="utf-8")
    )
    declared: set[str] = set()
    if isinstance(config, dict):
        if isinstance(config.get("provider"), dict):
            declared.update(config["provider"].keys())
        if isinstance(config.get("enabled_providers"), list):
            declared.update(
                i for i in config["enabled_providers"] if isinstance(i, str)
            )
    missing: dict[str, list[str]] = {}
    for role, route in (routing.get("roles") or {}).items():
        for cand in route.get("candidates") or []:
            provider = cand.get("provider")
            if provider and provider not in declared:
                missing.setdefault(provider, []).append(role)
    for provider, roles in sorted(missing.items()):
        print(
            f"warning: routing.json candidate provider '{provider}' (roles: {', '.join(sorted(set(roles)))}) is not in "
            "opencode.json provider keys or enabled_providers; auth or env based providers cannot be verified here",
            file=sys.stderr,
        )


def check_project_plugins(cwd: Path) -> None:
    """專案已有 plugin 時，全域與專案兩份會同時載入；去重靠新版 plugin 的旗標。"""
    for base in dict.fromkeys([cwd, *cwd.parents]):
        found = base / ".opencode" / "plugins" / "shoal-opencode.js"
        if found.is_file():
            print(
                f"warning: project plugin found at {found}; it loads alongside the global plugin. "
                "Rebuild it from this version (dedup flag) or remove it",
                file=sys.stderr,
            )
        if (base / ".git").exists():
            break


def do_enable(
    env: Mapping[str, str],
    config_arg: Optional[str],
    repo: Path,
    ref: str,
    dry_run: bool,
) -> int:
    state = state_dir(env)
    manifest = state / "install.manifest"
    cfg_in = config_input(env, config_arg)
    if not Path(cfg_in).is_dir():
        raise OpenCodeError(f"config directory does not exist: {cfg_in}")
    config_dir = Path(os.path.realpath(cfg_in))
    rows = read_manifest(manifest)
    if rows and manifest_value(rows, "state") == "enabled":
        legacy = any(
            rel == LEGACY_PLUGIN_ENTRY or rel.startswith(LEGACY_CONTROL_PREFIX)
            for _, _, rel in _entries(rows)
        )
        if not legacy:
            print("shoal-opencode already enabled; use --disable before reinstalling")
            return 0
        if dry_run:
            print("would disable a pre-2.0.0 install manifest first")
        else:
            print(
                "found a pre-2.0.0 install manifest; disabling it before installing the new names",
                file=sys.stderr,
            )
            do_disable(env, str(config_dir))
            rows = read_manifest(manifest)
    bun = shutil.which("bun", path=env.get("PATH"))
    if not bun and not dry_run:
        raise OpenCodeError("bun is required to build the OpenCode plugin")
    with tempfile.TemporaryDirectory(prefix="shoal-opencode-global-") as tmp:
        work = Path(tmp)
        plan = build_plan(repo, ref, work, env, bun if not dry_run else None)
        conflicts = find_conflicts(plan, config_dir, rows)
        if dry_run:
            for rel in plan:
                print(f"would install: {config_dir / rel}")
            if not bun:
                print(
                    "note: bun not found; --apply needs bun to build plugins/shoal-opencode.js"
                )
            if conflicts:
                print("would refuse (files not installed by shoal):")
                for path in conflicts:
                    print(f"  {path}")
            return 0
        if conflicts:
            lines = "\n".join(f"  {p}" for p in conflicts)
            raise OpenCodeError(
                "refusing to overwrite files that were not installed by shoal; nothing was written:\n"
                f"{lines}\nmove or remove them (or merge by hand), then run --enable again"
            )
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup_rel, suffix = f"backups/{stamp}", 1
        while (state / backup_rel).exists():
            backup_rel = f"backups/{stamp}-{suffix}"
            suffix += 1
        backup_dir = state / backup_rel
        backup_dir.mkdir(parents=True)
        lines = [
            "version|1",
            "state|enabled",
            f"config|{config_dir}",
            f"backup|{backup_rel}|",
        ]
        for created in ("agents", "plugins", "shoal"):
            if not (config_dir / created).is_dir():
                (config_dir / created).mkdir(parents=True)
                lines.append(f"mkdir|{created}")
        for rel, source in plan.items():
            installed = config_dir / rel
            if installed.exists():
                (backup_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(installed, backup_dir / rel)
                lines.append(f"entry|1|{sha256_file(installed)}|{rel}")
            else:
                lines.append(f"entry|0|{sha256_file(source)}|{rel}")
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        for rel, source in plan.items():
            installed = config_dir / rel
            tmp_target = installed.with_name(installed.name + ".shoal-tmp")
            shutil.copyfile(source, tmp_target)
            os.replace(tmp_target, installed)
    print(f"shoal-opencode enabled globally in {config_dir} (state: {state})")
    check_providers(config_dir)
    check_project_plugins(Path.cwd())
    return 0


def main(
    argv: Optional[list[str]] = None, env: Optional[Mapping[str, str]] = None
) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], allow_abbrev=False
    )
    parser.add_argument("--config-dir", metavar="DIR")
    group = parser.add_mutually_exclusive_group(required=True)
    for flag in ("enable", "disable", "rollback"):
        group.add_argument(f"--{flag}", dest="action", action="store_const", const=flag)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出會安裝的檔案（--enable），不寫入、不需要 bun",
    )
    parser.add_argument("--repo", type=Path, default=REPO, help="shoal repo（測試用）")
    parser.add_argument("--ref", default="HEAD")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    try:
        if args.action == "disable":
            return do_disable(env, args.config_dir)
        if args.action == "rollback":
            return do_rollback(env, args.config_dir)
        return do_enable(env, args.config_dir, args.repo, args.ref, args.dry_run)
    except OpenCodeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
