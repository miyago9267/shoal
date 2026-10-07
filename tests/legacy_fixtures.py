"""2.0.0 之前（舊名）安裝的 fixture 與 helper，給遷移測試用（docs/specs/shoal-rebrand N5）。

舊名只出現在 LEGACY_ 常數與 tests/fixtures/legacy_install/（逐檔取自 base commit 21d5986 的
installer 實際輸出）；測試本體只引用這裡的常數，產品面舊名掃描（tools/scan_legacy_names.py）因此為 0。
所有 home、config dir、state dir 都是呼叫端給的 temp 目錄，這裡不碰真實的 ~/.codex 等。
"""

from __future__ import annotations

import json
import re
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "legacy_install"

# ---- LEGACY_: names an earlier release installed ----
LEGACY_GATE = "hooks/pilotfish_autoroute_gate.py"
LEGACY_STATE_SUFFIX = ".pilotfish-install-state.json"
LEGACY_MARKER_BEGIN = "<!-- pilotfish-codex:begin -->"
LEGACY_MARKER_END = "<!-- pilotfish-codex:end -->"
LEGACY_CACHE = "plugins/cache/pilotfish-codex/pilotfish-jev-router/0.1.0"
LEGACY_CACHE_ROOT = "plugins/cache/pilotfish-codex"
LEGACY_JEV_DIR = "pilotfish-jev"
LEGACY_TABLES = (
    "[marketplaces.pilotfish-codex]",
    '[plugins."pilotfish-codex@pilotfish-codex"]',
    '[plugins."pilotfish-jev-router@pilotfish-codex"]',
)
LEGACY_MARKETPLACE_TOML = """
[marketplaces.pilotfish-codex]
last_updated = "2026-10-01T00:00:00Z"
source_type = "local"
source = "{source}"

[plugins."pilotfish-codex@pilotfish-codex"]
enabled = true

[plugins."pilotfish-jev-router@pilotfish-codex"]
enabled = true
"""
LEGACY_GROK_RULES = "rules/pilotfish-grok.md"
LEGACY_GROK_HOOKS_JSON = "hooks/pilotfish-grok.json"
LEGACY_GROK_HOOK_DIR = "hooks/pilotfish-grok"
LEGACY_GROK_UPSTREAM_MARKER = "<!-- pilotfish-grok v1.0.6 -->"
LEGACY_GROK_MARKER_RE = r"<!-- pilotfish-grok v\S+ -->"
LEGACY_OPENCODE_PLUGIN = "plugins/pilotfish-opencode.js"
LEGACY_OPENCODE_DIR = "pilotfish"
LEGACY_AGY_SKILL = "pilotfish-orchestration"
LEGACY_NAME_TOKENS = ("pilotfish", "Pilotfish", "PILOTFISH")

FAKE_CODEX = """#!/bin/sh
if [ "$1" = "--version" ]; then
  echo "codex-cli 0.150.0"
  exit 0
fi
exit 1
"""
FAKE_BUN = """#!/bin/sh
if [ "$1" = "build" ]; then
  out=
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--outfile" ]; then out=$2; fi
    shift
  done
  printf '%s\\n' "// shoal bundle" > "$out"
fi
exit 0
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(repo),
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def worktree_repo(dst: Path) -> Path:
    """Commit the parts of the working tree an installer reads into a temp git repo.

    Tests must not depend on what HEAD of the real repository holds, so every sync and
    install test builds its source from the files under test.
    """
    dst.mkdir(parents=True)
    ignore = shutil.ignore_patterns("node_modules", "__pycache__")
    for rel in (
        "install",
        "templates",
        "hooks",
        "plugin",
        "core",
        "hosts/grok/dist",
        "hosts/agy/dist",
        "hosts/opencode",
    ):
        shutil.copytree(ROOT / rel, dst / rel, ignore=ignore)
    for rel in ("hosts/grok/VERSION", "hosts/agy/VERSION", ".gitignore"):
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst / rel)
    git(dst, "init", "-q")
    git(dst, "add", "--all")
    git(dst, "commit", "-q", "-m", "worktree snapshot")
    return dst


def fake_bin(directory: Path, **scripts: str) -> Path:
    """A PATH directory holding fake `codex` and/or `bun` executables."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in scripts.items():
        target = directory / name
        target.write_text(body)
        target.chmod(0o755)
    return directory


