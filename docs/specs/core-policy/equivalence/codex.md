---
title: Codex 舊條款與 core 條款對照（shared-rules S4 前置）
status: draft
created: 2026-10-13
updated: 2026-10-13
---

<!-- markdownlint-disable MD025 -->

# Codex 舊條款與 core 條款對照（shared-rules S4 前置）

這份文件是 `docs/specs/shared-rules/SPEC.md` 的 A6 要求的逐節對照表，也是 S4（Codex 條款改由
`core/policy/` 產生）實作計畫的輸入。legacy 指 HEAD `5188257`（v3.4.0）的
`hosts/codex/src/agents-md.bootstrap.md`（47 行）、
`hosts/codex/src/agents-md.orchestration.md`（693 行）、手寫的 plugin `SKILL.md`（94 行
）與它連結的三份 reference。core 指 `core/policy/*.toml` 加 Codex 的 frame、placeholder、
omit 與 addenda。

這份文件只描述，不改任何 code、policy、測試或 `LOCK.json`。尺寸全部是在 repo 之外的暫存副本上，用
`tools/render.py --host codex --policy-preview` 實際組出來再量的（暫存副本加了一份 Codex 的
`[policy.placeholders]`、`[policy.documents]`、frame、omit 與 addenda 草稿，repo 本身沒有
動）。凡是沒有驗證到的事都寫在第 8 節。

## 讀法

位置縮寫：`bootstrap` 是 `hosts/codex/src/agents-md.bootstrap.md`；`orch` 是
`hosts/codex/src/agents-md.orchestration.md`；`SKILL.md`、`role-contract`、
`verification-contract`、`recovery-contract` 是
`plugin/plugins/shoal-codex/skills/shoal-orchestration/` 下的 `SKILL.md` 與
`references/*.md`。`templates/agents-md.*.md` 與 plugin 內的
`orchestration-policy.md` 都與 `hosts/codex/src/` 的檔案逐位元組相同（`cmp` 已確認，
`tools/render.py:1157-1162` 的 `MIRRORS` 維持後者）。

A3 規則編號：規則 1 = main 不自己改檔；規則 2 = role 派不出去時回報使用者、parent 不接手；規則 3 = 長指令交
`watcher`；規則 4 = 影響決策的研究用兩個 `researcher`。「通則」指 A3 的前半句「共用條款與 Codex 舊條款矛盾時以共用條款
為準」，但不在四條明列之內。

## 1. 逐節對照

每列是一條規則或機制（同一行裡不同處置的句子拆成多列）。處置六選一；`框架` 是 marker、標題與 frontmatter 等不含規則的機制行，另列、不
計入處置統計。「對照／錨點」欄：`core 同義` 列寫 core 條款 id；`Codex 調校` 與 `常駐改為按需` 列寫它會掛在哪個 core 條款
之後（`after:`）與所屬 addendum 區塊（`AO*` 掛 orchestration、`AE*` 掛 extensions，見 1.5）。

### 1.1 bootstrap（`agents-md.bootstrap.md`，47 行）

這份是常駐文字（安裝時整份放進使用者的 `AGENTS.md` managed block，`install/install.py:2059`、`2125`
）。

| 列 | 位置 | 內容 | 處置 | 對照／錨點 | 備註 |
|---|---|---|---|---|---|
| B0 | bootstrap:L1-5 | begin／version／markdownlint marker 與標題 | 框架 | policy-frames/bootstrap.md | L1-4 四行加空行；`<!-- shoal-codex v3.4.0 -->` 版本行由 frame 提供 |
| B1 | bootstrap:L6-7 | Shoal 啟用中；保留使用者的 Persona 與 Agent Rules，shoal 只補充、不取代其優先序 | core 沒有對應 |  | 見第 2 節 N1 |
| B2 | bootstrap:L9-10 | 把 approval、security、blocked-task isolation、parent-accountability 不變條件套用到本 session | core 同義 | bootstrap-risk, bootstrap-security, bootstrap-ownership, bootstrap-questions | 摘要句；內容分散在四個 core 條款 |
| B3 | bootstrap:L11-13 | 依能力選 model：atomic／routine 用 Luna，正常設計與 QA 用 Sol，深度架構才用 Astra executor | 常駐改為按需（2026-10-13 決定） | after:main-session-owns（orchestration）［AO0］ | 與 O5-O6 內容重疊但措辭不同；測試釘住此句原文 |
| B4 | bootstrap:L14-16 | `applier`、`scout` 只用 baseline（Luna），不升級，改派 `sol-executor`／`executor`／`verifier` | 常駐改為按需（2026-10-13 決定） | after:main-session-owns（orchestration）［AO0］ | 與 O10 重疊 |
| B5 | bootstrap:L17-20 | 清楚的修復／完成請求是一個 outcome，持續到 acceptance；phase 更新不需核准；明講「只做這步」才停 | core 同義 | bootstrap-outcome；continuation-default（extensions） | 「Phase updates do not require approval」只在 extensions（按需）；常駐 core 句較短 |
| B6 | bootstrap:L21-22 | 明確的 bounded workstream 或必經 review：主動派給最便宜且相符的 typed role | core 同義 | bootstrap-delegate-default；one-shot-spec |  |
| B7 | bootstrap:L22-23 | tightly coupled 的單一 local action 留在 parent | A3 行為變更，移除 | bootstrap-delegate-default | 通則（矛盾時以 core 為準）：local action 若是改檔，改為一律派 write-capable role；讀檔、跑指令、診斷仍在 main |
| B8 | bootstrap:L23-24 | 不要為每個指令開 child，也不要等使用者指名下一階段 | core 同義 | brake-per-call；dispatch-brake |  |
| B9 | bootstrap:L25 | AUTO／ASK 只用於明示的 unattended 續跑 | core 同義 | auto-ask-selection | core 措辭是「likely long autonomous work 前提供 AUTO/ASK」；`/goal` 差異見 O76b |
| B10 | bootstrap:L25-26 | 保留 material approval、security、release、destructive、external、irreversible 的關卡 | core 同義 | bootstrap-outcome；material-gates-first（extensions）；bootstrap-risk | bootstrap-outcome 只有「Material gates always stop」 |
| B11 | bootstrap:L27-30 | 使用者明示以 Astra 啟動 main session 時走 `astra-thinking` 契約，機械工作派 Luna role | 常駐改為按需（2026-10-13 決定） | after:main-session-owns（orchestration）［AO0］ |  |
| B12 | bootstrap:L31-33 | Astra main session 的 `max_tool_calls=12`、`max_wall_seconds=300` 只是建議值；不因題目難就換 main model | 常駐改為按需（2026-10-13 決定） | after:main-session-owns（orchestration）［AO0］ |  |
| B13 | bootstrap:L34-36 | override 無效或 Astra 不可用時，在做事前 fail-closed；重開無旗標 session 才回到 Luna/Sol | 常駐改為按需（2026-10-13 決定） | after:main-session-owns（orchestration）［AO0］ |  |
| B14 | bootstrap:L37-38 | 使用 GPT-6 role binding，`plan-critic` 在 Sol/high；approval、security、release 關卡不變 | 常駐改為按需（2026-10-13 決定） | after:main-session-owns（orchestration）［AO0］ |  |
| B15 | bootstrap:L39-41 | 避免重複驗證：一次 targeted primary acceptance，必要時最多再一次 fresh `verifier`；未變不重跑 | core 同義 | outcome-verification；identity-fingerprint；review-intent-strict（extensions） | core 的 bootstrap 沒有這句，同義規則在按需文件；也就是從常駐變按需 |
| B16 | bootstrap:L42-43 | 完整 routing／role／planning／verification 流程用 `shoal-orchestration` Skill | core 同義 | bootstrap-load-skill |  |
| B17 | bootstrap:L44-45 | Skill 或 Plugin 不可用時保留這些不變條件，用有界 fail-soft；不宣稱完整 shoal 驗證 | core 同義 | bootstrap-load-skill；reference-fail-soft（skill） |  |
| B18 | bootstrap:L46-47 | 空行與 `<!-- shoal-codex:end -->` | 框架 | policy-frames/bootstrap.md |  |

### 1.2 orchestration（`agents-md.orchestration.md`，693 行）

