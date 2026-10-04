---
title: OpenCode 全域安裝
status: draft
created: 2026-10-04
updated: 2026-10-04
---

<!-- markdownlint-disable MD025 -->

# OpenCode 全域安裝

## Background

Miyago 2026-10-04 要求把 shoal 裝到全域環境。其他四個 host 已是全域：
Claude（`~/.claude`，auto-update）、Codex（`~/.codex`）、agy（`~/.gemini`
連到 shoal dist）、grok（`~/.grok`，`tools/install_grok.py`）。OpenCode 還不是：

- `hosts/opencode/plugin/install/install.sh` 只接受 `--target <project>`，把
  role、plugin 與控制檔寫進 `<project>/.opencode/`。
- plugin 只讀專案底下的 `.opencode/pilotfish/{catalog,routing}.json`
  （`src/plugin/pilotfish-opencode.ts:18-19`，路徑以 `context.directory` 為根，
  `safeProjectPath` 防止穿越）。
- dotfile 的兩份 spec 曾刻意排除 daily config：`pilotfish-opencode` 的
  Out of scope「直接修改現有 dotfile OpenCode production config」，以及
  `pilotfish-opencode-local-routing` 的「修改 daily config/opencode 的 slim
  runtime」。**Miyago 2026-10-04 決定推翻這兩項，改為也裝進 daily config。**
- daily config 是 `~/.config/opencode`（連到 `~/dotfile/config/opencode`），
  已有使用者自己的 `agents/`（`monika` 等五個）與 `plugins/`（三個），名稱
  不與 pilotfish 的五個 role 衝突。
- daily `opencode.json` 的 `provider` 區塊有 openai、chatgpt-proxy、google、
  aluo、xai、grok-cli；deepseek 是 OpenCode 內建 provider，列在
  `enabled_providers`（auth 不在 `opencode.json`）。`routing.json` 的 scout
  主要候選 deepseek 因此在 daily 可用。
- `routing.json` 目前是 optional：只有 `catalog.json` 時 plugin 回退
  native routing（`pilotfish-opencode.ts:135-142`，`plugin-seam.test.ts:78-117`）。

## Requirements (EARS)

- **R1（設定查找）**：When the plugin resolves a route，it shall 以
  `catalog.json` 的存在決定使用哪一層：專案的
  `.opencode/pilotfish/catalog.json` 存在時只用專案層；不存在時改用全域
  `<config-dir>/pilotfish/`，其中 `<config-dir>` 為 `OPENCODE_CONFIG_DIR`，
  未設定時為 `~/.config/opencode`。同一層內 `routing.json` 維持 optional
  （缺少時回退 native routing），不跨層混用。全域路徑同樣做穿越檢查
  （realpath 必須在 `<config-dir>` 內）。
- **R2（全域安裝）**：The installer shall 支援 `--global [--config-dir DIR]`：
  - 五個 role md 寫到 `<config-dir>/agents/`。
  - plugin 寫到 `<config-dir>/plugins/pilotfish-opencode.js`。
  - `catalog.json`、`routing.json` 寫到 `<config-dir>/pilotfish/`。
  - 以上全部都是 manifest entry，`--disable`、`--rollback` 會一併處理。
  - manifest 與備份放在 `<state-dir>`（`$XDG_STATE_HOME/shoal/opencode-global`，
    預設 `~/.local/state/shoal/opencode-global`），不放進 `<config-dir>`，
    避免落入 dotfile 追蹤目錄。
  - `--enable`、`--disable`、`--rollback` 的語意與既有 `--target` 相同。
- **R2a（plugin 共存）**：When 同一個 OpenCode process 同時載入全域與專案
  的 plugin，the plugin shall 只註冊一次 `pilotfish_route`（以 `globalThis`
  上的旗標去重）；installer 在 `--global` 時若偵測到已知專案（`--target`
  記錄或 cwd）有 `.opencode/plugins/pilotfish-opencode.js`，輸出警告。
- **R3（不覆寫使用者檔案）**：When a target path 已存在且不是先前由本
  installer 安裝（manifest 無記錄或 hash 不符），the installer shall 中止
  並列出衝突，不寫入任何檔案。
- **R4（來源）**：The global install shall 使用 shoal committed HEAD 的
  `hosts/opencode/dist`，plugin 在暫存目錄 build（沿用
  `~/dotfile/config/opencode-harness/install-pilotfish.sh` 的作法）。
- **R5（provider 檢查）**：When installing globally，the installer shall 以
  `<config-dir>/opencode.json` 的 `provider` keys 與 `enabled_providers` 的
  聯集作為已宣告 provider，對 `routing.json` 中不在聯集內的候選輸出警告
  （不中止）；auth 或環境變數型的 provider 無法由 `opencode.json` 驗證，
  只檢查是否宣告。
- **R6（既有行為不變）**：`--target <project>` 的行為、輸出與測試不變。
- **R7（dotfile）**：`~/.config/opencode` 是 dotfile 追蹤的目錄；安裝產生的
  agents 與 `pilotfish/*.json` 以獨立 commit 進 dotfile；plugin bundle 是 build
  產物，比照 `opencode-harness` 加入 `.gitignore`；manifest 與備份不進版控（R2）。dotfile 兩份 spec 記錄推翻原決定的日期與理由。

## Non-goals

- 不改 role 文字、選模與權限推導。
- 不讓 plugin 自動改寫既有 session 的 model。
- 不處理 `opencode-harness`（它已載入 plugin，維持現狀）。

## Phases

| Phase | 內容 | 驗收 |
|---|---|---|
| O1 | plugin 設定查找（R1）與去重（R2a） | bun 測試：專案 catalog 優先、全域 fallback、routing optional 回退 native、穿越拒絕、重複載入只註冊一次；`plugin-seam.test.ts:78` 等既有測試全綠 |
| O2 | installer `--global`（R2–R6） | 以 temp config dir 與 temp state dir 測 enable、disable、rollback（rollback 後 agents、plugins、`pilotfish/*.json` 全部消失）、衝突中止、provider 警告對 daily `opencode.json` 不誤報 deepseek；`--target` 測試不變 |
| O3 | 安裝到 `~/.config/opencode` 並 commit dotfile（R7） | 安裝後 hash 與 dist 一致；dotfile `git status` 只出現 R7 預期的檔案；OpenCode 的 tool 清單只有一個 `pilotfish_route`（無法查證時列為未驗證）；dotfile 兩份 spec 已註記 |

## Rollback

同一台機器：`install.sh --global --rollback`（使用 `<state-dir>` 的備份）。
其他機器或 state 遺失：revert dotfile 的安裝 commit。
