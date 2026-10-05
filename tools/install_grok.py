#!/usr/bin/env python3
"""由 shoal 安裝 Grok Build 的 pilotfish-grok（docs/specs/grok-workflow，R4 至 R9）。

用法：
  python3 tools/install_grok.py [--grok-home DIR]                 dry-run（預設），不寫入
  python3 tools/install_grok.py --apply [--fix-toggles]           備份後安裝
  python3 tools/install_grok.py --restore <backup-dir> --apply    逐位元組還原該次備份
  python3 tools/install_grok.py --uninstall --apply               只移除 shoal 安裝的檔案

來源是 repo 的 committed HEAD（git archive hosts/grok/dist 與 hosts/grok/VERSION），
不是工作樹。安裝 agents/、roles/、rules/pilotfish-grok.md、hooks/pilotfish-grok.json 與
hooks/pilotfish-grok/（含 dispatch guard 的 shoal_guard.py，由 render 從 hooks/shoal_guard.py 產生；
dist 副本與同一 commit 的來源不同時中止）；config.snippet.toml 只是 config 合併的參考，不安裝。
所有會寫入的動作（安裝、--restore、--uninstall）都要 --apply；寫入前把要被取代或移除的
檔案與 config.toml 備份到 <grok-home>/backups/shoal-<timestamp>/。
只開啟明確列出的路徑，不掃描 grok home，不讀 credential、session、history 檔案。
config.toml 只有 --fix-toggles 會修改：刪除 [subagents.toggle] 裡把 shoal role 設成
false 的那幾行，其他位元組保留。

exit code：0 成功；1 安裝後驗證失敗；2 中止（來源、config 或既有檔案不符預期）。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tomllib
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIST = "hosts/grok/dist"
VERSION_PATH = "hosts/grok/VERSION"
INSTALL_TOPS = ("agents", "roles", "rules", "hooks")
RULES = "rules/pilotfish-grok.md"
HOOK_DIR = "hooks/pilotfish-grok"
GUARD_DIST = "hooks/pilotfish-grok/shoal_guard.py"
GUARD_SOURCE = "hooks/shoal_guard.py"
BEGIN = "<!-- pilotfish-grok:begin -->"
END = "<!-- pilotfish-grok:end -->"
CONFIG = "config.toml"


class InstallError(Exception):
    """中止（exit 2）。"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            timeout=60,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        detail = (
            exc.stderr.decode("utf-8", "replace").strip()
            if isinstance(exc, subprocess.CalledProcessError)
            else exc
        )
        raise InstallError(f"git {' '.join(args)} 失敗: {detail}") from exc


def load_source(repo: Path, ref: str) -> tuple[dict[str, bytes], str, str]:
    """(要安裝的檔案 {相對 grok home 的路徑: bytes}, VERSION, commit sha)；取自 git archive，不讀工作樹。"""
    commit = git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    archive = git(repo, "archive", commit, DIST, VERSION_PATH)
    files: dict[str, bytes] = {}
    version = ""
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            data = tar.extractfile(member).read()
            if member.name == VERSION_PATH:
                version = data.decode("utf-8").strip()
            elif member.name.startswith(DIST + "/"):
                rel = member.name[len(DIST) + 1 :]
                if rel.split("/", 1)[0] in INSTALL_TOPS:
                    files[rel] = data
    if not version or RULES not in files:
        raise InstallError(f"{commit[:7]} 的 {DIST} 或 {VERSION_PATH} 不完整")
    check_guard_single_source(repo, commit, files)
    return files, version, commit


def check_guard_single_source(repo: Path, commit: str, files: dict[str, bytes]) -> None:
    """dist 內的 shoal_guard.py 必須逐位元組等於同一個 commit 的 hooks/shoal_guard.py（render 產生，不可手抄）。

    該 commit 沒有 hooks/shoal_guard.py（舊版）時略過。
    """
    copy = files.get(GUARD_DIST)
    if copy is None:
        return
    try:
        source = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), "show", f"{commit}:{GUARD_SOURCE}"],
            check=True,
            capture_output=True,
            timeout=60,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return
    if source != copy:
        raise InstallError(
            f"{commit[:7]} 的 {DIST}/{GUARD_DIST} 與 {GUARD_SOURCE} 不同，"
            "先執行 python3 tools/render.py --host grok --write 再 commit"
        )


def shoal_roles(files: dict[str, bytes]) -> list[str]:
    return sorted(Path(rel).stem for rel in files if rel.startswith("roles/"))