| 列 | 位置 | 內容 | 處置 | 對照／錨點 | 備註 |
|---|---|---|---|---|---|
| O0 | orch:L1-5 | begin／version／markdownlint marker、`### Orchestration` 標題 | 框架 | policy-frames/orchestration.md |  |
| O1 | orch:L6-9 | Main-session policy；列出的 subagent role 忽略本節、自己完成、不再委派 | core 同義 | intro-named-roles（required） | legacy 名單只有 8 個 role，缺 `watcher`、`researcher`；core 名單由 `named_roles` 代入 |
| O2 | orch:L11-13 | role 負責有界的探索、執行與 fresh-context 驗證；framing、Plan、架構、整合與最終判斷留在 main | core 同義 | main-session-owns |  |
| O3 | orch:L14 | 小型、local、已穩定的工作直接完成 | A3 行為變更，移除 | direct-when-small | A3 規則 1：main 不自己改檔，一律派 write-capable role（使用者 `#direct` 例外） |
| O4 | orch:L16-21 | role 邊界表：標題列與 scout／plan-critic／security-reviewer／applier 四列 | core 沒有對應 |  | 見第 2 節 N2 |
| O5 | orch:L22 | `sol-executor` 列：用一般工程判斷的 bounded implementation | Codex 調校，移到 orchestration addendum | after:main-session-owns［AO1］ | Codex 專屬 role；若保留成表格需連同 L16-17 標題列 |
| O6 | orch:L23-27 | role 邊界表：executor／verifier／security-executor／watcher／researcher 五列 | core 沒有對應 |  | 見第 2 節 N2 |
| O7 | orch:L29-34 | Capability-first model routing：依工作面選 model 候選，不因「想多想」；role TOML 是 production binding | Codex 調校，移到 orchestration addendum | after:main-session-owns［AO1］ |  |
| O8 | orch:L36-44 | 工作面 × 預設候選 × Astra 候選對照表（Luna／Sol／Astra） | Codex 調校，移到 orchestration addendum | after:main-session-owns［AO1］ | 表中 L38、L41 的「Parent or `applier` Luna binding」會與 A3 衝突（parent 不改檔），搬移時需處理 |
| O9 | orch:L46-64 | Explicit Astra main-session mode：`gpt-6-astra` 的零寫入啟動指令、launch-time override、advisory 上限 | Codex 調校，移到 orchestration addendum | after:main-session-owns［AO1］ | 含 `codex --model gpt-6-astra` 程式碼區塊 |
| O10 | orch:L66-73 | `sol-executor`／`verifier` 用 Sol，`executor` 用 Astra 只做深度工作；Luna 管 atomic；自動升級不換 root model | Codex 調校，移到 orchestration addendum | after:main-session-owns［AO1］ |  |
| O11 | orch:L75-77 | Astra 不可用或 override 無效：在工作前 fail closed，改開無旗標 session 回 Luna/Sol | Codex 調校，移到 orchestration addendum | after:main-session-owns［AO1］ |  |
| O12 | orch:L79-82 | `applier`、`scout` 是 baseline-only：維持 Luna binding，不要求 Astra，超出邊界改派 `sol-executor`／`executor` | Codex 調校，移到 orchestration addendum | after:main-session-owns［AO1］ | L82 有 2 空格縮排的續行 |
| O13 | orch:L84-90 | 派工前只記錄 redacted routing context（model_candidate、model_snapshot 等）；tool-heavy route 要有 allowlist、預算；平台安全停止是 `capability_gap` | Codex 調校，移到 orchestration addendum | after:main-session-owns［AO1］ | 對應 install/benchmark_routing.py、install/verify_dispatch.py 的欄位 |
| O14 | orch:L92-97 | 低風險工作 main 做一次 targeted acceptance，不加獨立 verifier；risk-triggered 才一次 fresh verifier；未變不重跑 | core 同義 | outcome-verification；identity-fingerprint；risk-triggers；review-intent-strict（extensions） |  |
| O15 | orch:L99-102 | role 結果揭露證據邊界：`primary_flow`、`claim_relevant_edges`、`external_evidence`、`tool_actions`、`inconclusive_reason` | Codex 調校，移到 orchestration addendum | after:main-session-owns［AO1］ | 欄位只在 install/benchmark_routing.py 與此文件出現 |
| O16 | orch:L104-106 | 本階段不新增 computer-use role；證據證明值得再提升 | Codex 調校，移到 orchestration addendum | after:main-session-owns［AO1］ |  |
| O17 | orch:L108-113 | Decision cues：role fit 是主動委派訊號，不等使用者指名，brake 通過就派給最便宜相符的 typed role | core 同義 | bootstrap-delegate-default；delegate-cost-benefit |  |
| O18 | orch:L115-118 | 獨立偵察：兩個以上獨立面並行派 `scout`，各給獨占面與 stop condition | core 同義 | bootstrap-delegate-default；local-search-direct；discovery-scope-exclusive |  |
| O19 | orch:L119-121 | material Plan 核准前交 `plan-critic`；核准前 security 證據交 `security-reviewer` | core 同義 | plan-gate；risk-review-mandatory；security-reviewer-first |  |
| O20 | orch:L122-123 | 完整規格的機械重複工作交 `applier` | core 同義 | mech-default；execution-gate |  |
| O21 | orch:L123-125 | 需判斷的已核准實作交 `sol-executor`；證據顯示深度邊界才交 `executor` | Codex 調校，移到 orchestration addendum | after:execution-gate［AO2］ | core 的 execution-gate 只有 executor；Sol 與 Astra 分層是 Codex 專屬 |
| O22 | orch:L126 | 已核准的 security-sensitive 實作交 `security-executor` | core 同義 | execution-gate；security-executor-after-approval |  |
| O23 | orch:L127-128 | risk-triggered 實作後，把整合結果交 fresh `verifier` 做一次獨立反證 | core 同義 | verification-gate；outcome-verification |  |
| O24 | orch:L130-132 | parent 全程負責：framing、選 role、完整 brief、整合 findings 與寫入、解衝突、最終判斷 | core 同義 | main-session-owns；bootstrap-ownership |  |
| O25 | orch:L132-134 | 小型、local、已穩定的 edit 不必委派 | A3 行為變更，移除 | direct-when-small；delegate-cost-benefit | A3 規則 1 |
| O26 | orch:L133-135 | tightly coupled 的未知 bug 留在 parent，協調成本高於直接做時 | core 同義 | single-bug-direct |  |
| O27 | orch:L137-141 | Adaptive intent routing：依 intent、impact、reversibility、authority 分類；三個模式是描述性名稱，不是封閉的關鍵字分類器 | core 沒有對應 |  | core 的 interaction-shape 只看 outcome／acceptance 是否清楚；見第 2 節 N3 |
| O28 | orch:L143-144 | 模式表標題列 | core 同義 | interaction-shape |  |
| O29 | orch:L145 | `execute`：outcome 與範圍清楚；first safe move 是「Execute locally or delegate the least expensive matching role」 | A3 行為變更，移除 | interaction-shape；bootstrap-delegate-default | A3 規則 1：「Execute locally」分支（main 自己改）移除；「stop at the required gate」留在 interaction-shape |
| O30 | orch:L146-147 | `explore_then_plan`、`co_discover` 兩列 | core 同義 | interaction-shape；explore-then-plan-boundary | core 的 explore_then_plan 第一回合必須 read-only 並結束回合，比 legacy 嚴格；見 8.6 |
| O31 | orch:L149-152 | 這些模式只是初期範例；依證據與脈絡而非關鍵字；語意歧義、技術不確定、authority／risk 不確定要分開 | core 沒有對應 |  | 見第 2 節 N3 |
| O32 | orch:L152-154 | 明確意圖不等於一定 `explore_then_plan`：有界的 release 請求可維持 `execute` 且 `next_gate=approval` | core 沒有對應 |  | 見第 2 節 N4 |
| O33 | orch:L153-154 | approval gate 管 authority，route 管 interaction shape | core 同義 | interaction-shape；bootstrap-routing |  |
| O34 | orch:L156-159 | Outcome-level continuation：執行單位是使用者要的 outcome，不是一個指令 | core 同義 | execution-unit；continuation-heading |  |
| O35 | orch:L161-164 | route 欄位 `execution_scope`、`continuation_mode`、`stop_condition` | core 同義 | route-fields |  |
| O36 | orch:L166-170 | clear `execute` 預設 `execution_scope=outcome`；持續到 acceptance；回報 phase 邊界不是暫停理由 | core 同義 | continuation-default |  |
| O37 | orch:L172-175 | 「only inspect this file」「先做這一步」選 step／slice；「finish／fix」選 outcome；方向不清用最小可逆 slice 並停在 `decision` | core 同義 | step-vs-outcome | legacy 用彎引號 “ ”，core 用直引號 |
| O38 | orch:L177-181 | material 關卡優先於 continuation scope；acceptance 即停，不加未要求的 cleanup | core 同義 | material-gates-first（required） |  |
| O39 | orch:L183-184 | `AUTO`／`ASK` 是 likely long unattended work 的 presence gate，不是逐指令或逐 phase 的核准流程 | core 沒有對應 |  | required fragment「presence gates for likely long unattended work」出自此句；見第 2 節 N5 |
| O40 | orch:L184-186 | 有明確範圍的 attended 工作即使需要很多指令或 phase，也在既有授權下持續 | core 同義 | continuation-default |  |
| O41 | orch:L186-188 | `explicit_unattended` 只在使用者明示離開時續跑才選；headless／unattended 未選就在開工前暫停 | core 同義 | auto-ask-selection；route-fields |  |
| O42 | orch:L190-194 | Turn-scoped review intent：`review_intent` 與 `task_mode` 分開；`fast`／`default`／`strict` 不改 impact 與 authority | core 同義 | review-intent-select；review-intent-heading |  |
| O43 | orch:L196-198 | `fast`：略過 optional review、extra Sol calls 與非必要推理；使用者指名的測試與既有關卡照跑 | core 同義 | review-intent-fast | 「extra Sol calls」是 Codex 用語，core 句沒有；其餘字句等價 |
| O44 | orch:L199-200 | `default`：沿用既有 risk policy，沒有明確偏好時的 fallback | core 同義 | review-intent-default |  |
| O45 | orch:L200-203 | `strict`：完整 primary review／test；僅在 fingerprinted 語意分歧後允許 Luna baseline 加一個 Sol adjudicator | Codex 調校，移到 orchestration addendum | after:review-intent-strict（extensions）［AE2］ | core 的 strict 句是「不加第二個 verifier」；Luna／Sol 分層是 Codex 專屬 |
| O46 | orch:L205-207 | 偏好只限本回合；不從任務措辭、引用範例、否定句、模糊急迫推斷；矛盾退回 `default` | core 同義 | review-intent-turn-scoped |  |
| O47 | orch:L207-209 | Shoal 可對 `codex-auto-review` 發出 redacted、有版本的 advisory signal；缺 consumer 不削弱強制控制 | Codex 調校，移到 orchestration addendum | after:review-intent-turn-scoped（extensions）［AE3］ | `codex-auto-review` 只出現在 docs/specs/intent-aware-review-routing-1-6-0/SPEC.md，repo 內沒有程式消費者 |
| O48 | orch:L211-215 | 優先序：明確的本回合 `review_intent` > 既有 risk policy > Luna-first default | core 同義 | review-intent-turn-scoped | 「Luna-first」限定詞不在 core 句 |
| O49 | orch:L217-218 | host 的 permission 與 approval 控制對 external／release／destructive／irreversible 仍具權威 | core 同義 | material-gates-first；ext-no-authority（required） |  |
| O50 | orch:L218-220 | 既有 Stop hook 仍要求精確的 `automatic_plan_review` readiness 契約；`semantic_adjudication` 證據不能滿足該 gate | Codex 調校，移到 orchestration addendum | after:review-intent-turn-scoped（extensions）［AE5］ | 對應 hooks/shoal_autoroute_gate.py 的 REQUIRED_TASK |
| O51 | orch:L222-236 | 在內部 route decision 記錄邏輯訊號：`intent_confidence`、`change_impact`（含五級定義）、`reversible`、`discovery_budget`、`budget_exhausted`、`evidence_sufficient`、`blocking_decisions`、`next_gate` | core 沒有對應 |  | 見第 2 節 N6 |
| O52 | orch:L237-240 | 訊號清單內的 `execution_scope`、`continuation_mode`、`stop_condition` | core 同義 | route-fields |  |
| O53 | orch:L242-244 | Discovery 有 grounding floor 與 stopping ceiling；一個 discovery unit 的定義 | core 同義 | discovery-budget-intro |  |
| O54 | orch:L246-251 | 四個 budget 的最低證據與預設上限表 | core 同義 | discovery-budget-table | core 表省略「reversible」「targeted」「then narrow, pause, or ask」，後者移入 discovery-budget-stop |
| O55 | orch:L253-257 | 預設值不是猜測的許可；證據不再改變路線就停；floor 達不到要說明；ceiling 用盡就縮小、暫停或詢問，不轉為寫入授權 | core 同義 | discovery-budget-stop | 「The bands are defaults, not permission to guess」一句在 core 沒有 |
| O56 | orch:L259-260 | 預設自主：低風險、可逆、範圍清楚時直接選合理預設並繼續 | core 同義 | checkpoint-default |  |
| O57 | orch:L260-262 | 有界、可逆、證據可丟棄的低成本探索不必出 card 就可繼續 | core 沒有對應 |  | 見第 2 節 N7 |
| O58 | orch:L262 | 不要為每個小歧義要求使用者核准 | core 同義 | checkpoint-default |  |
| O59 | orch:L264-267 | 需要 material 選擇時出一張簡潔的高階 decision card（與 Claude 的 `AskUserQuestion` 同樣的互動風格），內含現況詮釋、建議預設、範圍與排除、一個問題 | Codex 調校，移到 orchestration addendum | after:checkpoint-unavailable（extensions）［AE6］ | card 的接法屬 A2 第三類 |
| O60 | orch:L267-268 | 有明確選項時列出並標示建議選項 | core 同義 | checkpoint-options |  |
| O61 | orch:L268-269 | 只在選擇會改變 outcome、permission、security 或 acceptance 邊界時才出 card | core 同義 | checkpoint-default |  |
| O62 | orch:L270-271 | 不要把 general-mode checkpoint 變成 Plan-mode 問卷；次要實作細節等方向確定後再問 | Codex 調校，移到 orchestration addendum | after:checkpoint-unavailable（extensions）［AE6］ | Plan mode 與 Default mode 的區分是 Codex 專屬（config.snippet.toml:11-12）；「defer」半句等價於 checkpoint-followups |
| O63 | orch:L272-273 | checkpoint 是例外的決策機制，不是逐步核准流程，也不取代內部 Plan 或繞過核准 | core 沒有對應 |  | 見第 2 節 N8 |
| O64 | orch:L275-279 | General-mode decision checkpoint：決策拆解、blocker 處置、風險、權限或 acceptance 選擇會改變 outcome 時，出一個含一個高階問題的結構化 checkpoint | core 同義 | checkpoint-default；checkpoint-question |  |
| O65 | orch:L279-280 | 這是互動契約，不是 Plan mode | Codex 調校，移到 orchestration addendum | after:checkpoint-unavailable（extensions）［AE6］ | 同 O62 |
| O66 | orch:L280-281 | 只在選定方向恢復且出現新的 material 邊界後才追問 | core 同義 | checkpoint-followups |  |
| O67 | orch:L282-283 | 一般低風險歧義：在本地選合理預設並記錄假設 | core 同義 | checkpoint-default |  |
| O68 | orch:L283-284 | 恰好兩或三個互斥選項；只在決定是 material 時標示建議 | core 同義 | checkpoint-options | core 一律把建議選項放第一並標「(Recommended)」，與「only when material」不同 |
| O69 | orch:L284-286 | 不要把 credentials、external write、destructive、release、irreversible 包進 card 的隱含授權 | core 同義 | explicit-approval-only（required） |  |
| O70 | orch:L288-294 | card schema `shoal-decision-checkpoint-v1` 的十個欄位、option 欄位、`affected_task_ids` 與 `excluded_scope` 定義 | Codex 調校，移到 orchestration addendum | after:checkpoint-unavailable（extensions）［AE6］ | 對應 install/decision_checkpoint.py 的 SCHEMA |
| O71 | orch:L296-299 | 保守解析回覆：精確選項才確認；明確拒絕維持 pending／blocked；其他、多重、引用或歧義回覆維持 pending 並澄清一次 | core 同義 | checkpoint-reply |  |
| O72 | orch:L299-300 | 不得把看似合理的自由文字回覆當成核准 | core 同義 | explicit-approval-only（required） |  |
| O73 | orch:L300-303 | 確認後產生含 checkpoint id、選項、task ids、resume point 的 resume record；下一回合保留 task ledger 並只在其範圍內繼續 | Codex 調校，移到 orchestration addendum | after:checkpoint-unavailable（extensions）［AE6］ | 對應 install/decision_checkpoint.py 的 resume_contract |
| O74 | orch:L305-319 | Optional MCP elicitation adapter：獨立安裝的 MCP bridge 可經 `elicitation/create` 呈現同一個 checkpoint，不是 core 依賴；缺失時退回原生 card | Codex 調校，移到 orchestration addendum | after:checkpoint-unavailable（extensions）［AE6］ |  |
| O75 | orch:L321-336 | multi-slice milestone 收尾送 `verifier` direction_checkpoint brief：`CONTINUE`／`PIVOT`／`ROLLBACK` | core 同義 | direction-checkpoint | core 版多一句 wrap-up：main 把最終報告草稿送同一個 checkpoint 逐句核對（shared-rules B5） |
| O76 | orch:L338-348 | Cost-unbounded continuation：只在使用者明示選擇時成立；AUTO stop list 與 direction check 仍有效 | core 同義 | cost-unbounded-continuation | 含「Escalate only to a higher executor tier or main-session takeover」，見 8.5 |
| O77 | orch:L350-351 | External／destructive／release／security-sensitive／irreversible 保留既有核准與 containment 關卡 | core 同義 | material-gates-first；auto-limits（required） |  |
| O78 | orch:L353-360 | 獨立 review 由風險觸發，不是「非 trivial」的同義詞；列舉觸發項；先走 primary user-visible flow，review 不取代該證據 | core 同義 | risk-triggers（required）；outcome-verification |  |
| O79 | orch:L362-369 | triggered material Plan：main 必須先呼叫 `plan-critic` 才能給 readiness 建議；有 security 證據先 `security-reviewer`；typed delegation 不可用就回報，不做本地 readiness 判斷 | core 同義 | risk-review-mandatory（required）；security-reviewer-first；review-circuit-breaker | core 句子是「mandatory {{dispatch_tool}} calls」，沒有「tool-use gate」這個詞 |
| O80 | orch:L371-379 | Review-service circuit breaker：`plan-critic`／`security-reviewer`／`verifier` 缺 receipt 是服務失敗不是使用者決定；重試一次；記錄 `WAITING_FOR_REVIEW`／`PAUSED_VERIFICATION` | core 同義 | review-circuit-breaker |  |
| O81 | orch:L379-380 | 不得僅因 review 服務不可用就 emit `PAUSED_NEEDS_USER` | core 沒有對應 |  | core 只說「not a user decision」；gate hook 的 BLOCK_REASON 有同一句；見第 2 節 N9 |
| O82 | orch:L380-381 | 保留 read-only 本地工作，只擋受影響的寫入或 claim；無關的已核准 slice 可繼續 | core 同義 | review-circuit-breaker |  |
| O83 | orch:L381-382 | 收到有效 receipt 或真正的使用者決定後，從記錄的 gate 恢復 | core 沒有對應 |  | 見第 2 節 N9 |
| O84 | orch:L384-390 | Task ledger：一個 prompt 含多個可獨立執行的 outcome 就拆成可追蹤的 task；每個 task 記 id、outcome、scope、dependencies、state、blocker、evidence | core 同義 | ledger-split | core 欄位沒有 stable id 與 blocker；多了「harness task/todo tool」 |
| O85 | orch:L392-397 | 四個 task 狀態 `PENDING`／`RUNNING`／`DONE`／`BLOCKED` 與定義 | core 同義 | ledger-split | core 只列狀態名，沒有逐項定義 |
| O86 | orch:L399-402 | runnable 的定義；先跑 runnable 再回頭看 blocked | core 同義 | ledger-runnable |  |
| O87 | orch:L402-407 | 兩個以上無依賴路徑、無寫入衝突的 runnable task 應水平並行（受並行上限限制）；有依賴者在前驅之後；共用 mutable 資源或獨占檔案範圍者序列化 | core 沒有對應 |  | 見第 2 節 N10 |
| O88 | orch:L407-408 | blocked task 不阻擋 sibling，除非有明確的 dependency edge | core 同義 | ledger-runnable |  |
| O89 | orch:L410-417 | task 變 blocked：記錄 blocker、goal 維持未完成、不把 sibling 標 blocked、有 runnable 就不 emit `PAUSED_NEEDS_USER`、同一穩定 blocker 不重複輸出 | core 同義 | ledger-runnable；ledger-blocked-only | 「non-interrupting status note is optional」一句在 core 沒有（只是許可，不是義務） |
| O90 | orch:L419-427 | 只剩 blocked task：輸出一次彙整提醒後停止；goal 維持 `BLOCKED`；人工回覆只清除受影響 task 及其下游；無新證據不重複 | core 同義 | ledger-blocked-only |  |
| O91 | orch:L429-438 | 大型／含糊／架構／高風險／plan-first 工作的 lifecycle 表：Discovery、Plan、Approval、Execution、Verification 各自的 gate 與可委派對象 | core 同義 | discovery-gate；plan-gate；approval-gate；execution-gate；verification-gate |  |
| O92 | orch:L440-445 | `plan-critic` brief：只回 bare `READY` 或帶 `Blocker:`／`Evidence:`／`Minimum revision:`／`Acceptance check:` 的 `REVISE`；格式錯誤是 protocol failure；REVISE 一次列出已知的 P0-P2 | core 同義 | review-verdicts | 欄位細節在 plan-critic 的 role contract（core/contracts/plan-critic.toml:101） |
| O93 | orch:L447-450 | 先審 envelope 再審下一個可執行 slice；兩者 READY 即求核准；共享 blocker 仍擋下游 | core 同義 | envelope-then-slice |  |
| O94 | orch:L452-460 | 每個 readiness unit：valid `REVISE` 後實質修訂並用 fresh `plan-critic`；兩次 REVISE 後逐項 FIX／DEFER／REJECT；不重送大致未變的 Plan | core 同義 | readiness-loop | core 多了 readiness epoch 與 closing review 規則 |
| O95 | orch:L462 | `READY` 只是 readiness，不是使用者核准或寫入授權 | core 同義 | approval-gate；risk-review-mandatory | core 沒有這一句原文，語意由「After readiness, present Plan and end turn」承接 |
| O96 | orch:L464-471 | 未完成的 root objective 在多個回合、決策回覆、導正、狀態詢問、暫停／恢復之間保持有效；脈絡清楚的替換意圖可取代；真的歧義就澄清一次 | core 同義 | objective-persists | 「no explicit cancellation phrase is required」在 core 沒有 |
| O97 | orch:L473-477 | 暫停前說明 objective、phase、待決事項、resume point；明確解決待決事項的回覆在同回合恢復；歧義回覆維持暫停並澄清一次 | core 同義 | pause-statement；checkpoint-reply |  |
| O98 | orch:L478-482 | 狀態或說明詢問不算解決待決事項，只做不受該決定限制的工作；其他導正吸收後繼續 | core 沒有對應 |  | 見第 2 節 N11 |
| O99 | orch:L484-488 | objective 未完成時不給一般性的最終回覆：繼續或 emit `PAUSED_NEEDS_USER`（blocker、一個問題、resume point）；使用者明示暫停就照辦且不捏造問題 | core 同義 | pause-statement | L488 結尾的「The pause」是被切斷的半句，接 L489 另一句，屬 legacy 瑕疵 |
| O100 | orch:L489-491 | review-service circuit-breaker 狀態用 `WAITING_FOR_REVIEW`／`PAUSED_VERIFICATION`，沒有待決使用者決定時不提問 | core 同義 | review-circuit-breaker |  |
| O101 | orch:L491-492 | 暫停在狀態或說明詢問期間持續，直到使用者明示恢復或新輸入明確取代 objective | core 沒有對應 |  | 見第 2 節 N11 |
| O102 | orch:L492-494 | 這個 liveness 不變條件不擴張 approval、security、destructive、external 或 scope 邊界 | core 同義 | ext-no-authority（required） |  |
| O103 | orch:L496-500 | 每次 agent 呼叫前辨識 phase 並套 dispatch brake；證據演進、寫入所有權重疊、沒有整合者、協調成本大於效益時不 fan out；discovery agent 只報事實 | core 同義 | dispatch-brake；collect-discovery |  |
| O104 | orch:L502-503 | 小型或 tightly coupled 的工作直接做 | A3 行為變更，移除 | direct-when-small；delegate-cost-benefit | A3 規則 1（小型工作的改檔）；tightly coupled 診斷仍留 main（single-bug-direct） |
| O105 | orch:L503-504 | 一個 worker 做有界的旁支；只有獨立、低重疊的工作才用有界並行 worker | core 同義 | dispatch-brake；parallel-launch |  |
| O106 | orch:L506-511 | 穩定的多檔機械重複有 rebuttable 的委派預設：完整 brief、獨占所有權、逐項 acceptance 時派一個 `applier`；main 負責 triage、整合、acceptance，worker 執行期間不改其範圍 | core 同義 | mech-default；mech-collect |  |
| O107 | orch:L511-514 | 直接執行 qualifying 工作需先有具體 blocker（證據演進、所有權衝突、typed worker unavailability、淨效益非正）；只是比較快不夠；預設可被反駁、非無條件 | A3 行為變更，移除 | mech-direct-blocker；direct-when-small | A3 規則 1 與 2：改檔只在 `#direct` 下；worker 不可用要回報使用者，不由 main 接手 |
| O108 | orch:L516 | qualifying 機械形狀之外，依淨效益選擇是否委派 | A3 行為變更，移除 | delegate-cost-benefit | A3 規則 1：有穩定執行契約的實作預設委派，不再逐案比淨效益 |
| O109 | orch:L517-519 | 權衡項：較低成本或 quota、保留稀缺的 main context、真正並行、獨立所有權、fresh-context 獨立性 vs context 重建、協調、整合、驗證成本 | core 沒有對應 |  | 見第 2 節 N12 |
| O110 | orch:L521-525 | 重複或同質工作要穩定、完整的 one-shot brief，不是數字門檻；其餘項目須獨立且同形狀；main 保留 triage／例外／整合／acceptance | core 同義 | brake-per-call |  |
| O111 | orch:L527-531 | delegation-planning layer 可調整 discovery 問題、拓撲、worker 數、所有權、順序、預算、停止條件；本 policy 對 role 語意、leaf 邊界、approval、verifier 契約仍具權威；agent TOML 擁有 model 與 reasoning-effort binding | core 同義 | baton-dispatch；model-routing | core 的 baton-dispatch 點名外部 skill `baton-dispatch`，缺席時直接套本 policy |
| O112 | orch:L533-535 | 單一未知 bug 的初始 root-cause discovery、trace 除錯、tightly coupled 的狀態傳遞留在 main | core 同義 | single-bug-direct |  |
| O113 | orch:L534-535 | 「以及第一個最小修復」在同一推理鏈時也留在 main | A3 行為變更，移除 | single-bug-direct；delegate-cost-benefit | A3 規則 1：root cause 與補救已知後，修復是 Execution 工作並派工 |
| O114 | orch:L535-536 | scout 只用於不擁有也不阻擋主診斷的有界旁支問題 | core 同義 | single-bug-direct |  |
| O115 | orch:L538-542 | security-sensitive 工作走分離的能力邊界：先 `security-reviewer` 並把 findings 帶進 Plan，兩個 review 不並行；核准後交 `security-executor` | core 同義 | security-sensitive-routing；security-reviewer-first；security-executor-after-approval；security-no-preapproval-write（皆 required） |  |
| O116 | orch:L544-550 | risk-triggered 工作在最小的 coherent 整合邊界做一次 fresh outcome `verifier`；security、serialization、irreversible 等邊界提前；不重送大致未變的 Plan | core 同義 | outcome-verification；readiness-loop |  |
| O117 | orch:L552-559 | 給 outcome verifier 精確 claim、acceptance 與 diff／paths；`CONFIRMED`／`REFUTED`／`INCONCLUSIVE`；REFUTED 需可重現的 P0-P2；每個 finding 的欄位 | core 同義 | review-verdicts；outcome-verification | 欄位與判準在 verifier 的 role contract（core/contracts/verifier.toml:102-133） |
| O118 | orch:L561-573 | role verdict 是證據不是權威；FIX／DEFER／REJECT 前先查；P0 凍結；P1 在核准範圍內修或暫停；引入的 P2 regression 維持 blocking | core 同義 | verdict-authority |  |
| O119 | orch:L574-576 | 有紀錄的 regrade 可用 verifier 引用的證據，只要該證據顯示不同 impact | core 沒有對應 |  | 見第 2 節 N13 |
| O120 | orch:L576-583 | 未經反證或重跑不得稱 blocker 已修；P3/P4 不開專屬 loop；`INCONCLUSIVE` 只在條件實質改變後重試一次；外部 PR review 逐項處置 | core 同義 | recheck-and-invalidate；verdict-authority |  |
| O121 | orch:L585-589 | severity 規則適用每次驗證；五輪預算是高風險恢復的緊急上限；AUTO／ASK 只用於 likely long unattended work | core 同義 | recovery-budget |  |
| O122 | orch:L591-594 | attended 且範圍明確的工作不為「可能很久」而問 mode；likely long unattended work 前提供 `AUTO` 或 `ASK` 並等待 | core 同義 | auto-ask-selection | core 在「direct imperative」下視為已選 AUTO，措辭比 legacy 少一個等待步驟；見 O126 |
| O123 | orch:L594 | 睡覺、吃飯或離開不構成繼續的授權 | core 同義 | auto-ask-selection |  |
| O124 | orch:L595-596 | headless 且未明示 unattended：emit `PAUSED_NEEDS_USER` 並結束 | core 同義 | auto-ask-selection；ask-mode |  |
| O125 | orch:L596-597 | 明示「continue while I am away」選 `AUTO` 並須宣告 | core 同義 | auto-ask-selection |  |
| O126 | orch:L597-598 | `/goal` 只保存 objective，不選任何 mode，也不放寬 authority | A3 行為變更，移除 | auto-ask-selection | 通則（A3 列舉的四條之外）：core 規定使用者給 `/goal` 或直接的完成命令即選 AUTO；見 8.4 |
| O127 | orch:L600-603 | `AUTO` 只允許核准範圍內可逆的工作與 main 的 P2 裁量；不授予版本控制、發布、安裝、credential、destructive、external、擴 scope、花錢的新權限 | core 同義 | auto-limits（required） |  |
| O128 | orch:L605-606 | `ASK` 只在目前 mode 有開放 `request_user_input` 時使用 | core 同義 | ask-mode | `question_tool` placeholder = `request_user_input`；core 句子是「when available」 |
| O129 | orch:L606-608 | 獨立設定的 MCP elicitation bridge 可作為同一 checkpoint 的選用結構化傳輸 | Codex 調校，移到 orchestration addendum | after:ask-mode［AO4］ | 同 O74 |
| O130 | orch:L608-612 | 兩個介面都不可用就以 `PAUSED_NEEDS_USER` 結束；headless 結束且不輪詢、重試、猜測；由 main 提問，不由 child 提問 | core 同義 | ask-mode；ask-questions-main |  |
| O131 | orch:L614-634 | P0 凍結 slice 與下游；containment 限於 agent 自己的工作；預設恢復是一次 targeted recheck；高風險最多五輪；每輪需實質變更；fingerprint 定義；五輪後 `PAUSED_VERIFICATION` | core 同義 | ask-questions-main；verdict-authority；recovery-budget；identity-fingerprint |  |
| O132 | orch:L636-639 | 最終報告要分開列出 confirmed、fixed、deferred、regraded／rejected、paused、inconclusive、narrowed claims、tests／gates／cost、未做的 external action | core 同義 | final-report |  |
| O133 | orch:L641-643 | model routing 屬 named agent 定義；不換其 model 與 reasoning effort；ad-hoc override 只用於沒有對應 role 的 agent | core 同義 | model-routing | 「reasoning effort」半句與 Codex 不傳 effort 的決定一致 |
| O134 | orch:L645-646 | `<!-- shoal-codex:spawn-transport:begin -->` 與 `#### Native typed spawn policy` | Codex 調校，移到 orchestration addendum | after:model-routing［AO3］ | 見第 3 節 |
| O135 | orch:L648-649 | 使用 Codex 原生 typed `spawn_agent`；policy 與 namespace 無關 | Codex 調校，移到 orchestration addendum | after:model-routing［AO3］ | 見第 3 節 T1 |
| O136 | orch:L651-654 | 每個 named-role 請求要有非空 `message`、已知 `agent_type`、符合 `[a-z0-9_]+` 的 `task_name`；`fork_turns` 預設 `none`，近期 fork 只能是 "1" 到 "3"；不做 full-history fork | Codex 調校，移到 orchestration addendum | after:model-routing［AO3］ | 見第 3 節 T2 |
| O137 | orch:L656-659 | 不傳 child 的 `model`／`reasoning_effort`／`service_tier`／`fork_context`；role TOML 擁有 model 與 effort；typed dispatch 不可用就 fail closed、不退回 untyped child | Codex 調校，移到 orchestration addendum | after:model-routing［AO3］ | 見第 3 節 T3；這是省略 effort 規則的依據 |
| O138 | orch:L661-663 | typed dispatch 是全有或全無的建立 child 邊界；不允許 untyped fallback | Codex 調校，移到 orchestration addendum | after:model-routing［AO3］ | 見第 3 節 T4 |
| O139 | orch:L663-665 | 請求無法建立或 typed 能力不可用時，parent 要嘛在 dispatch brake 下自己做有界工作，要嘛回報 delegation 不可用 | A3 行為變更，移除 | mech-direct-blocker；delegate-cost-benefit | A3 規則 2：「自己做」分支移除，只留「回報 delegation 不可用」；見第 3 節 T5 |
| O140 | orch:L667-669 | 這是 request-construction policy；receipt 驗證是事後證據分類，不是執行前取消；`max_depth` 只是 V1 相容狀態 | Codex 調校，移到 orchestration addendum | after:model-routing［AO3］ | 見第 3 節 T6 |
| O141 | orch:L670 | `<!-- shoal-codex:spawn-transport:end -->` | Codex 調校，移到 orchestration addendum | after:model-routing［AO3］ | 見第 3 節 |
| O142 | orch:L672-674 | 對每個 worker 一次給足 brief：goal、constraints、done criteria、paths、rationale、output format、budget、verification expectation | core 同義 | one-shot-spec | core 清單只到 rationale；output format／budget／verification expectation 不在 core 句 |
| O143 | orch:L674-675 | 從最便宜的合格 role 開始；兩次失敗後改任務邊界、升一級或接手 | core 同義 | one-shot-spec | 「take over」在 core 同樣保留，與 A3 規則 2 的關係見 8.5 |
| O144 | orch:L675-676 | scout 的發現是輸入；承載決定的單一事實要抽查 | core 同義 | scout-inputs |  |
| O145 | orch:L678-682 | 依資料依賴排程；兩個以上獨立 typed 呼叫就連續發出 `spawn_agent`；寫入 agent 獨占檔案；只在不相交範圍繼續；先收齊結果再做依賴工作 | core 同義 | parallel-launch；parallel-writers；collect-results | core 句子帶 `{{background_option}}`／`{{worktree_option}}`，Codex 沒有對應參數，見 8.2 |
| O146 | orch:L684 | 長時間行程屬於 main session | A3 行為變更，移除 | watcher-long-commands；bootstrap-delegate-default | A3 規則 3：可能很久或需等結果的指令交 `watcher`，main 不自己啟動背景 shell |
| O147 | orch:L685-687 | leaf 不得 detach；回傳精確指令、絕對工作目錄、環境、輸入路徑、完成條件，讓 orchestrator 執行並收集後再 resume | core 同義 | leaf-cannot-finish | 執行者從 main 改成 `watcher` |
| O148 | orch:L689-692 | `plan-critic` 與 `verifier` 不可互換；兩者都不寫 Plan 或修 finding；最終判斷在 main | core 同義 | review-verdicts；main-session-owns |  |
| O149 | orch:L693 | `<!-- shoal-codex:end -->` | 框架 | policy-frames/orchestration.md |  |

