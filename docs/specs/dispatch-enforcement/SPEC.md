---
title: Dispatch 強制與權限補強
status: approved
approved_by: Miyago
created: 2026-10-05
updated: 2026-10-05
---

<!-- markdownlint-disable MD025 -->

# Dispatch 強制與權限補強

## Background

Miyago 2026-10-05 決定：dispatch 的強制力全部由 shoal 提供，五個 host
要一樣強；role 權限補強一點。身分隔離（切 harness）等這份完成後再評估。

現況（2026-10-05 查證，main `0be0b84`）：

| Host | 現有強制 | 位置 |
|---|---|---|
| Claude Code | `PreToolUse` deny main 的直接改檔 | dotfile `config/ai/claude/hooks/pilotfish-dispatch-guard.py`，在 dotfile `settings.json:149`（PreToolUse）與 `:217`（UserPromptSubmit）註冊 |
| Codex CLI | `UserPromptSubmit` 注入選模訊號；`Stop` 在缺 plan-verifier 或需要升級時擋下結束 | shoal `hooks/pilotfish_autoroute_gate.py` |
| Grok Build | `PreToolUse`（matcher `^spawn_subagent$`）只在 plan mode 擋可寫入的 subagent；`SubagentStop` 檢查審查回報格式 | shoal `hosts/grok/dist/hooks/` |
| OpenCode | 無；plugin 只提供 `pilotfish_route` tool | shoal |
| Gemini / agy | 無 | — |

dotfile guard 的行為（要移植的對象）：

- `UserPromptSubmit` 記錄本輪狀態；`PreToolUse` 對 `Edit`、`Write`、
  `NotebookEdit`、`MultiEdit` 判斷，`Agent`、`Workflow` 視為已派工。
- 規則 R1：Jev 判定本輪是 judgment 或 mechanical 工作時，main 改檔一律
  deny，直到派出 agent。規則 R2：本輪沒派工時，main 直接改到第 3 個檔案
  就 deny（`PILOTFISH_GUARD_MAX_FILES`，預設 2）。
- prompt 含 `#direct` 時放行；`/tmp`、`$TMPDIR`、`.claude/projects/`、
  `.ai/` 不計。payload 有 `agent_id`（subagent）時不介入。
- `PILOTFISH_GUARD=enforce|shadow|off`，例外一律 fail-open，log 寫在
  `~/.local/state/miyago/jev/`。
- 依賴 dotfile `config/ai/shared/jev/pilotfish_route.py` 與 `jev-route.sh`
  寫出的本輪分類。

各 host 的 hook 能力：

| Host | 能否 deny 工具呼叫 | 依據 | 能否分辨 subagent |
|---|---|---|---|
| Claude Code | 可以 | 現行 guard | payload 的 `agent_id` |
| Codex CLI | 文件說可以：`apply_patch`、Bash、MCP、本地 function tool | 官方 hooks 文件（2026-10-05 讀取）；與 `subagent-service-tier-guard` 2026-07-16 的結論相反，本機 0.160.0 未實測 | 未知 |
| Grok Build | 可以：`{"decision":"deny"}` 或 exit 2；`Edit`/`Write` 對應 `search_replace` | `~/.grok/docs/user-guide/10-hooks.md:90、160-168、238-249` | 未知 |
| OpenCode | 型別有 `tool.execute.before` | `@opencode-ai/plugin` `index.d.ts:235`；丟例外能否擋未實測 | 未知 |
| Gemini / agy | 有 `PreToolUse` 事件（orca 使用中） | dotfile `config/ai/gemini/hooks.json:42`；能否 deny 未知 | 未知 |

權限缺口：

- Codex 的 write 等級沒有輸出 `sandbox_mode`，role 繼承 main 的設定；
  本機 main 是 `danger-full-access` 加 `approval_policy = "never"`。
