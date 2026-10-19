"""role 改名後，tools/sync_global.py 與 tools/install_grok.py 對舊名安裝檔案的處理。

mech-executor -> applier、plan-verifier -> plan-critic（docs/specs/delegation-default/RENAME.md）。
舊名只在本檔的 LEGACY_ROLE_NAMES；home 與 repo 一律是 temp 目錄。
規則：只移除確認是 shoal 安裝的檔案（位元組等於歷史版本，或 symlink 仍指向本 repo 的 dist），
dry-run 只回報，--apply 才移除；其餘不動。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import repo_fixtures as lf  # noqa: E402
from test_sync_global import POSIX, Base, git, snapshot  # noqa: E402

LEGACY_ROLE_NAMES = ("mech-executor", "plan-verifier")
OLD_MECH, OLD_PLAN = LEGACY_ROLE_NAMES


def rename_in_history(repo: Path, old: str, new: str, rel: str) -> None:
    """repo 的歷史裡有 rel 的舊名版本，HEAD 只剩新名（模擬發行過舊名的 repo 改名後的樣子）。"""
    (repo / rel.format(old)).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel.format(old)).write_text("released v1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"release {old}")
    git(repo, "mv", rel.format(old), rel.format(new))
    git(repo, "commit", "-q", "-m", f"rename {old}")


@unittest.skipUnless(POSIX, "needs git")
class CodexRenamedRoleTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.repo = self.tmp / "repo"
        (self.repo / "hooks").mkdir(parents=True)
        (self.repo / "templates" / "agents").mkdir(parents=True)
        git(self.repo, "init", "-q")
        (self.repo / "hooks" / "shoal_guard.py").write_text("# guard v1\n")
        rename_in_history(self.repo, OLD_MECH, "applier", "templates/agents/{}.toml")
        rename_in_history(self.repo, OLD_PLAN, "plan-critic", "templates/agents/{}.toml")
        self.agents = self.codex / "agents"
        self.agents.mkdir()
        for name in ("applier", "plan-critic"):
            (self.agents / f"{name}.toml").write_text("released v1\n")
        self.codex_sync("--apply")  # 先把 hook 等其他項目同步掉，之後只看 role 改名

    def codex_sync(self, *extra: str) -> str:
        code, lines = self.sync("--host", "codex", "--repo", str(self.repo), *extra)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        return lines[0]

    def test_dry_run_reports_and_apply_removes_released_old_roles(self) -> None:
        for old in LEGACY_ROLE_NAMES:
            (self.agents / f"{old}.toml").write_text("released v1\n")
        before = snapshot(self.codex, self.state, self.data)
        line = self.codex_sync()
        self.assertIn(f"renamed roles removed: {OLD_MECH}.toml, {OLD_PLAN}.toml", line)
        self.assertTrue(line.endswith("[dry-run]"), line)
        self.assertEqual(snapshot(self.codex, self.state, self.data), before)

        self.assertIn("renamed roles removed", self.codex_sync("--apply"))
        self.assertEqual(
            sorted(p.name for p in self.agents.iterdir()),
            ["applier.toml", "plan-critic.toml"],
        )
        self.assertEqual(self.codex_sync("--apply"), "codex: up-to-date")

    def test_user_edited_or_symlinked_old_role_is_drift_and_untouched(self) -> None:
        mine = self.agents / f"{OLD_MECH}.toml"
        mine.write_text("my own edits\n")
        elsewhere = self.tmp / "elsewhere.toml"
        elsewhere.write_text("released v1\n")
        (self.agents / f"{OLD_PLAN}.toml").symlink_to(elsewhere)
        line = self.codex_sync("--apply")
        self.assertEqual(
            line, f"codex: up-to-date (drift: {OLD_MECH}.toml, {OLD_PLAN}.toml)"
        )
        self.assertEqual(mine.read_text(), "my own edits\n")
        self.assertTrue((self.agents / f"{OLD_PLAN}.toml").is_symlink())
        self.assertEqual(elsewhere.read_text(), "released v1\n")


@unittest.skipUnless(POSIX, "needs git")
class GrokRenamedRoleTests(Base):
    OLD_FILES = tuple(
        f"{top}/{old}.{ext}"
        for old in LEGACY_ROLE_NAMES
        for top, ext in (("agents", "md"), ("roles", "toml"))
    )

    def setUp(self) -> None:
        super().setUp()
        self.repo = lf.worktree_repo(self.tmp / "repo")
        dist = self.repo / "hosts" / "grok" / "dist"
        for rel in self.OLD_FILES:
            (dist / rel).write_text(f"released {rel}\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "release old role names")
        git(self.repo, "rm", "-q", *(f"hosts/grok/dist/{rel}" for rel in self.OLD_FILES))
        git(self.repo, "commit", "-q", "-m", "rename roles")

    def seed(self) -> None:
        for rel in self.OLD_FILES:
            target = self.grok / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"released {rel}\n")

    def test_released_old_role_files_are_removed_only_with_apply(self) -> None:
        self.seed()
        before = snapshot(self.grok)
        line = self.sync("--host", "grok")[1][0]
        self.assertTrue(line.startswith("grok: updated (legacy migration: remove "), line)
        self.assertTrue(line.endswith("[dry-run]"), line)
        for rel in self.OLD_FILES:
            self.assertIn(rel, line)
        self.assertEqual(snapshot(self.grok), before)

        self.sync("--host", "grok", "--apply")
        for rel in self.OLD_FILES:
            self.assertFalse((self.grok / rel).exists(), rel)
        self.assertEqual(self.sync("--host", "grok", "--apply")[1], ["grok: up-to-date"])

    def test_edited_old_role_file_is_kept(self) -> None:
        self.seed()
        edited = self.grok / self.OLD_FILES[0]
        edited.write_text("my own edits\n")
        self.sync("--host", "grok", "--apply")
        self.assertEqual(edited.read_text(), "my own edits\n")
        for rel in self.OLD_FILES[1:]:
            self.assertFalse((self.grok / rel).exists(), rel)


@unittest.skipUnless(POSIX, "needs git")
class AgyRenamedRoleTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.repo = lf.worktree_repo(self.tmp / "repo")
        config = self.home / ".gemini" / "config"
        for kind in ("agents", "skills"):
            (config / kind).mkdir(parents=True)
            for src in (self.repo / "hosts" / "agy" / "dist" / kind).iterdir():
                (config / kind / src.name).symlink_to(src)
        self.agents = config / "agents"
        self.dist_agents = self.repo / "hosts" / "agy" / "dist" / "agents"

    def test_dangling_link_into_this_repo_is_removed_only_with_apply(self) -> None:
        for old in LEGACY_ROLE_NAMES:
            (self.agents / old).symlink_to(self.dist_agents / old)  # 目標已不存在
        line = self.sync("--host", "agy")[1][0]
        self.assertIn(f"legacy migration: remove agents/{OLD_MECH}, agents/{OLD_PLAN}", line)
        self.assertTrue(line.endswith("[dry-run]"), line)
        self.assertTrue((self.agents / OLD_MECH).is_symlink())

        self.sync("--host", "agy", "--apply")
        for old in LEGACY_ROLE_NAMES:
            self.assertFalse((self.agents / old).is_symlink(), old)
        self.assertIn("symlinks ok", self.sync("--host", "agy", "--apply")[1][0])

    def test_old_link_is_replaced_by_new_name_link_when_missing(self) -> None:
        """只掛了舊名的機器（2026-10 實機）：移除舊名後補上新名，不留下 'agents/<新名> 不是 symlink'。"""
        for old, new in zip(LEGACY_ROLE_NAMES, ("applier", "plan-critic")):
            (self.agents / new).unlink()
            (self.agents / old).symlink_to(self.dist_agents / old)  # 目標已不存在
        before = snapshot(self.home)
        line = self.sync("--host", "agy")[1][0]
        self.assertIn("relink agents/applier, agents/plan-critic", line)
        self.assertNotIn("symlink drift", line)  # dry-run 即將補上的不算 drift
        self.assertEqual(snapshot(self.home), before)

        self.sync("--host", "agy", "--apply")
        for old, new in zip(LEGACY_ROLE_NAMES, ("applier", "plan-critic")):
            self.assertFalse((self.agents / old).is_symlink(), old)
            self.assertEqual(
                (self.agents / new).resolve(), (self.dist_agents / new).resolve()
            )
        self.assertIn("symlinks ok", self.sync("--host", "agy", "--apply")[1][0])

    def test_existing_new_name_entry_is_not_overwritten(self) -> None:
        (self.agents / "applier").unlink()
        (self.agents / "applier").write_text("mine\n")
        (self.agents / OLD_MECH).symlink_to(self.dist_agents / OLD_MECH)
        self.sync("--host", "agy", "--apply")
        self.assertFalse((self.agents / OLD_MECH).is_symlink())
        self.assertEqual((self.agents / "applier").read_text(), "mine\n")

    def test_link_pointing_elsewhere_or_real_file_is_untouched(self) -> None:
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        (self.agents / OLD_MECH).symlink_to(elsewhere)
        (self.agents / OLD_PLAN).write_text("not a link\n")
        self.sync("--host", "agy", "--apply")
        self.assertTrue((self.agents / OLD_MECH).is_symlink())
        self.assertEqual((self.agents / OLD_PLAN).read_text(), "not a link\n")


if __name__ == "__main__":
    unittest.main()