### 1.3 plugin Skill 與它連結的 reference

`SKILL.md` 是手寫檔，`tools/render.py` 不產生它（`render_codex` 只處理 `agents/*.toml` 與
`src/` 內的檔案）。三份 contract 不在 `LOCK.json`，但 `SKILL.md:L89-94` 連到它們，
`tests/test_plugin.py:26-32` 要求它們存在。

| 列 | 位置 | 內容 | 處置 | 對照／錨點 | 備註 |
|---|---|---|---|---|---|
| S0 | SKILL.md:L1-4 | frontmatter：`name`、`description` | 框架 | policy-frames/skill.md | description 含 `bounded task routing`、`fresh-context verification`（lock fragment） |
| S1 | SKILL.md:L6-11 | Skill 是常駐 bootstrap 背後的詳細流程；bootstrap 對安全與核准不變條件具權威；本 Skill 提供完整契約 | core 同義 | skill-intro；skill-bootstrap-authority | legacy 另提到「active root `AGENTS.md`」；core 用 Skill 的通稱 |
| S2 | SKILL.md:L13-22 | First move：把請求分成 `execute`／`explore_then_plan`／`co_discover` | core 同義 | first-move-steps |  |
| S3 | SKILL.md:L24 | 任務邊界寫成 `goal -> in-scope -> stop condition` | core 沒有對應 |  | 見第 2 節 N14 |
| S4 | SKILL.md:L24-25 | 除非正確性或安全需要，不擴張到相鄰的 cleanup | core 同義 | material-gates-first | 「unless correctness or safety requires it」在 core 沒有 |
| S5 | SKILL.md:L27-31 | 第一個工具動作前：單指令工作給便宜的 parent 或 `applier`；一般設計給 `sol-executor`；深度判斷才 `executor`；意外結果先升 Sol 再升 Astra | Codex 調校，移到 orchestration addendum | after:main-session-owns（orchestration；SKILL 只留指向）［AO1］ | 含「cheap parent」，與 A3 衝突處同 O8 |
| S6 | SKILL.md:L35-39 | role 清單：Skill 引言與 scout、plan-critic 兩條 | core 沒有對應 |  | 見第 2 節 N2 |
| S7 | SKILL.md:L40 | `sol-executor`：用一般工程判斷的 bounded implementation | Codex 調校，移到 orchestration addendum | after:main-session-owns（orchestration）［AO1］ |  |
| S8 | SKILL.md:L41-42 | `executor`、`applier` 的邊界 | core 沒有對應 |  | 見第 2 節 N2 |
| S9 | SKILL.md:L43-45 | `applier`、`scout` 是 baseline-only Luna role；不傳 Astra override | Codex 調校，移到 orchestration addendum | after:main-session-owns（orchestration）［AO1］ |  |
| S10 | SKILL.md:L47-50 | 驗證與風險成比例：低風險一次 targeted acceptance，必要時最多一次獨立 verifier；未變不重跑 | core 同義 | outcome-verification；identity-fingerprint |  |
| S11 | SKILL.md:L52-54 | role 清單：security-reviewer、security-executor、verifier | core 沒有對應 |  | 見第 2 節 N2 |
| S12 | SKILL.md:L56-58 | root session 擁有 scope、Plan、approval、整合、finding 處置與最終判斷；不委派未知 bug 的第一個耦合根因，也不委派依賴演進中共享證據的工作 | core 同義 | main-session-owns；single-bug-direct；dispatch-brake |  |
| S13 | SKILL.md:L62-64 | 不得把 role approval、hook trust 或 Plugin 可用性當成 policy 整合、external mutation、destructive、release、security-sensitive 的授權 | Codex 調校，移到 orchestration addendum | after:ext-no-authority（extensions）［AE7］ | 「hook trust」「Plugin」是 Codex 專屬（hooks 需 `/hooks` 核准） |
| S14 | SKILL.md:L64-68 | security-sensitive 工作：`security-reviewer -> approved Plan -> security-executor -> verifier` | core 同義 | bootstrap-security；bootstrap-risk |  |
| S15 | SKILL.md:L70-72 | material Plan 先獨立審 envelope 再稱 ready；`READY` 不是使用者核准；保留 permission／security／external 關卡 | core 同義 | plan-gate；envelope-then-slice；approval-gate |  |
| S16 | SKILL.md:L76-79 | 獨立可跑的 task 分開追蹤；blocked 不擋 sibling；僅在無依賴、無寫入衝突、無共享 mutable 資源時並行；無 runnable 時報告一次 blocker 與 resume point | core 同義 | ledger-runnable；ledger-blocked-only | 「並行條件」半句同 O87，見第 2 節 N10 |
| S17 | SKILL.md:L83-87 | 先走 primary user-visible flow；risk-triggered 做 fresh verifier；回報 `CONFIRMED`／`REFUTED`／`INCONCLUSIVE`；修復後重查原失敗；claim 不超過證據 | core 同義 | outcome-verification；recheck-and-invalidate；final-report |  |
| S18 | SKILL.md:L89-94 | References：orchestration-policy.md、role-contract.md、verification-contract.md、recovery-contract.md | core 同義 | reference-policy；reference-extensions；reference-fail-soft | core 只列 policy 與 extensions 兩份；其餘三份見 R 列 |
| S19 | SKILL.md:L33 | 標題 Role routing | 框架 | skill 外框與 first-move／references 標題 | 標題行，無規則內容 |
| S20 | SKILL.md:L60 | 標題 Approval and security | 框架 | 同上 |  |
| S21 | SKILL.md:L74 | 標題 Blocked tasks and parallel work | 框架 | 同上 |  |
| S22 | SKILL.md:L81 | 標題 Verification | 框架 | 同上 |  |
| R0a | role-contract:L1 | 標題 Role contract | 框架 | 同上 |  |
| R0b | recovery-contract:L1 | 標題 Recovery contract | 框架 | 同上 |  |
| R1 | role-contract:L3-5 | shoal role 是安裝在 `<CODEX_HOME>/agents/` 的原生 Codex role；root session 保有 routing、scope、approval、整合與 finding 處置 | Codex 調校，移到 orchestration addendum | after:main-session-owns（orchestration）［AO5］ | 安裝位置是 Codex 專屬事實；所有權半句等價於 main-session-owns |
| R2 | role-contract:L7-17 | role × 邊界 × 不可做的事 表（九個 role） | core 沒有對應 |  | 見第 2 節 N2 |
| R3 | role-contract:L19-21 | 寫入 role 用獨占檔案所有權；使用者自己的額外 role 保留；同名但被客製的 shoal role 需逐 role 明示核准才能取代 | Codex 調校，移到 orchestration addendum | after:main-session-owns（orchestration）［AO5］ | 後半是 installer 行為（install/AGENT-INSTALL.md「customized same-name roles」）；前半等價於 parallel-launch |
| R4 | verification-contract:L1-13 | 驗證契約：陳述精確 claim 與 acceptance、跑 primary flow、risk-triggered 用 fresh verifier、回三種結果、每個 finding 記錄欄位；P0 凍結；P1／P2 regression 擋 claim | core 同義 | outcome-verification；verdict-authority；recheck-and-invalidate |  |
| R5 | recovery-contract:L3 | 保留最後一個已驗證的好 checkpoint | core 沒有對應 |  | 見第 2 節 N15 |
| R6 | recovery-contract:L4-5 | 只有在證據、候選、契約、前提或環境實質改變後才重試被擋的驗證 | core 同義 | recheck-and-invalidate；recovery-budget |  |
| R7 | recovery-contract:L6 | 不得覆寫獨立變更過的使用者 policy 或外部 artifact | core 沒有對應 |  | 見第 2 節 N15 |
| R8 | recovery-contract:L7-10 | 重複恢復失敗後標 `PAUSED_VERIFICATION` 只續跑無關的已核准工作；最終報告分開列出各類結果 | core 同義 | identity-fingerprint；final-report |  |

### 1.4 core 有、legacy 沒有的條款（切換後 Codex 新得到的行為）

反向檢查：以下 core 條款在 legacy 三份文件裡找不到對應句子，或 core 比 legacy 嚴。「依決定省略」的四項是 Codex 不輸出的
core 條款（bootstrap 的 effort 與 label 兩段是第 5 節拆出來的）。

| core 條款 | 內容 | 處置／性質 |
|---|---|---|
| bootstrap-named-roles | legacy bootstrap 沒有 named-role 豁免句（只有 orch:L6-9 在按需檔）；required | 新增（常駐） |
| bootstrap-ownership 第二句 | 「delegation defaults 優先於 host 內建的、不鼓勵 subagent 的指引」 | 新增 |
| bootstrap-delegate-default | A3 規則 1、3、4 的常駐落點：改檔一律派 role（`#direct` 例外）、偵察並行 `scout`、長指令交 `watcher`、研究兩個 `researcher` | 新增（A3） |
| bootstrap-collect、collect-results | background role 回報後先收集並用一行說明 | 新增 |
| bootstrap-verify-report | 回報完成前說明本回合做了哪些驗證、哪些沒跑（shared-rules B1） | 新增 |
| bootstrap-questions | 只問 material 問題，經 `request_user_input`，建議選項先 | 新增 |
| direct-when-small、delegate-cost-benefit、mech-direct-blocker | 見 O3、O25、O104、O107、O108 | A3 規則 1、2 |
| research-fanout | 影響決策的研究派兩個 `researcher`（`arm: experiment`／`arm: control`），legacy 只有 role 表一列 | A3 規則 4 |
| watcher-long-commands、leaf-cannot-finish 的執行者 | 長指令交 `watcher`；main 不啟動背景 shell | A3 規則 3 |
| plan-critic-gaps | main 可在需求問答後送 `plan-critic` 的 `mode: gaps` | 新增 |
| local-search-direct、discovery-scope-exclusive | 獨立偵察面並行；發出偵察前宣告 main／agent 的讀取範圍，「later read tools must reject mixed commands」 | 新增；後者的機制在 Codex 是否存在未驗證（8.2） |
| large-investigation | 大型跨面調查先有界唯讀探索、再由 main 合成 Plan；executor 等條件穩定；已診斷且補救已知的 finding 屬 Execution 工作 | 新增 |
| explore-then-plan-boundary | 第一回合 `discovery_read_only`：禁用寫入工具與會改動的 shell，回報後結束回合 | core 較 legacy 嚴格（8.4） |
| risk-review-mandatory 後半 | 更高優先序的禁令 → 開工前暫停，不得 direct fallback 或豁免 | 新增 |
| readiness-loop 後半 | readiness epoch：實質修訂後只開一次 closing review，不得重啟 loop | core 較 legacy 嚴格 |
| recheck-and-invalidate 前半 | 任何 verdict 之後的必要變更使 final-byte coverage 失效，需重跑 primary acceptance 與一次 fresh verifier | 新增 |
| scout-inputs 後半 | 不委派單檔讀取、最終決定、耦合的單線調查、Plan 合成、整合判斷 | 新增 |
| auto-ask-selection 前半 | 使用者給 `/goal` 或直接的完成命令即選 AUTO | 與 O126 衝突（8.4） |
| followup-by-mode | leaf 回報 `status: failed\|insufficient` 時，AUTO 下自行派後續、ASK 下回報後停；使用者切換 mode 時不再派新工作並列出仍在跑的 role | 新增 |
| parallel-writers | 平行寫入用 `{{worktree_option}}`（需 Git），沒有 Git 就不 fan out | 新增；Codex 沒有對應參數（8.2） |
| liveness、subagent-final-message | 以任務狀態判斷存活、不因懷疑而 kill；subagent 的最終訊息就是交付物 | 新增 |
| ext-extend-policy、ext-conflict-policy-wins | extensions 與 policy 衝突時以 policy 為準並回報使用者 | 新增（framing） |
| direction-checkpoint 的 wrap-up 句 | multi-slice 收尾時 main 把最終報告草稿送同一個 checkpoint 逐句核對（shared-rules B5） | 新增 |
| ledger-split 的 harness 工具 | 有 harness task/todo 工具就用它 | 新增 |
| effort-per-delegation | Codex 不允許呼叫端指定子 agent 的 reasoning effort（`orch:L656-659`） | 依決定省略 |
| dispatch-kind-label | `task_name` 必須符合 `[a-z0-9_]+`（`orch:L651-653`），`fix:` 的冒號不合法；gate 的指定呼叫也要求固定的 `task_name`（`hooks/shoal_autoroute_gate.py:1435`） | 依決定省略 |
| bootstrap 拆出的 effort 段、label 段 | 同上兩項在常駐 bootstrap 的版本（第 5 節） | 依決定省略 |

### 1.5 統計與 addendum 區塊

| 處置 | 列數 |
|---|---|
| core 同義 | 116 |
| Codex 調校，移到 orchestration addendum | 34 |
| 常駐改為按需（2026-10-13 決定） | 6 |
| A3 行為變更，移除 | 11 |
| 依決定省略 | 0 列 legacy；4 個 core 條款（上表） |
| core 沒有對應 | 24 |

另有 11 列 `框架`（marker、標題）。`core 沒有對應` 的 24 列合併成 15 項，見第 2 節。

addendum 區塊（把標為 `Codex 調校` 與 `常駐改為按需` 的 legacy 文字原樣放進
`hosts/codex/policy-addenda/<doc>.toml`；位元組含 2 位元組段落分隔；`AO3` 已扣掉 A3 的半句 69 位元組
）：

| 區塊 | 掛在 | 錨點 | 內容 | 來源 | 大小 |
|---|---|---|---|---|---|
| AO0 | orchestration | after:main-session-owns | 常駐 bootstrap 的 Codex 調校句（逐字搬入） | bootstrap:L11-16；bootstrap:L27-38 | 1232 B／20 行 |
| AO1 | orchestration | after:main-session-owns | Codex model 分層、Astra main-session mode、routing context | orch:L16-17；orch:L22；orch:L29-90；orch:L99-106 | 4369 B／77 行 |
| AO2 | orchestration | after:execution-gate | sol-executor／executor 分層選擇 | orch:L123-125 | 164 B／4 行 |
| AO3 | orchestration | after:model-routing | typed spawn transport（去掉 A3 的半句） | orch:L645-670 | 1342 B／26 行 |
| AO4 | orchestration | after:ask-mode | MCP elicitation bridge 句 | orch:L606-608 | 234 B／4 行 |
| AO5 | orchestration | after:main-session-owns | role 安裝位置與同名 role 保護 | role-contract:L3-5；role-contract:L19-21 | 348 B／8 行 |
| AE2 | extensions | after:review-intent-strict | strict 的 Luna／Sol 規則 | orch:L200-203 | 224 B／5 行 |
| AE3 | extensions | after:review-intent-turn-scoped | codex-auto-review advisory signal | orch:L207-209 | 195 B／4 行 |
| AE5 | extensions | after:review-intent-turn-scoped | Stop hook 契約句 | orch:L218-220 | 209 B／4 行 |
| AE6 | extensions | after:checkpoint-unavailable | Codex decision card 的接法 | orch:L264-267；orch:L270-271；orch:L279-280；orch:L288-294；orch:L300-303；orch:L305-319 | 2291 B／40 行 |
| AE7 | extensions | after:ext-no-authority | hook trust／Plugin 可用性不是授權 | SKILL.md:L62-64 | 213 B／4 行 |

`AO0` 是常駐 bootstrap 的 Codex 調校句（B3、B4、B11-B14）逐字搬進 orchestration 的版本；其中 B3、B4
與 `AO1` 內容重疊但措辭不同，因為測試釘住 bootstrap 的原句（`tests/test_policy.py:68-69`），所以這裡以「逐字保
留」計算最大值。掛在 `after:` 的 addendum 若前一個條款的 `sep` 是 `newline` 或 `space`，要加
`join = "paragraph"` 才不會黏在條列上（`tools/contracts.py:273-285`）。

## 2. core 沒有對應的規則

以下每項都是 legacy 才有、core 找不到對應句子的內容。這份文件不決定它們的去留。「通則」欄寫我判斷它是通則而非 Codex 調校的理由；「丟掉會
失去」欄寫不保留的後果。引文是 legacy 原文（在 `hosts/codex/src/` 或 plugin 內，行號見括號）。

### N1　列 B1

bootstrap:L6-7

```text
Shoal orchestration is active. Preserve the user's Persona and Agent Rules;
shoal supplements them and does not replace their precedence boundary.
```

- 通則的理由：這是 managed block 與使用者自己的 Persona／Agent Rules 之間的優先序，不涉及 model 或工具。
  Claude 的 core bootstrap 同樣會裝進使用者檔案，卻沒有這句。
- 丟掉會失去：常駐文字裡唯一說明 shoal 不取代使用者規則的句子；`bootstrap-ownership` 只說 delegation
  defaults 勝過 host 內建指引，沒提使用者規則。若保留要放進 frame 或 addendum，約 148 位元組、3 行，第 5 節的
  bootstrap 預算已無空間（8.1）。

### N2　列 O4、O6、S6、S8、S11、R2

orch:L16-21

```text
| Role | Boundary |
|---|---|
| `scout` | Broad or focused read-only repository reconnaissance |
| `plan-critic` | Pre-approval Plan challenge; `READY` or `REVISE` |
| `security-reviewer` | Pre-approval read-only security evidence |
| `applier` | Fully specified mechanical implementation |
```

orch:L23-27

```text
| `executor` | Bounded implementation requiring local judgment |
| `verifier` | Calibrated completed-work falsification; `CONFIRMED`, `REFUTED`, or `INCONCLUSIVE` |
| `security-executor` | Approved security-sensitive implementation |
| `watcher` | Long-running command or CI run followed to a terminal state; reports exit status and deciding output |
| `researcher` | Read-only external research with a source for every claim |
```

- 通則的理由：這是 role 名冊與邊界摘要，不是義務；除了 `sol-executor` 一列，內容與各 role 自己的 contract（
  `core/contracts/*.toml`）重複。core 的 policy 沒有這張表。
