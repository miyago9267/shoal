# grok role 文字對照表（Phase 2b-2）

grok 的七個 role 從 `legacy` 切到 `core`。本表逐條列出
`hosts/grok/src/agents/<role>.md`（`e7a9e28`，vendored 自
`pilotfish-grok` v1.0.6）的每一項義務，標示它在 core 輸出中的去處。
供 R6 reviewer 比對。

記號：

- 「前言」是 `SPEC.md` Decisions 的前言：條款一律以 Codex 1.8.1 原句為準，
  同一義務的措辭差異以 core 條款承接。
- `D<n>` 是 `SPEC.md` Decisions 的編號。
- 外框是 `hosts/grok/frames/<role>.md`：每個 role 一份，內容是原檔的
  YAML frontmatter（`name`、`description`、`model: inherit`、`prompt_mode`、
  `permission_mode`、`agents_md`），逐字照舊（D6）。
- addendum 在 `hosts/grok/addenda/<role>.toml`。
- 沒有 Decision 可以引用的義務一律保留成 addendum，沒有刪除。
- 沒有任何 replace：grok legacy 的 foreground 句子（「explicit timeout of at
  most 10 minutes」）與 core 相同，`main-session` 也是 grok 的用語。

Decision 7：切換後 `agents/*.md` 不再逐位元組等於上游 v1.0.6，
`upstream.lock` 的 grok 改記 `derived`。

## scout

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-12 frontmatter | 外框 | 保留（D6） |
| L14 fast read-only scout、leaf、不可 delegate | `identity` | 保留 |
| L14-16 依要求的廣度用檔案與文字搜尋，只讀相關片段 | `search-breadth` | 保留 |
| L16 回報直接答案加 `file:line` | `report-answer` | 保留 |
| L16-17 不編輯、不設計、不猜測 | `no-edit-design-guess` | 保留 |
| L17 缺證據時說明搜尋了什麼 | `state-evidence-gap` | 保留 |
| L19-21 用 `${{ tools.by_kind.* }}` 做 list、search、read；不用 execute 工具改動 workspace | addendum `tool-templates` | 保留（D6） |
| L23-24 最終訊息是交付物：先給答案、約 20 行內、不貼檔案 | 移除 | D3（scout 回報格式採 Codex） |
| L24-25 不可再 spawn subagent | `no-delegate` | 保留 |

## mech-executor

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-11 frontmatter | 外框 | 保留（D6） |
| L13 leaf mechanical executor、不可 delegate | `identity` | 保留 |
| L13-15 接收完整規格、照做、不擴 scope、不重新設計 | `exact-execution` | 保留 |
| L17 照 spec 慣例與周邊風格 | `follow-conventions` | 保留 |
| L17-19 完工前自行驗證、確認每個 done-criterion | `verify-own-work` | 保留 |
| L21-24 spec 含糊或錯誤時停下、回報實況、不猜，orchestrator 重新 spec | `stop-on-bad-spec` | 保留 |
| L24-25 精確的 blocked 是成功結果 | `blocked-is-success` | 保留 |
| L27 前景執行、explicit timeout 最多 10 分鐘 | `foreground-timeout` | 保留（D4） |
| L28-29 不 detach，detached 的工作脫離 task tracking | `no-detach` | 保留（D4） |
| L29-32 跑不完就不啟動，回報完整指令、目錄、環境、輸入、完成條件 | `no-start-long-command`、`report-long-command` | 保留（D4） |
| L34-35 最終訊息：改了什麼、驗了什麼、延後什麼 | `final-message` | 保留 |
| L37 不可再 spawn subagent | `no-spawn` | 保留 |

## executor

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-11 frontmatter | 外框 | 保留（D6） |
| L13 leaf implementation executor、不可 delegate | `identity` | 保留 |
| L13-16 接收 goal、constraints、done criteria，擁有局部設計決定 | `own-local-design` | 保留 |
| L18-21 資深工程師作法、最簡完整解、實際跑流程驗證 | `work-like-senior` | 保留 |
| L21-22 不加功能、抽象、防禦性處理 | `no-extras` | 保留 |
| L24-27 遇到架構分岔或 spec 衝突時回報並停下 | `escalate-fork` | 保留 |
| L29 前景執行、explicit timeout 最多 10 分鐘 | `foreground-timeout` | 保留（D4） |
| L30-31 不 detach | `no-detach` | 保留（D4） |
| L31-34 跑不完就不啟動，回報完整指令與條件 | `no-start-long-command`、`report-long-command` | 保留（D4） |
| L36-37 最終訊息：結果、決定與理由、延後與標記 | `final-message` | 保留 |
| L39 不可再 spawn subagent | `no-spawn` | 保留 |

