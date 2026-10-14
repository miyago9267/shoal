---
title: 模組化安裝：同一個 repo，使用者只裝選的模組
status: approved
approved_by: Miyago (2026-10-14)
created: 2026-10-14
updated: 2026-10-14
---

<!-- markdownlint-disable MD025 -->

# 模組化安裝：同一個 repo，使用者只裝選的模組

## Background

Miyago 2026-10-14：「我想要把 shoal 系列拆解出來，現在這包太肥了，如果要什麼的話就幫他裝模組」。
選定方向：留在同一個 repo，installer 只裝使用者選的模組；CI 與 tests 維持在一起；
拆成多個 repo 是之後的選項，不是現在。同日 roadmap（「開源專案方向規劃
2026-Q4」）：shoal 不再往 core 裡堆功能，只開一個擴充點給外掛模組接。

現況（main `7890a7c` 查證，只留影響設計的事實）：

- **Claude**：plugin `shoal@shoal`（source `./claude-plugin`）同時帶 role、skill、
  `policy/claude-md.bootstrap.md`、guard（`hooks/shoal_guard.py`）與
  `hooks/hooks.json`。dotfile `agent-stack-auto-update.sh:130` 只 `git archive`
  三個路徑，並把 `Explore.md` 另裝進 `~/.claude/agents/`。
  `tools/install_hooks.py --host claude` 是舊路徑，與 plugin 不並存。
- **Codex**：`install/install.py`（沒有模組旗標）寫 role TOML、AGENTS.md marker、
  `config.toml` 片段、`hooks.json`（guard 加 `shoal_autoroute_gate.py`）與 plugin。
  `shoal-codex` plugin 沒有 hook；`shoal-jev-router` 獨立列出。state 檔
  （`install.py:724`）記錄 `guard_registration`，沒有「選了哪些模組」。
- **agy**：`hosts/agy/dist` 由 dotfile `setup_gemini.sh:142` symlink；guard 走
  `install_hooks.py --host agy`。**Grok**：`tools/install_grok.py`（預設 dry-run）。
  **OpenCode**：`install.sh --global`，guard 與 role 同在
  `plugins/shoal-opencode.js`。
- **sync_global.py** 每日同步 codex、grok、agy、opencode（Claude 不在內）。它不讀
  模組選擇：codex 固定檢查 `jev_router_missing`（`:293`，缺就補裝）。
- guard 已有 `SHOAL_GUARD=enforce|shadow|off`（`shoal_guard.py:20`），今天「關
  guard」只能用環境變數，不是安裝選項。
- dev-only 重量：`docs`、`tests`、`install/` 的 benchmark 與 `role_fitness_*`、
  `tools/` 的 render 與 eval 腳本、`hosts/*/{src,frames,policy-frames,addenda}`。

## Requirements (EARS)

- **R1**：When 使用者執行 installer 且沒有指定模組，the installer shall 裝與今天
  相同的內容（該 host 的 core 加 host 模組、`dispatch-guard`，以及今天會裝的選配）。
- **R2**：When 使用者指定模組，the installer shall 只寫入這些模組的檔案與 hook
  entry，並把結果寫進 installed manifest。
- **R3**：The installer shall 一律裝 `core` 與 host 模組；`dispatch-guard` 與其他
  選配可以不裝。
- **R4**：When 沒有 manifest（既有機器），the installer 與 `sync_global.py` shall
  依實際存在的檔案推出模組，不新增、不移除。
- **R5**：While manifest 存在，`sync_global.py` shall 只同步 manifest 列出的模組，
  且不補裝未選的模組（包含 `jev_router_missing`）。
- **R6**：When 使用 `--dry-run` 或 `--list`，the installer shall 不寫入任何檔案，
  並列出將安裝或移除的模組與路徑。
- **R7**：When 使用者移除 `dispatch-guard`，the installer shall 只移除 shoal 的
  hook entry 與 guard 腳本，政策文字、role 與 skill 保持不變。
- **R8**：When guard chain 設有外部成員，`shoal_guard.py` shall 依序呼叫並合併
  結果；shoal 的程式碼 shall 不含任何特定外部模組的名稱。

## Module map

內建模組名 `dispatch-guard` 刻意和外部專案 `shoal-guard`（獨立 repo）區隔，避免混淆。