# ---- config.toml：只讀 [subagents.toggle]；--fix-toggles 以最小文字編輯刪行 ----
def read_config(home: Path) -> tuple[bytes | None, dict]:
    path = home / CONFIG
    if not path.is_file():
        return None, {}
    raw = path.read_bytes()
    try:
        return raw, tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise InstallError(f"{path} 不是合法的 TOML，不處理: {exc}") from exc


def flagged_toggles(parsed: dict, roles: list[str]) -> list[str]:
    toggles = parsed.get("subagents", {}).get("toggle", {})
    return [r for r in roles if toggles.get(r) is False]


_TOGGLE_HEADER = re.compile(
    r"^[ \t]*\[[ \t]*subagents[ \t]*\.[ \t]*toggle[ \t]*\][ \t]*(?:#.*)?$"
)
_ANY_HEADER = re.compile(r"^[ \t]*\[")


def remove_toggle_keys(raw: bytes, keys: list[str]) -> bytes:
    """刪除 [subagents.toggle] 內把 keys 設成 false 的整行；無法這樣編輯，或結果與預期不符時 raise。"""
    text = raw.decode("utf-8")
    old = tomllib.loads(text)
    lines = text.splitlines(keepends=True)
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if _TOGGLE_HEADER.match(line.rstrip("\r\n"))
        ),
        None,
    )
    if start is None:
        raise InstallError(
            "[subagents.toggle] 不是獨立的 table（可能是 dotted key 或 inline table），"
            "無法用最小文字編輯移除，請手動處理"
        )
    end = next(
        (i for i in range(start + 1, len(lines)) if _ANY_HEADER.match(lines[i])),
        len(lines),
    )
    names = "|".join(re.escape(k) for k in keys)
    target = re.compile(
        rf"^[ \t]*(?:{names}|\"(?:{names})\"|'(?:{names})')[ \t]*=[ \t]*false[ \t]*(?:#.*)?$"
    )
    kept = [
        line
        for i, line in enumerate(lines)
        if not (start < i < end and target.match(line.rstrip("\r\n")))
    ]
    new = "".join(kept)
    expected = copy.deepcopy(old)
    for key in keys:
        del expected["subagents"]["toggle"][key]
    try:
        actual = tomllib.loads(new)
    except tomllib.TOMLDecodeError as exc:
        raise InstallError(f"移除 toggle 後 TOML 不合法: {exc}") from exc
    if actual != expected:
        raise InstallError(
            "移除 toggle 後的內容與預期不符（key 可能寫成多行或重複），無法用最小文字編輯處理"
        )
    return new.encode("utf-8")


# ---- 計畫 ----
class Plan:
    def __init__(
        self,
        home: Path,
        files: dict[str, bytes],
        version: str,
        commit: str,
        fix_toggles: bool,
    ) -> None:
        self.home, self.files, self.version, self.commit = home, files, version, commit
        self.actions: dict[str, str] = {}  # rel -> add | replace | skip
        self.existing: dict[str, bytes] = {}
        for rel, data in files.items():
            path = home / rel
            if path.is_file():
                self.existing[rel] = path.read_bytes()
                self.actions[rel] = "skip" if self.existing[rel] == data else "replace"
            else:
                self.actions[rel] = "add"
        self.check_rules_markers()
        self.config_raw, parsed = read_config(home)
        self.flagged = flagged_toggles(parsed, shoal_roles(files))
        self.new_config = None
        if fix_toggles and self.flagged:
            self.new_config = remove_toggle_keys(self.config_raw, self.flagged)

    def check_rules_markers(self) -> None:
        old = self.existing.get(RULES)
        if old is None:
            return
        text = old.decode("utf-8", "replace")
        begins, ends = text.count(BEGIN), text.count(END)
        if begins > 1 or begins != ends:
            raise InstallError(
                f"{self.home / RULES} 的 begin/end marker 數量不符（{begins}/{ends}），"
                "請先手動整理，不自動取代"
            )

    def changes(self) -> list[str]:
        return [rel for rel, act in self.actions.items() if act != "skip"]


def describe(plan: Plan, fix_toggles: bool) -> list[str]:
    label = {"add": "新增", "replace": "取代", "skip": "略過（已與 dist 相同）"}
    out = [
        f"grok home: {plan.home}",
        f"來源: committed {plan.commit[:7]}，hosts/grok/VERSION {plan.version}",
    ]
    out += [f"  [{label[act]}] {rel}" for rel, act in sorted(plan.actions.items())]
    old = plan.existing.get(RULES)
    if old is not None and plan.actions[RULES] == "replace":
        outside = old.decode("utf-8", "replace")
        outside = outside.split(BEGIN, 1)[0] + outside.split(END, 1)[-1]
        if outside.strip():
            out.append(
                f"  注意：{RULES} 在 marker 之外還有內容，整個檔案會被取代（已備份）"
            )
    if plan.config_raw is None:
        out.append(f"  config.toml 不存在，不處理")
    elif plan.flagged:
        names = ", ".join(plan.flagged)
        out.append(
            f"  config.toml [subagents.toggle] 把 shoal role 設成 false: {names}"
        )
        out.append(
            "    將刪除這些 key，其他內容不動"
            if fix_toggles
            else "    加 --fix-toggles 才會移除；目前不改 config.toml"
        )
    else:
        out.append("  config.toml 沒有停用 shoal role，不改動")
    return out


