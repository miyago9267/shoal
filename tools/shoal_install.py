#!/usr/bin/env python3
"""shoal 模組安裝入口（modular-install）：薄前端，只包既有 installer，不重寫安裝邏輯。

用法：
  python3 tools/shoal_install.py --list [--host H]
  python3 tools/shoal_install.py --host H [--with M,..] [--without M,..] [--only M,..]   dry-run（預設）
  python3 tools/shoal_install.py --host H [...] --apply
  python3 tools/shoal_install.py --chain-add NAME --chain-command '["argv","..."]' --chain-hosts h1,h2 [--chain-order N] [--apply]
  python3 tools/shoal_install.py --chain-remove NAME [--apply]

--without 現在對這三個模組真的生效（再跑一次不帶它們，只移除 shoal 自己的 entry）：
  dispatch-guard   codex：install.py --no-guard；agy：install_hooks --uninstall；grok：install_grok --no-guard；
                   claude、opencode：guard 在 plugin 內，檔案照裝，manifest 沒有 dispatch-guard 時 guard 讀同一份
                   manifest 並以 off 模式執行（持久開關）
  codex-autoroute  codex：install.py --no-autoroute
  claude-explore   claude：移除 ~/.claude/agents/Explore.md（只在內容與 repo 的 dist 逐位元組相同時）
預設不變：dispatch-guard 新裝與既有都是開；jev-router 新裝關、既有維持現狀。

installed manifest：${XDG_DATA_HOME:-~/.local/share}/shoal/modules.json
  {"<host>": {"modules": [...], "version": "<VERSION>"}, "chain": [{"name","command","hosts","order"}]}
沒有 manifest 時由實際檔案推導（等於今天的行為）；第一次 --apply 才寫入。chain 成員只登記，註冊時不執行。
stdlib only。
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
EXPLORE_DIST = "hosts/claude/dist/agents/Explore.md"

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
    data = load_manifest(env) or {}
    version = (REPO / "VERSION").read_text().strip() if (REPO / "VERSION").is_file() else ""
    data[host] = {"modules": modules, "version": version}
    return _save_manifest(env, data)


def _save_manifest(env: Mapping[str, str], data: dict) -> Path:
    path = manifest_path(env)
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
        if "dispatch-guard" not in mods:
            cmds[0].append("--no-guard")
        if "codex-autoroute" not in mods:
            cmds[0].append("--no-autoroute")
        if "jev-router" in mods:
            cmds.append(["codex", "plugin", "add", JEV_PLUGIN])
        return cmds
    if host == "agy":
        cmd = [py, str(REPO / "tools/install_hooks.py"), "--host", "agy", "--home", str(home)]
        return [[*cmd, "--apply"] if "dispatch-guard" in mods else [*cmd, "--uninstall", "--apply"]]
    if host == "grok":
        cmd = [py, str(REPO / "tools/install_grok.py"), "--grok-home", str(home), "--apply"]
        return [cmd if "dispatch-guard" in mods else [*cmd, "--no-guard"]]
    if host == "opencode":
        cmd = ["sh", str(REPO / "hosts/opencode/plugin/install/install.sh"), "--global"]
        if env.get("OPENCODE_CONFIG_DIR"):
            cmd += ["--config-dir", str(home)]
        return [[*cmd, "--enable"]]
    return []


def explore_removal(host: str, mods: list[str], env: Mapping[str, str]) -> list[Path]:
    """claude-explore 關閉時要移除的檔案：只有 ~/.claude/agents/Explore.md 與 repo dist 逐位元組相同才算 shoal 的。"""
    if host != "claude" or "claude-explore" in mods:
        return []
    target = host_home("claude", env) / "agents" / "Explore.md"
    try:
        same = target.is_file() and target.read_bytes() == (REPO / EXPLORE_DIST).read_bytes()
    except OSError:
        same = False
    return [target] if same else []


# ---- chain（只登記到 manifest；註冊時不執行成員）----
def chain_members(env: Mapping[str, str]) -> list[dict]:
    chain = (load_manifest(env) or {}).get("chain")
    return sorted((m for m in chain if isinstance(m, dict)), key=lambda m: m.get("order", 0)) if isinstance(chain, list) else []


def _num(text: str) -> float | int:
    value = float(text)
    return int(value) if value == int(value) else value


def parse_chain_member(args: argparse.Namespace, reg: dict, env: Mapping[str, str]) -> dict:
    name = (args.chain_add or "").strip()
    if not name:
        raise InstallError("--chain-add 需要非空的名稱")
    if args.chain_command is None:
        raise InstallError("--chain-add 需要 --chain-command（JSON 陣列）")
    try:
        command = json.loads(args.chain_command)
    except ValueError as exc:
        raise InstallError(f"--chain-command 不是合法 JSON：{exc}") from exc
    if not (isinstance(command, list) and command and all(isinstance(a, str) and a for a in command)):
        raise InstallError("--chain-command 必須是非空字串組成的 JSON 陣列（argv，不經 shell）")
    hosts = _csv([args.chain_hosts or ""])
    if not hosts:
        raise InstallError("--chain-add 需要 --chain-hosts（逗號分隔）")
    unknown = [h for h in hosts if h not in reg["hosts"]]
    if unknown:
        raise InstallError(f"未知 host：{', '.join(unknown)}")
    order = args.chain_order
    if order is None:  # 重新登記同名成員沿用原本的 order；新成員排在現有最後
        current = {m.get("name"): m.get("order", 0) for m in chain_members(env)}
        order = current[name] if name in current else (max(current.values()) + 1 if current else 0)
    return {"name": name, "command": command, "hosts": hosts, "order": order}


def do_chain(args: argparse.Namespace, reg: dict, env: Mapping[str, str]) -> int:
    data = load_manifest(env) or {}
    chain = [m for m in data.get("chain", []) if isinstance(m, dict)] if isinstance(data.get("chain"), list) else []
    if args.chain_add is not None:
        member = parse_chain_member(args, reg, env)
        if any(m.get("name") == member["name"] for m in chain):
            chain = [member if m.get("name") == member["name"] else m for m in chain]
        else:
            chain.append(member)
        print(f"chain add: {member['name']}  hosts={','.join(member['hosts'])}  order={member['order']}  command={json.dumps(member['command'], ensure_ascii=False)}")
    else:
        if args.chain_remove not in [m.get("name") for m in chain]:
            print(f"chain: {args.chain_remove} 不在 chain 內，沒有變更")
            return 0
        chain = [m for m in chain if m.get("name") != args.chain_remove]
        print(f"chain remove: {args.chain_remove}")
    if not args.apply:
        print(f"dry-run：未寫入任何檔案；--apply 會寫 {manifest_path(env)}（成員只登記，不會被執行）")
        return 0
    print(f"manifest: {_save_manifest(env, {**data, 'chain': chain})}")
    return 0


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
    chain = chain_members(env)
    print("guard chain: " + ("(none)" if not chain else ""))
    for member in chain:
        print(f"  [{member['order']}] {member['name']}  hosts={','.join(member['hosts'])}  command={json.dumps(member['command'], ensure_ascii=False)}")
    return 0


def do_install(args: argparse.Namespace, reg: dict, env: Mapping[str, str], runner: Runner) -> int:
    host = args.host
    mods, source = resolve(host, reg, env, _csv(args.with_), _csv(args.without), _csv(args.only))
    print(f"host: {host}  modules: {', '.join(mods)}  (base: {source})")
    cmds = wrapped_commands(host, mods, env)
    removals = explore_removal(host, mods, env)
    for cmd in cmds:
        print("would run:" if not args.apply else "run:", " ".join(cmd))
    if host == "claude":
        for step in CLAUDE_STEPS:
            print(("would print: " if not args.apply else "run manually: ") + step)
        if "claude-explore" in mods:
            print("note: Explore.md 由 dotfile updater 裝進 ~/.claude/agents/")
    if host in ("claude", "opencode") and "dispatch-guard" not in mods:
        print(
            "note: dispatch-guard 關閉：guard 隨 plugin 的檔案仍會安裝，manifest 沒有 dispatch-guard 時它讀同一份 manifest，"
            "以 off 模式執行（同時不呼叫 chain 成員）；加回 --with dispatch-guard 即恢復"
        )
    for path in removals:
        print(("would remove: " if not args.apply else "remove: ") + str(path))
    path = manifest_path(env)
    if not args.apply:
        print(f"dry-run：未寫入任何檔案；--apply 會寫 {path}")
        return 0
    for cmd in cmds:
        code = runner(cmd, env)
        if code != 0:
            print(f"failed: {' '.join(cmd)} exit {code}；manifest 未更新", file=sys.stderr)
            return 1
    for path in removals:
        path.unlink(missing_ok=True)
    print(f"manifest: {write_manifest(env, host, mods)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    reg = load_registry()
    p.add_argument("--host", choices=reg["hosts"])
    p.add_argument("--list", action="store_true", help="列出模組、依賴與狀態（可加 --host）")
    p.add_argument("--with", dest="with_", action="append", default=[], metavar="MODULES", help="加選模組（逗號分隔）")
    p.add_argument("--without", action="append", default=[], metavar="MODULES", help="不選模組（dispatch-guard、codex-autoroute、claude-explore 會真的略過／移除，見說明）")
    p.add_argument("--only", action="append", default=[], metavar="MODULES", help="只裝這些（core 與 host 模組一律包含）")
    p.add_argument("--chain-add", metavar="NAME", help="登記 guard chain 成員（需要 --chain-command 與 --chain-hosts）")
    p.add_argument("--chain-command", metavar="JSON", help='成員的 argv，JSON 字串陣列，例如 \'["python3","/path/member.py"]\'')
    p.add_argument("--chain-hosts", metavar="HOSTS", help="成員適用的 host（逗號分隔）")
    p.add_argument("--chain-order", type=_num, metavar="N", help="執行順序（升冪）；預設：同名成員沿用原值，新成員為現有最大值加 1")
    p.add_argument("--chain-remove", metavar="NAME", help="從 chain 移除成員")
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
    if args.chain_add is not None or args.chain_remove is not None:
        if args.chain_add is not None and args.chain_remove is not None or args.host:
            parser.error("--chain-add、--chain-remove 不能互相搭配，也不能和 --host 一起用")
        try:
            return do_chain(args, reg, env)
        except InstallError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
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