- 丟掉會失去：一眼看全 role 邊界與「不可做的事」；邊界仍在各 role contract，派工路徑仍在 `execution-gate`、
  `bootstrap-delegate-default`。影響測試：`tests/test_delegation_default.py:214-216`
  。

### N3　列 O27、O31

orch:L139-141

```text
Before choosing a Plan shape or role, classify the request on intent,
impact, reversibility, and authority. Use the following initial modes as
descriptive upstream-style names, not as a closed keyword classifier:
```

orch:L149-152

```text
These modes cover the first implementation examples, not every future
scenario. Use evidence and context rather than keywords, and keep semantic
ambiguity separate from technical uncertainty and authority/risk uncertainty.
Clear intent does not require `explore_then_plan` by itself: a bounded release
```

- 通則的理由：如何判斷 routing 模式的方法，與 Codex 無關。core 的 `interaction-shape` 只依 outcome／
  acceptance 是否清楚分類。
- 丟掉會失去：失去「依 intent、impact、reversibility、authority 四軸分類」「模式不是封閉關鍵字分類器」「語意歧義、技術
  不確定、authority／risk 不確定三者分開」三個指示。

### N4　列 O32

orch:L152-153

```text
Clear intent does not require `explore_then_plan` by itself: a bounded release
request may remain `execute` with `next_gate=approval`. The approval gate
```

- 通則的理由：這是 routing 與 approval 互動的澄清，不涉及 Codex。
- 丟掉會失去：core 的 `interaction-shape` 把「otherwise-clear direction is
  broad/high-impact」歸 `explore_then_plan`，release 請求可能被劃進去而進入唯讀第一回合；legacy 明說有
  界 release 可以走 `execute` 加 `next_gate=approval`。丟掉會改變這類請求的行為。

### N5　列 O39

orch:L183-184

```text
`AUTO` and `ASK` are presence gates for likely long unattended work, not a
per-command or per-phase approval workflow. An attended task with clear scope
```

- 通則的理由：這句定義 `AUTO`／`ASK` 的性質，與 Codex 無關。它是 `LOCK.json` 兩個 surface 的 required
  fragment，也被兩個測試釘住。
- 丟掉會失去：失去「AUTO／ASK 不是逐指令或逐 phase 核准流程」這個限定；core 只有 `auto-ask-selection` 說何時提供
  。lock 與測試的處理見第 4、6 節。

### N6　列 O51

orch:L222-236

```text
Record these logical signals in the internal route decision:

- `intent_confidence`: `clear`, `partial`, or `unclear`.
- `change_impact`: `trivial`, `low`, `material`, `high`, or `critical`.
  `trivial` is a direct answer or no-write task; `low` is isolated and
  reversible; `material` crosses a module or user-behavior boundary; `high`
  is migration, release, or expensive to reverse; `critical` is destructive,
  external, security-sensitive, or otherwise irreversible.
- `reversible`: `yes`, `partial`, or `no`.
- `discovery_budget`: `none`, `minimum`, `bounded`, or `deep`.
- `budget_exhausted`: whether the selected discovery ceiling was reached.
- `evidence_sufficient`: whether the evidence supports the next gate.
- `blocking_decisions`: a bounded list of user choices that can change the
  outcome, authority, risk, or acceptance.
- `next_gate`: `discovery`, `approval`, `execution`, or `direction_check`.
```

- 通則的理由：這是 route decision 的記錄欄位表，被 `install/evaluate_dispatch.py:62-87`、
  `:386-390`、`install/execution_contract.py` 與
  `docs/specs/adaptive-intent-routing/live-routing-output.schema.json` 驗證，是通用的
  routing 紀錄格式，不是 Codex 調校。
- 丟掉會失去：失去 `intent_confidence`、`change_impact`（五級與定義）、`reversible`、
  `discovery_budget`、`budget_exhausted`、`evidence_sufficient`、
  `blocking_decisions`、`next_gate` 的定義；core 只有 `route-fields` 的三個欄位。上述評測工具照樣在，
  但 prompt 不再要求模型輸出這些欄位。

### N7　列 O57

orch:L260-262

```text
directly choose a reasonable default and continue. Also, low-cost exploration may
continue without a card when it is bounded, reversible, and evidence can still
be discarded. The policy must not ask the user to approve every small ambiguity.
```

- 通則的理由：通用的 checkpoint 例外，與 Codex 無關。
- 丟掉會失去：失去「有界、可逆、證據可丟棄的探索不必出 card」的明文許可；core 的 `checkpoint-default` 已讓低風險工作用預設
  繼續，實際損失小。

### N8　列 O63

orch:L272-273

```text
The checkpoint is an exception decision mechanism, not a step-by-step approval
workflow, and is not a replacement for the internal Plan or an approval bypass.
```

- 通則的理由：通用的 checkpoint 性質宣告。
- 丟掉會失去：失去「checkpoint 不取代內部 Plan、不是核准的繞道」；`explicit-approval-only`（required）仍擋
  住以自由文字當核准。

### N9　列 O81、O83

orch:L379-380

```text
claim `READY` or `CONFIRMED`, or emit `PAUSED_NEEDS_USER` solely because the
service is unavailable. Preserve read-only local work and block only the
```

orch:L381-382

```text
affected write or claim; unrelated approved safe slices may continue. Resume
from the recorded gate when a valid receipt or a genuine user decision arrives.
```

- 通則的理由：review 服務失敗時的行為，與 Codex 無關；`hooks/shoal_autoroute_gate.py` 的
  `BLOCK_REASON` 對 Codex 說了同一句（「Do not emit PAUSED_NEEDS_USER or ask the user
  solely because this review is pending」）。
- 丟掉會失去：失去「不得僅因服務不可用就 emit `PAUSED_NEEDS_USER`」與「收到有效 receipt 或真正的使用者決定後從記錄的
  gate 恢復」兩句；core 只說這是 service failure、不是 user decision。測試釘住第一句（
  `tests/test_policy.py:453`）。

### N10　列 O87

orch:L402-407

```text
runnable tasks before revisiting a blocked task. Two or more runnable tasks with
no dependency path or write-ownership conflict should execute horizontally in
parallel, subject to the bounded concurrency limit and the main session's
integration ownership. Tasks with a dependency path execute after their
predecessors; tasks sharing a mutable resource or exclusive file scope are
serialized. A blocked task does not block sibling tasks unless a dependency edge
```

- 通則的理由：任務並行與序列化的調度規則，與 Codex 無關；core 的並行條款（`parallel-launch`、
  `parallel-writers`）針對 agent 的啟動，不針對 task。
- 丟掉會失去：失去「無依賴、無寫入衝突的 runnable task 應水平並行」「有依賴者在前驅之後」「共用 mutable 資源或獨占檔案範圍者序列化
  」。`SKILL.md:L76-79` 有簡短版。測試：`tests/test_policy.py:297-300`。

### N11　列 O98、O101

orch:L478-482

```text
Answer status or explanation requests without treating them as decision
resolution; resume only work not gated by the unresolved decision, otherwise
remain paused at the recorded resume point. Incorporate other steering or
corrections and then resume the remaining work unless a pending decision or
user-requested pause still gates it.
```

orch:L491-492

```text
pause remains in force through status or explanation requests until the user
explicitly asks to resume or new input clearly supersedes the objective. This
```

- 通則的理由：使用者輸入穿插時的恢復規則，與 Codex 無關。core 的 `objective-persists`、`pause-statement`
  只涵蓋 objective 保持有效、暫停前的陳述、明示暫停。
- 丟掉會失去：失去「狀態或說明詢問不解決待決事項，只做不受它限制的工作，否則停在 resume point」「吸收其他導正後繼續」「暫停在狀態詢問期間持續
  到使用者明示恢復」。測試：`tests/test_policy.py:264-268`、`:275-277`。

### N12　列 O109

orch:L517-519

```text
Weigh lower cost or quota use, preservation of scarce main-session context, true
parallelism, isolated ownership, and fresh-context independence against context
reconstruction, coordination, integration, and verification cost.
```

- 通則的理由：委派權衡的判準清單，與 Codex 無關。core 改為「穩定執行契約的實作預設委派」，沒有權衡清單。
- 丟掉會失去：失去對非實作類委派（旁支問題、研究以外的探索）的成本效益判準。實作類的權衡已被 A3 規則 1 取代（O108）。

### N13　列 O119

orch:L574-576

```text
claim. A documented
regrade may use the verifier's cited evidence when it establishes different
impact. Never call a blocker fixed without contrary evidence or a successful
```

- 通則的理由：verdict 處置規則，與 Codex 無關。
- 丟掉會失去：失去「有紀錄的 regrade 可用 verifier 引用的證據」；core 的 `final-report` 只要求列出
  regraded findings，沒有說 regrade 的依據。測試：`tests/test_policy.py:384-386`。

### N14　列 S3

SKILL.md:L24

```text
Keep the task boundary as `goal -> in-scope -> stop condition`. Do not expand
```

- 通則的理由：通用的任務邊界格式（來自使用者的共用契約），與 Codex 無關。
- 丟掉會失去：失去 Skill 開頭的三段式邊界提示；`step-vs-outcome`、`material-gates-first` 已涵蓋停止條件。

### N15　列 R5、R7

recovery-contract:L3

```text
- Preserve the last verified good checkpoint.
```

recovery-contract:L6

```text
- Never overwrite an independently changed user policy or external artifact.
```

- 通則的理由：checkpoint 與外部 artifact 保護，屬通用的恢復規則（只出現在 plugin reference）。後者的實作面是
  installer 保留標記區外位元組。
- 丟掉會失去：失去「保留最後一個已驗證的好 checkpoint」「不得覆寫獨立變更過的使用者 policy 或外部 artifact」兩句；這兩份
  reference 不在 `LOCK.json`。

## 3. Typed spawn transport block

範圍是 `orch:L645-670`（兩個 marker 之間），逐字如下。

```text
<!-- shoal-codex:spawn-transport:begin -->
#### Native typed spawn policy

Use Codex's native typed `spawn_agent` surface. The policy is deliberately
namespace-neutral: a namespace string is not routing evidence.

Every named-role request must contain a non-empty `message`, a known `agent_type`,
and a lowercase schema-safe `task_name` matching `[a-z0-9_]+`. Use
`fork_turns = "none"` by default. A recent-turn fork is only the positive integer
string `"1"` through `"3"`. Do not use a full-history named-role fork.

Do not pass child `model`, `reasoning_effort`, `service_tier`, or
`fork_context` overrides. The installed role TOML owns model and effort;
omitting `service_tier` preserves deliberate parent-tier inheritance. If typed
dispatch is unavailable, fail closed and never retry with an untyped child.

Typed dispatch is an all-or-nothing child-creation boundary. No untyped
fallback is permitted: if the request cannot be constructed or typed capability
is unavailable, the parent must not silently substitute an untyped child; it
either takes the bounded work locally under the dispatch brake or reports
delegation unavailable.

This is request-construction policy. Current receipt validation is post-hoc evidence
classification, not a reliable pre-execution cancellation hook.
`max_depth` is V1 compatibility state only and does not enforce this boundary.
<!-- shoal-codex:spawn-transport:end -->
```

### 3.1 逐句處置

| 列 | 位置 | 內容 | 處置 | 備註 |
|---|---|---|---|---|
| T0 | L645-646 | begin marker 與 `#### Native typed spawn policy` 標題 | 留（`AO3`） | 標題被 `tests/test_install.py:641` 當作「舊整份 policy 才有、新 bootstrap 沒有」的標記 |
| T1 | L648-649 | 使用 Codex 原生 typed `spawn_agent`；policy 與 namespace 無關 | 留 | hook 實測 payload 的工具名是 `collaborationspawn_agent`（spec D6），`hooks/shoal_guard.py:1583` 兩種都收 |
| T2 | L651-654 | 非空 `message`、已知 `agent_type`、`[a-z0-9_]+` 的 `task_name`、`fork_turns` 預設 `none`、近期 fork 只能是 "1" 到 "3"、不做 full-history fork | 留 | 與 `hooks/shoal_autoroute_gate.py:1427-1434` 的驗證一致（鍵集合恰為 message、agent_type、task_name、fork_turns） |
| T3 | L656-659 | 不傳 child 的 `model`／`reasoning_effort`／`service_tier`／`fork_context`；role TOML 擁有 model 與 effort；typed dispatch 不可用就 fail closed，不退回 untyped child | 留 | 這是省略 effort 規則的依據；「fail closed」與 A3 規則 2 一致 |
| T4 | L661-663 | typed dispatch 是全有或全無的邊界；不允許 untyped fallback；parent 不得默默改用 untyped child | 留 |  |
| T5 | L663-665 | 「it either takes the bounded work locally under the dispatch brake or reports delegation unavailable」 | A3 規則 2：刪掉「takes the bounded work locally under the dispatch brake or」（69 位元組），只留「reports delegation unavailable」 | 這句讓 parent 在 typed dispatch 不可用時自己做事，與 `mech-direct-blocker`、`delegate-cost-benefit` 衝突 |
| T6 | L667-669 | 這是 request-construction policy；receipt 驗證是事後證據分類；`max_depth` 只是 V1 相容狀態 | 留 |  |
| T7 | L670 | end marker | 留 |  |

### 3.2 依賴這個 block 的測試與 installer 行

| 位置 | 釘住的文字 | 處置 | 備註 |
|---|---|---|---|
| test_policy.py:21 | `` `task_name` matching `[a-z0-9_]+` `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:21 | `` known `agent_type` `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:21 | `` non-empty `message` `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:22 | `` `"1"` through `"3"` `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:22 | `` `fork_turns = "none"` `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:22 | `full-history named-role fork` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:23 | `` child `model`, `reasoning_effort`, `service_tier`, or `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:23 | `never retry with an untyped child` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:24 | `Current receipt validation is post-hoc` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:24 | `namespace-neutral` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:27 | `agents.spawn_agent` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_policy.py:70 | `proactively dispatch the least expensive matching native typed role` | 改斷言為 core 句子 | bootstrap-delegate-default；one-shot-spec（B6） |
| test_policy.py:178 | `all-or-nothing child-creation boundary` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:179 | `No untyped fallback is permitted` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:180 | `must not silently substitute an untyped child` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:181 | `takes the bounded work locally` | 隨 A3 移除 | O139：A3 規則 2（parent 不接手） |
| test_templates.py:89 | `` native typed `spawn_agent` `` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:90 | `` non-empty `message` `` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:91 | `` `agent_type` `` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:92 | `` `[a-z0-9_]+` `` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:93 | `` `"1"` through `"3"` `` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:94 | `never retry with an untyped child` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:95 | `post-hoc` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:96 | `agents.spawn_agent` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_templates.py:97 | `fork_turns = "all"` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_templates.py:164 | `Typed dispatch is an all-or-nothing child-creation boundary` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:165 | `No untyped fallback is permitted` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:166 | `must not silently substitute an untyped child` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:167 | `retry as an untyped child` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_install.py:641 | `#### Native typed spawn policy` | 不受影響 | 標題在 orchestration addendum；bootstrap 不含 |
| test_render_codex.py:32-40 | golden 位元組比對（含此 block） | 需重生 golden | 見 6.3 |

- `spawn-transport:begin/end` 這兩個 marker 沒有任何程式碼使用：`grep` 在 `install/`、
  `tools/`、`hooks/`、`tests/` 都找不到，只出現在三份 policy 文字、
  `tests/golden/codex/agents-md.orchestration.md` 與
  `docs/specs/shoal-rebrand/RENAME.md:15`。
- `install/install.py:53-54` 的 `MARKER_BEGIN`／`MARKER_END` 是外層的
  `shoal-codex:begin/end`，`merge_instruction_text`（`:476-484`）與
  `install/probe_hybrid_runtime.py:23-34`、`install/legacy_codex.py:56-57`、
  `:261-270` 只認這一對；orchestration 檔的 frame 必須保留這一對，
  `tests/test_install.py:625-641` 才能模擬「舊整份 policy」。
- `hooks/shoal_autoroute_gate.py:73-79` 的 `ROUTE_ESCALATION_REQUIRED` 訊息重述 T2、
  T3 的規則（`task_name=automatic_model_route`、`fork_turns=none`、不傳 model 或
  reasoning 覆寫、不做 full-history fork）；這是行為依賴，不是文字依賴。

## 4. required_fragments 處置

驗證方式：把 `LOCK.json` 每個 Codex surface 的 fragment 用 `validate_prompt_lock` 的正規化（空
白壓縮加 casefold）對暫存副本的 core 輸出逐一比對。`validate_prompt_lock.py:294-310` 的大小上限、
fragment、mirror 比對是無條件檢查；migration marker 只免除變更預算（`:426-444`）。這份文件不改
`LOCK.json`，下表是建議。

| surface | fragment | core 輸出仍逐字含有 | 建議處置 | 依據（core 句子／位元組） |
|---|---|---|---|---|
| bootstrap-policy | `Treat a clear request to fix or complete something as one outcome` | 否 | 換成同一 surface 上的 core 句子 | `A clear request to fix or finish is one outcome: continue to acceptance.`（bootstrap-outcome） |
| bootstrap-policy | `Phase updates do not require approval` | 否 | 移到 core 規則實際所在的 surface | extensions 檔：`Reporting a phase boundary is progress reporting, not a request for approval or a reason to pause.`（continuation-default） |
| bootstrap-policy | `` AUTO`/`ASK` only for explicit unattended continuation `` | 否 | 移到 core 規則實際所在的 surface | orchestration 檔：`` Before likely long autonomous work, offer `AUTO` or `ASK` and wait, unless ... ``（auto-ask-selection）；語意不同，見 8.4 |
| bootstrap-policy | `material approval, security, release, destructive, external, and irreversible gates` | 否（core 是 `or irreversible`，且在 extensions 檔） | 換成同一 surface 上的 core 句子 | `Material gates always stop.`（bootstrap-outcome） |
| orchestration-template | `Outcome-level continuation` | 否（在 extensions 檔，`continuation-heading`） | 移到 core 規則實際所在的 surface | extensions 檔：`## Outcome-level continuation` |
| orchestration-template | `execution_scope` | 否（在 extensions 檔，`route-fields`） | 移到 core 規則實際所在的 surface | extensions 檔：`` - `execution_scope`: `step`, `slice`, or `outcome`. `` |
| orchestration-template | `phase boundary is progress reporting` | 否（在 extensions 檔） | 移到 core 規則實際所在的 surface | extensions 檔：`Reporting a phase boundary is progress reporting, not a request ...`（continuation-default） |
| orchestration-template | `presence gates for likely long unattended work` | 否 | core 沒有對應 | N5；若以 addendum 保留原句：154 位元組（含分隔），錨點 `after:auto-ask-selection` |
| orchestration-template | `material approval, security, release, destructive, external, or irreversible gates` | 否（在 extensions 檔，`material-gates-first`） | 移到 core 規則實際所在的 surface | extensions 檔：`Material approval, security, release, destructive, external, or irreversible gates always take precedence ...` |
| packaged-orchestration-policy | `Outcome-level continuation` | 否（在 extensions 檔，`continuation-heading`） | 移到 core 規則實際所在的 surface | extensions 檔：`## Outcome-level continuation` |
| packaged-orchestration-policy | `execution_scope` | 否（在 extensions 檔，`route-fields`） | 移到 core 規則實際所在的 surface | extensions 檔：`` - `execution_scope`: `step`, `slice`, or `outcome`. `` |
| packaged-orchestration-policy | `phase boundary is progress reporting` | 否（在 extensions 檔） | 移到 core 規則實際所在的 surface | extensions 檔：`Reporting a phase boundary is progress reporting, not a request ...`（continuation-default） |
| packaged-orchestration-policy | `presence gates for likely long unattended work` | 否 | core 沒有對應 | N5；若以 addendum 保留原句：154 位元組（含分隔），錨點 `after:auto-ask-selection` |
| packaged-orchestration-policy | `material approval, security, release, destructive, external, or irreversible gates` | 否（在 extensions 檔，`material-gates-first`） | 移到 core 規則實際所在的 surface | extensions 檔：`Material approval, security, release, destructive, external, or irreversible gates always take precedence ...` |
| orchestration-skill | `bounded task routing` | 否（core skill 文件沒有） | 保留 | Codex 的 skill frame 沿用 legacy frontmatter（`SKILL.md:L1-4`，414 位元組）；原句在 `description` |
| orchestration-skill | `fresh-context verification` | 否 | 保留 | 同上（`description`） |
| orchestration-skill | `CONFIRMED` | 否（在 orchestration 檔） | 移到 core 規則實際所在的 surface | `... returns **CONFIRMED**, **REFUTED**, or **INCONCLUSIVE** under its role contract.`（review-verdicts） |
| orchestration-skill | `REFUTED` | 否（同上） | 移到 core 規則實際所在的 surface | 同上 |
| orchestration-skill | `INCONCLUSIVE` | 否（同上） | 移到 core 規則實際所在的 surface | 同上；skill 本身可換成 `Read only the part needed for the current decision`（references-intro）與 `do not claim full shoal verification`（reference-fail-soft），Claude 的對應 surface 就是這樣用（LOCK claude-orchestration-skill） |
| plugin-agent-prompt | `Use shoal orchestration for this task` | 不適用（檔案不變） | 保留 | `openai.yaml` 手寫，core 不產生 |
| plugin-agent-prompt | `user explicitly started an Astra main session` | 不適用 | 保留 | 同上；此檔的 `default_prompt` 內含 Astra 調校（8.9） |
| plugin-agent-prompt | `unchanged approval gates` | 不適用 | 保留 | 同上 |
| plugin-manifest-description | `Hybrid shoal orchestration` | 不適用（檔案不變） | 保留 | `plugin.json` 手寫 |
| plugin-manifest-description | `Shoal orchestration workflow` | 不適用 | 保留 | 同上 |
| plugin-manifest-description | `fresh-context verification` | 不適用 | 保留 | 同上（此檔自己含有） |
| plugin-manifest-description | `Apply shoal orchestration to this task.` | 不適用 | 保留 | 同上 |

