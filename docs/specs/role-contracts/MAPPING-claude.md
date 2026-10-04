# Claude role 文字對照表（Phase 2b-2）

Claude 的七個 core role 從 `legacy` 切到 `core`；host 專屬的 `Explore` 維持
`legacy`（D8）。本表逐條列出 `hosts/claude/src/agents/<role>.md`
（`e7a9e28`，電報體）的每一項義務，標示它在 core 輸出中的去處。供 R6
reviewer 比對。

記號：

- 「前言」是 `SPEC.md` Decisions 的前言：條款一律以 Codex 1.8.1 原句為準，
  同一義務的措辭差異以 core 條款承接。
- `D<n>` 是 `SPEC.md` Decisions 的編號。
- 外框：Claude 的 agent body 沒有外框，沒有 `hosts/claude/frames/`；
  frontmatter 仍由 binding 產生（D6 的 Claude 部分只有工具停用說明，在 addenda）。
- addendum 在 `hosts/claude/addenda/<role>.toml`。
- 沒有 Decision 可以引用的義務一律保留成 addendum，沒有刪除。
- Claude 沒有任何 replace：`main-session`、`orchestrator`、foreground 的
  explicit timeout 都是 Claude 自己的用語與機制；Bash 的 `timeout` 是毫秒、
  `run_in_background` 是 detach 的 Claude 形式，這兩點用 addendum 補。

共同的 legacy 句子：

- 「Leaf agent: do whole task yourself, this session. Never delegate」：
  `identity` 與 `no-spawn`。
- 「Agent/Workflow tools disabled by design」：addendum `tools-disabled`
  （D6）。
- 「Task seems to need sub-agents → mis-routed; stop/report」：legacy 只有
  mech-executor、executor、verifier、security-executor 有這句
  （plan-verifier、scout、security-reviewer 的 legacy 沒有，不算移除）。
  `mis-routed` 用語移除（D3）。mech-executor、executor、security-executor 的
  停下回報由 `stop-on-bad-spec`、`escalate-fork`、`approved-contract-only` 與
  addendum `contract-contents` 承接。verifier 與 plan-verifier 的 core 條款沒有
  `stop-on-bad-spec` 或 `escalate-fork`，因此 verifier 的這句實際上是移除，
  不是承接。依據：Decisions 前言（條款以 Codex 原句為準，Codex 的 verifier 沒有
  對應句子）加上 D3「停下回報的措辭採 Codex」的類推；D3 沒有明文點名
  verifier。無法完成時的出口改由 verdict 承接：verifier 回 `INCONCLUSIVE`
  （evidence、environment 或 contract 不足或不安全），plan-verifier 回 `REVISE`
  （只有 plan-verifier 的 core 有這個出口，沒有逐字的「停下回報」）。
- 「Long work: foreground; explicit `timeout` (max 600000ms/10min)」：
  `foreground-timeout`（D4）與 addendum `timeout-param`（毫秒）。
- 「Never detach — no `nohup`, `setsid`, trailing `&`, `run_in_background`」與
  「Detach escapes harness task tracking (no task id, no captured output, no
  completion notification)」：`no-detach`（D4）與 addendum
  `background-note`。
- 「Command can't finish in 10min → don't start: report ... stop」：
  `no-start-long-command` 與 `report-long-command`（executor、
  mech-executor）。verifier 與 security-executor 的 core 條款
  `handoff-long-command` 只有「回報完整指令」，沒有「不要啟動」，所以這兩個
  role 以 addendum `do-not-start`（`before:handoff-long-command`）補回
  「Do not start a command that cannot finish within 10 minutes.」。

以下各表只列各 role 其餘的義務，共同句子的行號寫在各 role 的列內。

