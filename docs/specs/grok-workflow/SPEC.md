---
title: 補足 grok 的 AI workflow（v1.1.0）
status: completed
created: 2026-10-04
updated: 2026-10-06
---

<!-- markdownlint-disable MD025 -->

# 補足 grok 的 AI workflow（v1.1.0）

## Background

shoal 的五個 host 裡，grok 最不完整。2026-10-04 查證（shoal main
`e389230`、本機 Grok Build 0.2.118）：

- **沒有 orchestration policy。** 上游 `Nanako0129/pilotfish-grok` v1.0.6
  的 `templates/rules.pilotfish-grok.md` 沒有進 shoal；`hosts/grok/dist`
  只有 agents、roles 與 `config.snippet.toml`。少了它，grok 端沒有路由與
  Plan gate 的規則。
- **沒有安裝路徑。** grok 一直照上游 `install/AGENT-INSTALL.md` 手動安裝；
  `~/dotfile/script/common/setup_grok.sh` 不處理 agents、roles、rules。
  結果 `~/.grok/rules/pilotfish-grok.md` 停在 v1.0.4，`~/.grok/agents/`
  是上游舊文字，shoal 的 core 條款從未部署到 grok。
- **檢查看錯地方。** `check_agent_rule_sync.sh:172-185` 只檢查 dotfile
  的 vendored 目錄，不看 `~/.grok` 實際裝了什麼，所以 v1.0.4 的落差沒被
  發現。
- **可能停用了 role。** `~/.grok/config.toml:34-43` 的 `[subagents.toggle]`
  把七個 pilotfish role 都設成 `false`；上游規則只要求關閉 Claude 相容的
  agent 名稱。是否真的讓 role 失效尚未驗證。
- **上游沒有新版本。** v1.0.6（2026-07-29）之後只有 review bot 相關的
  commit，`templates/` 沒有變動；要補的能力都在 shoal 這側與 Grok Build
  原生功能。
- **Grok Build 原生能力未使用**（`~/.grok/docs/user-guide/`）：
  - `SubagentStop` hook 可以檢查 subagent 的最後回覆
    （`lastAssistantMessage`）並擋下結束，讓它再跑一輪（10-hooks.md:262）。
  - 每個 hook event 都帶 `permissionMode`（`default`、`auto`、`plan`、
    `bypassPermissions`），`PreToolUse` 可以 deny（10-hooks.md:234、238）。
  - plan mode 不會擋 subagent 的寫入（19-plan-mode.md:135）。
  - 全域 hooks 放在 `~/.grok/hooks/*.json`，不需要 trust（10-hooks.md:78）。

## Requirements (EARS)

### G1：orchestration policy

- **R1**：The grok host shall render `rules/pilotfish-grok.md` 到
  `hosts/grok/dist/`，內容取自上游 v1.0.6 的 `rules.pilotfish-grok.md`，
  逐字保留，只把版本 marker 換成 shoal 的 grok host 版本。
- **R2**：The grok host shall 有 `hosts/grok/VERSION`；rules 的 marker 為
  `<!-- pilotfish-grok v<VERSION> -->`。
- **R3**：When `render --host grok --check` runs，the rules file shall
  與 golden 逐位元組比對；上游原文另存一份 fixture，測試確認除了 marker
  之外與上游 v1.0.6 相同。

### G2：shoal 負責 grok 的安裝

- **R4**：The repo shall 提供 `tools/install_grok.py`，從 shoal 的
  committed HEAD（`git archive`）安裝 `agents/`、`roles/`、
  `rules/pilotfish-grok.md` 與 G3 的 hooks 到 grok home（預設 `~/.grok`，
  可用 `--grok-home` 指定）。
- **R5**：The installer shall 預設 dry-run，列出會新增、取代、略過的
  檔案與 config 變更；`--apply` 才寫入。任何寫入前，把要被取代的檔案與
  `config.toml` 一起備份到 `<grok-home>/backups/shoal-<timestamp>/`。
- **R6**：The installer shall 只處理 shoal 擁有的檔案與 config key；不讀
  也不寫任何 credential、session、history、auth 檔案。
- **R7**：When the installer 偵測到 `[subagents.toggle]` 把 shoal 的 role
  設成 `false`，it shall 在 dry-run 輸出中標示；只有加上
  `--fix-toggles` 時才把那些 key 移除，其他 key 不動。
- **R8**：The installer shall 提供 `--restore <backup-dir>`，把備份的檔案
  與 `config.toml` 逐位元組還原；`--uninstall` 只移除 shoal 安裝的檔案，
  不修改 `config.toml`。
- **R9**：The installer shall 在安裝後驗證：檔案 hash 與 committed dist
  相同、rules marker 與 `hosts/grok/VERSION` 一致。

### G3：用 grok 原生 hooks 補強 workflow

- **R10（輸出格式 gate）**：The grok host shall 提供 `SubagentStop` hook，
  分成三個 hook entry，matcher 分別為 `^verifier$`、`^plan-verifier$`、
  `^security-reviewer$`（定錨，避免 `verifier` 命中 `plan-verifier`）；
  腳本以 entry 參數判斷 role，不依賴官方未記載的 input 欄位。規則從
  `hosts/grok/dist/agents/` 的實際文字推導：
  - verifier：最後回覆含 `CONFIRMED`、`REFUTED`、`INCONCLUSIVE`，或
    `direction_checkpoint` 的 `CONTINUE`、`PIVOT`、`ROLLBACK` 任一 token，
    不限位置。
  - plan-verifier：單獨的 `READY`，或含 Blocker、Evidence、Minimum
    revision、Acceptance check 四個欄位的 `REVISE` 區塊。
  - security-reviewer：每個 finding 有 severity，且有 `file:line` 或明確的
    evidence gap；或明確寫沒有 finding。
  不符合時以 `{"decision":"block"}` 退回並附上缺少的部分。
