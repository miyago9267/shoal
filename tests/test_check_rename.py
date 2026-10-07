"""tools/check_rename.py 的測試（docs/specs/shoal-rebrand N7）。

替換規則以 RENAME.md 規則表為準：表裡每個「舊 -> 新」的 token 都要被 apply_rename 還原成表上的新名；
rename-aware 檢查另用 temp git repo 驗證 OK、DIFF 與 exit code。舊名只出現在 LEGACY_ 常數。
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_rename as cr  # noqa: E402

RENAME = ROOT / "docs" / "specs" / "shoal-rebrand" / "RENAME.md"
BASE_REF = "21d5986"

# ---- LEGACY_: (舊文字, 路徑, 期望的新文字)；路徑 None 表示不看路徑規則 ----
LEGACY_SAMPLES = [
    (
        "Use Pilotfish orchestration for this task",
        None,
        "Use shoal orchestration for this task",
    ),
    ('"Pilotfish orchestration workflow"', None, '"Shoal orchestration workflow"'),
    ("Hybrid Pilotfish orchestration", None, "Hybrid shoal orchestration"),
    (
        "# Pilotfish policy\n\nPilotfish routes work.",
        None,
        "# Shoal policy\n\nShoal routes work.",
    ),
    ("wrapped line\nPilotfish continues", None, "wrapped line\nshoal continues"),
    ("<!-- pilotfish v1.4.2-claude.4 -->", "x.md", "<!-- shoal-claude v2.0.0 -->"),
    (
        "<!-- pilotfish-claude v1.4.2-claude.4 -->",
        "x.md",
        "<!-- shoal-claude v2.0.0 -->",
    ),
    ("<!-- pilotfish-codex v1.8.3 -->", "x.md", "<!-- shoal-codex v2.0.0 -->"),
    ("<!-- pilotfish-codex:begin -->", "x.md", "<!-- shoal-codex:begin -->"),
    ("<!-- pilotfish-grok v1.0.6 -->", "x.md", "<!-- shoal-grok v2.0.0 -->"),
    ("<!-- pilotfish-agy v0.1.0 -->", "x.md", "<!-- shoal-agy v2.0.0 -->"),
    # 版本只在 .md 的 marker 與 Codex plugin manifest 內改，程式碼裡的 marker 樣式不動
    (
        'f"<!-- pilotfish-grok v{version} -->"',
        "x.py",
        'f"<!-- shoal-grok v{version} -->"',
    ),
    (
        '  "version": "1.8.3",',
        "plugin/plugins/pilotfish-codex/.codex-plugin/plugin.json",
        '  "version": "2.0.0",',
    ),
    (
        '  "version": "0.1.0",',
        "plugin/plugins/pilotfish-jev-router/.codex-plugin/plugin.json",
        '  "version": "0.1.0",',
    ),
    (
        "PILOTFISH_CLAUDE_ROOT and PILOTFISH_OPENCODE_SOURCE",
        None,
        "SHOAL_ROOT and SHOAL_ROOT",
    ),
    ("PILOTFISH_GROK_HOME", None, "SHOAL_GROK_HOME"),
    (
        "pilotfish-autoroute-v1 pilotfish-autoroute-v2",
        None,
        "shoal-autoroute-v1 shoal-autoroute-v1",
    ),
    (
        'Symbol.for("shoal.pilotfish-opencode.route-registered")',
        None,
        'Symbol.for("shoal.opencode.route-registered")',
    ),
    (
        "PilotfishOpenCodePlugin createPilotfishRouteTool pilotfishHome",
        None,
        "ShoalOpenCodePlugin createShoalRouteTool shoalHome",
    ),
    # 上游的真實名稱、網址與指向歷史文件的路徑不改
    (
        "https://github.com/Nanako0129/pilotfish and Nanako0129/pilotfish-grok",
        None,
        "https://github.com/Nanako0129/pilotfish and Nanako0129/pilotfish-grok",
    ),
    ("see miyago9267/pilotfish-codex", None, "see miyago9267/pilotfish-codex"),
    (
        "docs/specs/hybrid-pilotfish-runtime/SPEC.md",
        None,
        "docs/specs/hybrid-pilotfish-runtime/SPEC.md",
    ),
    (
        "install/evaluate_pilotfish_value_matrix.py",
        None,
        "install/evaluate_pilotfish_value_matrix.py",
    ),
]
LEGACY_PATH_SAMPLES = [
    (
        "plugin/plugins/pilotfish-codex/skills/pilotfish-orchestration/SKILL.md",
        "plugin/plugins/shoal-codex/skills/shoal-orchestration/SKILL.md",
    ),
    ("hooks/pilotfish_autoroute_gate.py", "hooks/shoal_autoroute_gate.py"),
    (
        "hosts/grok/dist/hooks/pilotfish-grok/shoal_guard.py",
        "hosts/grok/dist/hooks/shoal-grok/shoal_guard.py",
    ),
    (
        "hosts/opencode/plugin/src/plugin/pilotfish-opencode.ts",
        "hosts/opencode/plugin/src/plugin/shoal-opencode.ts",
    ),
    (
        "docs/benchmarks/PILOTFISH-VALUE-MATRIX.md",
        "docs/benchmarks/PILOTFISH-VALUE-MATRIX.md",
    ),
]
LEGACY_LOCK_TEXT = (
    "Use Pilotfish orchestration for this task.\n<!-- pilotfish-codex v1.8.3 -->\n"
)
LEGACY_LOCK_PATH = "plugin/pilotfish-codex/SKILL.md"
LEGACY_LOCK_FRAGMENT = "Use Pilotfish orchestration"


class ApplyRenameTests(unittest.TestCase):
    def test_samples(self) -> None:
        for old, path, new in LEGACY_SAMPLES:
            with self.subTest(old=old):
                self.assertEqual(cr.apply_rename(old, path), new)

    def test_paths(self) -> None:
        for old, new in LEGACY_PATH_SAMPLES:
            with self.subTest(old=old):
                self.assertEqual(cr.rename_path(old), new)

    def test_is_idempotent(self) -> None:
        for old, path, _new in LEGACY_SAMPLES:
            once = cr.apply_rename(old, path)
            self.assertEqual(cr.apply_rename(once, path), once, old)

    def test_every_token_of_the_rename_table_maps_to_its_new_name(self) -> None:
        text = RENAME.read_text(encoding="utf-8")
        table = text.split("## 規則", 1)[1].split("## 例外", 1)[0]
        checked = 0
        for line in table.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 3 or set(cells[0]) <= set("-: ") or cells[0] == "舊":
                continue
            legacy_name = re.compile("pilot" + "fish", re.IGNORECASE)
            old = [tok for tok in re.findall(r"`([^`]+)`", cells[0]) if legacy_name.search(tok)]
            new = [tok for tok in re.findall(r"`([^`]+)`", cells[1]) if re.search("shoal", tok, re.IGNORECASE)]
            if not old or not new or "同形狀" in cells[1] or "句首" in cells[1]:
                continue  # 刪除的列、只在 tests/ 的字串樣式、句首大小寫（LEGACY_SAMPLES 另測）
            pairs = (
                list(zip(old, new))
                if len(old) == len(new)
                else [(o, new[0]) for o in old]
                if len(new) == 1
                else []
            )
            self.assertTrue(pairs, f"cannot pair RENAME row: {cells[0]} -> {cells[1]}")
            for o, n in pairs:
                got = (
                    cr.apply_rename(o.replace("…", ""), "x.md")
                    if "…" in o
                    else cr.apply_rename(o, "x.md")
                )
                self.assertEqual(got, n.replace("…", ""), f"{o} -> {n}")
                checked += 1
        self.assertGreater(checked, 25)

    def test_scan_exceptions_and_the_rule_table_agree_on_protected_names(self) -> None:
        text = RENAME.read_text(encoding="utf-8")
        for upstream in (
            "Nanako0129/pilotfish",
            "Nanako0129/pilotfish-grok",
            "miyago9267/pilotfish-codex",
        ):
            self.assertIn(upstream, text)
            self.assertEqual(cr.apply_rename(upstream), upstream)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
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
    )


class CheckTests(unittest.TestCase):
    """temp repo：base commit 有舊路徑與舊 LOCK，工作樹是改名後的新路徑與新 LOCK。"""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.repo = Path(self.dir.name)
        git(self.repo, "init", "-q")
        lock = {
            "surfaces": [
                {
                    "id": "skill",
                    "path": LEGACY_LOCK_PATH,
                    "required_fragments": [LEGACY_LOCK_FRAGMENT],
                },
                {"id": "plain", "path": "plain.md", "required_fragments": ["keep"]},
            ],
            "mirrors": [{"left": LEGACY_LOCK_PATH, "right": "plain.md"}],
        }
        self.lock_path = "docs/specs/prompt-document-lock/LOCK.json"
        self.write(self.lock_path, json.dumps(lock))
        self.write(LEGACY_LOCK_PATH, LEGACY_LOCK_TEXT)
        self.write("plain.md", "keep\n")
        git(self.repo, "add", "--all")
        git(self.repo, "commit", "-q", "-m", "base")
        # 工作樹：改名後的結果
        (self.repo / LEGACY_LOCK_PATH).unlink()
        new_path = cr.rename_path(LEGACY_LOCK_PATH)
        lock["surfaces"][0].update(
            path=new_path, required_fragments=["Use shoal orchestration"]
        )
        lock["mirrors"] = [{"left": new_path, "right": "plain.md"}]
        self.new_path = new_path
        self.write(self.lock_path, json.dumps(lock))
        self.write(new_path, cr.apply_rename(LEGACY_LOCK_TEXT, LEGACY_LOCK_PATH))

    def write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_main(self) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cr.main(["--root", str(self.repo), "--base-ref", "HEAD"])
        return code, out.getvalue()

    def test_a_faithful_rename_is_ok_per_surface(self) -> None:
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertIn(f"OK    skill ({self.new_path})", out)
        self.assertIn("OK    plain (plain.md)", out)
        self.assertIn("OK    mirrors", out)
        self.assertIn("rename check: ok (0 diff)", out)

    def test_extra_edit_is_a_diff_with_an_excerpt(self) -> None:
        self.write(
            self.new_path,
            cr.apply_rename(LEGACY_LOCK_TEXT, LEGACY_LOCK_PATH) + "an extra sentence\n",
        )
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn(f"DIFF  skill ({self.new_path})", out)
        self.assertIn("+an extra sentence", out)
        self.assertIn("OK    plain (plain.md)", out)

    def test_a_missed_version_bump_is_a_diff(self) -> None:
        self.write(
            self.new_path,
            cr.apply_rename(LEGACY_LOCK_TEXT, LEGACY_LOCK_PATH).replace(
                "v2.0.0", "v1.8.3"
            ),
        )
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("-<!-- shoal-codex v2.0.0 -->", out)

    def test_wrong_path_or_fragments_or_mirrors_are_reported(self) -> None:
        lock = json.loads((self.repo / self.lock_path).read_text())
        lock["surfaces"][0]["path"] = "somewhere/else.md"
        lock["surfaces"][0]["required_fragments"] = ["changed"]
        lock["mirrors"] = []
        self.write(
            "somewhere/else.md", cr.apply_rename(LEGACY_LOCK_TEXT, LEGACY_LOCK_PATH)
        )
        self.write(self.lock_path, json.dumps(lock))
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("path: ", out)
        self.assertIn("required_fragments", out)
        self.assertIn("DIFF  mirrors", out)

    def test_the_real_repo_matches_its_base_commit(self) -> None:
        # base ref 在 shallow clone 不存在時略過；存在時必須全部 OK。
        probe = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{BASE_REF}^{{commit}}"],
            capture_output=True,
        )
        if probe.returncode != 0:
            self.skipTest(f"{BASE_REF} is not available in this clone")
        lines, bad = cr.check(ROOT, BASE_REF)
        self.assertEqual(bad, 0, "\n".join(lines))
        self.assertGreaterEqual(len([ln for ln in lines if ln.startswith("OK")]), 27)


if __name__ == "__main__":
    unittest.main()
