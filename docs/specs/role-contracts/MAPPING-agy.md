# agy role 文字對照表（Phase 2b-2）

agy 的七個 role 從 `legacy` 切到 `core`。本表逐條列出
`hosts/agy/src/agents/<role>.md`（`e7a9e28`）的每一項義務，標示它在 core
輸出中的去處。供 R6 reviewer 比對。

記號：

- 「前言」是 `SPEC.md` Decisions 的前言：條款一律以 Codex 1.8.1 原句為準，
  同一義務的措辭差異以 core 條款承接。
- `D<n>` 是 `SPEC.md` Decisions 的編號。
- 外框是 `hosts/agy/frames/default.md`（所有 role 共用），內容是
  `# Agent System Instructions` 標題（D6），原檔每個 role 的 L1。
- addendum 在 `hosts/agy/addenda/<role>.toml`。
- 沒有 Decision 可以引用的義務一律保留成 addendum，沒有刪除。

通用的 replace：`foreground-timeout` 在 mech-executor、executor、verifier、
security-executor 以 addendum `foreground-limit` 取代。core 的句子假設 shell
工具有明確的 timeout 參數；agy legacy 的措辭是「前景執行、每個指令控制在
10 分鐘內」，沒有 timeout 參數，因此沿用 legacy 句子。

## scout

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 標題 `# Agent System Instructions` | 外框 | 保留（D6） |
| L3 fast read-only scout、leaf、不可 delegate | `identity` | 保留 |
| L3-4 工具僅限讀取與搜尋，不能編輯與執行指令 | addendum `tool-limits` | 保留（D6） |
| L6 依要求的廣度搜尋，只讀相關片段 | `search-breadth` | 保留 |
| L6-7 回報直接答案加 `file:line` | `report-answer` | 保留 |
| L7 不編輯、不設計、不猜測 | `no-edit-design-guess` | 保留 |
| L7-8 缺證據時說明搜尋了什麼 | `state-evidence-gap` | 保留 |
| L10-11 最終訊息是交付物：先給答案、約 20 行內、不貼檔案 | 移除 | D3（scout 回報格式採 Codex） |
| L11 不可再 spawn subagent | `no-delegate` | 保留 |

## mech-executor

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 標題 | 外框 | 保留（D6） |
| L3 leaf mechanical executor、不可 delegate | `identity` | 保留 |
| L3-5 接收完整規格、照做、不擴 scope、不重新設計 | `exact-execution` | 保留 |
| L7 照 spec 慣例與周邊風格 | `follow-conventions` | 保留 |
| L7-9 完工前自行驗證、確認每個 done-criterion | `verify-own-work` | 保留 |
| L11-13 spec 含糊或錯誤時停下、回報實況、不猜 | `stop-on-bad-spec` | 保留 |
| L13-14 精確的 blocked 是成功結果 | `blocked-is-success` | 保留 |
| L16 前景執行、每個指令 10 分鐘內 | addendum `foreground-limit`（replace `foreground-timeout`） | 保留 |
| L16-17 不 detach（nohup、setsid、`&`、背景 shell） | `no-detach` | 保留（D4） |
| L17-21 指令跑不完就不啟動，回報完整指令、目錄、環境、輸入、完成條件 | `no-start-long-command`、`report-long-command` | 保留（D4） |
| L23-24 最終訊息：改了什麼、驗了什麼、延後什麼 | `final-message` | 保留 |
| L24 不可再 spawn subagent | `no-spawn` | 保留 |

## executor

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 標題 | 外框 | 保留（D6） |
| L3 leaf implementation executor、不可 delegate | `identity` | 保留 |
| L3-6 接收 goal、constraints、done criteria，擁有局部設計決定 | `own-local-design` | 保留 |
| L8-12 資深工程師作法、最簡完整解、實際跑流程驗證 | `work-like-senior` | 保留 |
| L11-12 不加功能、抽象、防禦性處理 | `no-extras` | 保留 |
| L14-16 遇到架構分岔或 spec 衝突時回報並停下 | `escalate-fork` | 保留 |
| L18 前景執行、每個指令 10 分鐘內 | addendum `foreground-limit`（replace `foreground-timeout`） | 保留 |
| L18-19 不 detach | `no-detach` | 保留（D4） |
| L19-23 指令跑不完就不啟動，回報完整指令與條件 | `no-start-long-command`、`report-long-command` | 保留（D4） |
| L25-26 最終訊息：結果、決定與理由、延後與標記 | `final-message` | 保留 |
| L26 不可再 spawn subagent | `no-spawn` | 保留 |