# ---- 寫入 ----
def write_file(
    path: Path, data: bytes, executable: bool = False, mode: int | None = None
) -> None:
    """取代既有檔案時保留原本的權限：config.toml 可能放 api_key，不能被放寬成 0644。"""
    if mode is None:
        if executable:
            mode = 0o755
        elif path.exists():
            mode = stat.S_IMODE(path.stat().st_mode)
        else:
            mode = 0o644
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".shoal-tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def is_hook_script(rel: str) -> bool:
    return rel.startswith("hooks/") and rel.endswith(".py")


def make_backup(
    home: Path,
    saved: dict[str, bytes],
    created: list[str],
    config: bytes | None,
    commit: str,
    action: str,
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    root, n = home / "backups", 0
    while True:
        target = root / f"shoal-{stamp}" if n == 0 else root / f"shoal-{stamp}-{n}"
        if not target.exists():
            break
        n += 1
    # 備份可能含 config.toml 的 secret：目錄 0700、檔案 0600
    (target / "files").mkdir(parents=True, mode=0o700)
    os.chmod(target, 0o700)
    for rel, data in saved.items():
        write_file(target / "files" / rel, data, mode=0o600)
    if config is not None:
        write_file(target / "files" / CONFIG, config, mode=0o600)
    manifest = {
        "version": 1,
        "action": action,
        "source": commit,
        "created": sorted(created),
        "saved": sorted(saved),
        "config_saved": config is not None,
    }
    write_file(
        target / "manifest.json",
        (json.dumps(manifest, indent=2) + "\n").encode("utf-8"),
    )
    return target


def prune_hook_dir(home: Path) -> None:
    try:
        (home / HOOK_DIR).rmdir()  # 只在空的時候成功
    except OSError:
        pass


def verify(plan: Plan) -> list[str]:
    """R9：檔案 hash 與 committed dist 相同，rules marker 與 hosts/grok/VERSION 一致。"""
    problems = []
    for rel, data in plan.files.items():
        path = plan.home / rel
        if not path.is_file() or sha256(path.read_bytes()) != sha256(data):
            problems.append(f"hash 不符: {rel}")
        elif is_hook_script(rel) and not os.access(path, os.X_OK):
            problems.append(f"hook 腳本不可執行: {rel}")
    rules = (
        (plan.home / RULES).read_text(encoding="utf-8")
        if (plan.home / RULES).is_file()
        else ""
    )
    if (
        rules.count(f"<!-- pilotfish-grok v{plan.version} -->") != 1
        or len(re.findall(r"<!-- pilotfish-grok v\S+ -->", rules)) != 1
    ):
        problems.append(
            f"{RULES} 的 marker 與 hosts/grok/VERSION（{plan.version}）不一致"
        )
    return problems


def do_install(plan: Plan, apply: bool, fix_toggles: bool) -> int:
    print("\n".join(describe(plan, fix_toggles)))
    changes = plan.changes()
    if plan.new_config is not None:
        changes.append(CONFIG)
    if not apply:
        print("dry-run：沒有寫入任何檔案；加 --apply 才會寫入")
        return 0
    if not changes:
        print("沒有需要變更的檔案，不建立備份")
    else:
        saved = {
            rel: plan.existing[rel] for rel in plan.changes() if rel in plan.existing
        }
        created = [rel for rel in plan.changes() if rel not in plan.existing]
        backup = make_backup(
            plan.home, saved, created, plan.config_raw, plan.commit, "install"
        )
        print(f"備份: {backup}")
        for rel in plan.changes():
            write_file(plan.home / rel, plan.files[rel], is_hook_script(rel))
        if plan.new_config is not None:
            write_file(plan.home / CONFIG, plan.new_config)
        print(
            f"已寫入 {len(plan.changes())} 個檔案"
            + ("，並移除 toggle" if plan.new_config is not None else "")
        )
    problems = verify(plan)
    if problems:
        print("驗證失敗：\n" + "\n".join(f"  {p}" for p in problems), file=sys.stderr)
        return 1
    print(
        f"驗證通過：{len(plan.files)} 個檔案 hash 與 committed dist 相同，rules marker = v{plan.version}"
    )
    return 0


def do_uninstall(home: Path, files: dict[str, bytes], commit: str, apply: bool) -> int:
    present = {
        rel: (home / rel).read_bytes()
        for rel in sorted(files)
        if (home / rel).is_file()
    }
    print(f"grok home: {home}")
    print("\n".join(f"  [移除] {rel}" for rel in present) or "  沒有 shoal 安裝的檔案")
    print("  config.toml 與其他檔案不動")
    if not apply:
        print("dry-run：沒有寫入任何檔案；加 --apply 才會移除")
        return 0
    if present:
        config = (home / CONFIG).read_bytes() if (home / CONFIG).is_file() else None
        print(f"備份: {make_backup(home, present, [], config, commit, 'uninstall')}")
        for rel in present:
            (home / rel).unlink()
        prune_hook_dir(home)
        print(f"已移除 {len(present)} 個檔案")
    return 0


def do_restore(home: Path, backup: Path, apply: bool) -> int:
    try:
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
        saved, created = list(manifest["saved"]), list(manifest["created"])
    except (OSError, ValueError, KeyError) as exc:
        raise InstallError(f"{backup} 不是 shoal 的備份目錄: {exc}") from exc
    if manifest.get("config_saved"):
        saved.append(CONFIG)
    for rel in saved + created:
        if rel != CONFIG and (
            rel.split("/", 1)[0] not in INSTALL_TOPS
            or ".." in Path(rel).parts
            or Path(rel).is_absolute()
        ):
            raise InstallError(f"備份的 manifest 含有不屬於 shoal 的路徑: {rel}")
    print(f"grok home: {home}\n備份: {backup}")
    print(
        "\n".join(
            [f"  [還原] {rel}" for rel in saved]
            + [f"  [刪除] {rel}（該次安裝新增的）" for rel in created]
        )
    )
    if not apply:
        print("dry-run：沒有寫入任何檔案；加 --apply 才會還原")
        return 0
    for rel in saved:
        data = (backup / "files" / rel).read_bytes()
        if not (home / rel).is_file() or (home / rel).read_bytes() != data:
            write_file(home / rel, data, is_hook_script(rel))
    for rel in created:
        (home / rel).unlink(missing_ok=True)
    prune_hook_dir(home)
    bad = [
        rel
        for rel in saved
        if (home / rel).read_bytes() != (backup / "files" / rel).read_bytes()
    ]
    if bad:
        print("還原後內容不符: " + ", ".join(bad), file=sys.stderr)
        return 1
    print(f"已還原 {len(saved)} 個檔案、刪除 {len(created)} 個")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], allow_abbrev=False
    )
    parser.add_argument(
        "--grok-home", type=Path, help="預設 $GROK_HOME，沒有則 ~/.grok"
    )
    parser.add_argument(
        "--apply", action="store_true", help="實際寫入；沒有這個旗標一律 dry-run"
    )
    parser.add_argument(
        "--fix-toggles",
        action="store_true",
        help="移除 [subagents.toggle] 中停用 shoal role 的 key",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--restore",
        type=Path,
        metavar="BACKUP_DIR",
        help="還原該次備份的檔案與 config.toml",
    )
    mode.add_argument(
        "--uninstall",
        action="store_true",
        help="只移除 shoal 安裝的檔案，不改 config.toml",
    )
    parser.add_argument("--repo", type=Path, default=REPO, help="shoal repo（測試用）")
    parser.add_argument("--ref", default="HEAD", help="要安裝的 ref，預設 HEAD")
    args = parser.parse_args(argv)
    if args.fix_toggles and (args.restore or args.uninstall):
        parser.error("--fix-toggles 只能用在安裝")
    home = (
        args.grok_home or Path(os.environ.get("GROK_HOME") or "~/.grok")
    ).expanduser()
    try:
        if args.restore:
            return do_restore(home, args.restore.expanduser(), args.apply)
        files, version, commit = load_source(args.repo, args.ref)
        status = (
            git(args.repo, "status", "--porcelain", "--", DIST, VERSION_PATH)
            .decode()
            .strip()
        )
        if status:
            print(
                "注意：工作樹的 hosts/grok 有未 commit 的變更，只安裝 committed 的內容"
            )
        if args.uninstall:
            return do_uninstall(home, files, commit, args.apply)
        return do_install(
            Plan(home, files, version, commit, args.fix_toggles),
            args.apply,
            args.fix_toggles,
        )
    except InstallError as exc:
        print(f"中止: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    # Windows 預設 cp1252，輸出中文會拋 UnicodeEncodeError，強制 UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