共 26 個 fragment：換成同一 surface 上的 core 句子 2；移到 core 規則實際所在的 surface 13；core 沒有對應
2；保留 9。沒有任何一項建議用 `以 Codex addendum 保留原句`；唯一不得不二選一的是 N5（`presence gates ...`），保
留它要 154 位元組，不保留就要把兩個 surface 的這個 fragment 刪掉。

其他 Codex surface（六個 role `templates/agents/*.toml`、`templates/hooks.json`、
`INSTALL_PROMPT.md`）的 fragment 來源是 `core/contracts`、`hooks.json` 與
`INSTALL_PROMPT.md`，這次切換不動它們，所以不受影響（未逐項重跑；`validate_prompt_lock` 在這些檔案不變時不會改變結
果）。

連帶要改的 lock 欄位（事實，不是提案）：三個 policy surface 與 SKILL.md 的內容差異遠超變更預算（見 5.4），所以需要新的
migration marker；`orchestration-template`、`packaged-orchestration-policy` 目前的
`delegation-default-3-0-0` 已在 base，新的 marker 必須換一個 `migration_id`（
`validate_prompt_lock.py:426-431`）；`bootstrap-policy` 與 `orchestration-skill`
目前沒有 marker。新增 extensions 的兩個 surface 需要 `--allow-lock-update`（`:402-424`）。

## 5. 大小預算

### 5.1 暫存渲染的假設

| key | 使用的值 | 依據 |
|---|---|---|
| dispatch_tool | `spawn_agent` | `hooks/shoal_guard.py:172`；`orch:L648` |
| question_tool | `request_user_input` | `orch:L311`、`L605-606` |
| named_roles | 十個 role（含 `sol-executor`、`watcher`、`researcher`） | `hosts/codex/binding.toml:43-85`；legacy `orch:L6-9` 只列八個 |
| shell_tool | `Bash` | `hooks/shoal_guard.py:1580` |
| write_tools | `apply_patch` | `hooks/shoal_guard.py:1571` |
| read_tools | `Bash` | 假設；repo 內找不到 Codex 的讀檔工具名（8.2） |
| background_option | 22 個字元的替身字串 | 沒有證據；`tests/test_policy.py:320` 要求 policy 不含 `run_in_background`（8.2） |
| worktree_option | 22 個字元的替身字串 | 沒有證據；`tests/test_policy.py:321`（8.2） |
| model_param／effort_param／label_param | `model`／`reasoning_effort`／`task_name` | `orch:L656`、`L652`；後兩者的條款被省略，但 `require_policy_complete` 要求詞彙內每個 key 都有值（`tools/render.py:347-358`） |
| goal_command／skill_term | `/goal`／`Skill` | `orch:L597`；`bootstrap:L42-44` |
| policy_doc／extensions_doc／references_dir | `orchestration-policy.md`／`workflow-extensions.md`／`references/` | `SKILL.md:L91`；extensions 檔名是假設（Codex 沒有這個檔） |

替身字串的長度每多（少）一個字元，bootstrap 多（少）1 位元組（1 處使用），orchestration 多（少）3 位元組（
`parallel-launch`、`watcher-long-commands`、`leaf-cannot-finish`），
`worktree_option` 在 orchestration 1 處。

### 5.2 bootstrap

frame：`<!-- shoal-codex:begin -->`、`<!-- shoal-codex v3.4.0 -->`、markdownlint
註解、`### Shoal always-on bootstrap`、空行（共 5 行 132 位元組），加上結尾的空行與
`<!-- shoal-codex:end -->`（2 行 26 位元組）：frame 合計 **158 位元組、7 行**（`orch:` 的對應是
`bootstrap:L1-5`、`L46-47`）。

| 項目 | 位元組 | 行 | 備註 |
|---|---|---|---|
| bootstrap-delegate-default | 808 | 12 | 含 1 處 `background_option`（22 字元替身） |
| bootstrap-risk（required） | 281 | 4 |  |
| bootstrap-named-roles（required） | 221 | 2 | 十個 role 的清單在第一行 |
| bootstrap-routing | 205 | 3 |  |
| bootstrap-load-skill | 188 | 3 |  |
| bootstrap-ownership | 183 | 3 |  |
| bootstrap-collect | 177 | 3 |  |
| bootstrap-verify-report | 161 | 2 |  |
| bootstrap-outcome | 134 | 2 |  |
| bootstrap-questions | 133 | 2 |  |
| bootstrap-security（required） | 77 | 1 |  |
| bootstrap-dispatch-brake（拆分後只剩 model 與 scope） | 53 | 1 |  |
| bootstrap-dispatch-effort（省略） | 293 | 4 | 省略 |
| bootstrap-dispatch-label（省略） | 109 | 2 | 省略 |
| 指標句（2 行草稿） | 157 | 2 | 見下 |

拆分方式：現行 `bootstrap-dispatch-brake` 是一條 461 位元組（Codex 值，7 行）的條款，含 effort、model
與 scope、label 三件事，且 sep 只能接在整條之後，省略任何一段都會讓剩下的文字黏在前一個條目上（暫存渲染實測：省略 effort 段後，剩下
的 Omit 接在上一條的行尾，沒有 "- " 前綴）。拆成三條，各自是獨立的條列項（各自帶 "- " 前綴與 newline 分隔）：

- `bootstrap-dispatch-effort`：原文第一句，從 "Explicit instruction:" 到 "high for
  security-reviewer)."；
- `bootstrap-dispatch-brake`（保留此 id）：`` - Omit `{{model_param}}` for named
  roles, state scope and stop. ``
- `bootstrap-dispatch-label`：`` - Start the `{{label_param}}` of every
  write-capable call with `fix:`, `feat:`, `refactor:`, `test:`, or `docs:`.
  ``

這會讓 Claude 的 claude-md.bootstrap.md 由 3103 變 3099 位元組（行數不變，diff 只在第 36-38 行：原本
「Omit ... and start」連在同一個條目的句子變成三個條目），需重生 Claude 的 golden 與 dist，並動到
`tests/test_delegation_default.py:397-398`（順序 effort、brake、label 時 brake 後面不再是
collect；改成 effort、label、brake 則不必改測試，但句子順序與現行不同）。

省略 effort 與 label 兩段共省 **404 位元組、6 行**（293 + 109 加兩個換行分隔；全條款版 3196 B／52 行，省略後
2792 B／46 行）。orchestration 側的 `effort-per-delegation`（534 B／7 行）與
`dispatch-kind-label`（203 B／3 行）省 739 位元組、10 行。

指標句草稿（2 行，掛 `after:bootstrap-routing`，`sep = "newline"`）：

```text
- Codex model tiers (Luna, Sol, Astra) and the Astra main-session mode: read the
  `shoal-orchestration` Skill's orchestration policy before choosing a tier.
```

| 組合 | 位元組 | 行 | 對上限 |
|---|---|---|---|
| frame + 12 個 core 條款 + 2 行指標句 | 2950 B | 48 行 | 上限 3000 B／48 行：剩 50 B、0 行 |
| 同上，指標句改 3 行（設計稿 213 B） | 3006 B | 49 行 | 超出 6 B、1 行 |
| 同上，指標句 4 行（owner 決定的上限） | 3063 B（4 行草稿實測） | 50 行 | 超出 63 B、2 行 |
| 2 行指標句加 B1 的 Persona 句（148 B、3 行） | 3098 B | 51 行 | 超出 98 B、3 行 |
| 沒有指標句 | 2792 B | 46 行 | 剩 208 B、2 行 |
| 不省略 effort 與 label（沒有指標句） | 3196 B | 52 行 | 超出 196 B、4 行 |

結論：在上限不變、替身字串 22 字元的條件下，指標句最多只能 2 行；owner 決定的「最多四行」在不縮短共用條款時放不滿（8.1）。最大的貢獻者是
`bootstrap-delegate-default`（808 B／12 行）、frame（158 B／7 行）、`bootstrap-risk`（281
B）、`bootstrap-named-roles`（221 B，十個 role 的清單）。

### 5.3 orchestration 與 extensions

| 組合 | 位元組 | 行 |
|---|---|---|
| core orchestration（58 個條款，含 frame 146 B／7 行，省略 effort 與 label） | 18419 B | 274 行 |
| 不省略時 | 19158 B | 284 行 |
| 加 orchestration 側 addenda（AO0-AO5，7689 B） | 26111 B | 417 行 |
| 其中不含 AO0（常駐句逐字搬入，1230 B） | 24879 B | 397 行 |
| 依題目算法：core orchestration + section 1 的全部 addendum 區塊（10821 B） | 29240 B | 約 474 行 |
| 再加上全部 `core 沒有對應` 項若都留成 addendum（orchestration 側 2712 B、extensions 側 1821 B） | 33773 B | 約 555 行 |

對上限 700 行／43000 位元組：所有組合都在內，最大的 33773 B 仍剩 9227 B、約 145 行，沒有超出。最大的貢獻者：core 的
`direction-checkpoint`（1305 B，在 extensions）不計；orchestration 內是
`verdict-authority`（836 B）、`readiness-loop`（750 B）、`recovery-budget`（672 B）、
`risk-review-mandatory`（567 B）、`recheck-and-invalidate`（599 B）；addendum 內是
`AO1`（4367 B）、`AE6`（2289 B）、`AO3`（1340 B）、`AO0`（1230 B）。

| 新 extensions 檔 | 位元組 | 行 |
|---|---|---|
| core extensions（40 個條款，不含 frame） | 9376 B | 170 行 |
| 加 extensions 側 addenda（AE2、AE3、AE5、AE6、AE7，3132 B） | 12508 B | 227 行 |
| 再加 extensions 側的 `core 沒有對應` 項（1821 B） | 14329 B | 約 259 行 |

新檔還要加 frame（Claude 的 `policy-frames/extensions.md` 是 87 位元組）。這個 surface 還沒有
lock 上限；作為參考，Claude 對應的 `claude-workflow-extensions` 上限是 180 行／9600 位元組，core
extensions 單獨（170 行／9376 B）在內，加上 Codex 的 addenda 後是超出 47 行／2908 B（12508 B 對
9600 B）。不提議調高任何上限。這個檔的上限由新增 surface 時的 `LOCK.json` 項目決定，這份文件不替它定值。

plugin skill：core skill 文件 1223 B／28 行，加 frame（Codex frontmatter 414 B 加標題）遠低於
`orchestration-skill` 的 100 行／4700 B。

### 5.4 與現行 lock 變更預算的差距

用 `validate_prompt_lock._diff_metrics` 對暫存輸出與現行檔案比：bootstrap 變更 79 行／5413 字元／比
例 0.932（預算 12／1000／0.2）；orchestration 變更 870 行／55327 字元／0.814（預算 32／3000／0.1）；
SKILL.md 108 行／5636／0.974（預算 14／1200／0.2）。預算全部數倍到數十倍超出，所以每個被改寫的 surface 都需要一次性
的 migration marker（`docs/specs/prompt-document-lock` 的 `update_protocol`）。

## 6. 測試影響

範圍：所有釘住 Codex policy／skill 文字的斷言。掃描方式：對 `tests/test_policy.py`、
`tests/test_templates.py`、`tests/test_astra_routing.py` 的相關測試函式用 AST 取出每個
`assertIn`／`assertNotIn`／`assertRegex` 與迴圈裡的字串，逐一對 core 輸出與 addendum 文字比對；其餘檔案
手動逐條列。分類依 section 1 的列。「改斷言為 core 句子」包含兩種：原句仍逐字在 core 輸出裡（只需改讀的檔案），與措辭不同、必須改寫成
core 的句子（處置欄註明）。

### 6.1 totals

| 類別 | 斷言數 |
|---|---|
| 改斷言為 core 句子 | 199 |
| 改斷言為 addendum 句子 | 90 |
| 隨 A3 移除 | 17 |
| 不受影響 | 44 |
| 待第 2 節決定 | 31 |
| 不再成立 | 1 |
| 合計 | 382 |

`待第 2 節決定`：這些斷言釘的是 `core 沒有對應` 的句子；N 項保留成 addendum 則歸 `改斷言為 addendum 句子`，不保留則歸
`隨 A3 移除` 以外的「刪除斷言」。`不再成立`：`assertNotIn("worktree", policy)`（
`tests/test_policy.py:321`）會被 core 的 `parallel-writers` 與 `leaf-cannot-finish`
（"absolute working/worktree directory"）打破，省略前者也救不了後者。迴圈裡的斷言每個字串算一次；
`tests/test_astra_routing.py:199-211` 的 10 個字串對 4 個來源（bootstrap、policy、
packaged、openai.yaml）各算一次。

### 6.2 逐條