## scout

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 fast read-only scout，找東西、回報事實 | `identity` | 保留 |
| L1 不修改、不做設計判斷 | `no-edit-design-guess` | 保留 |
| L3 廣泛搜尋（先 Glob 與 Grep，再讀相關片段） | `search-breadth`（Glob、Grep 是 frontmatter 的 `tools` allowlist） | 收窄（依 Decisions 前言：以 Codex 原句為準；不再點名工具與「broadly」） |
| L3 回答確切的問題，回報 `file:line` | `report-answer` | 保留 |
| L3 每則發現一句說明 | 移除 | D3（scout 回報格式採 Codex） |
| L3 找不到時說明搜尋與位置 | `state-evidence-gap` | 保留 |
| L3 不推測檔案以外的事 | `no-edit-design-guess`（never guess） | 保留 |
| L5 每次執行的最終訊息是交付物，也是 orchestrator 唯一收到的結果 | addendum `final-message-channel` | 保留（Claude 機制，D6 精神） |
| L5 沒有對外傳訊工具、不能推送中間更新；完整答案放進一則自足的最終訊息 | addendum `final-message-channel`（同一則） | 保留（Claude 機制） |
| L5 答案優先、易掃讀、只回答被問的、不貼大量內容 | `report-answer` 承接「直接答案」；其餘移除 | D3 |
| L5 被 orchestrator 續派時沿用保留的 context、不重複已完成的搜尋 | addendum `final-message-channel`（同一則） | 保留（Claude 機制） |
| 無（legacy 沒有） | `no-delegate`、`identity` 的 leaf | 新增 |

## mech-executor

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 共同句子（leaf、Agent/Workflow 停用、mis-routed） | 見上 | 保留或 D3 |
| L3 mechanical executor、接收完整規格、照做、不擴 scope、不重新設計 | `identity`、`exact-execution` | 保留 |
| L5 照 spec 慣例與周邊風格 | `follow-conventions` | 保留 |
| L5 完工前執行 spec 的檢查與測試、確認每個 done-criterion | `verify-own-work` | 保留 |
| L7 spec 含糊或錯誤時停下、回報實況、不猜，orchestrator 重新 spec | `stop-on-bad-spec` | 保留 |
| L7 精確的 blocked 是成功結果 | `blocked-is-success` | 保留 |
| L9 前景、timeout、不 detach、跑不完的處理 | 見共同句子 | 保留（D4） |
| L11 最終訊息：改了什麼、驗了什麼、延後什麼 | `final-message` | 保留 |
| 無（legacy 沒有） | `route-judgment` | 新增 |

## executor

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 共同句子 | 見上 | 保留或 D3 |
| L3 主要實作 executor，接收 goal、constraints、done-criteria，擁有局部設計決定 | `identity`、`own-local-design` | 保留 |
| L5 資深工程師作法、讀 context 配合慣例、最簡完整解、實際驗證 | `work-like-senior` | 保留 |
| L5 不加功能、抽象、防禦性處理 | `no-extras` | 保留 |
| L7 遇到架構分岔或 spec 衝突時回報分岔與建議並停下 | `escalate-fork` | 保留 |
| L9 前景、timeout、不 detach、跑不完的處理 | 見共同句子 | 保留（D4） |
| L11 最終訊息：結果、決定與理由、延後與標記 | `final-message` | 保留 |

