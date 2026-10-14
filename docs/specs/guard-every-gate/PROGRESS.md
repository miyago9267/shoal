# guard-every-gate 進度

規格：[SPEC.md](./SPEC.md)。版本：v3.6.0（S6）。分支 `guard-every-gate`，
draft PR #1。

## 各 slice

| Slice | Commit | 內容 |
| --- | --- | --- |
| spec | `cec173a`、`2054d08` | spec 草稿；依 plan-critic 的缺口修訂 |
| S0 | `3c33ad8`、`6a6fe41` | 只取 payload，不改規則；spec 核准 |
| S1a | `cb79039` | E1 於 Python guard、TS mirror、共用向量，預設關閉 |
| S1b | `67e1a88` | Claude 預設啟用 E1，`#direct` 可放行；不變式第 3 條 |
| S2 | `3097085` | Codex：`SubagentStart` 確認啟動，預設啟用 E1 |
| S3 | `c8e0479`、`9ae4686` | OpenCode：`bash`、`apply_patch`，`session.created` |
| S4 | `a00671e` | Grok：預設 enforce，`subagent_start`，shell 寫檔 |
| S5 | `fe102ed` | agy：預設 enforce，以 conversation 區分 main 與 subagent |
| S6 | 本 commit | 版本 3.6.0、CHANGELOG、INSTALL.md 預設值修正、本檔 |

## 實測 payload 的證據

只存欄位名與形狀，不存內容。

- S0：`tests/fixtures/claude_subagent_tool_shapes.json`（subagent 改檔、
  Workflow 子 agent）、`tests/fixtures/codex_subagent_tool_shapes.json`
  （subagent 改檔、spawn 成功與失敗）、
  `tests/fixtures/opencode_guard_event_shapes.json`（opencode 1.18.31）。
- S0 後段：`tests/fixtures/grok_guard_event_shapes.json`（Grok CLI 1.0.46）、
  `tests/fixtures/agy_guard_event_shapes.json`（agy 1.3.4）。
- 共用向量：`tests/fixtures/guard_vectors.json`（Python 與 TS 共用）。
- 已實測的行為：Grok 的 deny 對 main 與 subagent 的 `write`、
  `spawn_subagent` 都被遵守；agy 的 deny 對 main 與 subagent 的
  `write_to_file` 都被遵守。

## 付費實測用量

| Host | 次數 | 備註 |
| --- | --- | --- |
| Claude | 2 | 另有 live 驗證 2 次不算數、2 次有效 |
| Codex | 3 | |
| OpenCode | 3 | |
| Grok | 4 | 核准 3 次，多 1 次：capture hook 的 matcher 太寬，重跑 |
| agy | 2 | |

## live 驗證（2026-10-14）

第一輪的測試 repo 放在 `/private/tmp`，guard 依設計豁免暫存目錄，所以
Claude、Codex 那輪與 OpenCode、Grok 的部分執行不算數；之後改在
`~/shoal-live-360/` 重跑。教訓：live 驗證的 repo 不能放在 guard 豁免的路徑。

- Claude（2 次有效）：`general-purpose` 的 Edit 被 E1 擋下，deny 訊息列出
  出口；`shoal:applier` 放行；`#direct` 那回合的 Workflow child 與
  `general-purpose` 都放行，state 的 `direct_turns` 記到該回合。
- Codex（1 次有效，另有一次以 `applier` 驗證 `SubagentStart` 解鎖）：
  `worker` 的 `apply_patch` 被 E1 擋下，檔案未變，main 回報被擋；`applier`
  在 `SubagentStart` 後放行。
- OpenCode（2 次有效）：main 自己改檔被 R1 擋下，`applier` 的
  `session.created` 後放行。`general` 的 `apply_patch` 被 E1 擋下，但它改用
  `perl -0pi -e` 從 shell 寫檔成功；guard 的 shell 寫檔偵測原本不認得
  `perl -i`，`da7ba9e` 已補上。偵測是逐字比對，`python -c`、`node -e`、`cp`
  等直譯器或複製寫檔仍抓不到，屬已知限制。