| 位置 | 釘住的文字 | 處置 | 對應 |
|---|---|---|---|
| test_astra_routing.py:200 | `astra-thinking（bootstrap 來源）` | 改斷言為 addendum 句子 | RES 列 B11-B14 搬走；斷言移到 orchestration addendum（AO0／AO1） |
| test_astra_routing.py:200 | `astra-thinking（policy 來源）` | 改斷言為 addendum 句子 | AO1 |
| test_astra_routing.py:200 | `astra-thinking（packaged 來源）` | 改斷言為 addendum 句子 | 同 policy（mirror 位元組相同） |
| test_astra_routing.py:200 | `astra-thinking（openai.yaml 來源）` | 不受影響 | 檔案不變 |
| test_astra_routing.py:201 | `named inputs（bootstrap 來源）` | 改斷言為 addendum 句子 | RES 列 B11-B14 搬走；斷言移到 orchestration addendum（AO0／AO1） |
| test_astra_routing.py:201 | `named inputs（policy 來源）` | 改斷言為 addendum 句子 | AO1 |
| test_astra_routing.py:201 | `named inputs（packaged 來源）` | 改斷言為 addendum 句子 | 同 policy（mirror 位元組相同） |
| test_astra_routing.py:201 | `named inputs（openai.yaml 來源）` | 不受影響 | 檔案不變 |
| test_astra_routing.py:202 | `one sufficient pass（bootstrap 來源）` | 改斷言為 addendum 句子 | RES 列 B11-B14 搬走；斷言移到 orchestration addendum（AO0／AO1） |
| test_astra_routing.py:202 | `one sufficient pass（policy 來源）` | 改斷言為 addendum 句子 | AO1 |
| test_astra_routing.py:202 | `one sufficient pass（packaged 來源）` | 改斷言為 addendum 句子 | 同 policy（mirror 位元組相同） |
| test_astra_routing.py:202 | `one sufficient pass（openai.yaml 來源）` | 不受影響 | 檔案不變 |
| test_astra_routing.py:203 | `max_tool_calls=12（bootstrap 來源）` | 改斷言為 addendum 句子 | RES 列 B11-B14 搬走；斷言移到 orchestration addendum（AO0／AO1） |
| test_astra_routing.py:203 | `max_tool_calls=12（policy 來源）` | 改斷言為 addendum 句子 | AO1 |
| test_astra_routing.py:203 | `max_tool_calls=12（packaged 來源）` | 改斷言為 addendum 句子 | 同 policy（mirror 位元組相同） |
| test_astra_routing.py:203 | `max_tool_calls=12（openai.yaml 來源）` | 不受影響 | 檔案不變 |
| test_astra_routing.py:204 | `max_wall_seconds=300（bootstrap 來源）` | 改斷言為 addendum 句子 | RES 列 B11-B14 搬走；斷言移到 orchestration addendum（AO0／AO1） |
| test_astra_routing.py:204 | `max_wall_seconds=300（policy 來源）` | 改斷言為 addendum 句子 | AO1 |
| test_astra_routing.py:204 | `max_wall_seconds=300（packaged 來源）` | 改斷言為 addendum 句子 | 同 policy（mirror 位元組相同） |
| test_astra_routing.py:204 | `max_wall_seconds=300（openai.yaml 來源）` | 不受影響 | 檔案不變 |
| test_astra_routing.py:205 | `advisory（bootstrap 來源）` | 改斷言為 addendum 句子 | RES 列 B11-B14 搬走；斷言移到 orchestration addendum（AO0／AO1） |
| test_astra_routing.py:205 | `advisory（policy 來源）` | 改斷言為 addendum 句子 | AO1 |
| test_astra_routing.py:205 | `advisory（packaged 來源）` | 改斷言為 addendum 句子 | 同 policy（mirror 位元組相同） |
| test_astra_routing.py:205 | `advisory（openai.yaml 來源）` | 不受影響 | 檔案不變 |
| test_astra_routing.py:206 | `mechanical（bootstrap 來源）` | 改斷言為 addendum 句子 | RES 列 B11-B14 搬走；斷言移到 orchestration addendum（AO0／AO1） |
| test_astra_routing.py:206 | `mechanical（policy 來源）` | 改斷言為 core 句子 | core 句子 |
| test_astra_routing.py:206 | `mechanical（packaged 來源）` | 改斷言為 core 句子 | 同 policy（mirror 位元組相同） |
| test_astra_routing.py:206 | `mechanical（openai.yaml 來源）` | 不受影響 | 檔案不變 |
| test_astra_routing.py:207 | `Luna（bootstrap 來源）` | 改斷言為 core 句子 | core bootstrap／指標句仍含此字 |
| test_astra_routing.py:207 | `Luna（policy 來源）` | 改斷言為 addendum 句子 | AO1 |
| test_astra_routing.py:207 | `Luna（packaged 來源）` | 改斷言為 addendum 句子 | 同 policy（mirror 位元組相同） |
| test_astra_routing.py:207 | `Luna（openai.yaml 來源）` | 不受影響 | 檔案不變 |
| test_astra_routing.py:208 | `plan-critic（bootstrap 來源）` | 改斷言為 core 句子 | core bootstrap／指標句仍含此字 |
| test_astra_routing.py:208 | `plan-critic（policy 來源）` | 改斷言為 core 句子 | core 句子 |
| test_astra_routing.py:208 | `plan-critic（packaged 來源）` | 改斷言為 core 句子 | 同 policy（mirror 位元組相同） |
| test_astra_routing.py:208 | `plan-critic（openai.yaml 來源）` | 不受影響 | 檔案不變 |
| test_astra_routing.py:209 | `Sol（bootstrap 來源）` | 改斷言為 core 句子 | core bootstrap／指標句仍含此字 |
| test_astra_routing.py:209 | `Sol（policy 來源）` | 改斷言為 addendum 句子 | AO1 |
| test_astra_routing.py:209 | `Sol（packaged 來源）` | 改斷言為 addendum 句子 | 同 policy（mirror 位元組相同） |
| test_astra_routing.py:209 | `Sol（openai.yaml 來源）` | 不受影響 | 檔案不變 |
| test_astra_routing.py:212 | `fail-closed（bootstrap）` | 改斷言為 addendum 句子 | B13 搬走；AO1（O11 句） |
| test_astra_routing.py:213 | `no-flags（policy）` | 改斷言為 addendum 句子 | AO1（O11 句） |
| test_astra_routing.py:221 | `packaged == template` | 不受影響 | mirror 仍由 render 維持 |
| test_astra_routing.py:322 | `applier（policy）` | 改斷言為 core 句子 | applier 在 core；Astra 在 AO1 |
| test_astra_routing.py:322 | `applier（bootstrap）` | 改斷言為 core 句子 | core bootstrap 含 applier；Astra 只在指標句（措辭依賴指標草稿） |
| test_astra_routing.py:322 | `applier（applier role）` | 不受影響 | role 檔不變 |
| test_astra_routing.py:322 | `applier（SKILL.md）` | 改斷言為 addendum 句子 | core skill 文件不含；S5／S7／S9 的調校句在 orchestration addendum AO1 |
| test_astra_routing.py:322 | `Astra（policy）` | 改斷言為 addendum 句子 | applier 在 core；Astra 在 AO1 |
| test_astra_routing.py:322 | `Astra（bootstrap）` | 改斷言為 addendum 句子 | core bootstrap 含 applier；Astra 只在指標句（措辭依賴指標草稿） |
| test_astra_routing.py:322 | `Astra（applier role）` | 不受影響 | role 檔不變 |
| test_astra_routing.py:322 | `Astra（SKILL.md）` | 改斷言為 addendum 句子 | core skill 文件不含；S5／S7／S9 的調校句在 orchestration addendum AO1 |
| test_astra_routing.py:324 | `baseline-only（policy）` | 改斷言為 addendum 句子 | AO1（O12） |
| test_astra_routing.py:325 | `baseline-only（bootstrap）` | 改斷言為 addendum 句子 | B4 搬走；指標句若不含此詞即失敗 |
| test_astra_routing.py:326 | `never request Astra（applier role）` | 不受影響 | role 檔不變 |
| test_astra_routing.py:327 | `baseline-only Luna roles（SKILL.md）` | 改斷言為 addendum 句子 | S9 搬到 AO1；SKILL.md 改由 core 產生後不含 |
| test_astra_routing.py:483 | `Capability-first model routing` | 改斷言為 addendum 句子 | AO1（O7／O8／O16） |
| test_astra_routing.py:484 | `` Do not replace `plan-critic` `` | 改斷言為 addendum 句子 | AO1（O7／O8／O16） |
| test_astra_routing.py:485 | `Do not create a new computer-use role` | 改斷言為 addendum 句子 | AO1（O7／O8／O16） |
| test_astra_routing.py:487 | `Route by capability（bootstrap）` | 改斷言為 addendum 句子 | B3 搬走；指標句不含此字 |
| test_astra_routing.py:488 | `benchmark.PARENT_PROMPT 的字串` | 不受影響 | 不讀 policy 檔 |
| test_astra_routing.py:489 | `benchmark.PARENT_PROMPT 的字串` | 不受影響 | 不讀 policy 檔 |
| test_astra_routing.py:490 | `benchmark.PARENT_PROMPT 的字串` | 不受影響 | 不讀 policy 檔 |
| test_astra_routing.py:491 | `benchmark.PARENT_PROMPT 的字串` | 不受影響 | 不讀 policy 檔 |
| test_delegation_default.py:103 | `POLICY_SHA256 codex bootstrap` | 隨 A3 移除 | 守 delegation-default D17（Codex policy 不變）；被 shared-rules A1 取代 |
| test_delegation_default.py:104 | `POLICY_SHA256 codex orchestration` | 隨 A3 移除 | 同上 |
| test_delegation_default.py:214 | `ROLE_ROW 恰兩列（watcher、researcher）` | 待第 2 節決定 | N2：role 表是否保留 |
| test_delegation_default.py:215 | `` codex.count(`watcher`) == 1 `` | 隨 A3 移除 | 守 D17；core 的 watcher-long-commands 等條款會讓 `watcher` 出現多次 |
| test_delegation_default.py:216 | `` codex.count(`researcher`) == 1 `` | 隨 A3 移除 | 守 D17；core 的 research-fanout 等條款會讓 `researcher` 出現多次 |
| test_direction_milestone.py:48 | `with_wrapup in squash(text)（Codex 兩個路徑，目前走 else 分支）` | 改斷言為 core 句子 | direction-checkpoint（extensions 檔）；Codex 路徑要移到 CORE_SURFACES 並改指新 extensions 檔 |
| test_direction_milestone.py:50 | `assertIn(block, text)（Codex 兩個路徑）` | 改斷言為 core 句子 | 改為含 wrap-up 句的 core 句子 |
| test_direction_milestone.py:51 | `assertNotIn(WRAPUP, text)（Codex 兩個路徑）` | 改斷言為 core 句子 | 反轉為 assertIn：core 的 direction-checkpoint 含 wrap-up 句 |
| test_direction_milestone.py:52 | `` assertNotIn("may send the `verifier`")（兩個路徑） `` | 不受影響 |  |
| test_direction_milestone.py:53 | `assertNotIn("may receive the")（兩個路徑）` | 不受影響 |  |
| test_direction_milestone.py:58 | `assertIn(m2b block)（Codex 兩個路徑）` | 改斷言為 core 句子 | cost-unbounded-continuation（extensions 檔）；路徑改指新 extensions 檔 |
| test_install.py:636 | `installed.startswith(prefix)／endswith(suffix)（使用者位元組保留）` | 不受影響 | 與 policy 文字無關 |
| test_install.py:639 | `### Shoal always-on bootstrap` | 不受影響 | bootstrap frame 須保留此標題 |
| test_install.py:641 | `#### Native typed spawn policy 不在 installed` | 不受影響 | orchestration frame 須保留 begin／end marker（舊整份 policy 才能被換掉） |
| test_plugin.py:24 | `shoal-orchestration 在 SKILL.md` | 不受影響 | frame frontmatter 含 name |
| test_plugin.py:25 | `SKILL.md 不含 TODO` | 不受影響 |  |
| test_plugin.py:32 | `references/orchestration-policy.md 存在` | 不受影響 | mirror |
| test_plugin.py:32 | `references/role-contract.md 存在` | 不受影響 | 三份手寫 contract 在 R 列；core skill 只連兩份（8.9） |
| test_plugin.py:32 | `references/verification-contract.md 存在` | 不受影響 | 三份手寫 contract 在 R 列；core skill 只連兩份（8.9） |
| test_plugin.py:32 | `references/recovery-contract.md 存在` | 不受影響 | 三份手寫 contract 在 R 列；core skill 只連兩份（8.9） |
| test_plugin.py:33 | `agents/openai.yaml 存在` | 不受影響 |  |
| test_policy.py:13 | `<!-- shoal-codex v{version} -->` | 不受影響 | policy-frames 須保留版本 marker 行 |
| test_policy.py:16 | `` 每個 templates/agents/*.toml 的 `role` 名稱都出現在 policy（10 個） `` | 不受影響 | intro-named-roles 的 named_roles 列出全部十個 role |
| test_policy.py:21 | `` `task_name` matching `[a-z0-9_]+` `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:21 | `` known `agent_type` `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:21 | `` non-empty `message` `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:22 | `` `"1"` through `"3"` `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:22 | `` `fork_turns = "none"` `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:22 | `full-history named-role fork` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:23 | `` child `model`, `reasoning_effort`, `service_tier`, or `` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:23 | `never retry with an untyped child` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:24 | `Current receipt validation is post-hoc` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:24 | `namespace-neutral` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:27 | `agents.spawn_agent` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_policy.py:33 | `active delegation signal` | 改斷言為 core 句子 | 措辭改寫：bootstrap-delegate-default；delegate-cost-benefit（O17） |
| test_policy.py:34 | `proactively delegate` | 改斷言為 core 句子 | 措辭改寫：bootstrap-delegate-default；delegate-cost-benefit（O17） |
| test_policy.py:35 | `parallel independent discovery` | 改斷言為 core 句子 | 措辭改寫：bootstrap-delegate-default；local-search-direct；discovery-scope-exclusive（O18） |
| test_policy.py:36 | `start them in parallel` | 改斷言為 core 句子 | 措辭改寫：bootstrap-delegate-default；local-search-direct；discovery-scope-exclusive（O18） |
| test_policy.py:37 | `` material Plan to `plan-critic` before approval `` | 改斷言為 core 句子 | 措辭改寫：plan-gate；risk-review-mandatory；security-reviewer-first（O19） |
| test_policy.py:38 | `` pre-approval security evidence to `security-reviewer` `` | 改斷言為 core 句子 | 措辭改寫：plan-gate；risk-review-mandatory；security-reviewer-first（O19） |
| test_policy.py:39 | `` fully specified mechanical repetition to `applier` `` | 改斷言為 core 句子 | 措辭改寫：mech-default；execution-gate（O20） |
| test_policy.py:40 | `` approved, bounded implementation requiring judgment to `sol-executor` `` | 改斷言為 addendum 句子 | AO2 |
| test_policy.py:41 | `risk-triggered implementation` | 改斷言為 core 句子 | 措辭改寫：verification-gate；outcome-verification（O23） |
| test_policy.py:42 | `` fresh `verifier` for one independent refutation pass `` | 改斷言為 core 句子 | 措辭改寫：verification-gate；outcome-verification（O23） |
| test_policy.py:43 | `For low-risk, local, reversible work` | 改斷言為 core 句子 | 措辭改寫：outcome-verification；identity-fingerprint；risk-triggers；review-intent-strict（extensions）（O14） |
| test_policy.py:44 | `exactly one fresh outcome-verifier pass` | 改斷言為 core 句子 | 措辭改寫：outcome-verification；identity-fingerprint；risk-triggers；review-intent-strict（extensions）（O14） |
| test_policy.py:45 | `Do not repeat an unchanged check` | 改斷言為 core 句子 | 措辭改寫：outcome-verification；identity-fingerprint；risk-triggers；review-intent-strict（extensions）（O14） |
| test_policy.py:54 | `Atomic one-command/one-action work` | 改斷言為 addendum 句子 | AO1 |
| test_policy.py:55 | `Normal design, tool choice, interpretation, QA, or bounded implementation` | 改斷言為 addendum 句子 | AO1 |
| test_policy.py:56 | `` `sol-executor` / `verifier` GPT-6 Sol binding `` | 改斷言為 addendum 句子 | AO1 |
| test_policy.py:57 | `Use Astra only at the rare deep tier` | 改斷言為 addendum 句子 | AO1 |
| test_policy.py:58 | `Automatic typed escalation never switches the root model` | 改斷言為 addendum 句子 | AO1 |
| test_policy.py:59 | `main session should not wait for the user to name a subagent` | 改斷言為 core 句子 | 措辭改寫：bootstrap-delegate-default；delegate-cost-benefit（O17） |
| test_policy.py:68 | `Route by capability: atomic, routine, and ordinary tools stay on cheap Luna` | 改斷言為 addendum 句子 | AO0 |
| test_policy.py:69 | `` use Sol; reserve `executor` Astra for deep architecture `` | 改斷言為 addendum 句子 | AO0 |
| test_policy.py:70 | `proactively dispatch the least expensive matching native typed role` | 改斷言為 core 句子 | bootstrap-delegate-default；one-shot-spec（B6） |
| test_policy.py:79 | `clear bounded workstream or mandatory review` | 改斷言為 core 句子 | bootstrap-delegate-default；one-shot-spec（B6） |
| test_policy.py:80 | `proactively dispatch` | 改斷言為 core 句子 | 措辭改寫：bootstrap-delegate-default；one-shot-spec（B6） |
| test_policy.py:81 | `tightly coupled local action in the parent` | 隨 A3 移除 | B7：通則（矛盾時以 core 為準） |
| test_policy.py:82 | `do not create a child for every command` | 改斷言為 core 句子 | brake-per-call；dispatch-brake（B8） |
| test_policy.py:83 | `wait for the user to name the next phase` | 改斷言為 core 句子 | brake-per-call；dispatch-brake（B8） |
| test_policy.py:91 | `` `applier` and `scout` are baseline-only `` | 改斷言為 addendum 句子 | AO0、AO1 |
| test_policy.py:92 | `never request Astra` | 改斷言為 addendum 句子 | AO0、AO1 |
| test_policy.py:94 | `` route normal work to `sol-executor`; deep work to `executor`/`verifier` `` | 改斷言為 addendum 句子 | AO1 |
| test_policy.py:103 | `General-mode decision checkpoint contract` | 改斷言為 core 句子 | 措辭改寫：checkpoint-default；checkpoint-question（O64） |
| test_policy.py:104 | `shoal-decision-checkpoint-v1` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:105 | `exactly two or three mutually exclusive options` | 改斷言為 core 句子 | 措辭改寫：checkpoint-default（O67） |
| test_policy.py:106 | `checkpoint_id` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:107 | `current_interpretation` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:108 | `recommended_option` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:109 | `affected_task_ids` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:110 | `resume_point` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:111 | `approval_boundary` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:112 | `exact option number or identifier confirms` | 改斷言為 core 句子 | 措辭改寫：checkpoint-reply（O71） |
| test_policy.py:113 | `explicit rejection keeps the affected tasks pending or blocked` | 改斷言為 core 句子 | 措辭改寫：checkpoint-reply（O71） |
| test_policy.py:114 | `ambiguous reply remains pending` | 改斷言為 core 句子 | 措辭改寫：checkpoint-reply（O71） |
| test_policy.py:115 | `Never treat a plausible free-text answer as approval` | 改斷言為 core 句子 | explicit-approval-only（extensions） |
| test_policy.py:116 | `confirmed reply produces a resume record` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:117 | `card's implied authorization` | 改斷言為 core 句子 | 措辭改寫：explicit-approval-only（required）（O69） |
| test_policy.py:118 | `Optional MCP elicitation adapter` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:119 | `native decision card is the default interaction surface` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:120 | `optional adapter, not a shoal core dependency` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:121 | `fall back to the native card or concise text checkpoint` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:122 | `one concise, high-level decision` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:123 | `one high-level question` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:124 | `Do not turn a general-mode checkpoint into a Plan-mode questionnaire` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:125 | `defer secondary implementation details` | 改斷言為 addendum 句子 | AE6 |
| test_policy.py:134 | `default is autonomous` | 改斷言為 core 句子 | 措辭改寫：checkpoint-default（O56） |
| test_policy.py:135 | `low-risk, reversible, and scope is clear` | 改斷言為 core 句子 | 措辭改寫：checkpoint-default（O56） |
| test_policy.py:136 | `directly choose a reasonable default` | 改斷言為 core 句子 | checkpoint-default（O56） |
| test_policy.py:137 | `must not ask the user to approve every small ambiguity` | 改斷言為 core 句子 | checkpoint-default（O58） |
| test_policy.py:138 | `only when the choice changes the outcome` | 改斷言為 core 句子 | 措辭改寫：checkpoint-options（O60） |
| test_policy.py:139 | `permission, security, or acceptance boundary` | 改斷言為 core 句子 | 措辭改寫：checkpoint-default（O61） |
| test_policy.py:140 | `low-cost exploration may continue without a card` | 待第 2 節決定 | N7（O57） |
| test_policy.py:141 | `checkpoint is an exception decision mechanism` | 待第 2 節決定 | N8（O63） |
| test_policy.py:142 | `not a step-by-step approval workflow` | 待第 2 節決定 | N8（O63） |
| test_policy.py:146 | `ask the user to approve every decision` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_policy.py:153 | `Outcome-level continuation` | 改斷言為 core 句子 | continuation-heading（extensions） |
| test_policy.py:154 | `not one command, one tool call, or one checklist item` | 改斷言為 core 句子 | execution-unit（extensions） |
| test_policy.py:155 | `` `execution_scope` `` | 改斷言為 core 句子 | route-fields、first-move-steps（extensions／skill） |
| test_policy.py:156 | `` `continuation_mode` `` | 改斷言為 core 句子 | route-fields（extensions） |
| test_policy.py:157 | `` `stop_condition` `` | 改斷言為 core 句子 | route-fields（extensions） |
| test_policy.py:158 | `` default to `execution_scope=outcome` `` | 改斷言為 core 句子 | continuation-default（extensions） |
| test_policy.py:159 | `Continue through the necessary commands, phases, role handoffs, and verification` | 改斷言為 core 句子 | continuation-default（extensions） |
| test_policy.py:160 | `Reporting a phase boundary is progress reporting` | 改斷言為 core 句子 | continuation-default（extensions） |
| test_policy.py:161 | `Explicit wording such as “only inspect this file”` | 改斷言為 core 句子 | 措辭改寫：step-vs-outcome（O37） |
| test_policy.py:162 | `After acceptance, do not add cleanup` | 改斷言為 core 句子 | 措辭改寫：material-gates-first（required）（O38） |
| test_policy.py:163 | `presence gates for likely long unattended work` | 待第 2 節決定 | N5（O39） |
| test_policy.py:164 | `without asking for a mode merely because the work is likely to be long` | 改斷言為 core 句子 | 措辭改寫：auto-ask-selection（O122） |
| test_policy.py:172 | `The parent session remains responsible and accountable throughout` | 改斷言為 core 句子 | 措辭改寫：main-session-owns；bootstrap-ownership（O24） |
| test_policy.py:173 | `reconciles findings` | 改斷言為 core 句子 | 措辭改寫：main-session-owns；bootstrap-ownership（O24） |
| test_policy.py:174 | `integrates writes` | 改斷言為 core 句子 | main-session-owns；bootstrap-ownership（O24） |
| test_policy.py:175 | `makes final judgment` | 改斷言為 core 句子 | main-session-owns；bootstrap-ownership（O24） |
| test_policy.py:176 | `small, local, already-stable edit` | 隨 A3 移除 | O25：A3 規則 1 |
| test_policy.py:177 | `tightly coupled unknown bug` | 改斷言為 core 句子 | single-bug-direct（O26） |
| test_policy.py:178 | `all-or-nothing child-creation boundary` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:179 | `No untyped fallback is permitted` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:180 | `must not silently substitute an untyped child` | 改斷言為 addendum 句子 | AO3 |
| test_policy.py:181 | `takes the bounded work locally` | 隨 A3 移除 | O139：A3 規則 2（parent 不接手） |
| test_policy.py:189 | `Stable multi-file mechanical repetition` | 改斷言為 core 句子 | 措辭改寫：mech-default；mech-collect（O106） |
| test_policy.py:190 | `complete one-shot brief` | 改斷言為 core 句子 | mech-default（orchestration） |
| test_policy.py:191 | `exclusive ownership` | 改斷言為 core 句子 | execution-gate、mech-default（orchestration） |
| test_policy.py:192 | `per-item acceptance` | 改斷言為 core 句子 | mech-default（orchestration） |
| test_policy.py:193 | `` dispatch exactly one `applier` before the main session edits by default `` | 改斷言為 core 句子 | 措辭改寫：mech-default；mech-collect（O106） |
| test_policy.py:194 | `main session owns per-item triage, exceptions, integration, and acceptance` | 改斷言為 core 句子 | 措辭改寫：mech-default；mech-collect（O106） |
| test_policy.py:195 | `must not edit the worker-owned scope` | 改斷言為 core 句子 | 措辭改寫：mech-default；mech-collect（O106） |
| test_policy.py:196 | `specific named blocker before editing` | 隨 A3 移除 | O107：A3 規則 1 與 2 |
| test_policy.py:197 | `evolving or coupled evidence` | 隨 A3 移除 | O107：A3 規則 1 與 2 |
| test_policy.py:198 | `ownership or integration conflict` | 隨 A3 移除 | O107：A3 規則 1 與 2 |
| test_policy.py:199 | `typed worker unavailability` | 隨 A3 移除 | O107：A3 規則 1 與 2 |
| test_policy.py:200 | `non-positive net benefit` | 隨 A3 移除 | O107：A3 規則 1 與 2 |
| test_policy.py:201 | `slightly faster is insufficient` | 隨 A3 移除 | O107：A3 規則 1 與 2 |
| test_policy.py:202 | `default is rebuttable, not unconditional` | 隨 A3 移除 | O107：A3 規則 1 與 2 |
| test_policy.py:210 | `Outside that qualifying mechanical shape, choose delegation by net benefit` | 隨 A3 移除 | O108：A3 規則 1 |
| test_policy.py:211 | `lower cost or quota use` | 待第 2 節決定 | N12（O109） |
| test_policy.py:212 | `preservation of scarce main-session context` | 待第 2 節決定 | N12（O109） |
| test_policy.py:213 | `true parallelism` | 待第 2 節決定 | N12（O109） |
| test_policy.py:214 | `isolated ownership` | 待第 2 節決定 | N12（O109） |
| test_policy.py:215 | `fresh-context independence` | 待第 2 節決定 | N12（O109） |
| test_policy.py:216 | `context reconstruction, coordination, integration, and verification cost` | 待第 2 節決定 | N12（O109） |
| test_policy.py:217 | `Recurring or homogeneous work` | 改斷言為 core 句子 | 措辭改寫：brake-per-call（O110） |
| test_policy.py:218 | `stable, complete one-shot brief, not a numeric trigger` | 改斷言為 core 句子 | 措辭改寫：brake-per-call（O110） |
| test_policy.py:219 | `remaining items must be independent and the same shape` | 改斷言為 core 句子 | 措辭改寫：brake-per-call（O110） |
| test_policy.py:220 | `main session retains triage, exceptions, integration, and acceptance` | 改斷言為 core 句子 | 措辭改寫：brake-per-call（O110） |
| test_policy.py:228 | `smallest coherent integration boundary` | 改斷言為 core 句子 | outcome-verification（orchestration） |
| test_policy.py:229 | `complete claim can be independently refuted` | 改斷言為 core 句子 | 措辭改寫：outcome-verification；readiness-loop（O116） |
| test_policy.py:230 | `Independent review is risk-triggered` | 改斷言為 core 句子 | 措辭改寫：risk-triggers（required）；outcome-verification（O78） |
| test_policy.py:231 | `primary user-visible flow` | 改斷言為 core 句子 | 措辭改寫：risk-triggers（required）；outcome-verification（O78） |
| test_policy.py:232 | `Verify earlier for security changes` | 改斷言為 core 句子 | 措辭改寫：outcome-verification；readiness-loop（O116） |
| test_policy.py:233 | `serialization or other data boundaries` | 改斷言為 core 句子 | 措辭改寫：outcome-verification；readiness-loop（O116） |
| test_policy.py:234 | `irreversible operations` | 改斷言為 addendum 句子 | AE5 |
| test_policy.py:235 | `work that could block later integration` | 改斷言為 core 句子 | 措辭改寫：outcome-verification；readiness-loop（O116） |
| test_policy.py:236 | `substantially unchanged Plan` | 改斷言為 core 句子 | readiness-loop（orchestration） |
| test_policy.py:237 | `material revision or new evidence` | 改斷言為 core 句子 | 措辭改寫：outcome-verification；readiness-loop（O116） |
| test_policy.py:245 | `unfinished root objective remains active across turns` | 改斷言為 core 句子 | 措辭改寫：objective-persists（O96） |
| test_policy.py:246 | `user decision replies` | 改斷言為 core 句子 | 措辭改寫：objective-persists（O96） |
| test_policy.py:247 | `steering or corrections` | 改斷言為 core 句子 | objective-persists（O96） |
| test_policy.py:248 | `status or explanation requests` | 改斷言為 core 句子 | objective-persists（extensions） |
| test_policy.py:249 | `pause or resume` | 改斷言為 core 句子 | 措辭改寫：objective-persists（O96） |
| test_policy.py:250 | `new input does not clearly supersede it` | 改斷言為 core 句子 | 措辭改寫：objective-persists（O96） |
| test_policy.py:251 | `Contextually clear replacement intent may replace the objective` | 改斷言為 core 句子 | 措辭改寫：objective-persists（O96） |
| test_policy.py:252 | `no explicit cancellation phrase is required` | 改斷言為 core 句子 | 措辭改寫：objective-persists（O96） |
| test_policy.py:253 | `replacement intent is materially ambiguous` | 改斷言為 core 句子 | objective-persists（extensions） |
| test_policy.py:254 | `ask one concise clarification instead of silently abandoning it` | 改斷言為 core 句子 | 措辭改寫：objective-persists（O96） |
| test_policy.py:255 | `Before pausing for user input` | 改斷言為 core 句子 | 措辭改寫：pause-statement；checkpoint-reply（O97） |
| test_policy.py:256 | `current phase or slice` | 改斷言為 core 句子 | pause-statement（extensions） |
| test_policy.py:257 | `pending decision or blocker` | 改斷言為 core 句子 | 措辭改寫：pause-statement；checkpoint-reply（O97） |
| test_policy.py:258 | `exact resume point` | 改斷言為 core 句子 | pause-statement（extensions） |
| test_policy.py:259 | `Treat a reply that unambiguously resolves that pending decision` | 改斷言為 core 句子 | 措辭改寫：pause-statement；checkpoint-reply（O97） |
| test_policy.py:260 | `continue from the resume point in the same turn` | 改斷言為 core 句子 | 措辭改寫：pause-statement；checkpoint-reply（O97） |
| test_policy.py:261 | `within existing authorization and scope` | 改斷言為 core 句子 | 措辭改寫：pause-statement；checkpoint-reply（O97） |
| test_policy.py:262 | `If the reply is ambiguous, preserve the pause` | 改斷言為 core 句子 | 措辭改寫：pause-statement；checkpoint-reply（O97） |
| test_policy.py:263 | `ask one concise clarification` | 改斷言為 core 句子 | objective-persists（extensions） |
| test_policy.py:264 | `without treating them as decision resolution` | 待第 2 節決定 | N11（O98） |
| test_policy.py:265 | `resume only work not gated by the unresolved decision` | 待第 2 節決定 | N11（O98） |
| test_policy.py:266 | `otherwise remain paused at the recorded resume point` | 待第 2 節決定 | N11（O98） |
| test_policy.py:267 | `resume the remaining work` | 待第 2 節決定 | N11（O98） |
| test_policy.py:268 | `unless a pending decision or user-requested pause still gates it` | 待第 2 節決定 | N11（O98） |
| test_policy.py:269 | `Do not issue a normal final response` | 改斷言為 core 句子 | 措辭改寫：pause-statement（O99） |
| test_policy.py:270 | `active objective remains incomplete` | 改斷言為 core 句子 | 措辭改寫：pause-statement（O99） |
| test_policy.py:271 | `` explicitly emit `PAUSED_NEEDS_USER` `` | 改斷言為 core 句子 | 措辭改寫：pause-statement（O99） |
| test_policy.py:272 | `If the user explicitly requests a pause` | 改斷言為 core 句子 | 措辭改寫：pause-statement（O99） |
| test_policy.py:273 | `honor it without inventing a blocker or question` | 改斷言為 core 句子 | 措辭改寫：pause-statement（O99） |
| test_policy.py:274 | `active objective, current phase or slice, and exact resume point` | 改斷言為 core 句子 | 措辭改寫：pause-statement（O99） |
| test_policy.py:275 | `pause remains in force through status or explanation requests` | 待第 2 節決定 | N11（O101） |
| test_policy.py:276 | `until the user explicitly asks to resume` | 待第 2 節決定 | N11（O101） |
| test_policy.py:277 | `new input clearly supersedes the objective` | 待第 2 節決定 | N11（O101） |
| test_policy.py:278 | `does not expand approval, security, destructive-action` | 改斷言為 core 句子 | 措辭改寫：ext-no-authority（required）（O102） |
| test_policy.py:279 | `external-action, or scope boundaries` | 改斷言為 core 句子 | 措辭改寫：ext-no-authority（required）（O102） |
| test_policy.py:282 | `only when explicitly cancelled or replaced` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_policy.py:283 | `Treat a plausible reply` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_policy.py:284 | `resume useful in-scope work in the same turn` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_policy.py:291 | `task ledger` | 改斷言為 core 句子 | reference-extensions（skill） |
| test_policy.py:292 | `split a prompt into independently trackable task units` | 改斷言為 core 句子 | 措辭改寫：ledger-split（O84） |
| test_policy.py:293 | `blocked task does not block sibling tasks` | 改斷言為 core 句子 | ledger-runnable（O88） |
| test_policy.py:294 | `runnable task` | 改斷言為 core 句子 | ledger-runnable（extensions） |
| test_policy.py:295 | `dependencies are satisfied` | 改斷言為 core 句子 | 措辭改寫：ledger-runnable（O86） |
| test_policy.py:296 | `Prioritize runnable tasks` | 改斷言為 core 句子 | 措辭改寫：ledger-runnable（O86） |
| test_policy.py:297 | `execute horizontally in parallel` | 待第 2 節決定 | N10（O87） |
| test_policy.py:298 | `no dependency path or write-ownership conflict` | 待第 2 節決定 | N10（O87） |
| test_policy.py:299 | `Tasks with a dependency path execute after their predecessors` | 待第 2 節決定 | N10（O87） |
| test_policy.py:300 | `sharing a mutable resource or exclusive file scope are serialized` | 待第 2 節決定 | N10（O87） |
| test_policy.py:301 | `only blocked tasks remain` | 改斷言為 core 句子 | ledger-blocked-only（extensions） |
| test_policy.py:302 | `one consolidated blocker reminder` | 改斷言為 core 句子 | 措辭改寫：ledger-blocked-only（O90） |
| test_policy.py:303 | `` goal status remains `BLOCKED` `` | 改斷言為 core 句子 | 措辭改寫：ledger-blocked-only（O90） |
| test_policy.py:304 | `` Do not emit `PAUSED_NEEDS_USER` while runnable tasks remain `` | 改斷言為 core 句子 | 措辭改寫：ledger-runnable；ledger-blocked-only（O89） |
| test_policy.py:312 | `Schedule eligible calls by data dependency` | 改斷言為 core 句子 | 措辭改寫：parallel-launch；parallel-writers；collect-results（O145） |
| test_policy.py:313 | `independent typed calls are ready` | 改斷言為 core 句子 | 措辭改寫：parallel-launch；parallel-writers；collect-results（O145） |
| test_policy.py:314 | `` `spawn_agent` calls back-to-back `` | 改斷言為 core 句子 | 措辭改寫：parallel-launch；parallel-writers；collect-results（O145） |
| test_policy.py:315 | `exclusive file ownership` | 改斷言為 addendum 句子 | AO5 |
| test_policy.py:316 | `continue only on disjoint scope` | 改斷言為 core 句子 | 措辭改寫：parallel-launch；parallel-writers；collect-results（O145） |
| test_policy.py:317 | `collect every result before dependent work` | 改斷言為 core 句子 | 措辭改寫：parallel-launch；parallel-writers；collect-results（O145） |
| test_policy.py:320 | `run_in_background` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_policy.py:321 | `worktree` | 不再成立 | assertNotIn：core 的 parallel-writers、leaf-cannot-finish 含此字；見 8.2 |
| test_policy.py:332 | `program envelope` | 改斷言為 core 句子 | plan-gate、envelope-then-slice（orchestration） |
| test_policy.py:333 | `next executable slice` | 改斷言為 core 句子 | envelope-then-slice（orchestration） |
| test_policy.py:334 | `scope, non-goals` | 改斷言為 core 句子 | plan-gate（orchestration） |
| test_policy.py:335 | `acceptance that proves the slice outcome` | 改斷言為 core 句子 | 措辭改寫：discovery-gate；plan-gate；approval-gate；execution-gate；verification-gate（O91） |
| test_policy.py:336 | `slice-local budget` | 改斷言為 core 句子 | 措辭改寫：discovery-gate；plan-gate；approval-gate；execution-gate；verification-gate（O91） |
| test_policy.py:337 | `stop conditions` | 改斷言為 core 句子 | followup-by-mode（orchestration） |
| test_policy.py:338 | `Blocker:` | 改斷言為 core 句子 | 措辭改寫：review-verdicts（O92） |
| test_policy.py:339 | `Evidence:` | 改斷言為 core 句子 | 措辭改寫：review-verdicts（O92） |
| test_policy.py:340 | `Minimum revision:` | 改斷言為 core 句子 | 措辭改寫：review-verdicts（O92） |
| test_policy.py:341 | `Acceptance check:` | 改斷言為 core 句子 | 措辭改寫：review-verdicts（O92） |
| test_policy.py:342 | `` use a fresh `plan-critic` `` | 改斷言為 core 句子 | 措辭改寫：readiness-loop（O94） |
| test_policy.py:343 | `` two automatic `REVISE` verdicts for the same unit `` | 改斷言為 core 句子 | 措辭改寫：readiness-loop（O94） |
| test_policy.py:344 | `` disposition every blocker as `FIX`, `DEFER`, or `REJECT` `` | 改斷言為 core 句子 | 措辭改寫：readiness-loop（O94） |
| test_policy.py:345 | `Ask the user only for unresolved P0/P1` | 改斷言為 core 句子 | 措辭改寫：readiness-loop（O94） |
| test_policy.py:346 | `not merely to authorize another review round` | 改斷言為 core 句子 | 措辭改寫：readiness-loop（O94） |
| test_policy.py:347 | `substantially unchanged Plan` | 改斷言為 core 句子 | readiness-loop（orchestration） |
| test_policy.py:348 | `findings and dispositions into the Plan` | 改斷言為 core 句子 | 措辭改寫：security-sensitive-routing；security-reviewer-first；security-executor-after-approval；security-no-preapproval-write（皆 required）（O115） |
| test_policy.py:351 | `Plan epoch` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_policy.py:352 | `format-recovery` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_policy.py:372 | `Role verdicts are evidence, not implementation or scope authority` | 改斷言為 core 句子 | 措辭改寫：verdict-authority（O118） |
| test_policy.py:375 | `` label it `FIX`, `DEFER`, or `REJECT` `` | 改斷言為 core 句子 | 措辭改寫：verdict-authority（O118） |
| test_policy.py:377 | `documented deferral or evidence-backed rejection is an addressed finding` | 改斷言為 core 句子 | 措辭改寫：verdict-authority（O118） |
| test_policy.py:380 | `P0 freezes the affected slice` | 改斷言為 core 句子 | 措辭改寫：verdict-authority（O118） |
| test_policy.py:381 | `Fix P1 within approved scope or pause and ask` | 改斷言為 core 句子 | 措辭改寫：verdict-authority（O118） |
| test_policy.py:382 | `sharing a repository or path with the change does not make it claim-relevant` | 改斷言為 core 句子 | 措辭改寫：verdict-authority（O118） |
| test_policy.py:384 | `A documented regrade may use the verifier's cited evidence` | 待第 2 節決定 | N13（O119） |
| test_policy.py:388 | `stated missing evidence, contract, prerequisite, or environment` | 改斷言為 core 句子 | recheck-and-invalidate（orchestration） |
| test_policy.py:391 | `explicit acceptance and approved scope` | 改斷言為 core 句子 | 措辭改寫：verdict-authority（O118） |
| test_policy.py:397 | `` use Codex `request_user_input` only when that tool is exposed in the current mode `` | 改斷言為 core 句子 | 措辭改寫（regex，多句串接）：ask-mode／recovery-budget／identity-fingerprint |
| test_policy.py:401 | `` If neither surface is available, end the turn with `PAUSED_NEEDS_USER`, one concise question, choices, and a recommendation `` | 改斷言為 core 句子 | 措辭改寫（regex，多句串接）：ask-mode／recovery-budget／identity-fingerprint |
| test_policy.py:406 | `` Headless or noninteractive execution emits `PAUSED_NEEDS_USER` and exits `` | 改斷言為 core 句子 | 措辭改寫（regex，多句串接）：ask-mode／recovery-budget／identity-fingerprint |
| test_policy.py:410 | `five-pass budget below is an emergency ceiling for high-risk recovery, not a quota.*Default recovery is one targeted recheck.*High-risk, claim-critical P1/P2 re…` | 改斷言為 core 句子 | 措辭改寫（regex，多句串接）：ask-mode／recovery-budget／identity-fingerprint |
| test_policy.py:419 | `external evidence or prerequisites.*immediately preceding verifier's verdict or output alone is not new evidence.*tracked and staged diff.*untracked input paths…` | 改斷言為 core 句子 | 措辭改寫（regex，多句串接）：ask-mode／recovery-budget／identity-fingerprint |
| test_policy.py:427 | `headless run without explicit unattended mode` | 改斷言為 core 句子 | 措辭改寫：auto-ask-selection；ask-mode（O124） |
| test_policy.py:430 | `not a new adjacent-hardening audit` | 改斷言為 core 句子 | 措辭改寫：ask-questions-main；verdict-authority；recovery-budget；identity-fingerprint（O131） |
| test_policy.py:431 | `next pass would only search adjacent risk` | 改斷言為 core 句子 | 措辭改寫：ask-questions-main；verdict-authority；recovery-budget；identity-fingerprint（O131） |
| test_policy.py:432 | `batch-disposition every current-head finding` | 改斷言為 core 句子 | 措辭改寫：recheck-and-invalidate；verdict-authority（O120） |
| test_policy.py:435 | `` After five unsuccessful or still-blocking passes, mark the slice `PAUSED_VERIFICATION`, block its dependents, and continue unrelated approved safe slices `` | 改斷言為 core 句子 | 措辭改寫（regex，多句串接）：ask-mode／recovery-budget／identity-fingerprint |
| test_policy.py:445 | `mandatory tool-use gate` | 改斷言為 core 句子 | 措辭改寫：risk-review-mandatory（required）；security-reviewer-first；review-circuit-breaker（O79） |
| test_policy.py:446 | `` must call `plan-critic` before sending any readiness recommendation `` | 改斷言為 core 句子 | 措辭改寫：risk-review-mandatory（required）；security-reviewer-first；review-circuit-breaker（O79） |
| test_policy.py:447 | `` Do not return `READY` or `REVISE` from the main session first `` | 改斷言為 core 句子 | 措辭改寫：risk-review-mandatory（required）；security-reviewer-first；review-circuit-breaker（O79） |
| test_policy.py:448 | `typed delegation is unavailable` | 改斷言為 core 句子 | 措辭改寫：risk-review-mandatory（required）；security-reviewer-first；review-circuit-breaker（O79） |
| test_policy.py:449 | `Review-service circuit breaker` | 改斷言為 core 句子 | breaker-heading（extensions） |
| test_policy.py:450 | `one bounded retry for the same stable unit and typed role` | 改斷言為 core 句子 | 措辭改寫：review-circuit-breaker（O80） |
| test_policy.py:451 | `Do not loop` | 改斷言為 core 句子 | 措辭改寫：review-circuit-breaker（O80） |
| test_policy.py:452 | `` `WAITING_FOR_REVIEW` for plan or security readiness `` | 改斷言為 core 句子 | 措辭改寫：review-circuit-breaker（O80） |
| test_policy.py:453 | `` emit `PAUSED_NEEDS_USER` solely because the service is unavailable `` | 待第 2 節決定 | N9（O81） |
| test_templates.py:89 | `` native typed `spawn_agent` `` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:90 | `` non-empty `message` `` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:91 | `` `agent_type` `` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:92 | `` `[a-z0-9_]+` `` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:93 | `` `"1"` through `"3"` `` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:94 | `never retry with an untyped child` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:95 | `post-hoc` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:96 | `agents.spawn_agent` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_templates.py:97 | `fork_turns = "all"` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_templates.py:102 | `Decision cues` | 改斷言為 core 句子 | 措辭改寫：bootstrap-delegate-default；delegate-cost-benefit（O17） |
| test_templates.py:103 | `classify each bounded workstream` | 改斷言為 core 句子 | 措辭改寫：bootstrap-delegate-default；delegate-cost-benefit（O17） |
| test_templates.py:104 | `delegate it to the least expensive` | 改斷言為 core 句子 | 措辭改寫：bootstrap-delegate-default；delegate-cost-benefit（O17） |
| test_templates.py:105 | `two or more reconnaissance surfaces are independent` | 改斷言為 core 句子 | 措辭改寫：bootstrap-delegate-default；local-search-direct；discovery-scope-exclusive（O18） |
| test_templates.py:106 | `` bounded implementation requiring judgment to `sol-executor` `` | 改斷言為 addendum 句子 | AO2 |
| test_templates.py:107 | `` approved security-sensitive implementation to `security-executor` `` | 改斷言為 core 句子 | 措辭改寫：execution-gate；security-executor-after-approval（O22） |
| test_templates.py:108 | `After a risk-triggered implementation` | 改斷言為 core 句子 | 措辭改寫：verification-gate；outcome-verification（O23） |
| test_templates.py:109 | `` dispatch exactly one `applier` `` | 改斷言為 core 句子 | 措辭改寫：mech-default；mech-collect（O106） |
| test_templates.py:110 | `choose delegation by net benefit` | 隨 A3 移除 | O108：A3 規則 1 |
| test_templates.py:111 | `stable, complete one-shot brief, not a numeric trigger` | 改斷言為 core 句子 | 措辭改寫：brake-per-call（O110） |
| test_templates.py:112 | `smallest coherent integration boundary` | 改斷言為 core 句子 | outcome-verification（orchestration） |
| test_templates.py:113 | `` `spawn_agent` calls back-to-back `` | 改斷言為 core 句子 | 措辭改寫：parallel-launch；parallel-writers；collect-results（O145） |
| test_templates.py:120 | `Adaptive intent routing` | 待第 2 節決定 | N3（O27） |
| test_templates.py:121 | `` `execute` `` | 改斷言為 core 句子 | bootstrap-routing、continuation-default、interaction-shape、first-move-steps（bootstrap／orchestration／extensions／skill） |
| test_templates.py:122 | `` `explore_then_plan` `` | 改斷言為 core 句子 | bootstrap-routing、interaction-shape、explore-then-plan-boundary、first-move-steps（bootstrap／orchestration／skill） |
| test_templates.py:123 | `` `co_discover` `` | 改斷言為 core 句子 | bootstrap-routing、interaction-shape、first-move-steps（bootstrap／orchestration／skill） |
| test_templates.py:124 | `` `change_impact`: `trivial`, `low`, `material`, `high`, or `critical` `` | 待第 2 節決定 | N6（O51） |
| test_templates.py:125 | `` `discovery_budget` `` | 待第 2 節決定 | N6（O51） |
| test_templates.py:126 | `` `budget_exhausted` `` | 待第 2 節決定 | N6（O51） |
| test_templates.py:127 | `` `evidence_sufficient` `` | 待第 2 節決定 | N6（O51） |
| test_templates.py:128 | `` `none` `` | 改斷言為 core 句子 | discovery-budget-table（extensions） |
| test_templates.py:129 | `` `minimum` `` | 改斷言為 core 句子 | discovery-budget-table（extensions） |
| test_templates.py:130 | `` `bounded` `` | 改斷言為 core 句子 | discovery-budget-table（extensions） |
| test_templates.py:131 | `` `deep` `` | 改斷言為 core 句子 | discovery-budget-table（extensions） |
| test_templates.py:132 | `AskUserQuestion` | 改斷言為 addendum 句子 | AE6 |
| test_templates.py:133 | `` `direction_checkpoint` `` | 改斷言為 core 句子 | direction-checkpoint（extensions） |
| test_templates.py:134 | `` `CONTINUE` `` | 改斷言為 core 句子 | direction-checkpoint（extensions） |
| test_templates.py:135 | `` `PIVOT` `` | 改斷言為 core 句子 | direction-checkpoint、cost-unbounded-continuation（extensions） |
| test_templates.py:136 | `` `ROLLBACK` `` | 改斷言為 core 句子 | direction-checkpoint（extensions） |
| test_templates.py:137 | `Outcome-level continuation` | 改斷言為 core 句子 | continuation-heading（extensions） |
| test_templates.py:138 | `` `execution_scope` `` | 改斷言為 core 句子 | route-fields、first-move-steps（extensions／skill） |
| test_templates.py:139 | `` `continuation_mode` `` | 改斷言為 core 句子 | route-fields（extensions） |
| test_templates.py:140 | `` `stop_condition` `` | 改斷言為 core 句子 | route-fields（extensions） |
| test_templates.py:141 | `phase boundary is progress reporting` | 改斷言為 core 句子 | continuation-default（extensions） |
| test_templates.py:142 | `presence gates for likely long unattended work` | 待第 2 節決定 | N5（O39） |
| test_templates.py:150 | `Independent review is risk-triggered, not a synonym for non-trivial` | 改斷言為 core 句子 | 措辭改寫：risk-triggers（required）；outcome-verification（O78） |
| test_templates.py:151 | `a data, schema, serialization, migration, or release boundary` | 改斷言為 core 句子 | 措辭改寫：risk-triggers（required）；outcome-verification（O78） |
| test_templates.py:152 | `` After two automatic `REVISE` verdicts for the same unit `` | 改斷言為 core 句子 | 措辭改寫：readiness-loop（O94） |
| test_templates.py:153 | `not merely to authorize another review round` | 改斷言為 core 句子 | 措辭改寫：readiness-loop（O94） |
| test_templates.py:154 | `Sol escalation is narrower than the risk trigger` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |
| test_templates.py:159 | `The parent session remains responsible and accountable throughout` | 改斷言為 core 句子 | 措辭改寫：main-session-owns；bootstrap-ownership（O24） |
| test_templates.py:160 | `integrates writes` | 改斷言為 core 句子 | main-session-owns；bootstrap-ownership（O24） |
| test_templates.py:161 | `makes final judgment` | 改斷言為 core 句子 | main-session-owns；bootstrap-ownership（O24） |
| test_templates.py:162 | `small, local, already-stable edit` | 隨 A3 移除 | O25：A3 規則 1 |
| test_templates.py:163 | `tightly coupled unknown bug` | 改斷言為 core 句子 | single-bug-direct（O26） |
| test_templates.py:164 | `Typed dispatch is an all-or-nothing child-creation boundary` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:165 | `No untyped fallback is permitted` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:166 | `must not silently substitute an untyped child` | 改斷言為 addendum 句子 | AO3 |
| test_templates.py:167 | `retry as an untyped child` | 不受影響 | assertNotIn：core 輸出與 addendum 都不含此字串 |

### 6.3 非措辭、但會被切換打破的斷言

| 位置 | 斷言 | 會發生什麼 |
|---|---|---|
| test_render_codex.py:31 | len(golden) == 14 | 新增 extensions 檔（與可能的 skill 檔）後數量改變 |
| test_render_codex.py:32-35 | render 與 tests/golden/codex 逐位元組相同 | bootstrap、orchestration golden 要重生；新檔要新增 golden |
| test_render_codex.py:37-40 | templates/ 與 golden 相同 | 同上 |
| test_render_codex.py:42-43 | plugin mirror 等於 render 輸出（MIRRORS["codex"]） | MIRRORS 目前只有 orchestration；extensions 若要進 plugin 需新增項目 |
| test_core_policy.py:31-40 | EXPECTED_POLICY_TEXT／OMITS／REPLACES／ADDENDA 的 codex 項 | codex 從 legacy／空改為 core、四個 omit id、addenda 清單 |
| test_core_policy.py:409-414 | test_core_is_rejected_for_hosts_that_are_not_ready 迴圈含 codex | render.py 開放 codex 後要從迴圈移除 |
| test_core_policy.py:599-606 | codex 沒有 [policy.documents] 時 --policy-preview 回傳 2 | 有 documents 後此測試不成立 |
| test_prompt_document_lock.py:563-575 | LOCK 的 migration marker 只能是四個已記錄的 | 新增 Codex migration（新 migration_id）時要改期望值 |
| test_delegation_default.py:397-398 | bootstrap 條款順序：dispatch-brake 後面接 collect | 第 5 節的三條款拆分若順序為 effort、brake、label，需改；順序 effort、label、brake 則不必 |
| test_delegation_default.py:360-389 | Claude bootstrap 的「- Explicit instruction:」恰一行、含 pass `effort`、Omit `model`、label 字串 | 拆分後仍成立（Claude 輸出少 4 位元組，見第 5 節） |

### 6.4 確認不受影響的測試檔

`tests/test_autoroute_hook.py`、`test_adaptive_routing.py`、
`test_decision_checkpoint.py`、`test_execution_contract.py`、
`test_intent_review_matrix.py`、`test_intent_runtime_matrix.py`、
`test_review_intent_contract.py`、`test_hook_registration.py`、
`test_verify_dispatch.py`（只把 `templates/agents-md.orchestration.md` 當不透明檔案複製，
`:188`）、`test_check_rename.py`：已逐檔查過它們不讀 policy 或 skill 文字（`grep` 與讀取被測模組：
`install/decision_checkpoint.py`、`execution_contract.py`、
`intent_review_matrix.py`、`review_intent_contract.py`、`evaluate_dispatch.py`、
`hooks/shoal_autoroute_gate.py` 都沒有讀 `templates/agents-md.*`）。
`tests/test_delegation_default.py:351-440` 針對 Claude 的 core 輸出，不受影響，除了第 5 節的拆分
。`install/benchmark_routing.py:1536` 把 orchestration 檔當整份 `AGENTS.md` 放進
benchmark home（非測試），切換後內容改為 core 組出的 orchestration（不含 extensions），行為相同但文字不同。

## 7. 安裝與同步

- **把新 Codex policy 放上機器的指令**只有
  `python3 install/install.py --codex-home <CODEX_HOME>`（`--dry-run` 先看計畫）：它把
  `templates/agents-md.bootstrap.md` 換進使用者 `AGENTS.md`（或 `AGENTS.override.md`，
  `:501-508`）的 `shoal-codex:begin/end` 區塊（`install.py:2059`、`2125`、`476-484`），
  並在 `plugin_install_needed` 為真時（外掛未裝、無 state、或 state 的 `source_sha256` 與目前
  `plugin/` 目錄摘要不同，`:2137-2142`）執行
  `codex plugin marketplace add <repo>/plugin` 與
  `codex plugin add shoal-codex@shoal-codex`（`:656-707`），把 SKILL 與 references
  裝進 `<CODEX_HOME>/plugins/cache/shoal-codex/shoal-codex/<version>/`。
- **`tools/sync_global.py` 對 codex 只做**：2.0.0 之前舊名安裝的遷移（偵測到才跑 install.py）、
  `tools/install_hooks.py --host codex`（guard hook）、jev router 外掛不見時的
  `codex plugin add`、`templates/agents/*.toml` 的 role 檔（
  `tools/sync_global.py:309-349`，docstring `:15-24`「平常不跑 install/install.py」）。
  **不會**更新 `AGENTS.md` 區塊、`shoal-codex` 外掛、`config.toml`、`hooks.json` 的非 guard
  部分。
- **偵測已安裝版本**：`codex plugin list --json` 的 `installed` 列，要 `name`、
  `marketplaceName` 為 `shoal-codex`，`version` 等於 `install.py:124` 寫死的
  `SHOAL_PLUGIN_VERSION`，`enabled` 為真，且 `marketplaceSource.source` 指向本 repo 的
  `plugin/`（`:573-593`、`:629-643`）；已裝版本比來源新時中止（`:596-626`）。`AGENTS.md` 區塊的版本只靠
  `<!-- shoal-codex vX.Y.Z -->` 那一行。版本寫死在四處（`hosts/codex/VERSION`、
  `plugin.json`、`install.py:124`、frame 的 marker），改 policy 後要一起升（
  `validate_prompt_lock` 也要求 VERSION 變更）。
- **本機觀察（2026-10-13，唯讀）**：`~/.codex/AGENTS.md:207-208` 的區塊是 `v3.3.1`，plugin
  cache 只有 `3.3.1/` 一個版本，也就是這台機器連 3.4.0 的現行文字都還沒裝；其 cache 的
  `orchestration-policy.md` 與 repo 的 `templates/agents-md.orchestration.md` 只差
  第 2 行的版本 marker（`cmp` 在 char 48）。

做 live Codex 測試前要跑並檢查的（C = CODEX_HOME，R = repo；指令集中在後面的區塊）：

1. 指令 1-2：render 與 lock 先通過（需 LOCK.json 先更新）。
2. 指令 3：dry-run 確認計畫含 AGENTS.md 區塊與外掛，核准後再正式執行。
3. 指令 4：區塊 marker 是新版本，且 begin、end 各一個。
4. 指令 5：區塊位元組與 templates/agents-md.bootstrap.md 相同。
5. 指令 6-8：必須不存在的句子，bootstrap 的 B7 句、cache 內 orchestration-policy.md 的 O3 句與 T5
   的 A3 半句各為 0；指令 9：必須存在 main 不改檔的句子。
6. 指令 10-11：plugin cache 的 orchestration-policy.md（以及新 extensions 與 skill 檔）與
   repo 檔位元組相同，且 plugin list 的 version 是新版本。同版本號重裝時 codex plugin add 是否覆蓋舊
   cache 無法從 repo 驗證（8.10），所以版本要升，cmp 不可省。
7. 開新 Codex session（已開的 session 不會重讀 AGENTS.md）；若 hooks.json 有變，要在互動式 Codex 用
   /hooks 重新核准一次（shared-rules Risks）。

```sh
V=<新版本>; REF="$C/plugins/cache/shoal-codex/shoal-codex/$V/skills/shoal-orchestration/references"
python3 tools/render.py --host codex --check                       # 1
python3 install/validate_prompt_lock.py                            # 2
python3 install/install.py --codex-home "$C" --dry-run             # 3
grep -n 'shoal-codex v' "$C/AGENTS.md"; grep -c 'shoal-codex:begin' "$C/AGENTS.md"   # 4
sed -n '/<!-- shoal-codex:begin -->/,/<!-- shoal-codex:end -->/p' "$C/AGENTS.md" \
  | cmp - "$R/templates/agents-md.bootstrap.md"                    # 5
grep -c 'tightly coupled local action' "$C/AGENTS.md"              # 6, 要是 0
grep -c 'Complete small, local, already-stable work directly' "$REF/orchestration-policy.md"   # 7, 0
grep -c 'takes the bounded work locally' "$REF/orchestration-policy.md"                        # 8, 0
grep -c 'The main session does not edit files itself' "$C/AGENTS.md"                           # 9, 1
cmp "$REF/orchestration-policy.md" "$R/templates/agents-md.orchestration.md"                   # 10
codex plugin list --json                                           # 11, version 欄位
```

## 8. 未決事項

### 8.1 指標句「最多四行」與 48 行上限互相排斥

`bootstrap` 在 5.2 的計算下，frame 7 行加 12 個 core 條款 39 行就是 46 行，指標句最多 2 行；owner 決定的
「最多四行」放不滿，且 `B1` 的 Persona 句（3 行）完全放不進去。不提高上限的前提下，要嘛縮短共用條款（SPEC A5），要嘛把指標句限制在
2 行。證據：本文 5.2 的實際渲染。

### 8.2 兩個 placeholder 在 Codex 沒有值

`background_option`、`worktree_option` 必須是非空字串（`tools/contracts.py:314-325`），但
Codex 的 `spawn_agent` 沒有背景或 worktree 參數（`hooks/shoal_guard.py:1581` 註解「there
is no run_in_background」；`tests/test_policy.py:320-321` 要求 policy 不含這兩個詞）。受影響的
條款：`bootstrap-delegate-default`（A3 規則 3 的 `watcher` 路徑）、
`watcher-long-commands`、`leaf-cannot-finish`、`parallel-launch`、
`parallel-writers`。A4 允許 omit `parallel-writers`，但
`bootstrap-delegate-default` 與 `watcher-long-commands` 是 owner 決定的 A3 規則 3 本身，
不能省略，因此需要一個 Codex 的值或改條款；repo 內沒有證據。另外 `read_tools` 的 Codex 值（5.1）與
`discovery-scope-exclusive` 要求的「讀取工具拒絕混合指令」在 Codex 是否有機制（
`hooks/shoal_guard.py` 的 Codex adapter 只認 `apply_patch`、`Bash`、`spawn_agent`）也
沒有證據。`tests/test_policy.py:321` 的 `assertNotIn("worktree")` 會被
`leaf-cannot-finish` 打破，即使省略 `parallel-writers`。

### 8.3 skill 與 extensions 的輸出位置未定

`render_codex` 只輸出 `agents/*.toml` 與 `src/` 內檔案（`tools/render.py:613-642`），不呼叫
`policy_files`；`[policy.documents]` 的路徑相對於 dist（`templates/`），但 plugin 的
`SKILL.md` 與 `references/` 在 `plugin/` 下，`MIRRORS`（`:1157-1162`）只有
orchestration 一項。要產生 `SKILL.md` 與新的 extensions 檔、把它們放進 plugin，需要新增 mirror 或輸出路
徑；`tests/test_render_codex.py:31` 的 golden 數量 14 也會變。這是實作面，不是 owner 決定能回答的。

### 8.4 A3 只列四條，但 core 與 legacy 的矛盾不止四條

以下是 core 更嚴或不同、A3 沒點名的項目，目前都按「核心勝出」處理：（a）`/goal` 在 legacy 不選 mode（
`orch:L597-598`），在 core 選 AUTO 並受 `auto-limits` 約束（
`core/policy/orchestration.toml:506-512`）；（b）`explore_then_plan` 第一回合在 core 必須
唯讀並結束回合（`explore-then-plan-boundary`），legacy 只說「inspect and form provisional
Plan」；（c）建議選項在 core 一律放第一並標 "(Recommended)"，legacy 說只在 material 時標示（O68）；（d）
readiness epoch 與 closing review 是 core 新增的限制；（e）`bootstrap-collect` 等新增義務。這些要
不要也寫進 CHANGELOG 的行為變更清單，需要 owner 確認。

### 8.5 core 內部：「take over」與 A3 規則 2

`one-shot-spec`（"after two failures, escalate tier or take over"）與
`cost-unbounded-continuation`（"Escalate only to a higher executor tier or
main-session takeover"）允許 main 接手，與 A3 規則 2、`direct-when-small`、
`mech-direct-blocker` 的「不接手、只回報」互相抵觸；Claude 已在用同一份文字。legacy 的 `orch:L674-675`
也有同樣的 "take over"。需要 owner 說明接手指的是不是改檔。

### 8.6 kind label 省略的理由不完整

owner 的理由是「`task_name` 值被 autoroute gate 保留」。實際上 gate 只對指定 role 的那一次呼叫要求固定的
`task_name`（`hooks/shoal_autoroute_gate.py:1424-1436`）；更根本的原因是 Codex 自己的
transport 規則要求 `task_name` 符合 `[a-z0-9_]+`（`orch:L651-653`），`fix:` 的冒號不合法。結論相同
（省略），但 omit 的 `reason` 字串寫成後者較正確。

### 8.7 heading 層級

core 條款的標題固定是 `##`（例如 `## Routing and lifecycle`），legacy Codex 檔用 `###`／`####`
，frame 是 `### Orchestration`／`### Shoal always-on bootstrap`。切換後 orchestration
檔的層級是 `###` 底下接 `##`。沒有 lint（`hosts/*/src`、`templates` 不在 `lint:md`），但
`tests/test_install.py:639` 依賴 bootstrap 的 `###` 標題。