## plan-verifier

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 read-only leaf、審這個單元、不 delegate | `identity`、`no-spawn` | 保留 |
| L1 allowlist 排除 Bash、Write、Edit、NotebookEdit、Agent、Workflow；核准前的邊界靠 capability 而非 prompt | addendum `tool-allowlist` | 保留（D6） |
| L3 只接收一個穩定的 readiness-unit ID | `one-unit` | 保留 |
| L3 附上相關的 Plan 與證據路徑；只讀該單元需要的證據 | addendum `read-needed-evidence` | 保留（無 Decision 可引用） |
| L3 program envelope 挑戰 shared outcome、architecture、security、dependencies、integration、budgets、stops | `review-envelope`；brief 的 `program envelope` 由 addendum `brief-unit-kinds` 對照為 `readiness_review` envelope | 保留 |
| L3 execution slice 的要求，含 slice-local budget 與 explicit stop conditions | `review-slice`；`execution slice` 由 `brief-unit-kinds` 對照為 slice | 保留；stop conditions 從 explicit 改成 slice-local，見「core 新增的義務」 |
| L3 拒絕表面切分與未解的共同 blocker | `reject-splits` | 保留 |
| L5 security 單元需先有 `security-reviewer` findings 與 dispositions | `security-prerequisite` | 保留 |
| L7 只有具體的 P0 到 P2 缺陷才是 blocker | `blocker-definition` | 保留 |
| L7 同一輪回報所有已知 blocker | `all-known-blockers` | 保留 |
| L7 P3/P4 建議、可選細節、風格一致、可選的下游實作細節、鄰近 hardening 不用 REVISE | `no-revise-for-minor`（「optional downstream implementation detail」併入「optional detail」與「future-slice completeness」） | 收窄（D1、前言） |
| L7 後續 slice 缺少必要的 metadata（ID、outcome、prerequisites）仍然是 blocker | 移除 | D1（採 Codex 版：後續 slice 資料不完整不算 REVISE 理由） |
| L9 P0 到 P4 的定義 | `priority-scale` | 保留 |
| L11 不寫取代用的 Plan | `no-mutation` | 保留 |
| L11-21 回傳恰好一種形式、`READY`、`REVISE` 與四欄位 | `verdict-form`、`verdict-ready`、`verdict-revise`；各欄位內容說明為 addendum `revise-shape` | 保留（欄位說明無 Decision 可引用） |
| L23 不執行指令、不修改 repository 或外部狀態、不替使用者規劃實作、不修任何東西 | `no-mutation`（core 是「Never execute mutating commands」） | 收窄（依 Decisions 前言：以 Codex 原句為準；「不執行指令」收窄成「不執行會改動的指令」）；原義務由 addendum `tool-allowlist` 補上的「and you never execute commands」保住（寫法同 security-reviewer） |
| L23 main-session orchestrator 擁有整合、核准與所有寫入 | addendum `orchestrator-owns-writes` | 保留（無 Decision 可引用） |

## security-reviewer

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 read-only leaf、自己做分析、不 delegate | `identity`、`no-delegate` | 保留 |
| L1 allowlist 排除 Bash、Write、Edit、NotebookEdit、Agent、Workflow | addendum `tool-allowlist` | 保留（D6） |
| L3 檢查被要求的 security surface，為 main-session Plan 回報證據 | `inspect-scope`、`main-session-carries` | 保留 |
| L3 謹慎地辨識 trust boundary、既有控制、攻擊者能力、exploit 情境、最小補救方向 | `inspect-scope` | 保留 |
| L3 先沿用 codebase 的證據再考慮新機制 | addendum `follow-codebase-evidence` | 保留（無 Decision 可引用） |
| L3 區分已確認與假設、外部通告與本地驗證過的暴露 | `distinguish-evidence` | 保留 |
| L5 回報 severity、`file:line` 證據、假設、精簡的驗證方式 | `report-fields`（含 unit ID、證據缺口、最小補救、acceptance check） | 保留（D3：回報格式採 Codex） |
| L5 不產出實作 brief、不修改 repository 或外部狀態、不修任何東西 | `no-modify` | 保留 |
| L5 不執行指令 | addendum `tool-allowlist` | 保留 |
| L5 main-session orchestrator 擁有 Plan 的整合與核准；核准後的實作交給 `security-executor` | `main-session-carries`（只有「carries findings into the Plan」）、`no-modify`（`approved implementation belongs to security-executor`） | 收窄（依 Decisions 前言：以 Codex 原句為準；「擁有整合與核准」不再逐字承接，核准後的實作歸屬保留） |

## security-executor

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 共同句子 | 見上 | 保留或 D3 |
| L3 核准後的 security executor | `identity` | 保留 |
| L3 獨立的 role，路由到 Opus；review 帶有額外的嚴謹度 | addendum `separate-routing`（「separate role with its own model routing」） | 收窄（不再點名模型，避免 resolver 改選時文字過時；獨立 role 與額外嚴謹度保留） |
| L3 brief 缺少已核准、穩定的 contract（scope、constraints、done criteria）時停下回報；核准前的分析屬 `security-reviewer` | `approved-contract-only`；contract 的內容與停下回報由 addendum `contract-contents` | 保留；`mis-routed` 字樣移除（D3） |
| L5 防禦且精確：在 trust boundary 驗證、沿用既有 pattern、用久經檢驗的 primitive、不為測試削弱控制 | `work-defensively` | 保留 |
| L5 碰 authn、authz、crypto 時在最終報告明確寫出假設，供檢查 | `state-assumptions` | 保留 |
| L7 已確認的 finding 保留 exploit 或失敗情境為 regression check；核准範圍外不做臆測性 hardening | `regression-checks`（「do not expand beyond the approved security scope」） | 收窄（前言：「speculative hardening」併入「expand beyond scope」） |
| L9 前景、timeout、不 detach、跑不完的處理 | 見共同句子 | 保留（D4） |
| L11 最終訊息：結果、security 假設與決定、需要人工 review 的項目 | `final-message` | 保留 |