## plan-verifier

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-10 frontmatter | 外框 | 保留（D6） |
| L12 read-only leaf Plan verifier、不可 delegate | `identity` | 保留 |
| L12-13 capability 由 grok 強制為 read-only：沒有 shell、沒有檔案編輯 | addendum `capability-note` | 保留（D6） |
| L13-14 只接收一個穩定的 readiness-unit ID | `one-unit` | 保留 |
| L14-16 envelope 挑戰 shared outcome、architecture、security、dependencies、integration、budgets、stops | `review-envelope` | 保留 |
| L14-15 envelope 另外挑戰 scope 與 non-goals | addendum `envelope-scope-nongoals` | 保留（core 的 envelope 清單沒有這兩項，無 Decision 可引用） |
| L16-18 slice 需要 ready envelope、outcome、scope 與 non-goals、prerequisites、ownership、acceptance、rollback | `review-slice` | 保留 |
| 無（上游 v1.0.6 的 policy 把 budget 與 stops 放在 program envelope，slice 不寫） | addendum `slice-inherits-envelope`：envelope 已載明時 slice 沿用，slice 層缺少不算 blocker | 調和 core 新增的 slice-local budget 與 stops（D12） |
| L18 拒絕表面切分與未解的共同 blocker | `reject-splits` | 保留 |
| L20-21 security 單元需先有 `security-reviewer` findings 與 dispositions | `security-prerequisite` | 保留 |
| L23-26 回傳恰好一種形式；`READY` 不含其他文字 | `verdict-form`、`verdict-ready` | 保留 |
| L26-33 `REVISE` 附四欄位及各欄位內容說明 | `verdict-revise`；欄位內容說明為 addendum `revise-shape` | 保留（欄位說明無 Decision 可引用） |
| L35-36 不執行會改動的指令、不寫或取代 Plan、不修改檔案或外部狀態、不設計實作、不修 finding | `no-mutation` | 保留 |
| L36 不可再 spawn subagent | `no-spawn` | 保留 |
| 無（legacy 沒有）brief 用語 | addendum `brief-unit-kinds`：`program envelope` 視為 `readiness_review` envelope、`execution slice` 視為 slice | 新增，見下 |

core 新增、legacy 沒有：見文末「core 新增的義務」。

## security-reviewer

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-10 frontmatter（描述「before the first Plan-readiness review」） | 外框 | 保留（D6） |
| L12 read-only leaf security reviewer、不可 delegate | `identity` | 保留 |
| L12-13 capability 由 grok 強制為 read-only，含可用時的 web search | addendum `capability-note` | 保留（D6） |
| L13-15 檢查 trust boundary、既有控制、攻擊者能力、exploit 情境、最小補救方向 | `inspect-scope` | 保留 |
| L15-17 區分已確認與假設、外部通告與本地驗證過的暴露 | `distinguish-evidence` | 保留 |
| L19-20 回報 severity、unit ID、`file:line` 證據或證據缺口、假設、最小補救、acceptance check | `report-fields` | 保留 |
| L20-22 main session 在該單元第一次 `plan-verifier` 之前把 findings 與 dispositions 帶進 Plan | `main-session-carries` | 保留 |
| L22-23 不修改檔案與外部狀態、不產出實作 brief、不修 finding | `no-modify` | 保留 |
| L23-24 這是核准前的證據；核准後的實作屬 `security-executor` | `no-modify`（`approved implementation belongs to security-executor`）；「核准前」由 frontmatter 的 description 與 `main-session-carries` 的時序承接，沒有逐字句子 | 收窄（依 Decisions 前言：以 Codex 原句為準；核准後的實作歸屬保留） |
| L26 不可再 spawn subagent | `no-delegate` | 保留 |

## security-executor

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-11 frontmatter | 外框 | 保留（D6） |
| L13 leaf security executor、不可 delegate | `identity` | 保留 |
| L13-15 只接受已核准且穩定的實作 contract；核准前的證據屬 `security-reviewer` | `approved-contract-only` | 保留 |
| L15 這份工作值得持續使用高 reasoning effort | addendum `reasoning-effort`（`roles/security-executor.toml` 設 `reasoning_effort = "high"`） | 保留（D5 的精神：effort 說明是 host addendum） |
| L17-21 在 trust boundary 驗證、沿用既有 pattern、用久經檢驗的 primitive、不削弱控制；碰 authn、authz、crypto 寫出假設 | `work-defensively`、`state-assumptions` | 保留 |
| L23-25 已確認的 exploit 保留為 regression check、測 abuse case、不超出核准範圍 | `regression-checks` | 保留 |
| L27 前景執行、explicit timeout 最多 10 分鐘 | `foreground-timeout` | 保留（D4） |
| L28 不 detach | `no-detach` | 保留（D4） |
| L28-31 跑不完就回報完整指令與條件 | `handoff-long-command` | 保留（D4） |
| L33-34 最終訊息：結果、security 假設與決定、需要人工 review 的項目 | `final-message` | 保留 |
| L36 不可再 spawn subagent | `no-spawn` | 保留 |

