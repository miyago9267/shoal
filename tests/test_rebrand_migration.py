"""shoal 2.0.0 的遷移測試（docs/specs/shoal-rebrand N5、N8，SPEC R1 驗收）。

每個 host 先預置「base commit 21d5986 的 installer 實際裝出來的」舊名安裝
（tests/fixtures/legacy_install/，舊名只在 tests/legacy_fixtures.py 的 LEGACY_ 常數），再對
temp git repo（由工作樹建立，不看真實 repo 的 HEAD）跑 tools/sync_global.py：

  dry-run 的計畫只含「移除舊名＋安裝新名」且不寫入 -> --apply -> 只剩新名、非 shoal 檔案不動
  -> 再跑一次 up-to-date。

home、CODEX_HOME、GROK_HOME、XDG_*、OpenCode config dir 全是 temp 目錄；測試不讀寫真實的
~/.codex、~/.grok、~/.gemini、~/.config/opencode、~/.local 或 ~/dotfile。codex 與 bun 是 PATH 上的假執行檔。
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "install"))
sys.path.insert(0, str(ROOT / "tests"))
import hook_registration as hr  # noqa: E402
import install as installer  # noqa: E402
import install_grok  # noqa: E402
import install_hooks  # noqa: E402
import legacy_codex  # noqa: E402
import legacy_fixtures as lf  # noqa: E402
import sync_global  # noqa: E402

POSIX = sys.platform != "win32" and all(shutil.which(t) for t in ("sh", "git", "tar"))


class MigrationCase(unittest.TestCase):
    """共用：temp 目錄、由工作樹建的 repo、sync 呼叫。"""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="shoal-migrate-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = lf.worktree_repo(self.tmp / "repo")
        self.user = self.tmp / "user"
        self.user.mkdir()
        self.codex = self.tmp / "codex"
        self.codex.mkdir()
        self.grok = self.tmp / "grok"
        self.grok.mkdir()
        self.data, self.state = self.tmp / "data", self.tmp / "state"
        self.bin = lf.fake_bin(self.tmp / "bin", codex=lf.FAKE_CODEX, bun=lf.FAKE_BUN)

    def env(self, **extra: str) -> dict[str, str]:
        env = dict(os.environ)
        for key in (
            "OPENCODE_CONFIG_DIR",
            "OPENCODE_HARNESS_PLUGIN",
            "GROK_HOME",
            "CODEX_HOME",
        ):
            env.pop(key, None)
        env.update(
            HOME=str(self.user),
            CODEX_HOME=str(self.codex),
            GROK_HOME=str(self.grok),
            XDG_DATA_HOME=str(self.data),
            XDG_STATE_HOME=str(self.state),
            PATH=f"{self.bin}{os.pathsep}{env['PATH']}",
        )
        env.update(extra)
        return env

    def sync(
        self, *args: str, env: dict[str, str] | None = None
    ) -> tuple[int, list[str]]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sync_global.main(
                [*args, "--repo", str(self.repo)], env or self.env()
            )
        return code, buf.getvalue().splitlines()

    def one(self, *args: str, env: dict[str, str] | None = None) -> str:
        code, lines = self.sync(*args, env=env)
        self.assertEqual(code, 0, lines)
        self.assertEqual(len(lines), 1, lines)
        return lines[0]


@unittest.skipUnless(POSIX, "needs git and sh")
class CodexMigrationTests(MigrationCase):
    def setUp(self) -> None:
        super().setUp()
        lf.preseed_codex(self.codex, self.repo / "plugin", marketplace=True)
        self.legacy_state = self.codex.with_name(
            f"{self.codex.name}{lf.LEGACY_STATE_SUFFIX}"
        )
        self.new_state = self.codex.with_name(
            f"{self.codex.name}.shoal-install-state.json"
        )
        # 使用者自己的檔案：遷移不能動
        (self.codex / "hooks" / "notify.py").write_text("# user hook\n")
        (self.codex / "prompts").mkdir()
        (self.codex / "prompts" / "mine.md").write_text("# user prompt\n")
        self.user_files = {
            "hooks/notify.py": b"# user hook\n",
            "prompts/mine.md": b"# user prompt\n",
        }

    def sync_codex(self, *extra: str) -> str:
        return self.one("--host", "codex", *extra)

    def test_dry_run_lists_only_remove_old_and_install_new(self) -> None:
        before = lf.tree(self.tmp / "codex"), self.legacy_state.read_bytes()
        line = self.sync_codex()
        self.assertTrue(
            line.startswith("codex: updated (legacy migration: remove "), line
        )
        self.assertTrue(line.endswith("[dry-run]"), line)
        self.assertIn("remove legacy hooks.json groups: ", line)
        self.assertIn(f"remove {legacy_codex.LEGACY_GATE_RELATIVE}", line)
        self.assertIn("rename config.toml tables", line)
        self.assertIn(
            "install shoal_autoroute_gate.py, shoal-autoroute-v1 and shoal-guard-v1",
            line,
        )
        self.assertEqual(
            (lf.tree(self.tmp / "codex"), self.legacy_state.read_bytes()), before
        )
        self.assertFalse(self.new_state.exists())

    def test_apply_leaves_only_new_names_and_second_run_is_up_to_date(self) -> None:
        line = self.sync_codex("--apply")
        self.assertTrue(line.startswith("codex: updated (legacy migration:"), line)

        # hooks.json：只剩 shoal-autoroute-v1 與 shoal-guard-v1 兩個 projection，使用者的 Stop group 還在
        document = json.loads((self.codex / "hooks.json").read_text())
        hr.validate_owned_projection(document, hr.CURRENT_PROJECTION_ID)
        hr.validate_owned_projection(document, hr.GUARD_PROJECTION_ID)
        self.assertEqual(hr.legacy_autoroute_locations(document), [])
        commands = [
            c
            for cs in lf.hooks_commands(self.codex / "hooks.json").values()
            for c in cs
        ]
        self.assertEqual(
            sum("shoal_autoroute_gate.py" in c for c in commands), 2
        )  # UserPromptSubmit、Stop
        self.assertEqual(
            sum("shoal_guard.py" in c for c in commands), 2
        )  # UserPromptSubmit、PreToolUse
        self.assertEqual(sum("notify.py" in c for c in commands), 1)
        self.assertEqual(len(commands), 5)
        # gate 腳本與 guard 腳本是 HEAD 的位元組；舊 gate 不在了
        self.assertEqual(
            (self.codex / "hooks" / "shoal_autoroute_gate.py").read_bytes(),
            (self.repo / "hooks" / "shoal_autoroute_gate.py").read_bytes(),
        )
        self.assertEqual(
            (self.codex / "hooks" / "shoal_guard.py").read_bytes(),
            (self.repo / "hooks" / "shoal_guard.py").read_bytes(),
        )
        self.assertFalse((self.codex / lf.LEGACY_GATE).exists())
        # AGENTS.md：只有新 marker，marker 外的使用者內容不變
        policy = (self.codex / "AGENTS.md").read_text()
        self.assertEqual(policy.count(installer.MARKER_BEGIN), 1)
        self.assertEqual(policy.count(installer.MARKER_END), 1)
        self.assertNotIn(lf.LEGACY_MARKER_BEGIN, policy)
        self.assertNotIn(lf.LEGACY_MARKER_END, policy)
        self.assertTrue(policy.startswith("# My Codex rules\n\nkeep-before = true\n\n"))
        # config.toml：使用者的設定不動，marketplace 與 plugin table 改成新名
        config = (self.codex / "config.toml").read_text()
        self.assertIn('model_provider = "user-provider"', config)
        self.assertIn('[projects."/work/example"]', config)
        self.assertIn("[marketplaces.shoal-codex]", config)
        self.assertIn('[plugins."shoal-codex@shoal-codex"]', config)
        self.assertIn('[plugins."shoal-jev-router@shoal-codex"]', config)
        self.assertFalse(any(header in config for header in lf.LEGACY_TABLES))
        # cache 移除、jev 資料目錄改名且內容保留
        self.assertFalse((self.codex / lf.LEGACY_CACHE_ROOT).exists())
        self.assertEqual(
            (self.codex / "shoal-jev" / "config.json").read_text(),
            '{"mode": "shadow"}\n',
        )
        self.assertFalse((self.codex / lf.LEGACY_JEV_DIR).exists())
        # install state：新檔 committed，舊檔封存成 .pre-shoal-<ts>
        state = json.loads(self.new_state.read_text())
        self.assertEqual(state["status"], "committed")
        self.assertEqual(state["plugin"]["name"], "shoal-codex")
        self.assertEqual(
            state["hook_registration"]["projection_id"], hr.CURRENT_PROJECTION_ID
        )
        self.assertIn("shoal_policy", state["policy_ownership"])
        self.assertFalse(self.legacy_state.exists())
        archived = list(self.tmp.glob(f"codex{lf.LEGACY_STATE_SUFFIX}.pre-shoal-*"))
        self.assertEqual(len(archived), 1)
        # 使用者的檔案原樣
        for rel, data in self.user_files.items():
            self.assertEqual((self.codex / rel).read_bytes(), data, rel)
        # 只剩新名（備份檔不算）
        self.assertEqual(lf.legacy_names_in(self.codex), [])
        # 再跑一次：沒有變更
        before = lf.tree(self.codex), self.new_state.read_bytes()
        self.assertEqual(self.sync_codex("--apply"), "codex: up-to-date")
        self.assertEqual((lf.tree(self.codex), self.new_state.read_bytes()), before)

    def test_user_modified_gate_is_kept_as_backup_and_unregistered(self) -> None:
        gate = self.codex / lf.LEGACY_GATE
        modified = gate.read_bytes() + b"\n# experiment: gpt-6.1-sol\n"
        gate.write_bytes(modified)
        line = self.sync_codex()
        self.assertIn("unregister modified", line)
        self.assertIn("keep it as a .pre-shoal-<ts> backup", line)
        self.sync_codex("--apply")
        self.assertFalse(gate.exists())
        backups = list((self.codex / "hooks").glob("*.pre-shoal-*"))
        self.assertEqual([b.read_bytes() for b in backups], [modified])
        self.assertTrue(
            backups[0].name.startswith(Path(lf.LEGACY_GATE).name + ".pre-shoal-")
        )
        commands = [
            c
            for cs in lf.hooks_commands(self.codex / "hooks.json").values()
            for c in cs
        ]
        self.assertFalse(any(Path(lf.LEGACY_GATE).name in c for c in commands))
        self.assertEqual(sum("shoal_autoroute_gate.py" in c for c in commands), 2)
        self.assertEqual(self.sync_codex("--apply"), "codex: up-to-date")

    def test_tables_that_do_not_point_at_this_repo_are_left_alone(self) -> None:
        config = self.codex / "config.toml"
        elsewhere = self.tmp / "elsewhere" / "plugin"
        text = (
            lf.FIXTURES / "codex" / "config.toml"
        ).read_text() + lf.LEGACY_MARKETPLACE_TOML.format(source=elsewhere)
        config.write_text(text)
        cache = self.codex / lf.LEGACY_CACHE
        self.assertTrue(cache.is_dir())  # preseed 已建立
        line = self.sync_codex()
        self.assertIn(
            "leave config.toml tables that do not point at this repository", line
        )
        self.assertNotIn("rename config.toml tables", line)
        self.assertNotIn("stale plugin cache", line)
        self.sync_codex("--apply")
        after = config.read_text()
        for header in lf.LEGACY_TABLES:
            self.assertIn(header, after)
        self.assertNotIn("[marketplaces.shoal-codex]", after)
        self.assertTrue(cache.is_dir())

    def test_pending_legacy_transaction_aborts_without_writing(self) -> None:
        pending = self.legacy_state.with_suffix(".json.pending")
        pending.write_text('{"status": "aborted"}\n')
        before = lf.tree(self.codex)
        line = self.sync_codex("--apply")
        self.assertTrue(
            line.startswith(
                "codex: failed (legacy migration: legacy install transaction is pending"
            ),
            line,
        )
        self.assertEqual(lf.tree(self.codex), before)
        self.assertTrue(self.legacy_state.exists())

    def test_install_py_migrates_before_it_installs(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(
                installer.install(
                    source_root=self.repo,
                    codex_home=self.codex,
                    dry_run=True,
                    check_codex=False,
                ),
                0,
            )
        self.assertIn("legacy: would remove legacy hooks.json groups", out.getvalue())
        self.assertFalse(self.new_state.exists())
        self.assertTrue((self.codex / lf.LEGACY_GATE).exists())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                installer.install(
                    source_root=self.repo,
                    codex_home=self.codex,
                    dry_run=False,
                    check_codex=False,
                ),
                0,
            )
        self.assertTrue(self.new_state.exists())
        self.assertFalse((self.codex / lf.LEGACY_GATE).exists())
        self.assertEqual(lf.legacy_names_in(self.codex), [])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                installer.install(
                    source_root=self.repo,
                    codex_home=self.codex,
                    dry_run=False,
                    check_codex=False,
                ),
                0,
            )

    def test_proven_guard_script_may_be_upgraded_but_an_edited_one_may_not(
        self,
    ) -> None:
        guard = self.codex / "hooks" / "shoal_guard.py"
        guard.write_bytes(guard.read_bytes() + b"# edited by hand\n")
        with (
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(
                installer.InstallAbort, "installed_hook_drift: guard script"
            ),
        ):
            installer.install(
                source_root=self.repo,
                codex_home=self.codex,
                dry_run=False,
                check_codex=False,
            )

    def test_install_hooks_reminds_but_does_not_touch_legacy_groups(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = install_hooks.main(
                [
                    "--host",
                    "codex",
                    "--home",
                    str(self.codex),
                    "--repo",
                    str(self.repo),
                ],
                env=self.env(),
            )
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("2.0.0 之前的 autoroute 註冊", out.getvalue())
        document = json.loads((self.codex / "hooks.json").read_text())
        self.assertEqual(len(hr.legacy_autoroute_locations(document)), 2)  # UserPromptSubmit、Stop

    def test_legacy_install_state_still_blocks_a_direct_guard_removal(self) -> None:
        self.assertTrue(install_hooks.install_state_owns_guard(self.codex))
        self.legacy_state.unlink()
        self.assertFalse(install_hooks.install_state_owns_guard(self.codex))


class LegacyRegistrationTests(unittest.TestCase):
    def test_legacy_projection_digests_are_pinned(self) -> None:
        for projection_id, digest in hr.LEGACY_PROJECTION_DIGESTS.items():
            self.assertEqual(
                hr.legacy_projection_digest(projection_id), digest, projection_id
            )
        self.assertNotIn(hr.CURRENT_PROJECTION_ID, hr.LEGACY_PROJECTION_DIGESTS)
        self.assertNotIn(hr.CURRENT_PROJECTION_ID, hr.LEGACY_TRUSTED_PROJECTIONS)
        # 新 projection 是獨立的：digest 與兩個舊的都不同
        self.assertNotIn(
            hr.projection_digest(hr.CURRENT_PROJECTION_ID),
            hr.LEGACY_PROJECTION_DIGESTS.values(),
        )

    def test_exact_legacy_groups_are_removed_and_foreign_groups_stay(self) -> None:
        foreign = {"hooks": [{"type": "command", "command": "/user/hook.py"}]}
        near_miss = json.loads(json.dumps(hr.LEGACY_GROUP_V2))
        near_miss["hooks"][0]["timeout"] = 11
        for group in (hr.LEGACY_GROUP_V1, hr.LEGACY_GROUP_V2):
            document = {
                "hooks": {
                    "Stop": [foreign, group],
                    "UserPromptSubmit": [group, near_miss],
                }
            }
            cleaned, ids = hr.remove_legacy_autoroute(document)
            self.assertEqual(
                cleaned, {"hooks": {"Stop": [foreign], "UserPromptSubmit": [near_miss]}}
            )
            self.assertEqual(len(ids), 1)

    def test_unmigrated_legacy_group_is_a_collision_not_a_silent_duplicate(
        self,
    ) -> None:
        source = (ROOT / "templates" / "hooks.json").read_bytes()
        document = json.dumps({"hooks": {"Stop": [hr.LEGACY_GROUP_V2]}}).encode()
        with self.assertRaisesRegex(hr.HookRegistrationError, "canonical"):
            hr.merge_registration(document, source, owned_projection_id=None)


@unittest.skipUnless(POSIX, "needs git")
class GrokMigrationTests(MigrationCase):
    def setUp(self) -> None:
        super().setUp()
        (self.grok / "config.toml").write_text('[models]\ndefault = "grok-build"\n')
        (self.grok / "hooks").mkdir()
        (self.grok / "hooks" / "mine.json").write_text("{}\n")
        lf.preseed_grok(self.grok)
        (self.grok / lf.LEGACY_GROK_HOOK_DIR / "notes.txt").write_text("keep me\n")
        self.user_files = {
            "config.toml": b'[models]\ndefault = "grok-build"\n',
            "hooks/mine.json": b"{}\n",
            f"{lf.LEGACY_GROK_HOOK_DIR}/notes.txt": b"keep me\n",
        }

    def test_dry_run_apply_and_rerun(self) -> None:
        before = lf.tree(self.grok)
        line = self.one("--host", "grok")
        self.assertTrue(
            line.startswith("grok: updated (legacy migration: remove "), line
        )
        self.assertTrue(line.endswith("[dry-run]"), line)
        for rel in (
            lf.LEGACY_GROK_RULES,
            lf.LEGACY_GROK_HOOKS_JSON,
            f"{lf.LEGACY_GROK_HOOK_DIR}/shoal_guard.py",
        ):
            self.assertIn(rel, line)
        self.assertIn("; install ", line)
        self.assertIn("rules/shoal-grok.md", line)
        self.assertEqual(lf.tree(self.grok), before)

        self.one("--host", "grok", "--apply")
        self.assertFalse((self.grok / lf.LEGACY_GROK_RULES).exists())
        self.assertFalse((self.grok / lf.LEGACY_GROK_HOOKS_JSON).exists())
        self.assertEqual(
            sorted(p.name for p in (self.grok / lf.LEGACY_GROK_HOOK_DIR).iterdir()),
            ["notes.txt"],
        )
        self.assertTrue((self.grok / "rules" / "shoal-grok.md").is_file())
        self.assertTrue((self.grok / "hooks" / "shoal-grok.json").is_file())
        self.assertTrue(
            (self.grok / "hooks" / "shoal-grok" / "shoal_guard.py").is_file()
        )
        for rel, data in self.user_files.items():
            self.assertEqual((self.grok / rel).read_bytes(), data, rel)
        leftovers = [
            r
            for r in lf.legacy_names_in(self.grok)
            if r != lf.LEGACY_GROK_HOOK_DIR and not r.startswith(lf.LEGACY_GROK_HOOK_DIR + "/")
        ]
        self.assertEqual(leftovers, [])
        # 備份有舊檔，可還原
        backups = sorted((self.grok / "backups").glob("shoal-*"))
        self.assertEqual(len(backups), 1)
        manifest = json.loads((backups[0] / "manifest.json").read_text())
        self.assertIn(lf.LEGACY_GROK_RULES, manifest["saved"])
        self.assertEqual(self.one("--host", "grok", "--apply"), "grok: up-to-date")

    def test_old_files_without_a_shoal_mark_are_not_touched(self) -> None:
        shutil.rmtree(self.grok / "rules")
        shutil.rmtree(self.grok / "hooks")
        (self.grok / "hooks").mkdir()
        lf.preseed_grok(self.grok, shoal_build=False)
        before = {
            rel: data
            for rel, data in lf.tree(self.grok).items()
            if rel.startswith(
                (
                    "rules/" + Path(lf.LEGACY_GROK_RULES).name,
                    lf.LEGACY_GROK_HOOKS_JSON,
                    lf.LEGACY_GROK_HOOK_DIR,
                )
            )
        }
        line = self.one("--host", "grok", "--apply")
        self.assertNotIn("legacy migration", line)
        after = lf.tree(self.grok)
        for rel, data in before.items():
            self.assertEqual(after[rel], data, rel)

    def test_find_legacy_reports_foreign_files_without_removing_them(self) -> None:
        owned, foreign = install_grok.find_legacy(self.grok)
        self.assertEqual(
            sorted(owned),
            sorted(
                [
                    lf.LEGACY_GROK_RULES,
                    lf.LEGACY_GROK_HOOKS_JSON,
                    *(
                        f"{lf.LEGACY_GROK_HOOK_DIR}/{n}"
                        for n in (
                            "plan_mode_guard.py",
                            "shoal_guard.py",
                            "subagent_stop_gate.py",
                        )
                    ),
                ]
            ),
        )
        self.assertEqual(foreign, [f"{lf.LEGACY_GROK_HOOK_DIR}/notes.txt"])


@unittest.skipUnless(POSIX, "needs git")
class AgyMigrationTests(MigrationCase):
    def setUp(self) -> None:
        super().setUp()
        self.config = self.user / ".gemini" / "config"
        (self.config / "skills").mkdir(parents=True)
        (self.config / "agents").mkdir()
        dist = self.repo / "hosts" / "agy" / "dist"
        for agent in (dist / "agents").iterdir():
            (self.config / "agents" / agent.name).symlink_to(agent)
        self.old_link = self.config / "skills" / lf.LEGACY_AGY_SKILL
        # 舊名的 symlink 指向本 repo 的 hosts/agy/dist（該路徑已不存在，所以是斷的）
        self.old_link.symlink_to(dist / "skills" / lf.LEGACY_AGY_SKILL)

    def test_legacy_skill_symlink_is_relinked(self) -> None:
        line = self.one("--host", "agy")
        self.assertIn(
            f"legacy migration: relink skills/{lf.LEGACY_AGY_SKILL} -> skills/shoal-orchestration",
            line,
        )
        self.assertTrue(line.endswith("[dry-run]"), line)
        self.assertNotIn("symlink drift", line)
        self.assertTrue(self.old_link.is_symlink())

        self.one("--host", "agy", "--apply")
        self.assertFalse(self.old_link.is_symlink())
        new = self.config / "skills" / "shoal-orchestration"
        self.assertEqual(
            new.resolve(),
            (
                self.repo / "hosts" / "agy" / "dist" / "skills" / "shoal-orchestration"
            ).resolve(),
        )
        self.assertEqual(
            sorted(p.name for p in (self.config / "skills").iterdir()),
            ["shoal-orchestration"],
        )
        self.assertEqual(
            self.one("--host", "agy", "--apply"), "agy: up-to-date (symlinks ok)"
        )

    def test_symlink_that_points_elsewhere_is_reported_not_changed(self) -> None:
        self.old_link.unlink()
        elsewhere = self.tmp / "elsewhere" / lf.LEGACY_AGY_SKILL
        elsewhere.mkdir(parents=True)
        self.old_link.symlink_to(elsewhere)
        line = self.one("--host", "agy", "--apply")
        self.assertNotIn("legacy migration", line)
        self.assertIn("不指向本 repo 的 hosts/agy/dist，未動", line)
        self.assertEqual(self.old_link.resolve(), elsewhere.resolve())


@unittest.skipUnless(POSIX, "needs git")
class OpenCodeMigrationTests(MigrationCase):
    def setUp(self) -> None:
        super().setUp()
        self.config = self.tmp / "opencode"
        self.manifest = lf.preseed_opencode(self.config, self.state)
        (self.config / "opencode.json").write_text('{"provider": {}}\n')
        (self.config / "agents" / "my-own.md").write_text("# mine\n")
        self.user_files = {
            "opencode.json": b'{"provider": {}}\n',
            "agents/my-own.md": b"# mine\n",
        }
        self.extra = {"OPENCODE_CONFIG_DIR": str(self.config)}

    def test_old_manifest_is_disabled_then_new_names_are_enabled(self) -> None:
        env = self.env(**self.extra)
        before = lf.tree(self.config), self.manifest.read_bytes()
        line = self.one("--host", "opencode", env=env)
        self.assertTrue(
            line.startswith("opencode: updated (legacy migration: remove "), line
        )
        self.assertTrue(line.endswith("[dry-run]"), line)
        self.assertIn(lf.LEGACY_OPENCODE_PLUGIN, line)
        self.assertIn("; install ", line)
        self.assertIn("plugins/shoal-opencode.js", line)
        self.assertEqual((lf.tree(self.config), self.manifest.read_bytes()), before)

        self.one("--host", "opencode", "--apply", env=env)
        self.assertFalse((self.config / lf.LEGACY_OPENCODE_PLUGIN).exists())
        self.assertFalse((self.config / lf.LEGACY_OPENCODE_DIR).exists())
        self.assertEqual(
            (self.config / "plugins" / "shoal-opencode.js").read_text(),
            "// shoal bundle\n",
        )
        self.assertTrue((self.config / "shoal" / "catalog.json").is_file())
        self.assertTrue((self.config / "shoal" / "routing.json").is_file())
        recorded = [
            ln.split("|")[3]
            for ln in self.manifest.read_text().splitlines()
            if ln.startswith("entry|")
        ]
        self.assertIn("plugins/shoal-opencode.js", recorded)
        self.assertEqual(lf.legacy_names_in(self.config), [])
        for rel, data in self.user_files.items():
            self.assertEqual((self.config / rel).read_bytes(), data, rel)
        self.assertEqual(
            self.one("--host", "opencode", "--apply", env=env), "opencode: up-to-date"
        )

    def test_a_modified_old_plugin_stops_the_migration_without_writing(self) -> None:
        env = self.env(**self.extra)
        plugin = self.config / lf.LEGACY_OPENCODE_PLUGIN
        plugin.write_text("// user edit\n")
        before = lf.tree(self.config), self.manifest.read_bytes()
        code, lines = self.sync("--host", "opencode", "--apply", "--strict", env=env)
        self.assertEqual(code, 1)
        self.assertTrue(
            lines[0].startswith("opencode: failed (install.sh --disable"), lines
        )
        self.assertEqual((lf.tree(self.config), self.manifest.read_bytes()), before)

    def test_install_sh_enable_migrates_an_old_global_manifest_by_itself(self) -> None:
        script = self.repo / sync_global.OPENCODE_INSTALL
        done = subprocess.run(
            [
                "sh",
                str(script),
                "--global",
                "--config-dir",
                str(self.config),
                "--enable",
            ],
            env=self.env(**self.extra),
            capture_output=True,
            text=True,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("pre-2.0.0 install manifest", done.stderr)
        self.assertFalse((self.config / lf.LEGACY_OPENCODE_PLUGIN).exists())
        self.assertTrue((self.config / "plugins" / "shoal-opencode.js").is_file())
        self.assertEqual(lf.legacy_names_in(self.config), [])

    def test_target_install_disables_an_old_project_manifest_first(self) -> None:
        project = self.tmp / "project"
        control = project / ".opencode" / lf.LEGACY_OPENCODE_DIR
        plugin = project / ".opencode" / lf.LEGACY_OPENCODE_PLUGIN
        control.mkdir(parents=True)
        plugin.parent.mkdir(parents=True)
        plugin.write_text("// old project bundle\n")
        digest = hashlib.sha256(plugin.read_bytes()).hexdigest()
        (control / "install.manifest").write_text(
            f"version|1\nstate|enabled\nbackup|.opencode/{lf.LEGACY_OPENCODE_DIR}/backups/x|\n"
            f"entry|0|{digest}|.opencode/{lf.LEGACY_OPENCODE_PLUGIN}\n"
        )
        script = self.repo / "hosts" / "opencode" / "plugin" / "install" / "install.sh"
        done = subprocess.run(
            ["sh", str(script), "--target", str(project), "--enable"],
            env=self.env(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(plugin.exists())
        self.assertTrue(
            (project / ".opencode" / "plugins" / "shoal-opencode.js").is_file()
        )
        self.assertIn("state|disabled", (control / "install.manifest").read_text())
        self.assertIn(
            "state|enabled",
            (project / ".opencode" / "shoal" / "install.manifest").read_text(),
        )


class LegacyCodexUnitTests(unittest.TestCase):
    def test_nothing_found_in_a_fresh_home(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            self.assertFalse(legacy_codex.detect(home, ROOT / "plugin").found)

    def test_unmatched_legacy_marker_pair_is_rejected_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            (home / "AGENTS.md").write_text(f"{lf.LEGACY_MARKER_BEGIN}\nno end\n")
            findings = legacy_codex.detect(home, None)
            with self.assertRaisesRegex(
                legacy_codex.LegacyMigrationError, "unmatched or multiple"
            ):
                legacy_codex.apply(findings)
            self.assertIn(lf.LEGACY_MARKER_BEGIN, (home / "AGENTS.md").read_text())


if __name__ == "__main__":
    unittest.main()
