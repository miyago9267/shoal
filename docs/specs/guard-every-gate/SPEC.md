---
title: 每個 gate 都掛上 guard：改檔只來自可寫的 shoal role
status: approved
approved_by: Miyago (2026-10-13)
created: 2026-10-13
updated: 2026-10-14
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
  shadow（`:87`），因為 tool payload 分不出 main 與 subagent。（S5 後：agy 預設 enforce，見 E8
  agy 表。）
- deny 輸出：claude、codex 用 `hookSpecificOutput` 的 `permissionDecision`；其他
  host 走通用的 `{"decision": "deny"}`（`:1699-1711`），沒有證據顯示 grok 會遵守。
- Stop 完成檢查只在 claude、codex（`STOP_HOSTS`，`:94`）。
- OpenCode TS mirror 只訂閱 `chat.message` 與 `tool.execute.before`
  （`hosts/opencode/plugin/src/guard/opencode.ts:65,111,126`），deny 靠 throw；
  非 edit、非 `task` 的工具直接 return（`:133`），所以 shell 寫檔沒被看到；沒有
  結束事件的檢查。
- Codex 原本沒註冊 `PostToolUse`（`install/hook_registration.py` 只有
  `UserPromptSubmit`、`PreToolUse`、`Stop`；3.6.0 的 `shoal-guard-v5` 為完成檢查
  補上）。repo 沒有 spawn 工具的
  `tool_response` 形狀，也沒有 spawn 失敗的 payload 紀錄
  （`tests/fixtures` 與 specs 中只有 `shared-rules/SPEC.md` D6 提到
  `tool_response` 一詞，無欄位紀錄）。
- guard 的 subagent 路徑不讀任何 state：subagent 的 tool 事件直接進
  `subagent()`，只看 role 與 tool kind（`hooks/shoal_guard.py:937-960`、
  `:1425-1427`）。`direct` 只存在 main session 的 state 檔，由 prompt 事件寫入
  （`:1143-1162`）。OpenCode mirror 的 prompt 事件沒有 `direct`
  （`opencode.ts` 無此欄位）。
- 沒有任何 host 紀錄過 subagent 的 tool-call payload（只有 Claude
  `SubagentStart`：`tests/fixtures/claude_subagent_start_shape.json`；
  `codex_payload_shapes.json` 無 subagent 樣本），所以不知道它是否帶 main 的
  `session_id` 或 turn id，也不知道 Codex 對 subagent 的 `apply_patch`/`Bash`
  是否觸發 PreToolUse 並帶 `agent_type`。
- Claude `Workflow` 是沒有 role 的派工（`:1532-1540`），子 agent type 無紀錄；
  OpenCode 的 role 取自 `session.agent`（`opencode.ts:80`）。
- Grok 註冊 `UserPromptSubmit`、`PreToolUse`、`SubagentStop`
  （`hosts/grok/src/hooks/shoal-grok.json`）；沒有 Stop payload 紀錄。

## Requirements (EARS)

- **E0（先取得 subagent 的 payload）**：本 spec 任何規則啟用前，shall 以 live
  執行取得：Claude 與 Codex 的 SUBAGENT 的 edit 與 shell tool 事件欄位形狀（是否
  帶 main 的 `session_id`、turn/prompt id、`agent_id`、`agent_type`；Codex 是否
  對 subagent 觸發 hook）、Claude `Workflow` 子 agent 的 tool 事件，以及 Codex
  spawn 工具成功與失敗的 `PostToolUse`。只存欄位名到 `tests/fixtures`。E7 是通則，
  E0 是它的第一個應用。
- **E1（改檔只來自可寫的 shoal role）**：While guard 為 enforce，when 不是 shoal
  可寫 role 的 subagent 呼叫 edit 工具或以 shell 寫檔（字面偵測同 main），the
  guard shall deny；`is_exempt` 路徑與 main 相同地放行。任何 host 都可用的出口：
  `SHOAL_GUARD_WRITE_AGENTS`（agent type 逗號清單，預設空）與
  `SHOAL_GUARD_DIRECT=1`。使用者 prompt 的 `#direct` 只在 E0 證明 subagent
  payload 讓 guard 找得到當前 turn 的 main state 的 host 才能放行 subagent；其他
  host 的 `#direct` 只放行 main 自己的改檔，且 deny 訊息只列該 host 有效的出口。
  查找候選兩種，E0 後擇一：以 main `session_id` 查 state；或派工時寫以
  `agent_id` 為鍵的 per-dispatch marker。既有規則（main 改檔、verify role 不得
  改檔、leaf 不得派工、main 的背景 shell）不變。