### 8.8 legacy 瑕疵

`orch:L488` 以「The pause」結尾，下一行 L489 接另一句，是被切斷的半句（O99）。另外 legacy 的 named-role 豁
免名單只有八個 role（`orch:L6-9`），缺 `watcher`、`researcher`；legacy bootstrap 完全沒有豁免句。

### 8.9 手寫檔案的調校

`openai.yaml` 的 `default_prompt` 內含 Astra main-session 調校（`astra-thinking`、
`max_tool_calls=12`），`tests/test_astra_routing.py:197-211` 要求它含有這些詞。它不在「常駐文字」，
owner 的 2026-10-13 決定沒提；本文當作不受影響。`role-contract.md`、`verification-contract.md`
、`recovery-contract.md` 三份不在 lock，core skill 的 `reference-*` 條款只連 policy 與
extensions 兩份，`tests/test_plugin.py:26-32` 要求四份都存在，因此切換後它們若保留就是沒人連結的孤兒檔，若刪除要改測
試；未決。

### 8.10 未驗證的事實

（a）同版本號重裝時 `codex plugin add` 是否覆蓋 cache：查了 `install/install.py` 與
`tools/sync_global.py`，沒有證據，所以第 7 節要求升版與 `cmp`。（b）child agent 是否載入 `AGENTS.md`
（決定 `bootstrap-named-roles` 的價值）：repo 內沒有記錄。（c）`Bash` 是 Codex shell 工具的名稱只由
hook adapter 推得（`hooks/shoal_guard.py:1580`），沒有直接的 Codex 文件。（d）
`codex-auto-review` 在 repo 內只有
`docs/specs/intent-aware-review-routing-1-6-0/SPEC.md` 提到，沒有程式消費者，O47 的 `AE3`
區塊是否仍有用無法判斷。（e）第 6 節的分類由字串比對加人工覆核產生，`CORE_REWORD` 類別沒有逐條人工確認 core 句子的語意等價，只確認該
legacy 句落在 `core 同義` 列。