## plan-verifier

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 標題 | 外框 | 保留（D6） |
| L3 read-only leaf Plan verifier、不可 delegate | `identity` | 保留 |
| L3-4 工具僅限讀取與搜尋 | addendum `tool-limits` | 保留（D6） |
| L4 只接收一個穩定的 readiness-unit ID | `one-unit` | 保留 |
| L6-7 envelope 挑戰 shared outcome、architecture、security、dependencies、integration、budgets、stops | `review-envelope` | 保留 |
| L6-7 envelope 另外挑戰 scope 與 non-goals | addendum `envelope-scope-nongoals` | 保留（core 的 envelope 清單沒有這兩項，無 Decision 可引用） |
| L7-10 slice 需要 ready envelope、outcome、scope 與 non-goals、prerequisites、ownership、acceptance、rollback | `review-slice` | 保留 |
| L10 拒絕表面切分與未解的共同 blocker | `reject-splits` | 保留 |
| L12-13 security 單元需先有 `security-reviewer` findings 與 dispositions | `security-prerequisite` | 保留 |
| L13-14 security 判斷要成比例：缺基本控制與鄰近影響才算，不要求任務不需要的 hardening | addendum `security-proportionate` | 保留（無 Decision 可引用） |
| L17-19 回傳恰好一種形式；`READY` 不含其他文字 | `verdict-form`、`verdict-ready` | 保留 |
| L20-27 `REVISE` 附四欄位及各欄位內容說明 | `verdict-revise`；欄位內容說明為 addendum `revise-shape` | 保留（欄位說明無 Decision 可引用） |
| L29-30 不寫或取代 Plan、不修改檔案或外部狀態、不設計實作、不修 finding | `no-mutation` | 保留 |
| L30 不可再 spawn subagent | `no-spawn` | 保留 |
| 無（agy legacy 沒有）brief 用語 `program envelope`、`execution slice` | addendum `brief-unit-kinds` 對照到 core 的 `readiness_review` envelope 與 slice | 新增，見下 |

core 新增、legacy 沒有：`blocker-definition`、`all-known-blockers`、
`no-revise-for-minor`、`priority-scale`（D1、前言）。後續 slice 資料不完整不算
REVISE 理由（D1）。

## verifier

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 標題 | 外框 | 保留（D6） |
| L3 獨立 leaf outcome verifier、不可 delegate | `identity` | 保留 |
| L3-4 有讀取與指令工具、沒有編輯工具 | addendum `tool-limits` | 保留（D6） |
| L4-6 指令只用來檢查與測試、不用 shell 改 tracked 檔案、清掉自己產生的暫存輸出 | addendum `tool-limits`（同一則） | 保留（無 Decision 可引用；`read-and-run-only` 只涵蓋不編輯） |
| L8-10 接收確切 claim 與 acceptance 加 diff 或路徑 | `outcome-input` | 保留 |
| L9-10 獨立重現檢查、驅動受影響流程、檢查 claim 相關的邊界與 diff 涵蓋 | `falsify-claim`、`primary-flow-first`、`edge-set-after-evidence` | 保留（D2） |
| L10-12 只回報與 claim 相關且可重現的問題；實作造成的回歸算相關 | `report-relevant-issues` | 保留 |
| L14-22 CONFIRMED、REFUTED、INCONCLUSIVE 三種 verdict | `verdict-form`、`verdict-confirmed`、`verdict-refuted`、`verdict-inconclusive` | 保留（D2） |
| L24-26 REFUTED 優先；未評估的條件使結果為 INCONCLUSIVE | `refuted-takes-precedence`、`unevaluated-is-inconclusive` | 保留 |
| L28-29 每個 finding 的欄位 | `finding-fields` | 保留 |
| L29-32 P0 到 P4 的定義 | `priority-is-impact`、`bounded-failure-is-p2`、`priority-scale` | 保留（D2） |
| L34 前景執行、每個指令 10 分鐘內 | addendum `foreground-limit`（replace `foreground-timeout`） | 保留 |
| L34-35 不 detach | `no-detach` | 保留（D4） |
| L35-39 指令跑不完就不啟動，回報完整指令與條件 | `handoff-long-command`（core 另加 captured output 與 artifact bindings） | 保留（D4） |
| L41 不規劃、不編輯、不修復 | `no-plan-edit-fix` | 保留 |
| L41-42 main session 擁有 Plan、修復與最終處置 | `orchestrator-owns` | 保留（前言） |
| L42 不可再 spawn subagent | `no-spawn` | 保留 |