| 模組 | 內容 | 依賴 | 預設 | host |
|---|---|---|---|---|
| `core` | `core/`；render 進各 host dist，不單獨安裝 | 無 | 永遠 | 全部 |
| `host-claude` | `claude-plugin/{agents,skills,policy}`、`.claude-plugin/` | core | on | claude |
| `host-codex` | `templates/agents/`、`agents-md.*`、`config.snippet.toml`、`shoal-codex` | core | on | codex |
| `host-agy` | `hosts/agy/dist/{agents,rules,skills}` | core | on | agy |
| `host-grok` | `hosts/grok/dist/{agents,roles,rules}`、config snippet | core | on | grok |
| `host-opencode` | `agents/*.md`、`shoal/{catalog,routing}.json`、plugin 非 guard 部分 | core | on | opencode |
| `dispatch-guard` | `hooks/shoal_guard.py`；OpenCode 為 plugin 內 `src/guard/` | host 模組 | 新裝 on | 全部；關掉＝只有政策文字 |
| `codex-autoroute` | `hooks/shoal_autoroute_gate.py`、`templates/hooks.json` | host-codex | on | codex |
| `jev-router` | `plugin/plugins/shoal-jev-router` | host-codex | 新裝 off，既有機器維持現狀 | codex |
| `claude-explore` | `hosts/claude/dist/agents/Explore.md` 裝到 `~/.claude/agents/` | host-claude | 既有 on | claude |
| external module | 從自己的來源安裝；經 manifest 登記為 guard chain 成員。例：`shoal-guard`、之後的 jev-router | 無 | 使用者自選 | 依 manifest |

shoal 本身不附任何 external module 的程式碼。OpenCode 的 guard 與 role 能否切開
需讀碼確認（見 Open checks）。

## Installer UX

一個入口 `tools/shoal_install.py`，**薄前端**：只包住既有 installer，core 不加新邏輯。

```text
shoal install --host codex [--with dispatch-guard] [--without autoroute,jev-router]
shoal install --host claude --only core,host-claude    # 不要 dispatch-guard
shoal install --list [--host H]                        # 模組、依賴、已安裝狀態
shoal install --host H ... [--dry-run | --apply]       # 預設 dry-run
```

- 每個模組對應一個小函式呼叫既有 installer（codex 走 `install.py`，hook 走
  `install_hooks.py`，grok 走 `install_grok.py`，opencode 走 `install.sh --global`）。
  要新增的是 installer 內「略過某模組」的旗標，不是新流程。
- manifest：`${XDG_DATA_HOME:-~/.local/share}/shoal/modules.json`
  （`{host: {modules, version}, chain: [...]}`）。Codex install state 格式不動。
- 遷移：沒有 manifest 時由實際檔案推導（R4），第一次 `--apply` 才寫入。
- `sync_global.py` 讀 manifest 過濾模組；Claude 的模組選擇由 marketplace 的 plugin
  清單表達，不走 `sync_global.py`。

## 各 host 的打包單位

| host | 能否拆 base 與 guard |
|---|---|
| Codex | 已分開（plugin 無 hook；guard 與 autoroute 是 `hooks.json` entry），只缺 installer 旗標 |
| Claude | 需確認：第二個 plugin（`shoal-guard`）能否只帶 hook；`${CLAUDE_PLUGIN_ROOT}` 與 `--plugin` 路徑是否照常；role 是否仍是 `shoal:<role>` |
| agy、Grok | 看起來可分；需讀 installer 確認略過 hook 不影響 uninstall 與 drift 檢查 |
| OpenCode | 同一個 plugin JS，不確定；先不拆 bundle，用 `SHOAL_GUARD=off` 類設定 |

dev-only 重量留在 repo、不裝。Claude 本機路徑已只 archive 三個路徑；對外 GitHub
marketplace 是否只快取子目錄需要查。GitHub release 每 host 一個 tarball 為選配（S5）。

## Decisions

- **D1**：先做 manifest 與 installer 前端，不動既有 installer 的行為（S1 無
  behaviour change）。
- **D2**：`dispatch-guard` 以 hook entry 為單位開關，不改 guard 規則與 `SHOAL_GUARD`
  模式。
- **D3**：Claude 與 Codex plugin 拆分只在 S4 且查證可行後做；不可行就維持單一
  plugin，guard 用 installer 或環境變數控制。
