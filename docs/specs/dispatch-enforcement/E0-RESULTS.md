# E0 實測結果

2026-10-05 以 temp 專案與只記錄欄位名稱的 probe hook 實測。每個 host 跑一個
小 prompt：main 建立 `denyme.txt`（probe 回 deny），再派 write role 建立
`sub.txt`。probe 只記錄欄位名稱、型別與少數識別欄位，不記錄 prompt 或
tool_input 內容。

## 總表

| Host（版本） | deny 是否有效 | 本輪 id | subagent 辨識 | role 辨識 | 派工工具 | 編輯工具 |
|---|---|---|---|---|---|---|
| Claude Code 2.1.289 | 有效（`permissionDecision: deny`） | `session_id` + `prompt_id`（UUID） | payload 有 `agent_id` | `agent_type` | `Agent`（`tool_input.subagent_type`） | `Edit`、`Write`、`MultiEdit`、`NotebookEdit` |
| Codex CLI 0.160.0 | 有效（同上格式），`apply_patch` 被擋 | `session_id` + `turn_id`，沒有 `prompt_id` | `agent_id` | `agent_type` | `collaborationspawn_agent`（`tool_input.agent_type`） | `apply_patch`（`tool_input.command` 是 patch 全文） |
| Grok Build 1.0.46 | 有效（`{"decision":"deny"}`） | `sessionId` + `promptId` | subagent 有自己的 `sessionId`，payload 帶 `subagentType` | `subagentType` | `spawn_subagent`（`subagent_type`） | `search_replace`（`file_path`） |
| OpenCode 1.18.31 | 有效（`tool.execute.before` 丟例外） | `sessionID`（`ses_` 開頭，含底線） | `client.session.get` 的 `parentID` 不為 null | session 的 `agent` | `task`（`subagent_type`） | `apply_patch`（`patchText`）、`write`、`edit` |
| Gemini / agy 1.2.16 | 有效（`{"decision":"deny"}`），`write_to_file` 被擋 | `conversationId`，沒有 prompt id | subagent 是另一個 `conversationId`，payload 沒有任何 agent 欄位 | 無法辨識 | `invoke_subagent` | `write_to_file`（`TargetFile`） |

prompt 來源：五個 host 的 `UserPromptSubmit`（或對應事件）都沒有欄位分辨
使用者輸入與 model 排程的 prompt。

## 對設計的影響

1. **`#direct`**：依 R2，五個 host 都無法分辨 prompt 來源，所以不接受
   prompt 內的 `#direct`，改用環境變數 `SHOAL_GUARD_DIRECT=1`（整個
   session 放行）。
2. **agy**：無法分辨 main 與 subagent，依 R5 固定 shadow；R6 中靠 hook
   依 role 擋的項目不適用，只能用原生欄位。補測（同日）：`PreInvocation`
   每次模型呼叫都觸發，`invocationNum` 在一輪內從 0 遞增，只有 0 代表新的
   一輪；`invoke_subagent` 的 args 是
   `{"Subagents":[{"Model","Prompt","Role","TypeName"}]}`，派工 role 取
   `TypeName`。
3. **Codex**：本輪 id 用 `turn_id`。`apply_patch` 的檔案路徑要從 patch
   標頭（`*** Add File:`、`*** Update File:`、`*** Delete File:`、
   `*** Move to:`）解析。新 hook 必須經 Codex 的 hook trust（`hooks.state`
   的 `trusted_hash`）才會執行；installer 不代替使用者寫入 trust，安裝後
   要在互動 session 用 `/hooks` 核准一次。
4. **Grok**：預設也讀 `~/.claude/settings.json` 的 hooks（Claude 相容
   掃描）。Claude 註冊的 guard 會在 grok session 再跑一次，所以 adapter
   必須確認 payload 屬於自己的 host：Claude adapter 看到 `hookEventName`
   （grok 的 camelCase 欄位）時直接放行，由 grok 自己的註冊處理。
5. **OpenCode**：id 格式含底線，`ID_RE` 要允許 `_`。subagent 辨識需要
   呼叫 `client.session.get`。

## 順帶發現

- 本機全域安裝的 `~/.config/opencode/plugins/pilotfish-opencode.js` 在 live
  OpenCode 載入失敗：`failed to load plugin ... Plugin export is not a
  function`。E3 一併修正。
- Miyago 的 OpenCode 預設 agent `monika` 的 `task` 權限只允許少數
  subagent，不含 pilotfish 的 `executor`，所以 daily 環境派不出 executor。
  屬於 dotfile 設定，列在 E5 處理。
- 本機 grok CLI 原為 0.2.118，伺服器已拒絕（426），實測前已用
  `grok update` 更新到 1.0.46。
- Codex 第一次 probe 在 `~/.codex/config.toml` 寫入了 temp 目錄的 trust
  條目，已移除；agy probe 暫時修改的 `hooks.json` 已還原並逐位元組比對。
- grok 1.0.46 建立新檔用內建 `write_file`（`features.write_file` 預設
  true），不是 `search_replace`；guard 的 matcher 與 adapter 已補上。

## E4 實測：Codex per-role sandbox 與網路（2026-10-05）

以專案層 `.codex/agents/*.toml`（temp 專案，`codex exec -m gpt-6-luna`，
codex 0.160.0）讓 main 派 role，role 本身確實載入（回報帶 role 指定的字樣）。

| main 設定 | role 設定 | 結果 |
|---|---|---|
| `danger-full-access`（root config） | `sandbox_mode = "read-only"` | role 寫 workspace 內外都成功（rc=0） |
| `-s workspace-write` | `sandbox_mode = "read-only"` | role 寫 workspace 內成功，寫外部 `operation not permitted` |
| `-s workspace-write` | `workspace-write` 加 `[sandbox_workspace_write] network_access = true` | `curl` 失敗：`Could not resolve host` |

結論：0.160.0 的 subagent 繼承 main 的 runtime sandbox 與網路，role 檔的
`sandbox_mode` 與 `network_access` 都不生效。依 R6，Codex write 等級不輸出
`sandbox_mode`，維持現況並列為已知限制；Codex verifier 維持 `workspace-write`。
agy 沒有可證實的完整 tool 名單（無 `tools` 欄位的 agent 自報只有 10 個且缺
`run_command`），write 等級維持不加 allowlist，列為已知限制。