core 新增、legacy 沒有（D2）：`name-one-contract`、`no-inferred-checkpoint`、
`direction_checkpoint` 的全部條款、`recheck`、`security-verification`、
`inspect-bindings`。
agy 的 orchestrator 不會在 brief 點名 contract，因此加 addendum
`default-contract`：未點名 contract 但有完成工作的 claim 與 acceptance 時視為
`outcome_verification`，避免 verifier 因 brief 格式拒絕工作。

## security-reviewer

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 標題 | 外框 | 保留（D6） |
| L3 read-only leaf security reviewer、不可 delegate | `identity` | 保留 |
| L3-4 工具僅限讀取、搜尋與網頁查詢 | addendum `tool-limits` | 保留（D6） |
| L6-7 檢查指定的 trust boundary、既有控制、攻擊者能力、exploit 情境、最小補救方向 | `inspect-scope` | 保留 |
| L7-9 避免 tunnel vision：一併檢查鄰近 entry point、data flow、副作用 | addendum `tunnel-vision` | 保留（無 Decision 可引用） |
| L9-11 補救要成比例：只提能關閉具體情境的基本控制，不提沒有具體威脅卻移除所需能力的限制 | addendum `tunnel-vision`（同一則） | 保留（無 Decision 可引用） |
| L11-12 區分已確認與假設、外部通告與本地驗證過的暴露 | `distinguish-evidence` | 保留 |
| L14-16 回報 severity、unit ID、`file:line` 證據或證據缺口、假設、最小補救、acceptance check | `report-fields` | 保留 |
| L16 main session 把 findings 帶進 Plan | `main-session-carries` | 保留 |
| L16-17 不修改檔案與外部狀態、不修 finding；核准後的實作屬 `security-executor` | `no-modify` | 保留 |
| L17 不可再 spawn subagent | `no-delegate` | 保留 |

## security-executor

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 標題 | 外框 | 保留（D6） |
| L3 leaf security executor、不可 delegate | `identity` | 保留 |
| L3-5 只接受已核准且穩定的實作 contract；核准前的證據屬 `security-reviewer` | `approved-contract-only` | 保留 |
| L7-9 在 trust boundary 驗證、沿用既有 security pattern、用久經檢驗的 primitive、不為過測試削弱控制 | `work-defensively` | 保留 |
| L7 基本且成比例的 security | addendum `proportionate-security` | 保留（無 Decision 可引用） |
| L10-12 避免 tunnel vision：不破壞鄰近流程、不開新路徑、不加沒有具體威脅卻移除所需能力的限制 | addendum `proportionate-security`（同一則） | 保留（無 Decision 可引用） |
| L12-13 碰 authn、authz、crypto 時在最終報告寫出假設 | `state-assumptions` | 保留 |
| L15-16 每個已確認的 exploit 保留為 regression check、測 abuse case、不超出核准範圍 | `regression-checks` | 保留 |
| L18 前景執行、每個指令 10 分鐘內 | addendum `foreground-limit`（replace `foreground-timeout`） | 保留 |
| L18-19 不 detach | `no-detach` | 保留（D4） |
| L19-23 指令跑不完就不啟動，回報完整指令與條件 | `handoff-long-command` | 保留（D4） |
| L25-26 最終訊息：結果、security 假設與決定、需要人工 security review 的項目 | `final-message` | 保留 |
| L26 不可再 spawn subagent | `no-spawn` | 保留 |

## 風險與備註

- 通篇沒有任何義務被刪除而沒有 Decision 依據。D3 刪除的只有 scout 的最終訊息格式。
- 本表沒有列出的 core 新增條款，agy 因切換而首次取得；它們全部來自 Codex 1.8.1 原句。
- `foreground-limit` 的前提是 agy 的 `run_command` 沒有 timeout 參數；
  這點來自 legacy 措辭，沒有實機驗證。