- Codex 的 verify 等級是 `workspace-write`，verifier 可以改 repo 檔案。
- OpenCode 的 executor、security-executor 沒有 permission（OpenCode 不提供 mech-executor），
  沒有 `task: deny`，可以再派 subagent，違反 leaf 原則。
- agy 的 write 等級沒有工具欄位。
- Claude verifier 與 grok `execute` 擋了編輯工具，但 shell 仍可寫檔；Claude
  verify 的 denylist 沒有 `MultiEdit`（`hosts/claude/binding.toml:27`）。

定位：guard 是 policy 的強制推力，不是 security boundary。main 一律保有
shell，與 guard 同一個 uid 的 model 可以刪掉 state、改設定或環境變數關掉
guard；這類竄改列為已知限制，guard 只負責擋「不經 shell 的直接越權」。

## Requirements (EARS)

- **R1（單一來源）**：dispatch guard 的判斷邏輯 shall 只存在於 shoal，
  每個 host 只寫一層 adapter 轉換 hook 的輸入與輸出格式。dotfile 不再
  保留判斷邏輯。
- **R2（同等規則）**：When main session 在某 host 要直接改檔，the guard
  shall 套用與現行 Claude guard 相同的規則：R1 分類規則、R2 檔案數規則、
  `#direct`、豁免路徑、派工後本輪放行。門檻與訊息在五個 host 相同。
  另外修正現行 guard 的兩個 bypass：
  - 路徑先 `realpath`（不存在時 `normpath`）再判斷豁免與計數，
    `/tmp/../repo/x` 這類路徑不得視為豁免。
  - 只有派出 write 等級的 role（`executor`、`mech-executor`、
    `security-executor`）才算本輪已派工；派 scout、Explore 等唯讀 role
    不解鎖。
  - `#direct` 只在使用者輸入的 prompt 生效；若某 host 無法分辨 prompt
    是使用者輸入還是 model 排程（`/loop`、wakeup、goal continuation），
    該 host 不接受 `#direct`，改用環境變數放行。
- **R3（分類器選配）**：分類規則 shall 透過 provider 介面讀取本輪分類；
  沒有 provider 時只套用檔案數規則。shoal 不依賴 dotfile 或 Jev。
- **R4（失效安全與檔案安全）**：The guard shall 支援
  `SHOAL_GUARD=enforce|shadow|off`（`PILOTFISH_GUARD` 為相容別名），
  任何例外 fail-open。state 與 log 放在
  `${XDG_STATE_HOME}/shoal/guard/`；`XDG_STATE_HOME` 未設定或不是絕對
  路徑時用 `~/.local/state`。沿用現行的檔案防護：目錄 0700、檔案 0600、
  `O_NOFOLLOW`、owner 必須是本人、上層不得是 symlink、session 與
  prompt id 以白名單格式驗證。
  - 每次 fail-open 或略過（例如缺 id）記一筆不含內容的 `skip_reason`。
  - log 只允許固定欄位（event、tool、rule、decision、檔名 basename、
    skip_reason）；不得記錄 prompt、`tool_input` 或 raw payload。
- **R5（不擋 subagent）**：The main 規則 shall 不作用於 subagent。某 host
  無法分辨 main 與 subagent 時，該 host 的 guard 固定為 shadow，並在
  README 已知限制寫明。
