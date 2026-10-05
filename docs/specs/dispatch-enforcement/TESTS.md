# TESTS - dispatch-enforcement

> Acceptance cases for [SPEC.md](./SPEC.md)。離線測試一律使用 temp 目錄，不讀寫真實的
> `~/.claude`、`~/.codex`、`~/.grok`、`~/.gemini`。指令：
> `python3 -m unittest discover -s tests`。狀態以 2026-10-05 的工作樹為準。

## 規則與核心（E1，R1 至 R5、R8）

- **AC-DE-001:** The guard shall apply the same R1 classification rule, R2 file-count
  rule, `SHOAL_GUARD_DIRECT`, exempt paths and "write-level dispatch unlocks the
  turn"
  rule on every host. Status: passing (`tests/test_shoal_guard.py`,
  `tests/fixtures/guard_vectors.json`).
- **AC-DE-002:** When a subagent or a verify-level role calls a dispatch or edit
  tool,
  the guard shall deny it on hosts that identify the caller. Status: passing
  (`tests/test_shoal_guard.py`).
- **AC-DE-003:** The guard shall fail open on any exception, log only the whitelisted
  fields, and keep state files owner-only without following symlinks. Status: passing
  (`tests/test_shoal_guard.py`).
- **AC-DE-004:** The TypeScript port shall pass the same vectors. Status:
  pending (E3,
  `hosts/opencode/plugin/tests/guard-vectors.test.ts`, another executor).

## 權限補強（E4，R6）

- **AC-DE-010:** Per-role Codex `sandbox_mode` and `network_access` shall be verified
  live. Status: done, not effective in 0.160.0, recorded as a limitation
  ([E0-RESULTS.md](./E0-RESULTS.md)).
- **AC-DE-011:** Five hosts shall pass `render --check`, and the Claude verify level
  shall deny `MultiEdit`. Status: pending (E4; working tree has changes not
  verified here).

## 安裝與註冊（E5，R7）

- **AC-DE-020:** When the Codex installer runs on a fresh home, it shall install
  `hooks/shoal_guard.py`, register the guard groups under projection `shoal-guard-v1`
  and record both in state. Status: passing (`tests/test_install.py`).
- **AC-DE-021:** When it runs on a home installed before the guard existed, it
  shall add
  the script and groups, keep foreign groups, not raise `installed_hook_drift`,
  and be a
  no-op on the next run. Status: passing (`tests/test_install.py`).
- **AC-DE-022:** While the guard script is edited without state proof, or a canonical
  guard group is unowned, the Codex installer shall abort without writing. Status:
  passing (`tests/test_install.py`).
- **AC-DE-023:** The Codex installer shall not write hook trust. Status: passing
  (`tests/test_install.py`); the user approves the hook once with `/hooks`.
- **AC-DE-024:** Smoke staging shall keep working on a home that has the guard installed.
  Status: passing (`tests/test_stage_smoke_home.py`).
- **AC-DE-030:** The grok dist copy of the guard shall be byte-identical to
  `hooks/shoal_guard.py`, produced by render and rejected by `--check` when
  edited by
  hand. Status: passing (`tests/test_render_grok.py`).
- **AC-DE-031:** `install_grok.py` shall install the guard with its exec bit and
  hash,
  keep the plan-mode guard entry, and abort when the dist copy differs from the
  commit's
  source. Status: passing (`tests/test_install_grok.py`, `tests/test_grok_hooks.py`).
- **AC-DE-040:** `install_hooks.py` shall install the committed-HEAD script
  (0755) and
  merge entries into Claude `settings.json` or agy `hooks.json` without touching
  foreign
  hooks, follow a symlinked settings file, back up first (0600 in a 0700
  directory), and
  be idempotent. Status: passing (`tests/test_install_hooks.py`).
- **AC-DE-041:** `install_hooks.py --uninstall` shall remove only owned entries.
  Status: passing (`tests/test_install_hooks.py`).
- **AC-DE-050:** On Claude, after a global install, the guard shall deny one main
  direct edit and allow the edit after a write-level dispatch. Status: pending (live,
  after commit).
- **AC-DE-051:** On the other hosts, shadow mode shall log one `would_deny` and
  one
  allow after dispatch. Status: pending (live).

## 切換（E6）

- **AC-DE-060:** A host shall switch to enforce only after the Open question 1
  conditions, and the guard shall then deny once on that host. Status: pending.