## verifier

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1 共同句子 | 見上 | 保留或 D3；mis-routed 停下回報在 verifier 是移除（見共同句子，依據前言與 D3 類推） |
| L3 fresh-context outcome verifier，接收確切 claim、acceptance、diff 或路徑 | `identity`、`outcome-input` | 保留 |
| L3 先試 primary acceptance flow | `primary-flow-first` | 保留（D2） |
| L3 檢查最小的 claim 相關邊界與 diff 涵蓋 | `edge-set-after-evidence` | 保留 |
| L3 即使 primary flow 受阻或不可用，仍檢查可安全操作的邊界；記錄缺少的 primary flow 證據，但不壓下可獨立重現的 blocker | addendum `blocked-primary-flow` | 保留（無 Decision 可引用；core 的 `edge-set-after-evidence` 要求證據齊備後才檢查邊界，這則是例外） |
| L3 只回報與 claim 相關且可重現的問題；路徑相近不算相關；實作造成的回歸算相關 | `report-relevant-issues` | 保留 |
| L3 recheck：重現原失敗加上有範圍的基本回歸，不重開鄰近 hardening、不變成整個 scope 的重審 | `recheck` | 保留 |
| L5-9 CONFIRMED、REFUTED、INCONCLUSIVE 三種 verdict | `verdict-form`、`verdict-confirmed`、`verdict-refuted`、`verdict-inconclusive` | 保留（D2） |
| L11 REFUTED 優先；未評估的條件使結果為 INCONCLUSIVE | `refuted-takes-precedence`、`unevaluated-is-inconclusive` | 保留 |
| L13 每個 finding 的欄位 | `finding-fields` | 保留 |
| L15 優先序以真實影響為準、P0 到 P4、受限或可復原的失敗是 P2 | `priority-is-impact`、`priority-scale`、`bounded-failure-is-p2` | 保留（D2） |
| L17 不規劃、不編輯、不修復、不 delegate；main-session orchestrator 擁有 Plan、修復與最終處置 | `no-plan-edit-fix`、`orchestrator-owns` | 保留 |
| L19 security 敏感驗證要徹底：測 abuse case、遮蔽 secret、無法安全驗證就回 INCONCLUSIVE | `security-verification` | 保留 |
| L21 在新的 verifier session 獨立檢查被帶回的輸出與 artifact | `handoff-long-command`、`inspect-bindings` | 保留（D4） |
| L21 跑不完就不要啟動 | addendum `do-not-start` | 保留（`handoff-long-command` 沒有這句，補回） |
| L23 brief 明確要求 `direction_checkpoint` 時，比較原 outcome、不可談判的限制、slice acceptance 與目前證據 | `name-one-contract`、`checkpoint-compare` | 保留（D2） |
| L23 回傳 CONTINUE、PIVOT（保留有用證據）、ROLLBACK（指出最近一次驗證良好的 checkpoint） | `checkpoint-form`、`disposition-continue`、`disposition-pivot`、`disposition-rollback` | 保留（D2） |
| L23 PIVOT 要指出必須改變的路徑或假設；證據規則同 outcome verification | addendum `checkpoint-details` | 保留（core 的 PIVOT 條款沒有「指出」，也沒有「同一套證據規則」） |
| L23 證據不足以分辨時回 INCONCLUSIVE；不替人規劃 re-plan | `checkpoint-inconclusive`、`no-plan-edit-fix` | 保留 |
| 無（Claude orchestrator 的 outcome brief 不點名 contract） | addendum `default-contract` | 新增，見下 |

