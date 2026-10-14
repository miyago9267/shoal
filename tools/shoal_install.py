#!/usr/bin/env python3
"""shoal 模組安裝入口（modular-install S1）：薄前端，只包既有 installer，不重寫安裝邏輯。

用法：
  python3 tools/shoal_install.py --list [--host H]
  python3 tools/shoal_install.py --host H [--with M,..] [--without M,..] [--only M,..]   dry-run（預設）
  python3 tools/shoal_install.py --host H [...] --apply

S1 現在生效：--host、--list、dry-run（印出將執行的既有 installer 指令）、--apply（執行並寫
installed manifest）、--with jev-router（codex）。--without / --only 會驗證並記錄進 manifest，
但既有 installer 還不能略過 dispatch-guard、codex-autoroute、claude-explore，這三個要到 S3
才會真的略過；sync_global.py 已會依 manifest 過濾。

installed manifest：${XDG_DATA_HOME:-~/.local/share}/shoal/modules.json
  {"<host>": {"modules": [...], "version": "<VERSION>"}, "chain": [...]}
沒有 manifest 時由實際檔案推導（等於今天的行為）；第一次 --apply 才寫入。chain 由 S2 讀取，
S1 只保留不改。stdlib only。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Mapping, Optional

REPO = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO / "install" / "modules.json"
JEV_PLUGIN = "shoal-jev-router@shoal-codex"
# 既有 installer 還不能略過的選配模組：--without 只記錄，S3 才生效
RECORD_ONLY = ("dispatch-guard", "codex-autoroute", "claude-explore")

Runner = Callable[[list[str], Mapping[str, str]], int]


class InstallError(Exception):
    pass


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


# ---- manifest ----
def manifest_path(env: Mapping[str, str]) -> Path:
    data = env.get("XDG_DATA_HOME")
    base = Path(data).expanduser() if data else Path(env.get("HOME") or Path.home()) / ".local" / "share"
    return base / "shoal" / "modules.json"


def load_manifest(env: Mapping[str, str]) -> Optional[dict]:
    """manifest 不存在或不可解析時回傳 None（等同沒有 manifest，走推導）。"""
    try:
        data = json.loads(manifest_path(env).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def manifest_modules(env: Mapping[str, str], host: str) -> Optional[list[str]]:
    entry = (load_manifest(env) or {}).get(host)
    mods = entry.get("modules") if isinstance(entry, dict) else None
    return list(mods) if isinstance(mods, list) else None


def write_manifest(env: Mapping[str, str], host: str, modules: list[str]) -> Path:
    path = manifest_path(env)
    data = load_manifest(env) or {}
    version = (REPO / "VERSION").read_text().strip() if (REPO / "VERSION").is_file() else ""
    data[host] = {"modules": modules, "version": version}
    if not isinstance(data.get("chain"), list):
        data["chain"] = []
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".modules.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return path


# ---- homes ----
def _home(env: Mapping[str, str]) -> Path:
    return Path(env.get("HOME") or Path.home())


def host_home(host: str, env: Mapping[str, str]) -> Path:
    def pick(key: str, default: Path) -> Path:
        return Path(env[key]).expanduser() if env.get(key) else default

    home = _home(env)
    return {
        "codex": lambda: pick("CODEX_HOME", home / ".codex"),
        "grok": lambda: pick("GROK_HOME", home / ".grok"),
        "agy": lambda: home / ".gemini",
        "claude": lambda: pick("CLAUDE_CONFIG_DIR", home / ".claude"),
        "opencode": lambda: pick("OPENCODE_CONFIG_DIR", home / ".config" / "opencode"),
    }[host]()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _any_named(dist: Path, target: Path) -> bool:
    """repo dist 目錄裡有任何檔名在 target 底下也存在，就當作該 host 已裝。"""
    if not dist.is_dir() or not target.is_dir():
        return False
    return any((target / p.name).exists() or (target / p.name).is_symlink() for p in dist.iterdir())


# ---- inference（R4：沒有 manifest 時由實際檔案推導）----
# 原則：推導只會多算、不會少算。判斷不出來（檔案不存在、不是合法 JSON、讀不到、host 沒有可讀的
# hook 檔）一律視為已安裝，避免 --apply 寫出不含該模組的 manifest 而讓 sync 丟掉它。
def _shoal_hook_entries(host: str, home: Path) -> Optional[int]:
    """用 install_hooks 的辨識方式數 hook 檔裡 shoal 的 handler；讀不出來回傳 None。symlink 會跟隨。"""
    try:
        import install_hooks

        _, data = install_hooks.read_json(install_hooks.config_path(host, home, {}))
        return install_hooks.owned_entries(host, data) if data else None
    except Exception:
        return None


def _guard_installed(host: str, home: Path) -> bool:
    if host not in ("codex", "agy"):
        return True  # claude plugin、opencode plugin 內建；grok 沒有可靠的判斷
    return _shoal_hook_entries(host, home) != 0


def infer(host: str, env: Mapping[str, str], repo: Path = REPO) -> Optional[list[str]]:
    """回傳該 host 目前實際安裝的模組；host 完全沒裝時回傳 None。"""
    home = host_home(host, env)
    mods: list[str] = []
    if host == "codex":
        names = [p.stem for p in (repo / "templates" / "agents").glob("*.toml")]
        if not any((home / "agents" / f"{n}.toml").exists() for n in names):
            return None
        mods += ["core", "host-codex"]
        if _guard_installed("codex", home):
            mods.append("dispatch-guard")
        try:
            hooks = (home / "hooks.json").read_text(encoding="utf-8")
            json.loads(hooks)
            autoroute = "shoal_autoroute_gate" in hooks
        except (OSError, ValueError):
            autoroute = True
        if autoroute:
            mods.append("codex-autoroute")
        try:
            cfg = (home / "config.toml").read_text(encoding="utf-8")
            jev = JEV_PLUGIN in cfg or (home / "plugins/cache/shoal-codex/shoal-jev-router").exists()
        except OSError:
            jev = True
        if jev:
            mods.append("jev-router")
    elif host == "claude":
        if "shoal@shoal" not in _read(home / "plugins" / "installed_plugins.json"):
            return None
        mods += ["core", "host-claude", "dispatch-guard"]  # plugin 內建 guard
        if (home / "agents" / "Explore.md").exists():
            mods.append("claude-explore")
    elif host == "agy":
        if not _any_named(repo / "hosts/agy/dist/agents", home / "config" / "agents") and not _any_named(
            repo / "hosts/agy/dist/agents", home / "agents"
        ):
            return None
        mods += ["core", "host-agy"]
        if _guard_installed("agy", home):
            mods.append("dispatch-guard")
    elif host == "grok":
        if not _any_named(repo / "hosts/grok/dist/agents", home / "agents"):
            return None
        mods += ["core", "host-grok", "dispatch-guard"]
    elif host == "opencode":
        if not (home / "plugins" / "shoal-opencode.js").exists():
            return None
        mods += ["core", "host-opencode", "dispatch-guard"]  # guard 與 role 同在一個 plugin
    return mods


# ---- selection ----
def _csv(values: list[str]) -> list[str]:
    return [m.strip() for v in values for m in v.split(",") if m.strip()]


def resolve(
    host: str,
    reg: dict,
    env: Mapping[str, str],
    with_: list[str],
    without: list[str],
    only: list[str],
    repo: Path = REPO,
) -> tuple[list[str], str]:
    """回傳 (有序模組清單, 基底來源)。core 與 host 模組一律在內。"""
    mods = reg["modules"]
    available = [n for n, m in mods.items() if m["kind"] != "external" and host in m["hosts"]]
    for name in [*with_, *without, *only]:
        if name not in mods:
            raise InstallError(f"未知模組 {name}（--list 看清單）")
        if name not in available:
            raise InstallError(f"模組 {name} 不適用於 host {host}")
    required = ["core", f"host-{host}"]
    if only:
        chosen, source = set(only), "--only"
    else:
        existing = manifest_modules(env, host)
        if existing is not None:
            chosen, source = set(existing), "manifest"
        else:
            inferred = infer(host, env, repo)
            if inferred is not None:
                chosen, source = set(inferred), "inferred"
            else:
                chosen = {n for n in available if mods[n]["default_new"]}
                source = "new-install defaults"
    chosen |= set(with_)
    chosen -= set(without)
    chosen |= set(required)
    for name in sorted(chosen):
        for dep in mods[name]["depends_on"]:
            dep = f"host-{host}" if dep == "host" else dep
            if dep not in chosen:
                raise InstallError(f"模組 {name} 依賴 {dep}，但沒有被選取")
    return [n for n in available if n in chosen], source


# ---- wrapped commands ----
def wrapped_commands(host: str, mods: list[str], env: Mapping[str, str]) -> list[list[str]]:
    """--apply 會執行的既有 installer 指令；claude 沒有可由這裡執行的 installer，回傳空。"""
    py = sys.executable
    home = host_home(host, env)
    if host == "codex":
        cmds = [[py, str(REPO / "install/install.py"), "--codex-home", str(home)]]
        if "jev-router" in mods:
            cmds.append(["codex", "plugin", "add", JEV_PLUGIN])
        return cmds
    if host == "agy":
        return [[py, str(REPO / "tools/install_hooks.py"), "--host", "agy", "--home", str(home), "--apply"]]
    if host == "grok":
        return [[py, str(REPO / "tools/install_grok.py"), "--grok-home", str(home), "--apply"]]
    if host == "opencode":
        cmd = ["sh", str(REPO / "hosts/opencode/plugin/install/install.sh"), "--global"]
        if env.get("OPENCODE_CONFIG_DIR"):
            cmd += ["--config-dir", str(home)]
        return [[*cmd, "--enable"]]
    return []


CLAUDE_STEPS = (
    "claude plugin marketplace add miyago9267/shoal",
    "claude plugin install shoal@shoal",
)


def default_runner(cmd: list[str], env: Mapping[str, str]) -> int:
    return subprocess.run(cmd, env=dict(env), cwd=REPO).returncode


# ---- commands ----
def do_list(host: Optional[str], reg: dict, env: Mapping[str, str], repo: Path = REPO) -> int:
    hosts = [host] if host else None
    state: Optional[set[str]] = None
    source = ""
    if host:
        existing = manifest_modules(env, host)
        inferred = None if existing is not None else infer(host, env, repo)
        state = set(existing if existing is not None else inferred or [])
        source = "manifest" if existing is not None else ("inferred" if inferred is not None else "not installed")
        print(f"host: {host}（狀態來源：{source}）")
    print(f"{'module':<16}{'kind':<10}{'default':<9}{'depends_on':<18}{'hosts':<34}state")
    for name, m in reg["modules"].items():
        if hosts and host not in m["hosts"]:
            continue
        deps = ",".join(f"host-{host}" if d == "host" and host else d for d in m["depends_on"]) or "-"
        st = ("installed" if name in state else "-") if state is not None else ""
        if name == "external":
            st = "see chain" if state is not None else ""
        print(f"{name:<16}{m['kind']:<10}{('on' if m['default_new'] else 'off'):<9}{deps:<18}{','.join(m['hosts']):<34}{st}")
    return 0


def do_install(args: argparse.Namespace, reg: dict, env: Mapping[str, str], runner: Runner) -> int:
    host = args.host
    mods, source = resolve(host, reg, env, _csv(args.with_), _csv(args.without), _csv(args.only))
    print(f"host: {host}  modules: {', '.join(mods)}  (base: {source})")
    recorded = [m for m in RECORD_ONLY if m not in mods and m in reg["modules"] and host in reg["modules"][m]["hosts"]]
    if recorded:
        print(f"note: {', '.join(recorded)} 只記錄在 manifest；既有 installer 要到 S3 才能略過，S1 仍會照今天的內容安裝")
    cmds = wrapped_commands(host, mods, env)
    for cmd in cmds:
        print("would run:" if not args.apply else "run:", " ".join(cmd))
    if host == "claude":
        for step in CLAUDE_STEPS:
            print(("would print: " if not args.apply else "run manually: ") + step)
        if "claude-explore" in mods:
            print("note: Explore.md 由 dotfile updater 裝進 ~/.claude/agents/")
    path = manifest_path(env)
    if not args.apply:
        print(f"dry-run：未寫入任何檔案；--apply 會寫 {path}")
        return 0
    for cmd in cmds:
        code = runner(cmd, env)
        if code != 0:
            print(f"failed: {' '.join(cmd)} exit {code}；manifest 未更新", file=sys.stderr)
            return 1
    print(f"manifest: {write_manifest(env, host, mods)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    reg = load_registry()
    p.add_argument("--host", choices=reg["hosts"])
    p.add_argument("--list", action="store_true", help="列出模組、依賴與狀態（可加 --host）")
    p.add_argument("--with", dest="with_", action="append", default=[], metavar="MODULES", help="加選模組（逗號分隔）")
    p.add_argument("--without", action="append", default=[], metavar="MODULES", help="不選模組（S1 只記錄，見說明）")
    p.add_argument("--only", action="append", default=[], metavar="MODULES", help="只裝這些（core 與 host 模組一律包含）")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="預設；印出指令不寫入")
    mode.add_argument("--apply", action="store_true", help="執行既有 installer 並寫 manifest")
    return p


def main(argv: Optional[list[str]] = None, env: Optional[Mapping[str, str]] = None, runner: Runner = default_runner) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    reg = load_registry()
    if args.list:
        return do_list(args.host, reg, env)
    if not args.host:
        parser.error("需要 --host 或 --list")
    try:
        return do_install(args, reg, env, runner)
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
