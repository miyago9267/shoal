---
title: 每個 gate 都掛上 guard：改檔只來自可寫的 shoal role
status: proposed
created: 2026-10-13
updated: 2026-10-13
---

<!-- markdownlint-disable MD025 -->

# 每個 gate 都掛上 guard：改檔只來自可寫的 shoal role

## Background

Miyago 2026-10-13 兩句話：「只要有對應的 hook 可以當成事件閘門就要掛上去」；
範圍是「需要通用，claude 和 codex 都要擋，其餘只要有 harness 的 agent 也都得要能
擋，例如 opencode、pi、grok 等等」。

同日實測（`docs/specs/shared-rules/PROGRESS.md:147-152`）：Codex 的可寫 role 暫時
不可用時，main 改派內建的 `worker`（不是 shoal 的 role）改檔，沒有任何東西擋它。

現況（HEAD `15eae38` 查證）：

- 子 agent 改檔只擋 verify 類 role：`hooks/shoal_guard.py:943`
  （`role_access(role) == "verify"`）。type 不是 shoal role 時 `role_access` 回
  None（`:444`），所以可以改檔。
- main 解鎖：只有 Claude 等 `SubagentStart`（`START_UNLOCK_HOSTS`，`:121`）；
  其他 host 在派工呼叫當下解鎖（`:1171-1180`）。
- host 預設模式（`:80-85`）：claude、codex enforce；grok、agy shadow。agy 強制
  shadow（`:87`），因為 tool payload 分不出 main 與 subagent。
- deny 輸出：claude、codex 用 `hookSpecificOutput` 的 `permissionDecision`；其他
  host 走通用的 `{"decision": "deny"}`（`:1699-1711`），沒有證據顯示 grok 會遵守。
- Stop 完成檢查只在 claude、codex（`STOP_HOSTS`，`:94`）。
- OpenCode TS mirror 只訂閱 `chat.message` 與 `tool.execute.before`
  （`hosts/opencode/plugin/src/guard/opencode.ts:65,111,126`），deny 靠 throw；
  非 edit、非 `task` 的工具直接 return（`:133`），所以 shell 寫檔沒被看到；沒有
  結束事件的檢查。
- Codex 沒註冊 `PostToolUse`（`install/hook_registration.py` 只有
  `UserPromptSubmit`、`PreToolUse`、`Stop`）。repo 沒有 spawn 工具的
  `tool_response` 形狀，也沒有 spawn 失敗的 payload 紀錄
  （`tests/fixtures` 與 specs 中只有 `shared-rules/SPEC.md` D6 提到
  `tool_response` 一詞，無欄位紀錄）。
- Grok 註冊 `UserPromptSubmit`、`PreToolUse`、`SubagentStop`
  （`hosts/grok/src/hooks/shoal-grok.json`）；沒有 Stop payload 紀錄。

## Requirements (EARS)

- **E1（改檔只來自可寫的 shoal role）**：While guard 為 enforce，when 不是 shoal
  可寫 role 的 subagent 呼叫 edit 工具或以 shell 寫檔，the guard shall deny；例外
  只有兩個：使用者 prompt 帶獨立的 `#direct`，或該 agent type 列在
  `SHOAL_GUARD_WRITE_AGENTS`（逗號分隔，預設空）。deny 訊息寫出這兩個出口。既有
  規則（main 改檔、verify role 不得改檔、leaf 不得派工、main 的背景 shell）不變。
- **E2（派工不因名稱被擋）**：Where 派出的 agent type 不是 shoal role，the guard
  shall 放行這次派工（唯讀用途合法），且不因此解鎖 main 的改檔；寫入由 E1 把關。
- **E3（以啟動為準）**：Where host 有事件證明被派的 role 已啟動（Claude
  `SubagentStart`；Codex：依實測 payload 在「第一個帶該 role `agent_id` 與
  `agent_type` 的 tool 事件」與「spawn 工具的 `PostToolUse`」擇一；OpenCode：帶
  `parentID` 與 agent 名稱的子 session），the guard shall 以它而不是派工呼叫當作
  「可寫 role 已派出」。沒有此類事件的 host 維持依呼叫判斷，文件寫明。