- **R11（不卡死）**：When `stopHookActive` 為 true，the format gate shall
  放行，不再第二次擋下；任何解析錯誤都 fail-open。
- **R12（plan mode 防護）**：While `permissionMode` 為 `plan`，the grok host
  shall 以 `PreToolUse` hook（matcher `^spawn_subagent$`，官方文件記載
  `Task` 為其 alias）拒絕產生可寫入的 subagent。可寫入的判斷順序：
  1. `toolInput.capability_mode` 有值時以它為準，`read-only` 放行。
  2. 缺值時依 `subagent_type` 讀 `<grok-home>/roles/<type>.toml` 的
     `default_capability_mode`（grok 的 rules 要求 named role 不帶
     capability_mode，所以這是主要路徑）。
  3. built-in `explore`、`plan` 視為不可寫入；`general-purpose` 視為
     可寫入。
  4. 任何解析失敗都 fail-open。
  deny 的 reason 說明要先離開 plan mode。
- **R13**：The hooks shall 由 grok renderer 產生到 `hosts/grok/dist/hooks/`
  （設定 JSON 與 Python 腳本），腳本只用 Python 標準函式庫。

### G4：檢查與文件

- **R14**：`check_agent_rule_sync.sh` 的 grok 檢查 shall 改為讀 shoal
  的 `hosts/grok/dist` 與 `hosts/grok/VERSION`；`~/.grok` 實際安裝的
  rules marker 與 dist 不一致時只輸出警告，不讓檢查失敗（避免未安裝時
  一定紅）。這是 dotfile repo 的變更，與 shoal 分開 commit，在 G5 之後做。
- **R15**：README 的 host 表、`INSTALL.md` 與 `upstream.lock` shall 反映
  grok 由 shoal 安裝；README 補上指向 `pilotfish-grok` 的歸屬連結。

### 版本

- **R16**：shoal 產品版本 bump 為 `1.1.0`（新功能、無破壞性變更）。
  `CHANGELOG.md` 的 `## Unreleased` 改為 `## v1.1.0`，涵蓋 role-only 路線
  四步與本 spec 的 grok workflow。

## Non-goals

- Rhai workflow（`.grok/workflows/*.rhai`）：價值高但規模大，另案。
- `grok plugin` 打包發佈：會改變發佈方式，需 Miyago 另外決定。
- `default_fork_context`、persona I/O contract：官方沒有文件，需先實測。
- 修改 grok 的 role 文字（已由 role-contracts 處理）。
- 自動寫入 `~/.grok`：installer 預設 dry-run，實際安裝由 Miyago 核准。

## Decisions

1. **rules 以 vendor 方式保留上游原文**：不拆成 core 條款，因為各 host
   的 orchestration policy 尚未統一（role-contracts 的 Non-goals）。
2. **grok host 版本訂為 `1.0.6-shoal.1`**：表示衍生自上游 v1.0.6，加上
   shoal 的 core 條款與 hooks。
3. **installer 用 Python 寫在 `tools/`**：與 render、refresh_golden 同一
   套語言與測試方式；不沿用上游「讓 agent 照 runbook 操作」的作法，因為
   shoal 需要可重複、可測試的安裝。上游 AGENT-INSTALL 的安全規則（備份、
   只動自己的 key、驗證）全部保留。
4. **hooks 只檢查格式，不判斷內容對錯**：內容判斷屬於 verifier 本身；
   hook 只防止格式不合導致 orchestrator 無法解析。
5. Miyago 2026-10-04 核准：每個 phase 驗證後 commit、push、跑 CI；全部
   完成後發 v1.1.0 Release；G5 實際安裝到 `~/.grok` 並使用
   `--fix-toggles`。

## Phases

詳細步驟見 `TASKS.md`，驗收見 `TESTS.md`。

| Phase | 內容 | 前置 |
|---|---|---|
| G1 | rules 與 grok VERSION | — |
| G3 | SubagentStop 格式 gate、plan mode 防護（render 到 dist） | G1 |
| G2 | `tools/install_grok.py`（安裝 G1、G3 的 dist） | G1、G3 |
| G4 | shoal 文件、版本 v1.1.0 | G2 |
| G5 | 實際安裝到 `~/.grok`（Miyago 已核准，含 `--fix-toggles`） | G2 |
| G6 | dotfile 的 `check_agent_rule_sync.sh` 改寫（R14） | G5 |
| G7 | v1.1.0 tag 與 GitHub Release（Miyago 已核准） | G4、fresh verifier |

## Rollback

- shoal 端：revert 對應 commit。
- `~/.grok`：`install_grok.py --restore <backup-dir>` 還原，或
  `--uninstall` 移除 shoal 安裝的檔案。

## 完結狀態（2026-10-06）

- 已在 v1.1.0 實作並發布。v1.3.0 起 grok hooks 另含 shoal dispatch guard，live
  grok 1.0.46 已觀察到 hook 觸發；`plan_mode_guard` 未在 live 實測。