- **E1 與 Workflow / host 內建 agent**：同一規則，無特例。非 shoal 可寫 role 的
  Workflow 子 agent 或內建 agent，改檔一律 deny，除非在 allowlist。結果：會改檔
  的 Workflow 腳本必須派 shoal role；子 agent 能否如此由 E0 檢查（見 Open
  questions）。
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
- **E8（新 host 檢查表）**：`docs/DESIGN-INVARIANTS.md` shall 增加（invariant 3
  的文字在首次啟用 E1 的 slice S1b 同步更新，不留到最後）：有 harness 的
  host 必須把每個能當 gate 的事件掛到 guard；掛不上的列出原因與證據。沒有這張表
  就不接受新的 host binding。`pi` 目前不是 shoal host，加入時以此為進入條件。
  五個 host 的表：Claude、Codex、Grok 在本檔「Requirements」之後與「Decisions」之前的
  各個 E8 檢查表節，agy 在本檔最後一節，OpenCode 在
  [INSTALL.md](../../../INSTALL.md#claude-上-guard-的行為300-起)。

### E8 檢查表：Grok（S4，Grok CLI 1.0.46，2026-10-13；payload 見 `tests/fixtures/grok_guard_event_shapes.json`）

| 事件 | 掛上？ | 規則 | 沒掛的原因／證據 |
|---|---|---|---|
| `pre_tool_use`（`write`、`search_replace` 等 edit 工具） | 是 | R1（strict）、E1、VERIFY_EDIT | deny 已實測被遵守（main 與 subagent 的 `write`） |
| `pre_tool_use`（`run_terminal_command`） | 是（S4 新增 matcher） | G5（strict 的 shell 寫檔）、E1 的 shell 寫檔、B2 的檢查記錄 | 欄位 `toolInput.command` 已取得；背景 shell 無對應旗標，G4 不適用 |
| `pre_tool_use`（`spawn_subagent`） | 是 | 記 pending dispatch；subagent 呼叫則 LEAF | deny 對 dispatch 已實測有效 |
| `subagent_start` | 是（S4 新增） | E3（以啟動為準）、記錄 subagent id -> 主 session／role／`#direct` | 在主 session id 下送出，帶 `subagentId`、`subagentType` |
| `user_prompt_submit` | 是 | `#direct` 偵測、回合邊界 | 帶 `prompt`、`promptId` |
| `stop`（`reason == end_turn`） | 是，預設 shadow（S4 新增） | B2/B3 完成檢查 | `{"decision":"block"}` 依文件可擋但**未實測**，待 live；session 結束時的第二次 `stop` 不帶 `end_turn`，忽略 |
| `subagent_stop` | 是（既有的格式 gate，非 guard） | verifier／plan-critic／security-reviewer 的輸出格式 | 與 guard 無關 |
| `post_tool_use`、`session_start`、`session_end` | 否 | 無 | B2 仍以 `PreToolUse` 的前景 shell 呼叫記錄（本 host 的完成檢查只記錄，沒有註冊 `PostToolUse` 的版本）；其餘無規則需要它們；`post_tool_use` 的 `spawn_subagent` 結果只能事後確認，E3 已由 `subagent_start` 取代 |
| 派出不存在的 role | 未知 | 無 | 實測不確定（一次觀察像是起了通用 subagent 而非報錯）；若起了通用 subagent，其 `subagent_start` 的型別不是 shoal 可寫 role，E1 照常擋它的寫入 |

### E8 檢查表：Claude（S2，Claude Code 2.1.x，2026-10-13；payload 見 `tests/fixtures/claude_subagent_tool_shapes.json`、`claude_subagent_start_shape.json`、`stop_payload_shapes.json`）

註冊在 `claude-plugin/hooks/hooks.json` 與 `tools/install_hooks.py --host claude`。

| 事件 | 掛上？ | 規則 | 沒掛的原因／證據 |
|---|---|---|---|
| `UserPromptSubmit` | 是 | `#direct` 偵測、回合邊界（`prompt_id`） | 帶 `prompt`、`prompt_id` |
| `PreToolUse`（matcher `Edit\|Write\|NotebookEdit\|MultiEdit\|Agent\|Workflow\|Bash`） | 是 | R1／G5（strict）、E1、VERIFY_EDIT、LEAF、G4、R2、B2 的檢查記錄（有 `PostToolUse` 之後只作後備）、記 pending dispatch | deny 已實測被遵守；subagent 的 Write／Edit／Bash 都會觸發，`Bash` 帶 `tool_input.command`。其他工具（`Read`、`Grep` 等）不在 matcher：沒有規則需要 |
| `PostToolUse`（matcher `Bash`） | 是（attached）：completion check counts executed shell calls（3.6.0 起） | B2：main 的前景 `Bash`（不寫檔、不是宣告）執行完才把 `checked` 設為真；同時記 `post_seen`。subagent 的 `PostToolUse`（帶 `agent_id`）不算；背景 `Bash` 不算 | 工具已經執行完才觸發（payload 帶 `tool_response`、`duration_ms`），無法阻止任何事；使用者拒絕或沒跑成的呼叫不會觸發，所以 `PreToolUse` 只代表「嘗試」。舊註冊（沒有這個事件）的後備：同一個 session 在第一次看到 `PostToolUse` 之前，`PreToolUse` 的前景 `Bash` 仍算；看過一次之後 `PreToolUse` 不再算。Claude 的非零 exit 改走 `PostToolUseFailure`（2.1.x 實際看到 hook 標為 `PostToolUseFailure:Bash`），所以另掛 matcher `Bash` 的 `PostToolUseFailure`，adapter 與 `PostToolUse` 同一規則（main 才算、subagent 與背景不算）。失敗事件的 payload shape 未擷取，adapter 只依賴 `tool_name`、`tool_input.command`、`tool_input.run_in_background`、`agent_id`、`session_id`、`prompt_id`（不讀 `error`／`tool_response`）；形狀不符就 fail-open |
| `SubagentStart` | 是（3.3.1 起） | E3（以啟動為準釋放 pending dispatch）、`#direct` 對 subagent 的放行 | 帶 `agent_id`、`agent_type`、與 main 相同的 `session_id`；Workflow 的 child 也會觸發 |
| `SubagentStop` | 否 | 無 | 目前沒有規則需要 subagent 的結束：完成檢查擋的是 main 的 `Stop`。payload 帶 `agent_transcript_path`、`last_assistant_message`、`stop_hook_active`；能否擋 subagent 的結束未實測 |
| `Stop`（main） | 是（3.4.0 起） | B2/B3 完成檢查 | payload 已實測；guard 的 `{"decision":"block"}` 有送出一次（fixture `facts`），Claude 如何處理該輸出未實測（`stop_payload_shapes.json`），失效時只是照常結束 |
| `SessionStart` | guard 沒掛；plugin 另掛 `emit-sessionstart.sh` 注入 bootstrap | 無 | 該 hook 不是 guard；沒有規則需要 session 開始事件（fixture 未記錄其 payload） |
| fixture 未列出的其他事件 | 否 | 無 | 未實測；沒有規則需要 |

### E8 檢查表：Codex（S3，codex-cli 0.160.1，2026-10-13）

payload 見 `tests/fixtures/codex_payload_shapes.json`、
`codex_subagent_tool_shapes.json`（後者的 `events_codex_supports` 列 11 個事件）。

註冊在 `install/hook_registration.py`（`shoal-guard-v5`；v4 加 `SubagentStart`，v5 加 `PostToolUse`），由
`tools/install_hooks.py --host codex` 與 `install/install.py` 寫入 `hooks.json`；
新增的群組要在 Codex 用 `/hooks` 核准。

| 事件 | 掛上？ | 規則 | 沒掛的原因／證據 |
|---|---|---|---|
| `PreToolUse`（matcher `^(apply_patch\|spawn_agent\|collaborationspawn_agent\|Bash)$`） | 是 | R1／G5（strict）、E1、VERIFY_EDIT、LEAF、記 pending dispatch、B2 的檢查記錄（有 `PostToolUse` 之後只作後備） | subagent 的 `apply_patch`、`Bash` 帶 `agent_id`、`agent_type`；`Bash` 的 `tool_input` 只有 `command`，沒有 `run_in_background`（故無 G4）。其他工具不在 matcher：沒有規則需要 |
| `PermissionRequest` | 否 | 無 | 在 `events_codex_supports` 內，但三次實測都沒有出現（`events_seen` 不含它），payload 與能否擋都未實測。改檔與 shell 閘門已在 `PreToolUse`，目前沒有規則需要它；E7 規定沒有實測 payload 不啟用 |
| `PostToolUse`（matcher `^Bash$`） | 是（attached，`shoal-guard-v5`）：completion check counts executed shell calls | B2：同 Claude 的規則，用 `tool_input.command` 判斷不寫檔、不是宣告；subagent 的（帶 `agent_id`）不算。`events_codex_supports` 沒有獨立的失敗事件，假設非零 exit 也會觸發 `PostToolUse`（未實測） | 工具已經執行完才觸發，無法阻止；`tool_response` 是字串。spawn 的 `PostToolUse` 只帶 `{task_name}`，沒有 `agent_id`，失敗的 spawn 根本不觸發，所以啟動改由 `SubagentStart` 判斷。後備：Codex 的 guard 讀不到 `/hooks` 核准狀態，所以同一個 session 在第一次看到 `PostToolUse` 之前，`PreToolUse` 的前景 `Bash` 仍算（沒重新核准的使用者不會每次 Stop 都被擋）；看過一次之後 `PreToolUse` 不再算 |
| `PreCompact`、`PostCompact` | 否 | 無 | 未實測（`events_seen` 不含）；沒有規則與 compaction 有關 |
| `SessionStart` | 否 | 無 | 有觸發，帶 `source`；沒有規則需要 session 開始 |
| `SessionEnd` | 否 | 無 | 有觸發，沒有 `turn_id`；沒有規則需要 session 結束 |
| `UserPromptSubmit` | 是 | `#direct` 偵測、回合邊界（`turn_id`） | 帶 `prompt`、`turn_id` |
| `Stop`（main） | 是（3.4.0 起，預設 enforce） | B2/B3 完成檢查 | fixture run A 觀察到 guard 擋了一次，main 接著跑了唯讀檢查，第二次 `Stop` 通過 |
| `SubagentStart` | 是（`shoal-guard-v4` 起） | E3（以啟動為準）、`direct_agents` 記錄 | 帶 `agent_id`、`agent_type`，只在 role 真的啟動時觸發（未知的 `agent_type` 不觸發）；`turn_id` 是 subagent 自己的 |
| `SubagentStop` | 否 | 無 | 目前沒有規則需要 subagent 的結束：完成檢查擋的是 main 的 `Stop`。payload 有 `last_assistant_message`、`stop_hook_active`；能否擋未實測 |

## Decisions

- **D1**：擋「寫」，不擋「派工的名稱」（E1/E2）。原因：其他 plugin 的唯讀 agent
  仍可用，規則也不需要維護各 host 內建 agent 名單。
- **D2**：allowlist 用環境變數，不寫進政策文字。原因：使用者自己的 agent（例如
  statusline setup）是每台機器各自的事實。
- **D3**：先有證據再啟用（E7）。原因：2026-10-13 有兩個猜測被推翻（agy 的 tools
  省略不等於不受限；Codex 會退而用 `worker`）。
- **D5**：plan-critic 審查（2026-10-13）促成 E0 與 E1 出口的重寫。
- **D4**：本 spec 只在找到啟動事件的 host 上取代 `guard-declared-direct` M11 的
  「沒有 start event 的 host 維持依呼叫判斷」。

## Slices

每個 slice 一個 commit；live 次數是待核准的預算。

| # | 內容 | 驗收 |
|---|---|---|
| S0 | E0：只取 payload，存 fixtures，不改規則 | fixtures commit；live：Claude 2（subagent 改檔、Workflow 子 agent）、Codex 3（subagent 改檔、spawn 成功 PostToolUse、spawn 失敗） |
| S1a | E1/E2 於 Python guard、TS mirror、共用向量（含可用處的 `#direct` 放行、allowlist 放行、exempt 路徑）；各 host 預設不啟用（走現有 mode 開關） | 向量、unittest、bun test |
| S1b | Claude 啟用 E1；invariant 3 文字 | live：Claude 2（general-purpose 改檔被擋；`shoal:executor` 經 Workflow 不被擋，或轉為 conditional open question） |
| S2 | Codex：依 E0 形狀啟用 E1 與 E3 | live：Codex 2（移走可寫 role 後 `worker` 改檔被擋且 main 回報；正常派工仍可用） |
| S3 | OpenCode：E5、E1（出口依自己 payload 的 E0 式取得，列出內建 agent 名與 `session.agent` 值）、預設 enforce；有證據才做 E6 | bun test；live：OpenCode 3 |
| S4 | Grok：deny 是否被遵守、Stop payload，只啟用有證據的 | live：Grok 3 |
| S5 | agy 重測 main 與 subagent 的區分 | live：agy 2 |
| S6 | docs、版本、CHANGELOG | CI 三個平台 |

## Non-goals

- 不做指令分類器。
- 不依 agent 名稱擋派工。
- 本 spec 不把 `pi` 加為 host。

## Risks

- E1 會擋掉「非 shoal agent 合法改檔」的流程。緩解：`#direct`、
  `SHOAL_GUARD_WRITE_AGENTS`、deny 訊息同時寫出兩者。Claude 內建會改檔的 agent
  清單，repo 文件查不到，列在 S1a。
- OpenCode、Grok 若 main 與 subagent 的訊號有誤，enforce 會擋掉正常工作。緩解：
  E7，且先 shadow 跑一次再開 enforce。
- 若 E0 顯示 Codex 不對 subagent 的工具呼叫觸發 hook，E1 在 Codex 無法以 hook
  實作；屆時改為擋非 shoal role 的派工名稱（D1 的例外），並回報 Miyago。
- hook 註冊變更後，Codex 要再用 `/hooks` 核准一次。

## Open questions

設計無。需要 Miyago 核准本 spec，以及 live 預算：Claude 4、Codex 5、OpenCode 3、
Grok 3、agy 2。

條件式：E0 若顯示 Workflow 子 agent 不能以 shoal role 執行，S1b 前回報 Miyago。

### E8 檢查表：agy（S5，agy 1.3.4，2026-10-13；payload 見 `tests/fixtures/agy_guard_event_shapes.json`）

agy 的 payload 沒有事件名稱、role、parent id，所以 **main 與 subagent、以及 subagent 的 role 都是從
conversation 順序推斷的**：`invoke_subagent` 的 PreToolUse 記下 `Subagents[].TypeName`，之後出現的新
`conversationId` 的 `SessionStart` 認領最舊的一筆（優先同 workspace）。role 不一致時只知道存取類別，類別也不一致就是
unknown：unknown 不擋，只記 `would_deny_unknown_class`。同一 workspace 內兩個 agy session 同時派工可能被混淆。
`PreInvocation` 沒有使用者 prompt，所以 agy 沒有 `#direct`，出口只有派 write role 並等它啟動、`SHOAL_GUARD_WRITE_AGENTS`、`SHOAL_GUARD_DIRECT=1`。

| 事件 | 掛上？ | 規則 | 原因／證據 |
|---|---|---|---|
| `PreToolUse`（`write_to_file`、`replace_file_content`、`multi_replace_file_content`） | 是 | R1（strict）、E1、VERIFY_EDIT（role 已知時） | deny 已實測被遵守（main 與 subagent 的 `write_to_file`） |
| `PreToolUse`（`run_command`） | 是（S5 起以 `--event` 區分） | G5（strict 的 shell 寫檔）、E1 的 shell 寫檔、B2 | 欄位 `CommandLine`、`Cwd` |
| `PreToolUse`（`invoke_subagent`） | 是 | 記 pending；subagent conversation 呼叫則只記 log（不執行 LEAF） | 分不出 main 與 subagent 時，不擋 main 派工 |
| `SessionStart` | 是（S5 新增） | 認領 pending，判定 main／subagent；write 類別即「已啟動」解鎖 main（E3） | 新 conversation 的 SessionStart 即 subagent 啟動；`invoke_subagent` 的 PostToolUse 早於 subagent 啟動，不可當證據 |
| `PreInvocation` | 是 | 回合邊界（`invocationNum == 0`） | 每次 model call 都觸發 |
| `Stop` | 是，預設 shadow（S5 新增） | B2/B3 完成檢查，僅 main、`fullyIdle: true` | 擋的輸出未實測，`SHOAL_GUARD_STOP=enforce` 才擋 |
| `PostInvocation`、`PostToolUse` | 否 | 無 | 無規則需要；B2 仍以 `PreToolUse` 的前景 shell 呼叫記錄（沒有註冊 `PostToolUse`） |