- **D4**：`core` 不能獨立安裝；它是 render 的來源，產物隨 host 模組出貨。
- **D5**（2026-10-14 owner）：新裝時 `dispatch-guard` 預設 ON；`jev-router` 預設
  OFF（依賴 Jev 環境）。既有機器維持現有狀態（R4）。
- **D6**（roadmap）：installer 前端是薄層，只包既有 installer，core 不新增功能；
  對外只開一個擴充點，即 guard chain（S2）。
- **D7**：`shoal-guard` 是獨立 repo（多 session 寫入衝突 guard：claim ledger 在
  `$(git rev-parse --git-common-dir)/shoal-guard/`、一檔一 session、
  `shoal-guard stage` 只 stage 自己的 hunk、標出 formatter-only diff）。可單獨當
  hook 使用；搭配 shoal 時只經 guard chain 接入。

## Slices

| # | 內容 | 驗收 |
|---|---|---|
| S1 | `modules.json` schema、`--list`、`--dry-run`，各 host 預設等於現況；`sync_global.py` 讀 manifest（沒有時走推導） | unittest（schema、推導、sync 過濾）；每個 host 一次 dry-run，輸出與今天相同 |
| S2 | **Guard chain 擴充點（唯一改 core 的 slice）**，細節見下 | 見下 |
| S3 | `dispatch-guard`、`codex-autoroute`、`jev-router` 各 host 可選，`--without` 實作與移除 | unittest 加 `install_hooks --uninstall` 回歸；各 host 暫存 home apply 後 dry-run 為空 |
| S4 | Claude 拆 `shoal` 與 `shoal-dispatch-guard` plugin（已實作：`claude-guard-plugin/`，同一個 marketplace）；Codex 只補 installer 旗標 | live 僅 Claude 1 次：只裝 base 可派 role 且無 hook，再裝 guard 確認 hook 觸發 |
| S5 | README、INSTALL.md 的模組說明；release 範圍 | `bun run lint:md`、`scan_legacy_names.py` |

**S2 guard chain**：

- 設定：manifest 的 `chain` 陣列，每項 `{name, command (argv), hosts, order}`。
- 順序：依 `order` 升冪，`dispatch-guard` 自己的判斷先跑，再依序呼叫外部成員。
- deny 語意：任一成員 deny 即 deny（第一個 deny 的理由回給 host）。成員出錯、
  逾時或輸出不可解析，一律 fail-open 並寫一行 log，與 guard 現行 fail-open 一致。
- per-host：成員收到 host 的原始 payload（同一份 stdin JSON，roadmap 的
  「same stdin JSON」）；host adapter 只轉換輸出格式，不做特例。
- parity：Python（`shoal_guard.py`）與 TS（OpenCode `src/guard/`）以共用 vectors
  驗證行為一致。
- 驗收：shoal-guard 只靠設定就能接入（以 fake 外部成員測試），且 shoal 程式碼
  不含 `shoal-guard` 字樣（grep 為 0）。

## Non-goals

- 現在拆成多個 repo。
- 改 role 或 policy 文字。
- 改 guard 規則、模式或預設值（guard chain 只加呼叫外部成員）。
- 重寫既有 installer。
- 建置 shoal-guard 本身（獨立 repo）。

## Risks

- Codex state 驗證很嚴（`install.py:837-934`）；只拿掉 guard 或 autoroute 可能被
  判定 state 不符。S3 先確認既有 `guard_registration` 分支夠用，不繞過驗證。
- 兩個 plugin 的版本要同步，否則 base 與 guard 可能不相容。
- `jev_router_missing` 目前自動補裝；改讀 manifest 後，沒有 manifest 又缺 jev 的
  舊機器不能被視為「選擇不要」。
- dotfile 的 `setup_gemini.sh` 與 updater 在 repo 外，S1 要同步改。
- guard chain 每多一個外部成員就多一次 process 呼叫；逾時上限需定義，避免拖慢
  每次 tool call。

## Open checks

查證，不是決策：Claude 第二個 plugin 只帶 hook 是否可行；公開 marketplace 的快取
範圍；agy、Grok、OpenCode 略過 guard 後 uninstall 與 drift 檢查是否正常；chain
成員的逾時預設值。
