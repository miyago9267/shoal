"""shoal --update（repo-layout P3，R13、R14）：把本機 checkout 的 committed HEAD 同步到各 host。

由 tools/shoal_install.py --update [--apply] 呼叫；不帶 --apply 是 dry-run，只回報會做什麼。
不含 git pull（D10）：只更新 checkout 目前的 committed HEAD。stdlib only，不用 bash、tar、timeout。

每步輸出一行 `<step>: up-to-date | updated | skipped | failed`（dry-run 的 updated 行尾加 [dry-run]）：
  cleanup               清掉上次殘留的 `.old` 與暫存目錄（`.old` 只在正式目錄不存在時才還原，否則刪除）
  interpreter           把 PATH 上 python3 的真實路徑寫到 ${XDG_DATA_HOME:-~/.local/share}/shoal/python（guard hook 用）
  marketplace           匯出 HEAD 的 Claude marketplace，與現有目錄逐檔比對 sha256，有差異才兩次 rename 交換
  claude marketplace    claude plugin marketplace add|update
  claude plugin <id>    claude plugin install|update（guard plugin 依模組清單與 chain）
  explore               ~/.claude/agents/Explore.md（claude-explore 模組未被停用時）
  codex marketplace     以 install/install.py 的 P2 邏輯匯出並登記 shoal 擁有的目錄
  sync <host>           tools/sync_global.py 的各 host 摘要
  verify <what>         匯出內容、guard、Explore.md 與已安裝檔案逐位元組比對 sha256
claude 步驟任何一個失敗：把 `.old` rename 還原並回報 failed，全部成功後才刪 `.old`。
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping, Optional

import shoal_install as si

sys.path.insert(0, str(si.REPO / "install"))
import shoal_version as sv  # noqa: E402

REPO = si.REPO
MARKETPLACE_MANIFEST = ".claude-plugin/marketplace.json"
MARKETPLACE_NAME = "shoal"
CORE_PLUGIN = "shoal"
GUARD_PLUGIN = "shoal-dispatch-guard"
GUARD_SOURCE_FILE = (
    "hooks/shoal_guard.py"  # repo 內的 guard 正本；guard plugin 內的副本必須相同
)
CLI_TIMEOUT = 120


class UpdateError(Exception):
    pass


@contextmanager
def _environ(env: Mapping[str, str]) -> Iterator[None]:
    """install/install.py 的 P2 函式讀 os.environ；呼叫期間暫時換成 --update 的 env，結束後還原。"""
    if env is os.environ:
        yield
        return
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _load_codex_install():
    """載入 install/install.py（P2 的匯出與登記函式）；dataclass 需要模組先放進 sys.modules。"""
    cached = sys.modules.get("shoal_codex_install")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location("shoal_codex_install", REPO / "install" / "install.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["shoal_codex_install"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _extract(data: bytes, dest: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        if hasattr(tarfile, "data_filter"):
            archive.extractall(dest, filter="data")
        else:
            archive.extractall(dest)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.shoal-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Updater:
    def __init__(self, env: Mapping[str, str], apply: bool, repo: Path = REPO) -> None:
        self.env, self.apply, self.repo = env, apply, repo
        self.failed = False
        self.data = si.manifest_path(
            env
        ).parent  # ${XDG_DATA_HOME:-~/.local/share}/shoal
        self.mp = self.data / "claude-marketplace"

    # ---- output ----
    def emit(self, step: str, status: str, detail: str = "") -> None:
        if status == "failed":
            self.failed = True
        line = f"{step}: {status}" + (f" ({detail})" if detail else "")
        if status == "updated" and not self.apply:
            line += " [dry-run]"
        print(line, flush=True)

    # ---- git ----
    def git(self, *args: str) -> bytes:
        # Windows 上 subprocess 不會找 .cmd shim，要先用 which 解析
        git = si.which("git", self.env) or "git"
        cmd = [git, "-c", "core.autocrlf=false", "-C", str(self.repo), *args]
        try:
            proc = subprocess.run(
                cmd, env=dict(self.env), capture_output=True, timeout=120
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UpdateError(f"git {args[0]} 無法執行: {exc}") from exc
        if proc.returncode != 0:
            tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
            raise UpdateError(
                f"git {args[0]} 失敗: {tail[-1] if tail else 'exit ' + str(proc.returncode)}"
            )
        return proc.stdout

    def export(self, paths: list[str], dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        _extract(self.git("archive", "--format=tar", "HEAD", "--", *paths), dest)

    def blob(self, path: str) -> bytes:
        return self.git("show", f"HEAD:{path}")

    def source_stable(self) -> bool:
        """HEAD 有 CHANNEL 檔且寫 stable 才是 stable epoch；沒有檔案就是 beta。"""
        try:
            return sv.stable_marker(self.blob(sv.CHANNEL_FILE).decode("utf-8", "replace"))
        except UpdateError:
            return False

    def marketplace_info(self) -> tuple[list[str], dict[str, dict]]:
        """(要匯出的路徑, {plugin 名稱: {"source": 相對路徑, "version": ...}})，全由 HEAD 的 marketplace.json 決定。"""
        try:
            doc = json.loads(self.blob(MARKETPLACE_MANIFEST))
            plugins = {}
            for item in doc["plugins"]:
                src = item.get("source")
                if isinstance(src, str) and src.startswith("./"):
                    plugins[item["name"]] = {
                        "source": src[2:].rstrip("/"),
                        "version": item.get("version"),
                    }
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise UpdateError(f"{MARKETPLACE_MANIFEST} 無法解析: {exc}") from exc
        if CORE_PLUGIN not in plugins:
            raise UpdateError(f"{MARKETPLACE_MANIFEST} 沒有 {CORE_PLUGIN} plugin")
        paths = [
            ".claude-plugin",
            *dict.fromkeys(p["source"] for p in plugins.values()),
        ]
        return paths, plugins

    # ---- cleanup ----
    def cleanup(self) -> None:
        """啟動時清掉上次殘留。`.old` 通常是上次失敗後已還原的舊目錄，直接刪；
        只有正式目錄不見（兩次 rename 之間被中斷）時才把 `.old` 還原。"""
        done: list[str] = []
        for target, stage_glob in (
            (self.mp, ".claude-marketplace.*"),
            (self.data / "codex-marketplace", ".codex-marketplace-*"),
        ):
            old = target.with_name(target.name + ".old")
            if old.exists():
                if not target.exists():
                    done.append(f"restore {old.name}")
                    if self.apply:
                        os.rename(old, target)
                else:
                    done.append(f"remove {old.name}")
                    if self.apply:
                        shutil.rmtree(old, ignore_errors=True)
            for leftover in (
                sorted(self.data.glob(stage_glob)) if self.data.is_dir() else []
            ):
                done.append(f"remove {leftover.name}")
                if self.apply:
                    shutil.rmtree(leftover, ignore_errors=True)
        if done:
            self.emit("cleanup", "updated", ", ".join(done))

    # ---- claude CLI ----
    def claude(self, exe: str, *args: str) -> tuple[int, str]:
        try:
            proc = subprocess.run(
                [exe, *args],
                env=dict(self.env),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=CLI_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 127, str(exc)
        return proc.returncode, proc.stdout if proc.returncode == 0 else (
            proc.stderr or proc.stdout
        )

    def claude_list(self, exe: str, *args: str) -> list[dict]:
        code, text = self.claude(exe, *args)
        if code != 0:
            return []
        try:
            rows = json.loads(text)
        except ValueError:
            return []
        return (
            [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
        )

    def wanted_plugins(self, plugins: dict[str, dict]) -> list[tuple[str, str]]:
        """(plugin 名稱, 不需要的原因；空字串＝要裝)。guard 規則與 install 入口相同：選了 dispatch-guard 或 chain 在 claude 有成員。"""
        wanted = [(CORE_PLUGIN, "")]
        if GUARD_PLUGIN in plugins:
            mods = si.manifest_modules(self.env, "claude")
            wanted.append(
                (
                    GUARD_PLUGIN,
                    ""
                    if si.guard_wanted(mods, self.env, "claude")
                    else "模組 dispatch-guard 未選且 chain 無 claude 成員",
                )
            )
        return wanted

    def claude_steps(
        self, exe: str, changed: bool, plugins: dict[str, dict]
    ) -> tuple[list[tuple[str, str, str]], Optional[str]]:
        """回傳 (步驟結果, 錯誤)。changed＝marketplace 目錄剛換新；dry-run 只讀（list），其餘回報會做什麼。"""
        out: list[tuple[str, str, str]] = []
        registered = any(
            r.get("name") == MARKETPLACE_NAME
            for r in self.claude_list(exe, "plugin", "marketplace", "list", "--json")
        )
        mp_status = "up-to-date"
        if not registered:
            verb, mp_status = "add", "updated"
        elif changed:
            verb, mp_status = "update", "updated"
        else:
            verb = ""
        if verb:
            if self.apply:
                code, text = self.claude(
                    exe,
                    "plugin",
                    "marketplace",
                    verb,
                    str(self.mp) if verb == "add" else MARKETPLACE_NAME,
                )
                if code != 0:
                    return (
                        out,
                        f"claude plugin marketplace {verb} exit {code}: {_last(text)}",
                    )
            out.append(("claude marketplace", mp_status, verb))
        else:
            out.append(("claude marketplace", "up-to-date", ""))
        installed = (
            {r.get("id"): r for r in self.claude_list(exe, "plugin", "list", "--json")}
            if registered or self.apply
            else {}
        )
        for name, skip in self.wanted_plugins(plugins):
            pid = f"{name}@{MARKETPLACE_NAME}"
            step = f"claude plugin {pid}"
            if skip:
                out.append((step, "skipped", skip))
                continue
            row = installed.get(pid)
            source = plugins[name]["version"]
            if row is None:
                verb = "install"
            elif (
                isinstance(row.get("version"), str)
                and isinstance(source, str)
                and sv.is_channel_switch(row["version"], source, source_stable=self.source_stable())
            ):
                # beta -> stable：plugin manager 用純 SemVer，會把 stable 當成較舊，先移除再裝。
                verb = "reinstall"
            elif changed or (
                row.get("version")
                and plugins[name]["version"]
                and row["version"] != plugins[name]["version"]
            ):
                verb = "update"
                if row.get("version") == plugins[name]["version"]:
                    # Claude 依版本號快取 plugin；版本沒升，plugin update 不會刷新 cache。
                    out.append((step, "skipped", "marketplace 內容有變但版本沒升，cache 不會刷新；請升 hosts/claude/VERSION 並 render"))
                    continue
            else:
                out.append((step, "up-to-date", ""))
                continue
            if self.apply:
                for sub in ("uninstall", "install") if verb == "reinstall" else (verb,):
                    code, text = self.claude(exe, "plugin", sub, pid)
                    if code != 0:
                        return out, f"claude plugin {sub} {pid} exit {code}: {_last(text)}"
            out.append((step, "updated", verb))
        return out, None

    # ---- marketplace（R13 的交換契約）----
    def swap(self, stage: Path, post) -> Optional[str]:
        """現有目錄 -> `.old`、暫存 -> 正式名稱（兩次 rename，不用 rmtree 加複製）；
        `post()` 回傳錯誤字串就還原 `.old` 並回傳該錯誤；成功才刪 `.old`。"""
        mp, old = self.mp, self.mp.with_name(self.mp.name + ".old")
        had = mp.exists()
        try:
            if had:
                os.rename(mp, old)
            os.rename(stage, mp)
        except OSError as exc:
            if had and old.exists() and not mp.exists():
                os.rename(old, mp)
            return f"rename failed: {exc}"
        error = post()
        if error is not None:
            bad = self.data / ".claude-marketplace.rolledback"
            try:
                os.rename(mp, bad)
                if had:
                    os.rename(old, mp)
            except OSError as exc:
                return f"{error}; rollback failed: {exc}"
            shutil.rmtree(bad, ignore_errors=True)
            return error
        if had:
            shutil.rmtree(old, ignore_errors=True)
        return None

    def update_claude(self) -> None:
        exe = si.which("claude", self.env)
        if exe is None:
            for step in (
                "marketplace",
                "claude marketplace",
                "claude plugin",
                "explore",
            ):
                self.emit(step, "skipped", "claude not on PATH")
            return
        paths, plugins = self.marketplace_info()
        scratch = (
            tempfile.TemporaryDirectory(prefix="shoal-update-")
            if not self.apply
            else None
        )
        try:
            if self.apply:
                self.data.mkdir(parents=True, exist_ok=True)
                stage = Path(
                    tempfile.mkdtemp(prefix=".claude-marketplace.", dir=self.data)
                )
            else:
                stage = Path(scratch.name) / "stage"  # type: ignore[union-attr]
            self.export(paths, stage)
            changed = not self.mp.is_dir() or si.tree_digest(stage) != si.tree_digest(
                self.mp
            )
            if not changed:
                shutil.rmtree(stage, ignore_errors=True)
                self.emit("marketplace", "up-to-date")
                results, error = self.claude_steps(exe, False, plugins)
            elif not self.apply:
                self.emit("marketplace", "updated", "內容與 HEAD 不同")
                results, error = self.claude_steps(exe, True, plugins)
            else:
                captured: dict = {}

                def post() -> Optional[str]:
                    captured["results"], err = self.claude_steps(exe, True, plugins)
                    return err

                error = self.swap(stage, post)
                results = captured.get("results", [])
                if error is None:
                    self.emit("marketplace", "updated", "swapped")
                else:
                    self.emit("marketplace", "failed", f"{error}; 已還原")
                    results = []
            if not (self.apply and changed):
                if error is not None:
                    self.emit("claude marketplace", "failed", error)
            for step, status, detail in results:
                self.emit(step, status, detail)
        finally:
            if scratch is not None:
                scratch.cleanup()
            if self.apply:
                for leftover in self.data.glob(".claude-marketplace.*"):
                    shutil.rmtree(leftover, ignore_errors=True)
        self.update_explore()

    def update_explore(self) -> None:
        mods = si.manifest_modules(self.env, "claude")
        if mods is not None and "claude-explore" not in mods:
            self.emit("explore", "skipped", "模組 claude-explore 未選")
            return
        want = self.blob(si.EXPLORE_DIST)
        target = si.host_home("claude", self.env) / "agents" / "Explore.md"
        try:
            same = target.is_file() and target.read_bytes() == want
        except OSError:
            same = False
        if same:
            self.emit("explore", "up-to-date")
            return
        if self.apply:
            _atomic_write(target, want)
        self.emit("explore", "updated", str(target))

    # ---- codex ----
    def update_codex(self) -> None:
        home = si.host_home("codex", self.env)
        if si.which("codex", self.env) is None:
            self.emit("codex marketplace", "skipped", "codex not on PATH")
            return
        if not home.is_dir():
            self.emit("codex marketplace", "skipped", f"{home} 不存在")
            return
        mod = _load_codex_install()
        with (
            _environ(self.env),
            tempfile.TemporaryDirectory(prefix="shoal-update-") as tmp,
        ):
            export_dir = mod._codex_export_dir()
            fresh = Path(tmp) / "fresh"
            self.export(list(mod.CODEX_EXPORT_PATHS), fresh)
            current = export_dir.is_dir() and si.tree_digest(
                export_dir
            ) == si.tree_digest(fresh)
            installed = mod._plugin_is_installed(source_root=self.repo, codex_home=home)
            switch = any(
                isinstance(row.get("version"), str)
                and row.get("name") == mod.SHOAL_PLUGIN_NAME
                and sv.is_channel_switch(
                    row["version"], mod.SHOAL_PLUGIN_VERSION, source_stable=self.source_stable()
                )
                for row in mod._installed_plugin_rows(home) or []
            )
            if current and installed and not switch:
                self.emit("codex marketplace", "up-to-date")
                return
            if not self.apply:
                self.emit("codex marketplace", "updated", str(export_dir))
                return
            if switch and not mod._remove_plugin(codex_home=home):
                self.emit("codex marketplace", "failed", "plugin remove failed before channel switch")
                return
            result = mod._install_plugin(
                source_root=self.repo, codex_home=home, dry_run=False, enabled=True
            )
        if result.get("status") == "installed":
            self.emit("codex marketplace", "updated", str(export_dir))
        else:
            self.emit(
                "codex marketplace", "failed", f"plugin status {result.get('status')}"
            )

    # ---- interpreter（Claude guard plugin 的 hooks/run.sh 讀這個路徑）----
    def record_interpreter(self) -> None:
        if not self.apply:
            self.emit("interpreter", "updated", str(si.interpreter_path(self.env)))
            return
        real = si.record_interpreter(self.env)
        self.emit("interpreter", "updated" if real else "skipped", real or "python3 not resolved")

    # ---- host sync（沿用 sync_global.py）----
    def sync_hosts(self) -> None:
        cmd = [
            sys.executable,
            str(self.repo / "tools" / "sync_global.py"),
            "--repo",
            str(self.repo),
        ]
        if self.apply:
            cmd.append("--apply")
        try:
            proc = subprocess.run(
                cmd,
                env=dict(self.env),
                cwd=self.repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=900,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.emit("sync", "failed", str(exc))
            return
        seen = False
        for line in proc.stdout.splitlines():
            host, sep, rest = line.partition(": ")
            status = rest.split(" ", 1)[0]
            if sep and status in ("up-to-date", "updated", "skipped", "failed"):
                seen = True
                if status == "failed":
                    self.failed = True
                print(f"sync {line}", flush=True)  # sync_global 已自行加 [dry-run]
        if not seen or proc.returncode != 0:
            self.emit(
                "sync",
                "failed",
                f"exit {proc.returncode}: {_last(proc.stderr or proc.stdout)}",
            )

    # ---- hash 檢查 ----
    def verify(self) -> None:
        exe = si.which("claude", self.env)
        if exe is None:
            self.emit("verify", "skipped", "claude not on PATH")
            return
        if not self.mp.is_dir():
            self.emit(
                "verify marketplace",
                "skipped" if not self.apply else "failed",
                f"{self.mp} 不存在",
            )
            return
        paths, plugins = self.marketplace_info()
        with tempfile.TemporaryDirectory(prefix="shoal-verify-") as tmp:
            fresh = Path(tmp) / "fresh"
            self.export(paths, fresh)
            expected, actual = si.tree_digest(fresh), si.tree_digest(self.mp)
        if expected != actual:
            self.emit(
                "verify marketplace",
                "skipped" if not self.apply else "failed",
                "已安裝的 marketplace 與 HEAD 不符"
                if self.apply
                else "尚未更新（dry-run）",
            )
            return
        self.emit("verify marketplace", "up-to-date", f"sha256 {expected[:12]}")
        guard = plugins.get(GUARD_PLUGIN)
        if guard is None or dict(self.wanted_plugins(plugins)).get(GUARD_PLUGIN):
            self.emit("verify guard", "skipped", "guard plugin 不需要")
            return
        installed = self.mp / guard["source"] / GUARD_SOURCE_FILE
        want = _sha(self.blob(GUARD_SOURCE_FILE))
        try:
            got = _sha(installed.read_bytes())
        except OSError as exc:
            self.emit("verify guard", "failed", str(exc))
            return
        if got == want:
            self.emit("verify guard", "up-to-date", f"sha256 {got[:12]}")
        else:
            self.emit(
                "verify guard", "failed", f"sha256 {got[:12]} != repo {want[:12]}"
            )


def _last(text: str) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return (lines[-1] if lines else "no output")[:200]


def run_update(env: Mapping[str, str], apply: bool) -> int:
    up = Updater(env, apply)
    try:
        up.git("rev-parse", "--verify", "HEAD^{commit}")
    except UpdateError as exc:
        up.emit("head", "failed", f"沒有 committed HEAD（{exc}）")
        return 1
    steps = (up.cleanup, up.record_interpreter, up.update_claude, up.update_codex, up.sync_hosts, up.verify)
    for step in steps:
        try:
            step()
        except (UpdateError, OSError) as exc:
            up.emit(
                step.__name__.replace("_", " "),
                "failed",
                f"{type(exc).__name__}: {exc}",
            )
    return 1 if up.failed else 0
