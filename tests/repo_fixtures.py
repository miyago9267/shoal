"""測試共用：把工作樹中 installer 會讀的部分 commit 成 temp git repo。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
        "tools",
        "plugins/codex",
        "plugins/jev-router",
        ".agents",
        "core",
        "prompts",
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