- **R6（權限補強）**：凡是靠 hook 依 role 擋的項目，前提是 E0 證實該
  host 的 hook 能辨識呼叫者的 role；不能辨識時改用原生欄位，兩者都沒有
  就列為已知限制。
  - 所有 host 的 write 等級 shall 不能再派 subagent：有原生欄位就用
    （OpenCode `task: deny`），沒有就由 hook 在 subagent 呼叫派工工具時
    deny。
  - Codex 的 write 等級 shall 輸出 `sandbox_mode = "workspace-write"`；
    E4 以 temp home 驗證 per-role 設定確實覆蓋 main 的
    `danger-full-access`（executor 寫 workspace 外的路徑要失敗）。
  - verify 等級 shall 不能使用編輯工具：Codex verifier 由 hook deny
    `apply_patch`；其他 host 維持現有原生欄位。shell 寫檔不擋（測試要寫
    cache），所以 Codex verifier 在 `workspace-write` 下仍可經 shell 改
    repo，這個 deny 只擋編輯工具，列為已知限制。
  - Claude verify 等級的 `disallowedTools` 補上 `MultiEdit`。
  - agy 的 write 等級依 E0 結果補工具欄位或 hook。
  - Codex write 等級開網路、verify 不開（`network_access`）。E0 確認
    per-role 設定可行；不可行時 write 等級維持現況並列為已知限制，不讓
    executor 失去 `bun install` 等能力。
- **R7（安裝）**：shoal shall 負責五個 host 的 guard 安裝與註冊，保留
  非 shoal 的既有 hook；disable／rollback 一併移除。各 host 的寫入點：

  | Host | 由誰寫入 | 寫到哪裡 | event |
  |---|---|---|---|
  | Claude Code | 新增 `tools/install_hooks.py --host claude`；dotfile auto-update 改呼叫它 | `~/.claude/settings.json`（`CLAUDE_CONFIG_DIR` 優先） | `UserPromptSubmit`、`PreToolUse` |
  | Codex CLI | `install/install.py`，新增 guard 的 projection ID 並擴充 state inventory | `~/.codex/hooks.json`、`~/.codex/hooks/` | `UserPromptSubmit`、`PreToolUse` |
  | Grok Build | `tools/install_grok.py` | `~/.grok/hooks/pilotfish-grok.json` | `UserPromptSubmit`、`PreToolUse` |
  | OpenCode | plugin 本身（`tool.execute.before`） | 隨 plugin 安裝 | plugin hook |
  | Gemini / agy | `tools/install_hooks.py --host agy`（E0 確認可擋才做） | `~/.gemini/config/hooks.json` | 依 E0 |

  `install_hooks.py` 只增刪以 shoal 標記的 entry，不碰其他 hook。
- **R8（行為一致的證明）**：Python 與 TypeScript（OpenCode）兩份實作
  shall 通過同一份測試向量 `tests/fixtures/guard_vectors.json`，至少涵蓋：
  `..` 與 symlink 路徑、派 scout 後改第 3 個檔要 deny、派 executor 後
  allow、缺 id 時記 `skip_reason`、log 欄位白名單、XDG 未設定或為相對
  路徑、目錄是 symlink、檔案 owner 不同。

## Non-goals

- 不偵測 main 透過 shell 寫檔（啟發式擋不完整，列為已知限制）。
- 不做身分隔離與切 harness（第 3 步，另案）。
- 不新增 role，不改選模，不改 Jev 分類器本身。
- 不擋 subagent 的 shell 寫檔。

## Decisions

1. **程式位置**：`hooks/shoal_guard.py`，只用標準函式庫，Claude、Codex、
   grok、agy 共用；各 host 的 adapter 只處理事件欄位名稱（例如 grok 是
   camelCase）與輸出格式。
2. **OpenCode 用 TypeScript 移植**，不讓 plugin 依賴 Python；以 R8 的
   測試向量保證兩份行為相同。
3. **分類 provider**：guard 讀
   `${XDG_STATE_HOME}/shoal/guard/turns/<session>.json`（`prompt_id`、
   `role`）。Jev 改成寫這個檔案的 provider，留在 dotfile。
4. **Claude 的切換**：shoal guard 安裝並驗證後，dotfile 移除舊 guard 的
   註冊（dotfile 獨立 commit），避免同一事件跑兩次。
5. **版本**：受影響 host 各自 bump `hosts/<host>/VERSION`，CHANGELOG 開
   v1.3.0 段。Codex 的 `templates/hooks.json` 是 lock surface，E2 的變更
   走 lock 預算並 bump `hosts/codex/VERSION`。