## verifier

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-13 frontmatter | 外框 | 保留（D6） |
| L15 獨立 leaf outcome verifier、不可 delegate | `identity` | 保留 |
| L15-16 capability 由 grok 強制為 execute：可讀與 shell，不可編輯 | addendum `capability-note`；`read-and-run-only`（Read and run only; never plan, edit, fix, or delegate） | 保留（D6） |
| L16-17 接收確切 claim 與 acceptance 加 diff 或路徑 | `outcome-input` | 保留 |
| L19-20 獨立重現檢查、驅動受影響流程、檢查 claim 相關邊界與 diff 涵蓋 | `falsify-claim`、`primary-flow-first`、`edge-set-after-evidence` | 收窄（依 Decisions 前言：以 Codex 原句為準；邊界檢查改為主流程取得證據之後才做）；D2 |
| L20-22 只回報與 claim 相關且可重現的問題；實作造成的回歸算相關 | `report-relevant-issues` | 保留 |
| L24-33 三種 verdict 與判準 | `verdict-form`、`verdict-confirmed`、`verdict-refuted`、`verdict-inconclusive` | 保留（D2） |
| L35-37 REFUTED 優先；未評估的條件使結果為 INCONCLUSIVE | `refuted-takes-precedence`、`unevaluated-is-inconclusive` | 保留 |
| L39-40 每個 finding 的欄位 | `finding-fields` | 保留 |
| L42-50 P0 到 P4 的定義、受限或可復原的失敗是 P2 | `priority-is-impact`、`priority-scale`、`bounded-failure-is-p2` | 保留（D2） |
| L52-53 不規劃、不編輯、不修復、不 delegate；main-session orchestrator 擁有 Plan、修復與最終處置 | `read-and-run-only`、`no-plan-edit-fix`、`orchestrator-owns` | 保留 |
| L55-57 security 敏感驗證要徹底：測 abuse case、遮蔽 secret、無法安全驗證就回 INCONCLUSIVE | `security-verification`（abuse case、secret、INCONCLUSIVE 都在；「remains thorough」一句沒有逐字承接） | 收窄（依 Decisions 前言：以 Codex 原句為準） |
| L59-65 前景、不 detach、跑不完回報完整指令與條件、重新檢查 artifact binding | `foreground-timeout`、`no-detach`、`handoff-long-command`、`inspect-bindings` | 保留（D4） |
| L67 不可再 spawn subagent | `no-spawn` | 保留 |

core 新增、legacy 沒有：見文末「core 新增的義務」。
shoal 沒有 vendor 上游 v1.0.6 的 policy 檔（`rules.pilotfish-grok.md`），repo
內看不到 grok 的 orchestrator 如何寫 brief；legacy 的 verifier 只說「接收確切
claim 與 acceptance 加 diff 或路徑」，沒有點名 contract。因此加 addendum
`default-contract`：未點名 contract 但有完成工作的 claim 時視為
`outcome_verification`，缺少的 acceptance 列為未驗證項目回報。

## core 新增的義務

新文字有、舊文字沒有的要求（括號內是對應條款）：

- scout：無。
- mech-executor：`route-judgment`（需要判斷或跨系統、重工具的工作時停下，
  回報邊界供 orchestrator 轉給 `executor` 或 `verifier`；「tool-heavy」含糊，
  以 addendum `mechanical-not-tool-heavy` 釐清：規格完整的機械性修改不算）。
- executor：無。
- plan-verifier：`review-slice` 的 slice-local budget 與 slice-local stop
  conditions（以 `slice-inherits-envelope` 調和）；`blocker-definition`、
  `all-known-blockers`、`no-revise-for-minor`（含 future-slice completeness 不算
  REVISE 理由，D1）、`priority-scale`。
- verifier：`name-one-contract` 與 `no-inferred-checkpoint`（以
  `default-contract` 調和）；`direction_checkpoint` 的全部條款（D2）；
  `recheck`；`falsify-claim` 的「calibrated to reproducible evidence rather
  than suspicion or finding volume」；`primary-flow-first` 與
  `edge-set-after-evidence` 的先後順序。
- security-reviewer：無。
- security-executor：無。

## 風險與備註

- 唯一被刪除的義務是 scout 的最終訊息格式（D3）；標示「收窄」的是措辭或條件
  收緊，不是刪除。
- `reasoning-effort` 的歸類：D5 只明列 Codex 的 effort 說明是 Codex addendum；
  grok 的同一句沿用同樣處理，保留而不刪。
- `brief-unit-kinds` 與 `default-contract` 的文字與 agy、Claude 相同；若
  之後決定升進 core，要同步移除各 host 的 addendum。
