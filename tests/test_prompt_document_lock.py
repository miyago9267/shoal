from __future__ import annotations

import json
import sys
import shutil
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "install"))

from validate_prompt_lock import (  # noqa: E402
    PromptLockError,
    check_change_budget,
    load_lock,
    validate_lock,
)


class PromptDocumentLockTests(unittest.TestCase):
    @contextmanager
    def _git_repo_with_current_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = load_lock(ROOT)
            for surface in lock["surfaces"]:
                source = ROOT / surface["path"]
                destination = root / surface["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            manifest = root / "docs" / "specs" / "prompt-document-lock" / "LOCK.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / manifest.relative_to(root), manifest)
            for version_file in {surface["version_file"] for surface in lock["surfaces"]}:
                destination = root / version_file
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / version_file, destination)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "prompt-lock@test.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Prompt Lock Test"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "test: establish prompt lock"], cwd=root, check=True)
            yield root

    def test_current_prompt_surfaces_pass_the_lock(self) -> None:
        report = validate_lock(ROOT, base_ref="HEAD")

        self.assertEqual(report["status"], "ok")
        self.assertGreaterEqual(report["surface_count"], 10)
        self.assertEqual(report["base_diff"], "checked")

    def test_manifest_covers_the_prompt_and_description_surfaces(self) -> None:
        lock = load_lock(ROOT)
        paths = {surface["path"] for surface in lock["surfaces"]}

        self.assertIn("templates/agents-md.bootstrap.md", paths)
        self.assertIn("templates/agents-md.orchestration.md", paths)
        self.assertIn(
            "plugin/plugins/pilotfish-codex/skills/pilotfish-orchestration/references/orchestration-policy.md",
            paths,
        )
        self.assertIn("plugin/plugins/pilotfish-codex/skills/pilotfish-orchestration/SKILL.md", paths)
        self.assertIn("INSTALL_PROMPT.md", paths)

    def test_small_text_change_stays_within_a_surface_budget(self) -> None:
        surface = {
            "max_changed_lines": 2,
            "max_changed_characters": 80,
            "max_change_ratio": 0.5,
        }

        metrics = check_change_budget(surface, "one\ntwo\n", "one\ntoo\n")

        self.assertEqual(metrics["changed_lines"], 2)
        self.assertEqual(metrics["changed_characters"], 6)

    def test_large_prompt_rewrite_is_rejected(self) -> None:
        surface = {
            "max_changed_lines": 2,
            "max_changed_characters": 20,
            "max_change_ratio": 0.2,
        }

        with self.assertRaisesRegex(PromptLockError, "change budget"):
            check_change_budget(
                surface,
                "keep this contract\n" * 8,
                "replace this contract\n" * 8,
            )

    def test_git_base_diff_budget_is_enforced(self) -> None:
        with self._git_repo_with_current_lock() as root:
            scout = root / "templates" / "agents" / "scout.toml"
            scout.write_text(scout.read_text(encoding="utf-8") + "bounded\n" * 9, encoding="utf-8")

            with self.assertRaisesRegex(PromptLockError, "change budget"):
                validate_lock(root, base_ref="HEAD")

    def test_protected_prompt_change_requires_a_version_update(self) -> None:
        with self._git_repo_with_current_lock() as root:
            scout = root / "templates" / "agents" / "scout.toml"
            scout.write_text(
                scout.read_text(encoding="utf-8").replace("fast, read-only", "quick, read-only"),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(PromptLockError, "VERSION update"):
                validate_lock(root, base_ref="HEAD")

    def test_manifest_declares_immutable_update_protocol(self) -> None:
        lock = load_lock(ROOT)

        self.assertEqual(lock["schema_version"], 2)
        self.assertEqual(lock["status"], "active")
        self.assertTrue(lock["manifest_immutable"])
        self.assertIn("--allow-lock-update", lock["update_protocol"])
        self.assertNotIn("path", lock["version_gate"])
        self.assertTrue(lock["version_gate"]["require_change_for_protected_surfaces"])

    def test_manifest_drift_requires_explicit_update_mode(self) -> None:
        with self._git_repo_with_current_lock() as root:
            manifest = root / "docs" / "specs" / "prompt-document-lock" / "LOCK.json"
            manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            with self.assertRaisesRegex(PromptLockError, "LOCK.json changed"):
                validate_lock(root, base_ref="HEAD")

    def test_new_surface_requires_explicit_lock_renewal(self) -> None:
        with self._git_repo_with_current_lock() as root:
            manifest = root / "docs" / "specs" / "prompt-document-lock" / "LOCK.json"
            lock = json.loads(manifest.read_text(encoding="utf-8"))
            lock["surfaces"] = [
                surface
                for surface in lock["surfaces"]
                if surface["path"] != "templates/agents/sol-executor.toml"
            ]
            manifest.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
            (root / "templates" / "agents" / "sol-executor.toml").unlink()
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "test: establish previous lock"], cwd=root, check=True)

            current_manifest = ROOT / "docs" / "specs" / "prompt-document-lock" / "LOCK.json"
            shutil.copyfile(current_manifest, manifest)
            shutil.copyfile(
                ROOT / "templates" / "agents" / "sol-executor.toml",
                root / "templates" / "agents" / "sol-executor.toml",
            )

            with self.assertRaisesRegex(PromptLockError, "LOCK.json changed"):
                validate_lock(root, base_ref="HEAD")
            report = validate_lock(root, base_ref="HEAD", allow_lock_update=True)
            added = next(
                item for item in report["surfaces"] if item["id"] == "sol-executor-agent"
            )
            self.assertTrue(added["added"])

    def test_mirrored_policy_drift_is_rejected(self) -> None:
        with self._git_repo_with_current_lock() as root:
            policy = root / "plugin" / "plugins" / "pilotfish-codex" / "skills" / "pilotfish-orchestration" / "references" / "orchestration-policy.md"
            policy.write_text(policy.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            with self.assertRaisesRegex(PromptLockError, "mirror"):
                validate_lock(root, base_ref="HEAD")


CLAUDE_AGENT_FILES = (
    "executor",
    "Explore",
    "mech-executor",
    "plan-verifier",
    "scout",
    "security-executor",
    "security-reviewer",
    "verifier",
)
CLAUDE_SKILL_DIR = "hosts/claude/dist/skills/pilotfish-orchestration"
LOCK_RELATIVE = "docs/specs/prompt-document-lock/LOCK.json"


def _claude_paths() -> set[str]:
    return {f"hosts/claude/dist/agents/{name}.md" for name in CLAUDE_AGENT_FILES} | {
        f"{CLAUDE_SKILL_DIR}/SKILL.md",
        f"{CLAUDE_SKILL_DIR}/references/orchestration-policy.md",
        f"{CLAUDE_SKILL_DIR}/references/workflow-extensions.md",
    }


class ClaudeSurfaceLockTests(unittest.TestCase):
    """AC-CE-001/002/003/005/007: Claude surfaces and the per-host VERSION gate."""

    _git_repo_with_current_lock = PromptDocumentLockTests._git_repo_with_current_lock

    def _edit(self, root: Path, relative: str, old: str, new: str) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def _bump(self, root: Path, version_file: str) -> None:
        path = root / version_file
        path.write_text(path.read_text(encoding="utf-8").strip() + ".bump\n", encoding="utf-8")

    def test_lock_covers_exactly_the_eleven_claude_surfaces(self) -> None:
        lock = load_lock(ROOT)
        claude = {s["path"] for s in lock["surfaces"] if s["path"].startswith("hosts/claude/")}

        self.assertEqual(claude, _claude_paths())
        self.assertEqual(len(claude), 11)
        for path in claude:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_every_surface_names_its_own_host_version_file(self) -> None:
        for surface in load_lock(ROOT)["surfaces"]:
            expected = (
                "hosts/claude/VERSION"
                if surface["path"].startswith("hosts/claude/")
                else "hosts/codex/VERSION"
            )
            self.assertEqual(surface["version_file"], expected, surface["id"])

    def test_surface_without_a_host_version_file_is_rejected(self) -> None:
        with self._git_repo_with_current_lock() as root:
            manifest = root / LOCK_RELATIVE
            for bad in (None, "VERSION", "../VERSION", "hosts/claude/README.md"):
                lock = json.loads((ROOT / LOCK_RELATIVE).read_text(encoding="utf-8"))
                if bad is None:
                    del lock["surfaces"][0]["version_file"]
                else:
                    lock["surfaces"][0]["version_file"] = bad
                manifest.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(PromptLockError, "version_file|missing fields"):
                    load_lock(root)

    def test_claude_agent_beyond_its_budget_fails_and_names_the_surface(self) -> None:
        with self._git_repo_with_current_lock() as root:
            executor = root / "hosts/claude/dist/agents/executor.md"
            lines = executor.read_text(encoding="utf-8").splitlines()
            # Five edited front-matter lines are 10 changed lines against a budget of 8.
            lines[1:6] = [f"edited-{index}: value" for index in range(5)]
            executor.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._bump(root, "hosts/claude/VERSION")

            with self.assertRaisesRegex(PromptLockError, "claude-executor-agent: .*budget exceeded"):
                validate_lock(root, base_ref="HEAD")

    def test_claude_surface_losing_a_required_fragment_fails(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._edit(
                root,
                "hosts/claude/dist/agents/Explore.md",
                "Never modify anything.",
                "Modify files when convenient.",
            )
            self._bump(root, "hosts/claude/VERSION")

            with self.assertRaisesRegex(PromptLockError, "claude-explore-agent: required fragment"):
                validate_lock(root, base_ref="HEAD")

    def test_claude_change_without_claude_version_bump_fails(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._edit(
                root,
                "hosts/claude/dist/agents/executor.md",
                "Work like a senior engineer",
                "Work as a senior engineer",
            )

            with self.assertRaisesRegex(PromptLockError, "VERSION update: hosts/claude/VERSION"):
                validate_lock(root, base_ref="HEAD")

    def test_claude_change_with_only_claude_version_bump_passes_without_root_version(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self.assertFalse((root / "VERSION").exists())
            self._edit(
                root,
                "hosts/claude/dist/agents/executor.md",
                "Work like a senior engineer",
                "Work as a senior engineer",
            )
            self._bump(root, "hosts/claude/VERSION")

            report = validate_lock(root, base_ref="HEAD")

            self.assertEqual(report["status"], "ok")
            self.assertFalse((root / "VERSION").exists())

    def test_version_gate_is_per_host(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._edit(
                root,
                "hosts/claude/dist/agents/executor.md",
                "Work like a senior engineer",
                "Work as a senior engineer",
            )
            self._bump(root, "hosts/codex/VERSION")
            with self.assertRaisesRegex(PromptLockError, "VERSION update: hosts/claude/VERSION"):
                validate_lock(root, base_ref="HEAD")

        with self._git_repo_with_current_lock() as root:
            self._edit(root, "templates/agents/scout.toml", "fast, read-only", "quick, read-only")
            self._bump(root, "hosts/claude/VERSION")
            with self.assertRaisesRegex(PromptLockError, "VERSION update: hosts/codex/VERSION"):
                validate_lock(root, base_ref="HEAD")

        with self._git_repo_with_current_lock() as root:
            self._edit(root, "templates/agents/scout.toml", "fast, read-only", "quick, read-only")
            self._bump(root, "hosts/codex/VERSION")
            self.assertEqual(validate_lock(root, base_ref="HEAD")["status"], "ok")

    def test_claude_renewal_needs_the_flag_offline(self) -> None:
        """AC-CE-007 offline: the CLI in a temp git repo, without and with --allow-lock-update."""

        with self._git_repo_with_current_lock() as root:
            manifest = root / LOCK_RELATIVE
            previous = json.loads(manifest.read_text(encoding="utf-8"))
            previous["surfaces"] = [
                s for s in previous["surfaces"] if not s["path"].startswith("hosts/claude/")
            ]
            manifest.write_text(json.dumps(previous, indent=2) + "\n", encoding="utf-8")
            subprocess.run(["git", "rm", "-rq", "hosts/claude/dist"], cwd=root, check=True)
            subprocess.run(["git", "add", "--", LOCK_RELATIVE], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "test: previous lock"], cwd=root, check=True)

            shutil.copyfile(ROOT / LOCK_RELATIVE, manifest)
            for path in _claude_paths():
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, destination)

            script = str(ROOT / "install" / "validate_prompt_lock.py")
            base = [sys.executable, script, "--root", str(root), "--base-ref", "HEAD"]
            denied = subprocess.run(base, capture_output=True, text=True, check=False)
            allowed = subprocess.run(
                [*base, "--allow-lock-update", "--json"], capture_output=True, text=True, check=False
            )

            self.assertEqual(denied.returncode, 1)
            self.assertIn("LOCK.json changed", denied.stderr)
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            report = json.loads(allowed.stdout)
            added = {item["path"] for item in report["surfaces"] if item.get("added")}
            self.assertEqual(added, _claude_paths())


EQUIVALENCE = "docs/specs/core-policy/equivalence/claude.md"
SCOUT = "templates/agents/scout.toml"
SCOUT_ID = "scout-agent"


class MigrationMarkerTests(unittest.TestCase):
    """core-policy P0: one-time per-surface migration waives only the change budget."""

    _git_repo_with_current_lock = PromptDocumentLockTests._git_repo_with_current_lock

    def _manifest(self, root: Path) -> Path:
        return root / LOCK_RELATIVE

    def _mark(self, root: Path, surface_id: str, migration_id: str, equivalence: str = EQUIVALENCE) -> None:
        manifest = self._manifest(root)
        lock = json.loads(manifest.read_text(encoding="utf-8"))
        for surface in lock["surfaces"]:
            if surface["id"] == surface_id:
                surface["migration"] = {"migration_id": migration_id, "equivalence": equivalence}
        manifest.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    def _commit(self, root: Path, message: str) -> None:
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", message], cwd=root, check=True)

    def _write_equivalence(self, root: Path, text: str = "| section | maps to |\n") -> None:
        path = root / EQUIVALENCE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _overshoot(self, root: Path, relative: str = SCOUT, lines: int = 9) -> None:
        """Append lines past the change budget (not max_lines) and bump the host VERSION."""

        path = root / relative
        path.write_text(path.read_text(encoding="utf-8") + "bounded\n" * lines, encoding="utf-8")
        version = root / "hosts/codex/VERSION"
        version.write_text(version.read_text(encoding="utf-8").strip() + ".bump\n", encoding="utf-8")

    def _marked_overshoot(self, root: Path, migration_id: str = "claude-core-1") -> None:
        self._write_equivalence(root)
        self._mark(root, SCOUT_ID, migration_id)
        self._overshoot(root)

    def test_marker_with_flag_and_new_id_waives_the_budget_for_that_surface_only(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._marked_overshoot(root)

            with self.assertRaisesRegex(PromptLockError, "LOCK.json changed"):
                validate_lock(root, base_ref="HEAD")
            report = validate_lock(root, base_ref="HEAD", allow_lock_update=True)

            scout = next(item for item in report["surfaces"] if item["id"] == SCOUT_ID)
            self.assertEqual(scout["migration"], "claude-core-1")
            self.assertGreater(scout["changed_lines"], 8)
            self.assertTrue(all("migration" not in item for item in report["surfaces"] if item["id"] != SCOUT_ID))

    def test_unmarked_surface_stays_budgeted_while_another_is_migrating(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._marked_overshoot(root)
            self._overshoot(root, "templates/agents/executor.toml")

            with self.assertRaisesRegex(PromptLockError, "executor-agent: .*budget exceeded"):
                validate_lock(root, base_ref="HEAD", allow_lock_update=True)

    def test_marker_does_not_waive_the_version_gate(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._marked_overshoot(root)
            subprocess.run(["git", "checkout", "--", "hosts/codex/VERSION"], cwd=root, check=True)

            with self.assertRaisesRegex(PromptLockError, "VERSION update: hosts/codex/VERSION"):
                validate_lock(root, base_ref="HEAD", allow_lock_update=True)

    def test_marker_already_in_base_is_inert(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._write_equivalence(root)
            self._mark(root, SCOUT_ID, "claude-core-1")
            self._commit(root, "test: migration landed")
            self._overshoot(root)

            for allow in (False, True):
                with self.assertRaisesRegex(PromptLockError, "scout-agent: .*budget exceeded"):
                    validate_lock(root, base_ref="HEAD", allow_lock_update=allow)

    def test_base_and_head_both_marked_without_flag_fails_when_over_budget(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._write_equivalence(root)
            self._mark(root, SCOUT_ID, "claude-core-1")
            self._commit(root, "test: migration landed")
            self._overshoot(root)

            with self.assertRaisesRegex(PromptLockError, "budget exceeded"):
                validate_lock(root, base_ref="HEAD")

    def test_reverse_migration_with_new_id_passes(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._write_equivalence(root)
            self._mark(root, SCOUT_ID, "claude-core-1")
            self._commit(root, "test: forward migration landed")
            self._mark(root, SCOUT_ID, "claude-core-1-rollback")
            self._overshoot(root)

            report = validate_lock(root, base_ref="HEAD", allow_lock_update=True)

            scout = next(item for item in report["surfaces"] if item["id"] == SCOUT_ID)
            self.assertEqual(scout["migration"], "claude-core-1-rollback")

    def test_pull_request_path_rejects_an_active_migration(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._marked_overshoot(root)

            with self.assertRaisesRegex(PromptLockError, "migration is not accepted"):
                validate_lock(root, base_ref="HEAD", allow_lock_update=True, allow_migration=False)

            script = str(ROOT / "install" / "validate_prompt_lock.py")
            base = [sys.executable, script, "--root", str(root), "--base-ref", "HEAD", "--allow-lock-update"]
            denied = subprocess.run([*base, "--no-migration"], capture_output=True, text=True, check=False)
            allowed = subprocess.run(base, capture_output=True, text=True, check=False)
            self.assertEqual(denied.returncode, 1)
            self.assertIn("migration is not accepted", denied.stderr)
            self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_pull_request_path_ignores_an_inert_marker(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._write_equivalence(root)
            self._mark(root, SCOUT_ID, "claude-core-1")
            self._commit(root, "test: migration landed")
            manifest = self._manifest(root)
            manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            report = validate_lock(root, base_ref="HEAD", allow_lock_update=True, allow_migration=False)

            self.assertEqual(report["status"], "ok")

    def test_marked_surface_over_max_bytes_still_fails(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._marked_overshoot(root)
            scout = root / SCOUT
            lock = load_lock(root)
            limit = next(s["max_bytes"] for s in lock["surfaces"] if s["id"] == SCOUT_ID)
            scout.write_text(scout.read_text(encoding="utf-8") + "x" * limit, encoding="utf-8")

            with self.assertRaisesRegex(PromptLockError, "absolute size limit"):
                validate_lock(root, base_ref="HEAD", allow_lock_update=True)

    def test_marked_surface_missing_a_fragment_still_fails(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._marked_overshoot(root)
            lock = load_lock(root)
            fragment = next(s["required_fragments"][0] for s in lock["surfaces"] if s["id"] == SCOUT_ID)
            scout = root / SCOUT
            scout.write_text(scout.read_text(encoding="utf-8").replace(fragment, "gone"), encoding="utf-8")

            with self.assertRaisesRegex(PromptLockError, "scout-agent: required fragment"):
                validate_lock(root, base_ref="HEAD", allow_lock_update=True)

    def test_equivalence_file_missing_or_empty_fails(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._mark(root, SCOUT_ID, "claude-core-1")
            self._overshoot(root)

            with self.assertRaisesRegex(PromptLockError, "equivalence file is missing"):
                validate_lock(root, base_ref="HEAD", allow_lock_update=True)

            self._write_equivalence(root, " \n\n")
            with self.assertRaisesRegex(PromptLockError, "equivalence file is empty"):
                validate_lock(root, base_ref="HEAD", allow_lock_update=True)

    def test_equivalence_path_outside_the_repository_fails(self) -> None:
        with self._git_repo_with_current_lock() as root:
            self._write_equivalence(root)
            for bad in ("../outside.md", "/etc/hosts", "docs\\table.md", ""):
                self._mark(root, SCOUT_ID, "claude-core-1", bad)
                with self.assertRaisesRegex(PromptLockError, "equivalence must stay inside"):
                    load_lock(root)

    def test_equivalence_symlink_escaping_the_repository_fails(self) -> None:
        with self._git_repo_with_current_lock() as root, tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "table.md"
            target.write_text("outside\n", encoding="utf-8")
            link = root / EQUIVALENCE
            link.parent.mkdir(parents=True, exist_ok=True)
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            self._mark(root, SCOUT_ID, "claude-core-1")
            self._overshoot(root)

            with self.assertRaisesRegex(PromptLockError, "escapes the repository"):
                validate_lock(root, base_ref="HEAD", allow_lock_update=True)

    def test_malformed_markers_are_rejected_by_the_schema(self) -> None:
        with self._git_repo_with_current_lock() as root:
            bad_markers = (
                "claude-core-1",
                {"migration_id": "claude-core-1"},
                {"equivalence": EQUIVALENCE},
                {"migration_id": "claude-core-1", "equivalence": EQUIVALENCE, "extra": 1},
                {"migration_id": "Claude Core", "equivalence": EQUIVALENCE},
                {"migration_id": "ab", "equivalence": EQUIVALENCE},
                {"migration_id": "-core-1", "equivalence": EQUIVALENCE},
                {"migration_id": "a" * 65, "equivalence": EQUIVALENCE},
                {"migration_id": 7, "equivalence": EQUIVALENCE},
            )
            for marker in bad_markers:
                lock = json.loads((ROOT / LOCK_RELATIVE).read_text(encoding="utf-8"))
                lock["surfaces"][0]["migration"] = marker
                self._manifest(root).write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(PromptLockError, "migration"):
                    load_lock(root)

    def test_real_lock_carries_no_migration_marker(self) -> None:
        self.assertTrue(all("migration" not in s for s in load_lock(ROOT)["surfaces"]))


class RepoPathSemanticsTests(unittest.TestCase):
    """repo 相對路徑的判斷不分平台：Windows 語意下的 rooted、drive 路徑也要拒絕。"""

    def test_rooted_and_drive_paths_are_rejected_on_every_platform(self) -> None:
        import validate_prompt_lock

        check = validate_prompt_lock._is_relative_repo_path
        for bad in ("/etc/hosts", "C:/x", "C:x", "//server/share", "../o.md", "a/../b", "docs\\t.md", ""):
            self.assertFalse(check(bad), bad)
        self.assertTrue(check("docs/specs/core-policy/equivalence/claude.md"))