6. **Codex 與 autoroute gate 並存**：guard 用獨立的 script 與 projection
   ID，不併入 `pilotfish_autoroute_gate.py`。兩者都掛 `UserPromptSubmit`，
   guard 在這個事件只寫 state、不輸出 context，不影響 gate 的選模訊號；
   `PreToolUse` 只有 guard 使用。

## Phases

| Phase | 內容 | 驗收 |
|---|---|---|
| E0 | 實測各 host 的 deny 能力、session／prompt id 欄位與格式、subagent 與 role 辨識欄位、prompt 來源能否分辨、Codex 每 role 網路與 sandbox 設定 | 每個 host 一列結果，附指令與實際輸出；未能確認的列為限制 |
| E1 | `shoal_guard.py` 核心、測試向量、Claude adapter；Jev provider 改寫新路徑 | 測試向量全過；shadow 模式與 dotfile guard 對照，除 R2 列出的差異外逐筆一致，差異逐筆標註對應的 R2 項目 |
| E2 | Codex、grok adapter | 各 host 單元測試；E0 確認可擋的 host 以 temp home 實測 deny；Codex 在既有已安裝的 home 上 reinstall 不觸發 `installed_hook_drift`，`validate_prompt_lock` 綠 |
| E3 | OpenCode TS 移植、agy adapter（若 E0 可行） | 測試向量全過；bun test、typecheck 綠 |
| E4 | R6 權限補強：binding、render、golden、lock | 五個 host `--check` 綠；lock 依 host bump；`--explain` 顯示新欄位 |
| E5 | 依 R7 安裝與註冊；dotfile 移除舊 guard 兩處註冊 | Claude：enforce，全域安裝後實際擋下一次 main 越權改檔，並放行一次派工後的改檔。其他 host：shadow，在 temp home 產生 `would_deny` 與派工後 allow 各一筆 |
| E6 | 非 Claude host 切 enforce（條件化，逐 host） | 符合 Open question 1 的條件後切換，該 host 實際擋下一次 |

E0 需要少量 live 呼叫（每個 host 一個小 prompt），執行前取得核准。

## 已知限制

- guard 在 Windows 為 no-op（依賴 POSIX 語意），不支援 Windows。
- guard 不防同 uid 的 model 經 shell 竄改 state、設定或環境變數。
- main 與 subagent 經 shell 寫檔都不擋。
- Codex verifier 的 `apply_patch` deny 只擋編輯工具，不擋 shell 寫檔。
- 無法辨識 subagent 或 role 的 host，對應規則維持 shadow（R5、R6）。
- Codex 0.160.0 的 subagent 繼承 main 的 sandbox 與網路，role 檔的
  `sandbox_mode`、`network_access` 不生效（E0-RESULTS 的 E4 實測），所以
  Codex write 等級不輸出 `sandbox_mode`，role 層的限制只能靠 hook。
- agy 沒有可證實的完整工具名單，write 等級不加 allowlist；agy 也無法辨識
  role，所以 write role 能否再派 subagent 目前沒有強制手段。

## Rollback

- 單一 host：`SHOAL_GUARD=off`，或該 host installer 的 disable。
- 全部：revert 對應 commit；dotfile 舊 guard 的移除是獨立 commit，可單獨
  revert 回到現況。

## Open questions

1. **非 Claude host 何時切 enforce**：建議以 shadow log 為條件，不設
   固定天數：每個 host 至少 20 筆決策、至少 1 筆 `would_deny`、誤擋 0、
   `skip_reason` 比例 0（避免 guard 因缺 id 一直略過，看起來卻零誤擋）。
2. **（已寫入 R6，待核准）Codex executor 的網路**：write 等級開網路，
   verify 不開。
3. **（已決定，2026-10-05，採建議）deny 訊息的語言**：英文；
   `SHOAL_GUARD_LANG=zh-TW` 切繁中。