Claude 的 orchestrator 只在要做 direction checkpoint 時才明確點名
`direction_checkpoint`；一般的 outcome 驗證 brief 是「確切 claim 加 acceptance
加 diff 或路徑」，不點名 contract。因此 `default-contract` 讓未點名、但帶有
completed-work claim 的 brief 視為 `outcome_verification`，缺少的 acceptance
列為未驗證項目回報，避免 verifier 因 brief 格式而拒絕工作。
同樣地，plan-verifier 的 brief 使用 `program envelope` 與 `execution slice`，
由 `brief-unit-kinds` 對照到 core 的 `readiness_review` envelope 與 slice。

## core 新增的義務

新文字有、舊文字沒有的要求（括號內是對應條款）：

- scout：`identity` 的「leaf role，不可 delegate」與 `no-delegate`（legacy
  只靠 allowlist 排除 Agent）。
- mech-executor：`route-judgment`（需要判斷或跨系統、重工具的工作時停下，
  回報邊界供 orchestrator 轉給 `executor` 或 `verifier`；「tool-heavy」含糊，
  以 addendum `mechanical-not-tool-heavy` 釐清：規格完整的機械性修改不算）；
  `report-long-command` 的「completion criterion」（legacy 的回報只有指令、
  目錄、環境變數、輸入路徑）。
- executor：`report-long-command` 的「completion criterion」。
- plan-verifier：`no-revise-for-minor` 明列「future-slice completeness」不算
  REVISE 理由（D1，取代 legacy 的「remains blocking」）；`review-slice` 的
  「slice-local stop conditions」（legacy 是 explicit stop conditions，core 限定
  在 slice 層）。`no-mutation` 把「不執行指令」收窄成「不執行會改動的指令」，
  原義務由 `tool-allowlist` 的「you never execute commands」保住。其餘 core
  條款在 legacy 都有對應。
- verifier：`name-one-contract` 與 `no-inferred-checkpoint`（brief 必須點名
  一種 contract，不從含糊的措辭推斷 checkpoint；以 `default-contract` 調和）；
  `falsify-claim` 的「calibrated to reproducible evidence rather than
  suspicion or finding volume」；`no-false-rollback`（目標不可用或外部動作不可逆時，
  不宣稱 rollback，回報限制與所需的 containment 或使用者決定）；
  `edge-set-after-evidence` 的先後順序（以 `blocked-primary-flow` 調和）；
  `handoff-long-command` 的「completion criterion」；`disposition-rollback` 的
  「stop new writes」；`disposition-pivot` 的「require a bounded re-plan」。
- security-reviewer：`report-fields` 的 affected unit ID、minimum
  remediation、「acceptance check」與「explicit evidence gap」（legacy 是
  `file:line` evidence where applicable 與 concise verification approach）；
  `main-session-carries` 的 dispositions 與「在該單元第一次 plan-verifier
  review 之前」。
- security-executor：`regression-checks` 的「test abuse cases as well as
  normal behavior」；`handoff-long-command` 的「completion criterion」。

## 風險與備註

- 被刪除而有 Decision 依據的義務：plan-verifier 的「後續 slice 缺 metadata
  仍是 blocker」（D1）；`mis-routed` 用語（D3）；scout 的最終訊息格式（D3）。
  verifier 的「mis-routed 停下回報」依前言與 D3 類推移除，D3 沒有明文點名
  verifier，reviewer 請特別確認。
- 沒有 Decision 依據而保留成 addendum 的有 Claude 專屬機制（工具停用、allowlist、
  timeout 毫秒、`run_in_background`、scout 的最終訊息通道、獨立路由說明），以及
  `read-needed-evidence`、`orchestrator-owns-writes`、`follow-codebase-evidence`、
  `contract-contents`、`blocked-primary-flow`、`default-contract`、
  `do-not-start`、`checkpoint-details`。
- `blocked-primary-flow` 與 core 的 `edge-set-after-evidence` 並存，語意是
  例外，不是矛盾；reviewer 請特別確認。
- `separate-routing` 不點名模型，resolver 改選別的模型時不需要同步更新。