def preseed_codex(
    home: Path, plugin_root: Path | None = None, *, marketplace: bool = False
) -> None:
    """A Codex home as the base commit's installer left it (plus user content around it)."""
    codex = FIXTURES / "codex"
    for rel in (
        "AGENTS.md",
        "config.toml",
        "hooks.json",
        LEGACY_GATE,
        "hooks/shoal_guard.py",
    ):
        target = home / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(codex / rel, target)
    (home / "agents").mkdir(exist_ok=True)
    for template in (ROOT / "templates" / "agents").glob("*.toml"):
        shutil.copy2(template, home / "agents" / template.name)
    for rel in (LEGACY_GATE, "hooks/shoal_guard.py"):
        (home / rel).chmod(0o600)
    state = home.with_name(f"{home.name}{LEGACY_STATE_SUFFIX}")
    shutil.copy2(codex / "state.json", state)
    if marketplace:
        assert plugin_root is not None
        config = home / "config.toml"
        config.write_text(
            config.read_text() + LEGACY_MARKETPLACE_TOML.format(source=plugin_root)
        )
        cache = home / LEGACY_CACHE
        cache.mkdir(parents=True)
        (cache / "plugin.json").write_text("{}\n")
        jev = home / LEGACY_JEV_DIR
        jev.mkdir()
        (jev / "config.json").write_text('{"mode": "shadow"}\n')


def preseed_grok(home: Path, *, shoal_build: bool = True) -> None:
    """A Grok home with the base commit's rules and hooks (the upstream marker when shoal_build is False)."""
    grok = FIXTURES / "grok"
    for rel in (LEGACY_GROK_RULES, LEGACY_GROK_HOOKS_JSON):
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(grok / rel, home / rel)
    shutil.copytree(grok / LEGACY_GROK_HOOK_DIR, home / LEGACY_GROK_HOOK_DIR)
    for script in (home / LEGACY_GROK_HOOK_DIR).glob("*.py"):
        script.chmod(0o755)
    if not shoal_build:
        rules = home / LEGACY_GROK_RULES
        text = rules.read_text()
        import re

        rules.write_text(
            re.sub(r"<!-- pilotfish-grok v\S+ -->", LEGACY_GROK_UPSTREAM_MARKER, text)
        )
        (home / LEGACY_GROK_HOOK_DIR / "shoal_guard.py").unlink()


def preseed_opencode(config: Path, state_root: Path) -> Path:
    """An OpenCode global install made by the base commit's install_global.sh; returns the manifest path."""
    shutil.copytree(FIXTURES / "opencode" / "config", config, dirs_exist_ok=True)
    manifest = state_root / "shoal" / "opencode-global" / "install.manifest"
    manifest.parent.mkdir(parents=True)
    text = (
        (FIXTURES / "opencode" / "install.manifest")
        .read_text()
        .replace("__CONFIG__", str(config.resolve()))
    )
    manifest.write_text(text)
    (manifest.parent / "backups" / "20261001-000000").mkdir(parents=True)
    return manifest


def tree(root: Path) -> dict[str, tuple[bytes, int]]:
    """{relative path: (bytes, mode)} for every regular file and symlink target text under root."""
    out: dict[str, tuple[bytes, int]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            out[rel] = (("-> " + str(path.readlink())).encode(), 0)
        elif path.is_file():
            out[rel] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
    return out


def legacy_names_in(root: Path) -> list[str]:
    """Relative paths under root whose name or text still holds a legacy name (installer backups hold the old bytes, so they are skipped)."""
    found = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if ".pre-shoal-" in rel or ".shoal-codex-" in rel or "/backups/" in f"/{rel}":
            continue
        if any(token in rel for token in LEGACY_NAME_TOKENS):
            found.append(rel)
        elif path.is_file() and not path.is_symlink():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if any(token in text for token in LEGACY_NAME_TOKENS):
                found.append(rel)
    return found


def hooks_commands(hooks_json: Path) -> dict[str, list[str]]:
    """{event: [command, ...]} of every handler in a hooks.json, in order."""
    document = json.loads(hooks_json.read_text())
    return {
        event: [h["command"] for group in groups for h in group["hooks"]]
        for event, groups in document["hooks"].items()
    }
