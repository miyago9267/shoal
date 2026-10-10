# role 改名對照表

delegation-default 的 D11。role 名稱是 core 的 key（`core/roles.toml`），所有 host
一起改名；行為、model、effort、權限與 prompt 語意都不變。

| 舊名 | 新名 | 說明 |
|---|---|---|
| `mech-executor` | `applier` | 照完整規格套用的機械實作 |
| `plan-verifier` | `plan-critic` | Plan 的補漏與把關（唯讀） |

- 上游專案（見 `upstream.lock`）仍使用舊名；比對上游文字時先套用上表。
  `tests/fixtures/grok/` 的上游原文 fixture 保留舊名，測試比對前再替換。
- 歷史紀錄（`CHANGELOG.md` 過往段落、`docs/specs/` 其他 spec、`docs/benchmarks/`、
  `docs/verification/`、`artifacts/`、`install/previous/`）保留舊名，不回改。
- 舊名只在遷移用的地方出現：`tools/sync_global.py` 的 `RENAMED_ROLES`、
  `tools/install_grok.py` 的 `RENAMED_ROLE_FILES`、`tests/legacy_fixtures.py` 的
  `LEGACY_ROLE_NAMES`，以及 `reason_code` 等沿用的識別字
  （例如 `autoroute_plan_verifier_missing`，因為已記錄的 evidence 用這個值）。
- 舊安裝的處理：sync 只移除確認是 shoal 安裝的舊名檔案（位元組等於歷史版本，或
  agy symlink 仍指向本 repo 的 dist）；dry-run 只回報，`--apply` 才移除。
- Claude 由 dotfile 複製安裝，不在本 repo 的 sync 範圍；改名後舊名 agent 檔需在
  dotfile 端移除（S8）。

## prompt lock 遷移對照（migration `delegation-default-3-0-0`）

v3.0.0 的改寫超過單一 surface 的變動上限（硬上限 32 行），所以下列三個 surface 在
`docs/specs/prompt-document-lock/LOCK.json` 掛上這個 migration marker（Miyago
2026-10-10 核准 spec；`--allow-lock-update` 與 commit trailer `Lock-Renewal: approved`
照 prompt-document-lock 的更新程序）。marker 只免除變動預算，`max_lines`、
`max_bytes`、`required_fragments`、mirror 與 VERSION gate 照常。

| Surface | 變動 |
|---|---|
| `orchestration-template`（`templates/agents-md.orchestration.md`）、`packaged-orchestration-policy`（Codex plugin 內的同文鏡像） | 只有上方的 role 改名（44 行，逐行對照本文上表）與版本 marker `2.1.1` → `3.0.0`；沒有條款增減。Codex 的 policy 不經 core 條款組裝（D16） |
| `claude-orchestration-policy`（`hosts/claude/dist/skills/shoal-orchestration/references/orchestration-policy.md`） | role 改名、版本 marker，加上 core 條款變動，來源是 `CLAUSES.md`，見下表 |

| 條款 | 變動 |
|---|---|
| `effort-per-delegation`、`dispatch-kind-label`、`plan-critic-gaps`、`research-fanout`、`followup-by-mode`、`collect-results` | 新增（`CLAUSES.md` S3、S4） |
| `long-running-main` → `watcher-long-commands`；`leaf-cannot-finish` | 長指令改派 `watcher`，main 不自己開背景 shell |
| `direct-when-small`、`local-search-direct`、`delegate-cost-benefit`、`single-bug-direct`、`bootstrap-ownership` | 改寫為預設派工（`CLAUSES.md` S5） |
| `Explore` | 不再列入 role 清單與路由（SPEC D14） |

這些變動不擴張任何 approval、security、destructive、external 或 release 的權限。

## prompt lock 遷移對照（migration `delegation-default-3-0-2`）

v3.0.2 改寫 `watcher` 的長指令條款（`CLAUSES.md` 2026-10-10 第四輪修訂），變動超過
`claude-watcher-agent` 的單次變動預算（8 行）。只有這個 surface 掛 marker；
`max_lines` 30、`max_bytes` 2600 與其他預算都沒有改。流程同上（`--allow-lock-update`、
commit trailer `Lock-Renewal: approved`）。

| Surface | 變動 |
|---|---|
| `claude-watcher-agent`（`hosts/claude/dist/agents/watcher.md`） | `long-command-background` 改為「除非 brief 說很快，否則背景執行再輪詢」，加 Claude addendum（`run_in_background: true`、`EXIT_STATUS=` log、輪詢迴圈）；`run-to-terminal` 拿掉「in the foreground」；description 不再寫「in its own foreground」。不擴張任何權限 |
