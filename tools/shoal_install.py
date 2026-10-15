#!/usr/bin/env python3
"""shoal 模組安裝入口（modular-install）：薄前端，只包既有 installer，不重寫安裝邏輯。

用法：
  python3 tools/shoal_install.py --list [--host H]
  python3 tools/shoal_install.py --host H [--with M,..] [--without M,..] [--only M,..]   dry-run（預設）
  python3 tools/shoal_install.py --host H [...] --apply

dry-run 會呼叫底層 installer 的 dry-run 並顯示輸出；claude、codex、bun 等外部 CLI 以 shutil.which 解析，找不到時 dry-run 回報 skipped。
agy 的 agents、skills 連到 hosts/agy/dist（symlink 失敗時改複製並在 manifest 記 agy_mode: copy）。
  python3 tools/shoal_install.py --chain-add NAME --chain-command '["argv","..."]' --chain-hosts h1,h2 [--chain-events E1,E2] [--chain-order N] [--apply]
  python3 tools/shoal_install.py --chain-remove NAME [--apply]

--without 現在對這三個模組真的生效（再跑一次不帶它們，只移除 shoal 自己的 entry）：
  dispatch-guard   codex：install.py --no-guard；agy：install_hooks --uninstall；grok：install_grok --no-guard；
                   claude：guard 是獨立 plugin shoal-dispatch-guard，沒選就不裝它（已裝的要自行 uninstall）；
                   opencode：guard 在 plugin 內，檔案照裝，manifest 沒有 dispatch-guard 時 guard 讀同一份
                   manifest 並以 off 模式執行（持久開關）
  codex-autoroute  codex：install.py --no-autoroute
  claude-explore   claude：移除 ~/.claude/agents/Explore.md（只在內容與 repo 的 dist 逐位元組相同時）
預設不變：dispatch-guard 新裝與既有都是開；jev-router 新裝關、既有維持現狀。

installed manifest：${XDG_DATA_HOME:-~/.local/share}/shoal/modules.json
  {"<host>": {"modules": [...], "version": "<VERSION>"}, "chain": [{"name","command","hosts","order","events"?}]}
沒有 manifest 時由實際檔案推導（等於今天的行為）；第一次 --apply 才寫入。chain 成員只登記，註冊時不執行。
stdlib only。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Mapping, Optional

REPO = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO / "install" / "modules.json"
JEV_PLUGIN = "shoal-jev-router@shoal-codex"
# 與 hooks/shoal_guard.py 的 CHAIN_EVENTS 相同（tests 比對）；不 import guard，installer 保持獨立。
CHAIN_EVENTS = ("PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionEnd", "Stop")
EXPLORE_DIST = "hosts/claude/dist/agents/Explore.md"

Runner = Callable[[list[str], Mapping[str, str]], int]
Previewer = Callable[[list[str], Mapping[str, str]], tuple[int, str]]


class InstallError(Exception):
    pass


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def default_runner(cmd: list[str], env: Mapping[str, str]) -> int:
    sys.stdout.flush()  # 子程序直接寫 stdout，先送出我們已印的行，輸出順序才對
    return subprocess.run(cmd, env=dict(env), cwd=REPO).returncode


def default_previewer(cmd: list[str], env: Mapping[str, str]) -> tuple[int, str]:
    """跑底層 installer 的 dry-run 並回傳 (exit code, 輸出)；無法啟動時 exit code 為 127。"""
    try:
        proc = subprocess.run(cmd, env=dict(env), cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f"{exc}\n"
    return proc.returncode, proc.stdout + proc.stderr


def which(name: str, env: Mapping[str, str]) -> Optional[str]:
    """外部 CLI 一律用 shutil.which 解析（Windows 上的 .cmd shim 才找得到）；找不到回傳 None。"""
    return shutil.which(name, path=env.get("PATH"))


# ---- manifest ----
def manifest_path(env: Mapping[str, str]) -> Path:
    # 和 guard（Python/TS）同一條規則：XDG Base Directory spec，非絕對路徑的 XDG_DATA_HOME 一律忽略，
    # 退回 $HOME/.local/share；不展開 ~，也不把相對路徑當成相對 cwd，兩邊才會讀到同一份 manifest。
    data = env.get("XDG_DATA_HOME")
    if data and os.path.isabs(data):
        base = Path(data)
    else:
        base = Path(env.get("HOME") or Path.home()) / ".local" / "share"
    return base / "shoal" / "modules.json"


def load_manifest(env: Mapping[str, str]) -> Optional[dict]:
    """manifest 不存在或不可解析時回傳 None（等同沒有 manifest，走推導）。"""
    try:
        data = json.loads(manifest_path(env).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def chain_hosts(env: Mapping[str, str], host: str) -> bool:
    """manifest 的 chain 是否有適用於該 host 的成員。"""
    return any(host in (m.get("hosts") or []) for m in chain_members(env))


def guard_wanted(mods: Optional[list[str]], env: Mapping[str, str], host: str) -> bool:
    """guard hook 要不要註冊：選了 dispatch-guard，或 chain 在這個 host 有成員（chain-only 模式，由 guard 端處理）。"""
    return mods is None or "dispatch-guard" in mods or chain_hosts(env, host)


def manifest_modules(env: Mapping[str, str], host: str) -> Optional[list[str]]:
    entry = (load_manifest(env) or {}).get(host)
    mods = entry.get("modules") if isinstance(entry, dict) else None
    return list(mods) if isinstance(mods, list) else None


def write_manifest(env: Mapping[str, str], host: str, modules: list[str], extra: Optional[dict] = None) -> Path:
    data = load_manifest(env) or {}
    version = (REPO / "VERSION").read_text().strip() if (REPO / "VERSION").is_file() else ""
    data[host] = {"modules": modules, "version": version, **(extra or {})}
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
        return True  # opencode plugin 內建；grok 沒有可靠的判斷（claude 看 CLAUDE_GUARD_PLUGIN，不走這裡）
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
        installed = _read(home / "plugins" / "installed_plugins.json")
        if "shoal@shoal" not in installed:
            return None
        mods += ["core", "host-claude"]
        if CLAUDE_GUARD_PLUGIN in installed:  # S4：guard 是獨立 plugin
            mods.append("dispatch-guard")
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
    """--apply 會執行的 installer 指令（Python 腳本或外部 CLI）；claude 的 CLI 步驟見 claude_steps。"""
    py = sys.executable
    home = host_home(host, env)
    if host == "codex":
        cmds = [[py, str(REPO / "install/install.py"), "--codex-home", str(home)]]
        if not guard_wanted(mods, env, host):
            cmds[0].append("--no-guard")
        if "codex-autoroute" not in mods:
            cmds[0].append("--no-autoroute")
        if "jev-router" in mods:
            cmds.append(["codex", "plugin", "add", JEV_PLUGIN])
        return cmds
    if host == "agy":
        cmd = [py, str(REPO / "tools/install_hooks.py"), "--host", "agy", "--home", str(home)]
        return [[*cmd, "--apply"] if guard_wanted(mods, env, host) else [*cmd, "--uninstall", "--apply"]]
    if host == "grok":
        cmd = [py, str(REPO / "tools/install_grok.py"), "--grok-home", str(home), "--apply"]
        return [cmd if guard_wanted(mods, env, host) else [*cmd, "--no-guard"]]
    if host == "opencode":
        cmd = [py, str(REPO / "tools/opencode_global.py")]
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
    member = {"name": name, "command": command, "hosts": hosts, "order": order}
    if args.chain_events is not None:
        events = _csv([args.chain_events])
        bad = [e for e in events if e not in CHAIN_EVENTS]
        if not events or bad:
            raise InstallError(f"--chain-events 不認得：{', '.join(bad) or '(空)'}；可用：{', '.join(CHAIN_EVENTS)}")
        member["events"] = events
    return member


def _guard_follow_up(hosts: list[str], before: dict[str, bool], args: argparse.Namespace, env: Mapping[str, str], runner: Runner) -> int:
    """chain 變更讓某 host 的 guard hook 決定翻轉時，重跑該 host 的 guard 安裝步驟（只在 manifest 有該 host 且沒選
    dispatch-guard 時才可能翻轉）。codex/agy/grok 重跑單一 guard installer；claude 只印 plugin 指令（plugin 由使用者裝）。"""
    for host in hosts:
        mods = manifest_modules(env, host)
        if mods is None or "dispatch-guard" in mods or host not in before:
            continue
        now = guard_wanted(mods, env, host)
        if now == before[host]:
            continue
        if host == "claude":
            verb = "install" if now else "uninstall"
            print(("would print: " if not args.apply else "run manually: ") + f"claude plugin {verb} {CLAUDE_GUARD_PLUGIN}")
            continue
        if host not in ("codex", "agy", "grok"):
            continue
        cmd = wrapped_commands(host, mods, env)[0]
        print(("would run: " if not args.apply else "run: ") + " ".join(cmd))
        if args.apply:
            code = runner(cmd, env)
            if code != 0:
                print(f"failed: {' '.join(cmd)} exit {code}；manifest 已更新，請手動重跑上面這行", file=sys.stderr)
                return 1
    return 0


def do_chain(args: argparse.Namespace, reg: dict, env: Mapping[str, str], runner: Runner = default_runner) -> int:
    data = load_manifest(env) or {}
    before = {h: guard_wanted(manifest_modules(env, h), env, h) for h in reg["hosts"]}
    chain = [m for m in data.get("chain", []) if isinstance(m, dict)] if isinstance(data.get("chain"), list) else []
    if args.chain_add is not None:
        member = parse_chain_member(args, reg, env)
        if any(m.get("name") == member["name"] for m in chain):
            old = next(m for m in chain if m.get("name") == member["name"])
            if "events" not in member and "events" in old:
                member["events"] = old["events"]  # 重新登記沒帶 --chain-events：沿用原本的訂閱
            chain = [member if m.get("name") == member["name"] else m for m in chain]
        else:
            chain.append(member)
        print(f"chain add: {member['name']}  hosts={','.join(member['hosts'])}  order={member['order']}  command={json.dumps(member['command'], ensure_ascii=False)}"
              + (f"  events={','.join(member['events'])}" if "events" in member else ""))
    else:
        if args.chain_remove not in [m.get("name") for m in chain]:
            print(f"chain: {args.chain_remove} 不在 chain 內，沒有變更")
            return 0
        chain = [m for m in chain if m.get("name") != args.chain_remove]
        print(f"chain remove: {args.chain_remove}")
    if not args.apply:
        print(f"dry-run：未寫入任何檔案；--apply 會寫 {manifest_path(env)}（成員只登記，不會被執行）")
        _preview_follow_up(data, chain, before, args, reg, env)
        return 0
    print(f"manifest: {_save_manifest(env, {**data, 'chain': chain})}")
    return _guard_follow_up(list(reg["hosts"]), before, args, env, runner)


def _preview_follow_up(data: dict, chain: list, before: dict[str, bool], args: argparse.Namespace, reg: dict, env: Mapping[str, str]) -> None:
    """dry-run：manifest 還沒寫，用暫時覆蓋的 env 預覽（不寫檔）會觸發哪些 guard 步驟。"""
    with tempfile.TemporaryDirectory(prefix="shoal-chain-preview-") as tmp:
        preview = {**env, "XDG_DATA_HOME": tmp}
        _save_manifest(preview, {**data, "chain": chain})
        _guard_follow_up(list(reg["hosts"]), before, args, preview, default_runner)


CLAUDE_GUARD_PLUGIN = "shoal-dispatch-guard@shoal"


def claude_steps(mods: list[str], env: Mapping[str, str]) -> list[tuple[list[str], Optional[list[str]]]]:
    """(顯示用 argv, 失敗時的備援 argv)。marketplace 或 plugin 已存在時 add、install 會失敗，改走 update。"""
    steps: list[tuple[list[str], Optional[list[str]]]] = [
        (["claude", "plugin", "marketplace", "add", "miyago9267/shoal"], ["claude", "plugin", "marketplace", "update", "shoal"]),
        (["claude", "plugin", "install", "shoal@shoal"], ["claude", "plugin", "update", "shoal@shoal"]),
    ]
    if guard_wanted(mods, env, "claude"):
        steps.append((["claude", "plugin", "install", CLAUDE_GUARD_PLUGIN], ["claude", "plugin", "update", CLAUDE_GUARD_PLUGIN]))
    return steps


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(path: Path) -> str:
    """檔案或目錄樹的內容 sha256（目錄含相對路徑）；copy 模式用它比對 hosts/agy/dist。"""
    if path.is_file():
        return _digest_file(path)
    h = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(item.relative_to(path).as_posix().encode("utf-8") + b"\0")
        h.update(_digest_file(item).encode("ascii"))
    return h.hexdigest()


def agy_mode(env: Mapping[str, str]) -> Optional[str]:
    entry = (load_manifest(env) or {}).get("agy")
    return entry.get("agy_mode") if isinstance(entry, dict) else None


def agy_items(repo: Path = REPO) -> list[tuple[str, Path]]:
    """hosts/agy/dist 的 agents、skills 項目：(相對 ~/.gemini/config 的路徑, 來源)。"""
    items = []
    for kind in ("agents", "skills"):
        root = repo / "hosts" / "agy" / "dist" / kind
        if root.is_dir():
            items += [(f"{kind}/{p.name}", p) for p in sorted(root.iterdir())]
    return items


def _copy_item(src: Path, dst: Path) -> None:
    if dst.is_dir() and not dst.is_symlink():
        shutil.rmtree(dst)
    elif dst.exists() or dst.is_symlink():
        dst.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def link_agy(env: Mapping[str, str], apply: bool) -> str:
    """agents、skills 連到 hosts/agy/dist（G2）；回傳 "symlink" 或 "copy"。

    不覆蓋使用者自己的檔案：已存在且不是 shoal 的 symlink（copy 模式則是內容不同的非自有檔）一律保留並回報。
    os.symlink 丟 OSError（Windows 無權限）時，這個與其後的項目改為複製，並由呼叫端在 manifest 記 agy_mode: copy。
    """
    config = host_home("agy", env) / "config"
    copy_mode = agy_mode(env) == "copy"
    for rel, src in agy_items():
        dst = config / rel
        want = os.path.realpath(src)
        if dst.is_symlink():
            if os.path.realpath(dst) == want:
                print(f"ok: {dst}")
            else:
                print(f"kept: {dst} 是指向別處的 symlink，未動")
            continue
        if dst.exists():
            if tree_digest(dst) == tree_digest(src):
                print(f"ok: {dst}")
            elif copy_mode:  # 上次由 shoal 複製的，內容過期就更新
                print(("would update copy: " if not apply else "update copy: ") + str(dst))
                if apply:
                    _copy_item(src, dst)
            else:
                print(f"kept: {dst} 已存在且不是 shoal 的 symlink，未動")
            continue
        verb = "copy" if copy_mode else "link"
        print(f"would {verb}: {dst} -> {src}" if not apply else f"{verb}: {dst} -> {src}")
        if not apply:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not copy_mode:
            try:
                os.symlink(src, dst, target_is_directory=src.is_dir())
                continue
            except OSError as exc:
                print(f"note: symlink 失敗（{exc}），agy 改用複製模式")
                copy_mode = True
        _copy_item(src, dst)
    return "copy" if copy_mode else "symlink"


AGY_BEGIN, AGY_END = "<!-- shoal-agy:begin -->", "<!-- shoal-agy:end -->"
AGY_OWNED = "<!-- shoal-agy:installer -->"  # 入口自己寫的區塊前綴；沒有它的 shoal-agy 區塊視為外部 composer 產生


def agy_bootstrap() -> str:
    text = (REPO / "hosts/agy/dist/rules/shoal-agy.md").read_text(encoding="utf-8")
    return text[text.index(AGY_BEGIN) : text.index(AGY_END) + len(AGY_END)]


def upsert_gemini_md(env: Mapping[str, str], apply: bool) -> None:
    """把 agy bootstrap 以標記區塊放進 ~/.gemini/GEMINI.md（agy 不讀 config/rules）。

    GEMINI.md 是 symlink，或已有外部 composer 產生的 shoal-agy 區塊時不寫入（managed externally），只檢查內容；
    永遠不寫穿 symlink。
    """
    dst = host_home("agy", env) / "GEMINI.md"
    block = agy_bootstrap()
    owned = AGY_OWNED + "\n" + block
    if dst.is_symlink():
        text = dst.read_text(encoding="utf-8", errors="replace") if dst.exists() else ""
        ok = block in text
        print(f"managed externally: {dst} 是 symlink，未寫入；shoal-agy 區塊{'內容相符' if ok else '缺少或與 repo 不符'}")
        return
    text = dst.read_text(encoding="utf-8") if dst.exists() else ""
    if AGY_BEGIN in text and AGY_OWNED not in text:
        ok = block in text
        print(f"managed externally: {dst} 的 shoal-agy 區塊不是入口寫的，未寫入；內容{'相符' if ok else '與 repo 不符'}")
        return
    if AGY_OWNED in text:
        a = text.index(AGY_OWNED)
        b = text.index(AGY_END, a) + len(AGY_END)
        new = text[:a] + owned + text[b:]
    else:
        new = text + ("\n" if text and not text.endswith("\n") else "") + ("\n" if text else "") + owned + "\n"
    if new == text:
        print(f"ok: {dst}")
        return
    print(("would write: " if not apply else "write: ") + f"{dst}（shoal-agy 區塊）")
    if apply:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(new, encoding="utf-8")


def install_explore(env: Mapping[str, str], apply: bool) -> None:
    """claude-explore 選中時把 repo 的 Explore.md 裝進 ~/.claude/agents；使用者自己的同名檔不覆蓋。"""
    src, dst = REPO / EXPLORE_DIST, host_home("claude", env) / "agents" / "Explore.md"
    if dst.is_file() and dst.read_bytes() == src.read_bytes():
        print(f"ok: {dst}")
    elif dst.exists():
        print(f"kept: {dst} 已存在且內容與 repo 的 dist 不同，未動")
    else:
        print(("would install: " if not apply else "install: ") + str(dst))
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)


def preview_command(cmd: list[str]) -> Optional[list[str]]:
    """把 --apply 的指令轉成底層 installer 的 dry-run 形式；外部 CLI 沒有預覽，回傳 None。"""
    if cmd[0] != sys.executable:
        return None
    name = Path(cmd[1]).name
    if name == "install.py":
        return [*cmd, "--dry-run"]
    if name == "opencode_global.py":
        return [*cmd, "--dry-run"]
    return [c for c in cmd if c != "--apply"]  # install_hooks.py、install_grok.py 沒有 --apply 就是 dry-run


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
        print(f"  [{member['order']}] {member['name']}  hosts={','.join(member['hosts'])}  command={json.dumps(member['command'], ensure_ascii=False)}"
              + (f"  events={','.join(member['events'])}" if isinstance(member.get("events"), list) else ""))
    return 0


def do_install(args: argparse.Namespace, reg: dict, env: Mapping[str, str], runner: Runner, previewer: Previewer = default_previewer) -> int:
    host = args.host
    mods, source = resolve(host, reg, env, _csv(args.with_), _csv(args.without), _csv(args.only))
    print(f"host: {host}  modules: {', '.join(mods)}  (base: {source})")
    cmds = wrapped_commands(host, mods, env)
    removals = explore_removal(host, mods, env)
    # 外部 CLI（codex plugin add、claude plugin ...）以 shutil.which 解析；找不到：dry-run 回報 skipped，--apply 失敗。
    missing: list[str] = []
    resolved: list[list[str]] = []
    for cmd in cmds:
        if cmd[0] == sys.executable:
            resolved.append(cmd)
        elif (exe := which(cmd[0], env)) is not None:
            resolved.append([exe, *cmd[1:]])
        else:
            missing.append(cmd[0])
    if host == "codex" and which("codex", env) is None:  # install.py 自己要呼叫 codex --version
        missing.append("codex")
    for cmd in cmds:
        print("would run:" if not args.apply else "run:", " ".join(cmd))
    if host == "claude":
        claude_exe = which("claude", env)
        for shown, _ in claude_steps(mods, env):
            print(("would run: " if not args.apply else "run: ") + " ".join(shown))
        if claude_exe is None:
            missing.append("claude")
        if "claude-explore" in mods:
            install_explore(env, args.apply)
    for name in dict.fromkeys(missing):
        extra = "；改用 claude plugin marketplace add miyago9267/shoal（見 README）" if name == "claude" else ""
        print(f"skipped: {name} not found on PATH{extra}")
    chain_only = "dispatch-guard" not in mods and chain_hosts(env, host)
    if chain_only and host in ("codex", "agy", "grok", "claude"):
        print(f"note: dispatch-guard 關閉但 chain 在 {host} 有成員：仍註冊 shoal hook（chain-only 模式），讓 chain 能執行")
    if host == "claude" and "dispatch-guard" not in mods and not chain_only:
        print(f"note: dispatch-guard 關閉：不安裝 {CLAUDE_GUARD_PLUGIN}（hook 都在那個 plugin）；若已裝過，自行執行 claude plugin uninstall {CLAUDE_GUARD_PLUGIN}")
    if host == "opencode" and "dispatch-guard" not in mods:
        print(
            "note: dispatch-guard 關閉：guard 隨 plugin 的檔案仍會安裝，manifest 沒有 dispatch-guard 時它讀同一份 manifest，"
            "以 off 模式執行（同時不呼叫 chain 成員）；加回 --with dispatch-guard 即恢復"
        )
    for path in removals:
        print(("would remove: " if not args.apply else "remove: ") + str(path))
    extra_manifest: dict = {}
    if host == "agy":
        mode = link_agy(env, args.apply)
        upsert_gemini_md(env, args.apply)
        if args.apply and mode == "copy":
            extra_manifest["agy_mode"] = "copy"
    path = manifest_path(env)
    if not args.apply:
        failed_preview = False
        for cmd in cmds:
            pcmd = preview_command(cmd)
            if pcmd is None or (host == "codex" and "codex" in missing):
                continue
            code, text = previewer(pcmd, env)
            print(f"preview（{' '.join(pcmd[1:])}）:")
            for line in text.rstrip().splitlines():
                print(f"  {line}")
            if code != 0:
                print(f"preview failed: exit {code}", file=sys.stderr)
                failed_preview = True
        print(f"dry-run：未寫入任何檔案；--apply 會寫 {path}")
        return 1 if failed_preview else 0
    if missing:
        raise InstallError(f"{', '.join(dict.fromkeys(missing))} not found on PATH，無法 --apply")
    for cmd in resolved:
        code = runner(cmd, env)
        if code != 0:
            print(f"failed: {' '.join(cmd)} exit {code}；manifest 未更新", file=sys.stderr)
            return 1
    if host == "claude":
        for shown, fallback in claude_steps(mods, env):
            code = runner([claude_exe, *shown[1:]], env)
            if code != 0 and fallback:
                code = runner([claude_exe, *fallback[1:]], env)
            if code != 0:
                print(f"failed: {' '.join(shown)} exit {code}；manifest 未更新", file=sys.stderr)
                return 1
    for path in removals:
        path.unlink(missing_ok=True)
    print(f"manifest: {write_manifest(env, host, mods, extra_manifest)}")
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
    p.add_argument("--chain-events", metavar="EVENTS", help=f"成員訂閱的事件（逗號分隔，{', '.join(CHAIN_EVENTS)}）；省略＝只有 PreToolUse，重新登記時沿用原值")
    p.add_argument("--chain-order", type=_num, metavar="N", help="執行順序（升冪）；預設：同名成員沿用原值，新成員為現有最大值加 1")
    p.add_argument("--chain-remove", metavar="NAME", help="從 chain 移除成員")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="預設；印出指令不寫入")
    mode.add_argument("--apply", action="store_true", help="執行既有 installer 並寫 manifest")
    return p


def main(
    argv: Optional[list[str]] = None,
    env: Optional[Mapping[str, str]] = None,
    runner: Runner = default_runner,
    previewer: Previewer = default_previewer,
) -> int:
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
            return do_chain(args, reg, env, runner)
        except InstallError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if not args.host:
        parser.error("需要 --host 或 --list")
    try:
        return do_install(args, reg, env, runner, previewer)
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