- Grok（2+1 次有效）：main 自己改檔被 R1 擋下，`applier` 的
  `subagent_start` 後放行；通用 subagent 類型會被 Grok 改寫成
  `shoal:executor`，因此改用專案層級的自訂 agent `plain-writer` 驗證：其改檔
  被 E1 擋下，`applier` 接手成功。Stop 的完成檢查以只記錄模式記下
  would_block。
- agy（2 次有效）：main 自己改檔被 R1 擋下，deny 訊息只列 agy 能用的三個
  出口（無 `#direct`）；conversation 推論正確（`scout` 判為唯讀、`applier`
  判為可寫）。未觸發「非可寫 subagent 改檔被擋」：`scout` 沒有寫檔工具，自行
  拒絕。`applier` 回來後 main 再改檔仍被擋。證據：raw stream（round3 `a2.out`）在
  `invoke_subagent` 之後、main 的下一個回應之前有一則 `system_message`（step 8）；guard log
  （2026-10-14T05:58:04Z）在 subagent 的 `SessionStart` 之後出現一筆 main 的
  `turn_boundary`，中間沒有 main 的新 `SessionStart`。程式只在 `PreInvocation` 且
  `invocationNum == 0` 時才記 `turn_boundary`，所以推得：subagent 回報讓 main 開了新一輪
  invocation，編號從 0 起算。stream 不含 `invocationNum`，這是推論，沒有直接看到該欄位。
  解鎖因此維持到 subagent 回報為止，不是「到下一次模型呼叫」。

付費執行次數（含不算數的，capture＋第一輪＋重跑）：Claude 2+2+2、
Codex 3+2+1、OpenCode 3+2+2、Grok 4+1+2+1、agy 2+2。

## 尚未 live 驗證

來源是 SPEC 的 E8 檢查表與 INSTALL.md。

- Grok：`stop` 的 `{"decision":"block"}` 輸出（目前只記 `would_block`，
  `SHOAL_GUARD_STOP=enforce` 才擋）。
- Grok：派出不存在的 role 會怎樣（一次觀察像是起了通用 subagent）。
- agy：各事件的先後順序（`SessionStart` 認領 `invoke_subagent` 的 pending）
  只是推斷，沒有多組並行的實測。
- agy：`--event` 參數的 hook 註冊在 agy 實際觸發的情形。
- agy：`Stop` 的擋住輸出格式。
- OpenCode：subagent 的 `bash` 被 throw 後是否真的 deny。
- OpenCode：`permission.ask`（尚未量測）、`session.promptAsync` 重新提示。
- Codex：舊註冊升級到 `shoal-guard-v4` 後，用 `/hooks` 重新核准的流程；
  核准前以第一次工具呼叫作為啟動依據的路徑。

## 已知限制

- 2026-10-14 本機負載過高，完整 unit suite 沒有跑完；只跑了 render、
  prompt lock、install、plugin、delegation default 與 OpenCode `bun test`
  等針對性檢查。整合驗證交給 PR #1 的 CI。
- CI 結果：PR #1 的 CI 在 `0e6e6b1` 全綠（ubuntu、macOS、windows 的 Python tests
  與 Markdown lint）。OpenCode plugin 的 `bun test` 原本沒有 CI job，現在補上。

## 合併前驗證的發現與剩餘風險

- 合併前 verifier 確認 guard 行為正確；指出文件缺口（Claude、Codex 的 E8 表、過時的
  INSTALL 說明、agy 回合措辭、OpenCode 沒有 CI），已在同一個 commit 修正。
- agy：類別 unknown 的 subagent（混合派工）只記 `would_deny_unknown_class`，不擋。
- agent type 名稱的信任：可寫權限以 host 回報的名稱為準。verifier 認為前提多半不成立
  （自訂 agent 取 `executor` 之類的名稱，或 Grok 改寫通用型別）。便宜的驗證：Grok 跑一次，
  比對 `subagent_start.subagentType` 與實際載入的 agent；Claude 用一個叫 `executor` 的專案 agent
  寫 repo，看是否被放行。
- OpenCode 的 `perl -i` 偵測只有 unit test，沒有重跑 live。