### 8.11 固定決定之間的緊張

（a）「常駐 tuning 移到按需，bootstrap 留最多四行指標」與 48 行上限：見 8.1。（b）「長指令交 `watcher`」與 Codex
沒有背景參數：見 8.2。（c）「caps 不提高、validator 規則不變」與大量超出變更預算：靠 migration marker 解決，不需改
validator，但需要更新 `LOCK.json`（`--allow-lock-update`，且
`tests/test_prompt_document_lock.py:563-575` 的期望值要改）。（d）`Codex 調校` 列 O8（
`orch:L38`、`L41`）與 S5（`SKILL.md:L27-31`）寫「Parent or `applier` Luna binding」「
cheap parent」，與 A3 規則 1 衝突；逐字搬入會把矛盾帶進 addendum。

## 9. LOCK.json 更新紀錄

- 三個 Codex policy surface（`bootstrap-policy`、`orchestration-template`、
  `packaged-orchestration-policy`）改用 `migration_id`
  `shared-rules-codex-core`，equivalence 指向本檔。
- `bootstrap-policy` fragment 換成 core 句子
  （`A clear request to fix or finish is one outcome`、
  `Material gates always stop.`、
  `The main session does not edit files itself`）。
- 兩個 orchestration surface 移除搬到 extensions 的四個 fragment，保留
  `presence gates ...`，補上 Claude 對應 surface 的三個逐字 fragment。
- `test_policy.py` 的 `For low-risk, local, reversible work, use one
  targeted acceptance check ...` 在 core 沒有等價句（第 1030 列原定改斷言為
  core 句子，但 core 的 `risk-triggers` 只列觸發條件，沒有「不加 verifier」
  的正向規則）。處置：保留原句逐字，作為 addendum
  `pending-shared-low-risk-targeted-check`（`after:risk-triggers`），
  待升為共用條款。
- 擁有者決定登錄兩個 Codex extensions surface：`extensions-template`
  （`templates/agents-md.extensions.md`）與 `packaged-workflow-extensions`
  （plugin 的 `workflow-extensions.md`），互為 mirror，版本檔
  `hosts/codex/VERSION`；上限 270 行／15600 bytes，per-change budget 同
  `claude-workflow-extensions`（30 行、4000 字元、0.2）。
- `hosts/codex/VERSION` 已提升到 3.5.0。
- 修正 8.11（d）留下的矛盾：plugin `SKILL.md` 移除「implement
  directly」與「cheap parent」，改為派給一個可寫入的 role；orchestration
  addendum 表中單指令列的 Astra 欄由「Never open a child」改為
  「Never Astra」。