- **E4（每個能擋的 host 都要擋）**：規則只定義一次（Python guard 與 TS mirror 以
  共用向量保持一致）。host 要進 enforce，須有 live payload 證明兩件事：hook 能
  deny，且 payload 分得出 main 與 subagent。目標：claude、codex、opencode
  enforce；grok 在 live 證明 deny 被遵守後 enforce；agy 以現行 CLI 重測，若仍分
  不出 main 與 subagent 就維持 shadow 並記錄證據。
- **E5（shell 寫檔也算）**：OpenCode 的 guard shall 涵蓋 shell 寫檔（與 Python
  guard 的 G5 相同的字面偵測）與 E1。
- **E6（結束事件）**：Where host 有可被 hook 阻擋的 turn 結束事件（待實測：
  OpenCode `session.idle`、Grok），the guard shall 掛上 shared-rules 的 B2/B3 完成
  檢查；否則記錄為不可用。
- **E7（先取得 payload）**：在某 host 啟用規則前，shall 以一次 live 執行取得該規則
  依賴的真實 payload，把欄位形狀（只存欄位名，不存內容）存到 `tests/fixtures`；
  不依猜測的形狀啟用。
- **E8（新 host 檢查表）**：`docs/DESIGN-INVARIANTS.md` shall 增加：有 harness 的
  host 必須把每個能當 gate 的事件掛到 guard；掛不上的列出原因與證據。沒有這張表
  就不接受新的 host binding。`pi` 目前不是 shoal host，加入時以此為進入條件。

## Decisions

- **D1**：擋「寫」，不擋「派工的名稱」（E1/E2）。原因：其他 plugin 的唯讀 agent
  仍可用，規則也不需要維護各 host 內建 agent 名單。
- **D2**：allowlist 用環境變數，不寫進政策文字。原因：使用者自己的 agent（例如
  statusline setup）是每台機器各自的事實。
- **D3**：先有證據再啟用（E7）。原因：2026-10-13 有兩個猜測被推翻（agy 的 tools
  省略不等於不受限；Codex 會退而用 `worker`）。
- **D4**：本 spec 只在找到啟動事件的 host 上取代 `guard-declared-direct` M11 的
  「沒有 start event 的 host 維持依呼叫判斷」。

## Slices

每個 slice 一個 commit；live 次數是待核准的預算。

| # | 內容 | 驗收 |
|---|---|---|
| S1 | E1/E2 於 Python guard 與 TS mirror，共用向量；claude、codex 生效 | 向量、unittest；live：Claude 1（general-purpose 改檔被擋）、Codex 1（移走可寫 role 後 `worker` 改檔被擋，main 回報） |
| S2 | Codex 取得 payload（E7）後做 E3 | captured 形狀 fixture；live：Codex 2（成功與 spawn 失敗各一）加 1 次複測 |
| S3 | OpenCode：E5、E1、預設 enforce；有證據才做 E6 | bun test；live：OpenCode 3 |
| S4 | Grok：deny 是否被遵守、Stop payload，只啟用有證據的 | live：Grok 3 |
| S5 | agy 重測 main 與 subagent 的區分 | live：agy 2 |
| S6 | E8 不變式文字、docs、版本、CHANGELOG | CI 三個平台 |

## Non-goals

- 不做指令分類器。
- 不依 agent 名稱擋派工。
- 本 spec 不把 `pi` 加為 host。

## Risks

- E1 會擋掉「非 shoal agent 合法改檔」的流程。緩解：`#direct`、
  `SHOAL_GUARD_WRITE_AGENTS`、deny 訊息同時寫出兩者。Claude 內建會改檔的 agent
  清單，repo 文件查不到，列在 S1。
- OpenCode、Grok 若 main 與 subagent 的訊號有誤，enforce 會擋掉正常工作。緩解：
  E7，且先 shadow 跑一次再開 enforce。
- hook 註冊變更後，Codex 要再用 `/hooks` 核准一次。

## Open questions

設計無。需要 Miyago 核准本 spec，以及 live 預算：Claude 1、Codex 4、OpenCode 3、
Grok 3、agy 2。
