---
title: Grok 舊條款與 core 條款對照（shared-rules S7 前置）
status: draft
created: 2026-10-13
updated: 2026-10-13
---

<!-- markdownlint-disable MD025 -->

# Grok 舊條款與 core 條款對照（shared-rules S7 前置）

這份文件是 [shared-rules](../../shared-rules/SPEC.md) 的 S7（Grok 改由 core
產生條款）的輸入：先把 Grok 現行的 main-session 條款逐行列出，再說明每一行在
core 裡對應什麼、要移到哪裡、哪些要拿掉。它不決定任何一條規則的去留，也不提議
條款文字；需要決定的地方在第 2、5、9 節標明。

查證基準：shoal HEAD `5188257`（v3.4.0），加上寫作時工作樹裡尚未 commit、
由其他人進行中的修改（本文件不碰它們）：

- `core/policy/{bootstrap,extensions,orchestration}.toml`：新增
  `bootstrap-effort`、`bootstrap-kind-label`、`small-parallel-units`，改寫
  `bootstrap-dispatch-brake`、`one-shot-spec`、`cost-unbounded-continuation`
  （把 take over 改成 report to the user）。
- v3.4.1 的版本 bump：`hosts/grok/VERSION` 為 `3.4.1`、dist 的 marker 與
  `tests/test_render_grok.py:66` 的 `assertEqual(version, ...)`。

core 還在變動；下文的條款 id、計數、行號是這個狀態的結果，commit 前再變動就要
重算（`git diff --stat -- core/policy` 看變動，1.2 的計數與 3.3、4.2 的大小隨
之重算）。

「legacy 檔」指 `hosts/grok/src/rules/shoal-grok.md`（257 行、HEAD 版本
16,015 bytes）。HEAD 版本的四個副本逐位元組相同：

```sh
git show HEAD:hosts/grok/dist/rules/shoal-grok.md > "$TMPDIR/dist.md"
git show HEAD:hosts/grok/src/rules/shoal-grok.md | cmp - "$TMPDIR/dist.md"
git show HEAD:tests/golden/grok/rules/shoal-grok.md | cmp - "$TMPDIR/dist.md"
cmp ~/.grok/rules/shoal-grok.md "$TMPDIR/dist.md"
```

三個 `cmp` 都沒有輸出（相同）。本機 `~/.grok` 已安裝的 hooks（`hooks/shoal-grok.json`、
`hooks/shoal-grok/*.py`）也與 HEAD 的 dist 相同。

名詞：「core」指 `core/policy/*.toml` 的 124 個條款（bootstrap 14、
orchestration 61、skill 9、extensions 40；required 15 個）；`shared-rules`
D1 決定規則共用、host adapter 只放工具與參數名稱、model 綁定與調校參數。
Grok 專屬的本機文件（`~/.grok/docs/user-guide/*.md`）在 repo 之外，下文以檔名
引用，屬於本機證據，不是 repo 內容。

## 1. 逐節對照

下表涵蓋 legacy 檔所有非空白行（`L` 是 legacy 檔的行號；用腳本檢查過，
1 至 257 行沒有未被任何一列涵蓋的非空白行）。一行含多個規則時拆成多列。
處置欄第一個詞是五種處置之一，括號內是 core 條款 id 或接點。

處置統計（共 116 列）：`core 同義` 69、`Grok 調校，移到 addendum`
16、`行為變更，移除` 13、`core 沒有對應` 18、
`做不到，省略` 0（legacy 沒有任何一條是 Grok 做不到的；做不到的判斷在
第 3 節，針對 core 條款）。`core 沒有對應` 的 18 列中，G72
與 G91 只是標題，不是規則，所以第 2 節只有 16 項（N1-N16）。

`行為變更，移除` 的 13 列中，屬於 owner 已定的四個例子（main 不自己改檔、
role 不可用要回報而不是由 parent 接手、長指令交 `watcher`、決策性研究用兩個
`researcher`）的有：L78、L113-114、L126（direct）、L142（修補）、L165-167（接手）、
L178、L180-182（誰跑）。其餘六列（L41-42 的「連兩次 REVISE 就問使用者」、L90-92 的
內建 `explore`、L119-121 的「未知檔案先派 `scout`」、L128 的「其他委派可選」、
L215-216 的「宣告 AUTO／ASK」、L219 的「`/goal` 只保留目標」）不在那四個例子裡，
是依「legacy 與 core 矛盾時 core 優先」的一般原則分類，需要 plan 階段確認
（第 9 節 U11）。研究的兩個 `researcher` 在 legacy 沒有對應文字（legacy 完全沒有
`researcher`），所以不是「移除」而是 core 新增（見 1.2）。

| # | legacy 位置 | 內容 | 處置 |
| --- | --- | --- | --- |
| G01 | L1-3 | begin marker、版本 marker、`## Orchestration` 標題 | `Grok 調校，移到 addendum`（落在 policy-frames 外框，不接條款；同 Claude 的 `bootstrap.md`）。installer 靠 `<!-- shoal-grok:begin -->` 與 `<!-- shoal-grok:end -->` 計數、靠版本 marker 驗證 |
| G02 | L257 | end marker | `Grok 調校，移到 addendum`（同上，外框） |
| G03 | L5 | 標題 `### Non-negotiable native Plan gate` | `Grok 調校，移到 addendum`（Plan Mode 小節的標題；接在 `plan-gate` 之前） |
| G04 | L7-9（前半） | 大型、含糊、架構性、高風險或明說 plan-first 的任務，一律要用原生 Plan Mode | `Grok 調校，移到 addendum`（接在 `plan-gate` 之後；core 沒有 Plan Mode 概念） |
| G05 | L7-9（後半） | 同一句：這類任務也一律要一次 fresh `plan-critic` readiness pass，不限於 risk trigger | `core 沒有對應`（core 只對 risk-triggered unit 強制 `plan-critic`：`plan-gate`、`risk-review-mandatory`；`risk-triggers` 明寫檔案數等不算 trigger。見第 2 節 N1） |
| G06 | L9-11 | 不在 Plan Mode 時，第一個 tool call 必須是 `enter_plan_mode`，先於 repository discovery 與實作 | `Grok 調校，移到 addendum`（接在 `explore-then-plan-boundary` 之後） |
| G07 | L11-12 | 使用者已用 `/plan` 進入就沿用；「the verifier gate still applies」（原文沒有說是 plan-critic 還是 verifier，上游同字） | `Grok 調校，移到 addendum`（同上；用詞含糊，第 9 節 U12） |
| G08 | L12-13 | `enter_plan_mode` 被拒或不可用：不寫檔、不用實作工具，請使用者進入 Plan Mode | `Grok 調校，移到 addendum`（同上；與 core `mech-direct-blocker` 的「不可用就回報」方向一致） |
| G09 | L15-16 | Plan Mode 內 discovery 唯讀，唯一允許的寫入是 session 的 `plan.md` | `Grok 調校，移到 addendum`（接在 `explore-then-plan-boundary` 之後；core 該條款禁止所有 `{{write_tools}}`，沒有 `plan.md` 例外） |
| G10 | L16-18（前） | main 先合成完整 Plan，再派 fresh `plan-critic` | `core 同義`（`plan-gate`、`review-verdicts`） |
| G11 | L17（參數） | 派 `plan-critic` 時帶 `background: false` | `Grok 調校，移到 addendum`（接在 `risk-review-mandatory` 之後；參數名稱衝突見第 9 節 U1） |
| G12 | L16-19（brief） | brief 要含：目標 readiness unit 的 ID 與 kind、完整 Plan 文字、相關 evidence 路徑 | `core 沒有對應`（第 2 節 N2） |
| G13 | L19-20 | 目標寫成 `## Target readiness unit` 區塊，含 `- ID:` 與 `- Kind:`（`program envelope` 或 `execution slice`） | `core 沒有對應`（第 2 節 N3；Grok 的 plan-critic addendum `brief-unit-kinds` 依賴這兩個 kind 詞） |
| G14 | L20-21 | 子 agent 用安裝時的唯讀 capability，只審這一個 unit | `core 同義`（`review-verdicts`「Plan review stays read-only」；單一 unit 在 plan-critic 的 role 條款 `one-unit`） |
| G15 | L21-24 | `READY` 是單獨一個詞；`REVISE` 含一到多個 blocker，各有四個欄位；格式不合是 protocol failure | `core 同義`（`review-verdicts`；四欄格式在 role 側 `revise-shape` addendum） |
| G16 | L25-27 | 涉及 security 的 unit，每次 initial／re-review 的 brief 必須明說 `security-reviewer` 的 findings 與處置已帶進 Plan，不能只靠 Plan 文字 | `core 沒有對應`（第 2 節 N4） |
| G17 | L29-34 | 長或大型工作：envelope 放共同 outcome、non-goals、scope、架構、security、dependencies、integration、budget、stops；slice 要有穩定 ID、owner、prerequisite、acceptance、rollback；先審 envelope，再只審下一個可執行 slice，兩者 READY 才呈給核准；不預審下游 slice | `core 同義`（`plan-gate`、`envelope-then-slice`） |
| G18 | L34-36 | 共同 blocker 與未滿足的 prerequisite 仍然擋住相依工作 | `core 同義`（`envelope-then-slice`） |
| G19 | L36-38 | 初次核准只完整描述下一個可執行 slice，後面的 slice 只留 ID、outcome、prerequisite | `core 沒有對應`（第 2 節 N5） |
| G20 | L40-41 | 收到 `REVISE`：main 實質修改該 unit，送新的 fresh `plan-critic` | `core 同義`（`readiness-loop`） |
| G21 | L41-42 | 同一 unit 連兩次自動 `REVISE` 後暫停，並詢問使用者怎麼處理 | `行為變更，移除`（core `readiness-loop`：main 逐項處置 FIX／DEFER／REJECT、再開一次 closing review，「Ask user only for unresolved P0/P1, product/authority choice, or unmet original scope—not merely permission for another review round」） |
| G22 | L42-44 | 上限不等於 `READY`；切碎不能重置；使用者指示的繼續仍允許 | `core 同義`（`readiness-loop`、`envelope-then-slice`） |
| G23 | L44-47（行為） | 每個必要 readiness unit 都 `READY` 才能呈現核准；這個關卡也適用使用者用 `/plan` 開的 session | `core 同義`（`explore-then-plan-boundary`、`risk-review-mandatory`） |
| G24 | L45-47（工具） | 呈現核准的工具是 `exit_plan_mode` | `Grok 調校，移到 addendum`（接在 `approval-gate` 之後） |
| G25 | L49-52（前半） | 使用者在之後的互動明確核准前，不可寫 source、不可用實作工具 | `core 同義`（`approval-gate`、`risk-review-mandatory`「implementation begins only after explicit approval in a later turn」） |
| G26 | L52（核准） | 廣泛的初始請求不算核准 | `core 同義`（`approval-gate`） |
| G27 | L52-54（跳過） | 「略過規劃」「略過核准」「立刻開始」「做到檔案改完為止」都不能豁免這個關卡 | `core 沒有對應`（第 2 節 N6） |
| G28 | L52-54（權限） | 自動權限（always-approve、`bypassPermissions`）不是使用者對 Plan 的核准 | `core 沒有對應`（第 2 節 N7；用到 Grok 的 permission mode 名稱，但原則本身不依賴 Grok） |
| G29 | L54 | 無人值守的 run 呈現 verified Plan 後必須停下 | `core 同義`（`risk-review-mandatory`「After readiness, present Plan and end turn」） |
| G30 | L56-58 | 每個核准後的 security-sensitive 執行 slice 都有強制的執行邊界 | `core 同義`（`security-sensitive-routing`、`security-executor-after-approval`，皆 required） |
| G31 | L57-59 | envelope 上的 `security-reviewer` findings 仍是各 slice 的限制；envelope 本身不是可執行 contract | `core 沒有對應`（第 2 節 N8） |
| G32 | L59-62 | 核准後第一次改 source 前，main 必須成功派出 `security-executor` 並帶穩定 contract；main 與其他 role 不得直接實作該 slice | `core 同義`（`security-executor-after-approval`、`security-sensitive-routing`；main 不改檔另見 `bootstrap-delegate-default`） |
| G33 | L63-66 | direct-work 許可、dispatch brake、coordination-cost 啟發、matching-role-optional、single-unknown-bug 例外、失敗接手規則，都不能豁免這條邊界 | `core 沒有對應`（第 2 節 N9；core 的 `#direct` 沒有 security 例外） |
| G34 | L66-67 | 派工不可用或失敗：不改 source、不用實作工具，直接停 | `core 同義`（`delegate-cost-benefit`、`mech-direct-blocker`：unavailable worker 回報使用者） |
| G35 | L67-69 | 實作失敗：停下或改派 `security-executor`；main 與其他 role 都不得接手該 slice | `core 沒有對應`（第 2 節 N10；與 core `one-shot-spec` 的「take over」有出入） |
| G36 | L70-73 | Grok Build 的 main-session 條款；七個 role 列舉，role 身分時略過本節、自己完成、不再委派 | `core 同義`（`intro-named-roles`、`bootstrap-named-roles`，皆 required）。列舉少 `watcher`、`researcher`（`named_roles` 會是九個） |
| G37 | L75-77 | 用 named role 做有邊界的 discovery、執行、fresh-context 驗證；framing、Plan、架構、釐清、整合、最終判斷留在 main | `core 同義`（`main-session-owns`、`bootstrap-ownership`） |
| G38 | L78 | 「Complete small, local, already-stable work directly.」 | `行為變更，移除`（main 不自己改檔；core `bootstrap-delegate-default`、`direct-when-small`，只有使用者的 `#direct` 例外） |
| G39 | L80-88 | role 對照表（七列：scout、plan-critic、security-reviewer、applier、executor、verifier、security-executor） | `core 同義`（各 role 的路由在 `discovery-gate`、`plan-gate`、`execution-gate`、`verification-gate`、`security-*`；表格形式 core 沒有，也沒有 `watcher`、`researcher` 列） |
| G40 | L90 | 沒有安裝 `Explore` role；discovery 用 `scout` | `core 同義`（`bootstrap-delegate-default`、`local-search-direct`） |
| G41 | L90-92（built-in） | Grok 內建的 `explore` 不是 shoal named role，沒有自訂路由 | `Grok 調校，移到 addendum`（接在 `bootstrap-named-roles` 之後；內建型別 `explore`／`plan`／`general-purpose` 見 `16-subagents.md`） |
| G42 | L90-92（可用） | 內建 `explore` 在有用時仍可用於廣泛搜尋 | `行為變更，移除`（core `bootstrap-delegate-default`、`local-search-direct`：獨立 surface 的偵察走 `scout`） |
| G43 | L94-95 | 大型、含糊、架構性、高風險或 plan-first 的工作使用五階段 lifecycle | `core 同義`（`discovery-gate`、`plan-gate`、`approval-gate`、`execution-gate`、`verification-gate`） |
| G44 | L99 | Discovery 階段：先進 Plan Mode，再用唯讀 discovery 穩定問題、範圍、證據格式、停止條件；可派唯讀 `scout` 掃不重疊的 surface | `core 同義`（`discovery-gate`；進 Plan Mode 的部分已在 L9-11 列） |
| G45 | L100 | Plan 階段：main 寫一份 `plan.md`（outcome、non-goals、scope、envelope、slices）；強制 fresh 唯讀 `plan-critic` 先審 envelope 再審下一個 slice；`REVISE` 把所有權交回 main | `core 同義`（`plan-gate`、`envelope-then-slice`、`review-verdicts`；`plan.md` 檔名見 L15-16） |
| G46 | L101 | Approval 階段：`READY` 後才用 `exit_plan_mode` 呈現並等核准；只允許唯讀釐清，不送實作 brief、不改 source | `core 同義`（`approval-gate`；工具名見 L45-47） |
| G47 | L101（子 agent） | 「Parent Plan Mode does **not** replace read-only capability on child agents.」 | `Grok 調校，移到 addendum`（接在 `approval-gate` 之後；依據 `19-plan-mode.md`「Subagents are not covered by the parent session's plan-mode edit gate」，hook 見 `plan_mode_guard.py`） |
| G48 | L102 | Execution 階段：核准的 contract 有穩定 scope、獨占 owner、constraints、done criteria、整合、驗證；依 contract 與信任邊界選 `applier`／`executor`／`security-executor` | `core 同義`（`execution-gate`） |
| G49 | L103 | Verification 階段：整合後的結果有明確 claim 與可測的 acceptance；fresh `verifier` 只回 `CONFIRMED`／`REFUTED`／`INCONCLUSIVE` | `core 同義`（`verification-gate`、`review-verdicts`） |
| G50 | L105 | 標題 `### Dispatch` | `core 同義`（`dispatch-heading`，標題文字不同） |
| G51 | L107-111 | 每次 `spawn_subagent` 前辨識 phase 並套 dispatch brake；證據會變動、寫入 ownership 重疊、沒有整合 owner、協調成本高於效益時不 fan out；discovery agent 只回報事實，由 main 調和並寫 Plan | `core 同義`（`dispatch-brake`、`collect-discovery`） |
| G52 | L113-114 | 最小可行的執行形狀：小或緊耦合的任務 main 直接做 | `行為變更，移除`（就「改檔」而言；core `direct-when-small`、`bootstrap-delegate-default`。讀取、診斷仍在 main：`single-bug-direct`、`local-search-direct`） |
| G53 | L114-115 | 有界的旁支任務用一個 worker；只有獨立、低重疊的工作流才平行 | `core 同義`（`brake-per-call`、`parallel-launch`、`large-investigation`） |
| G54 | L115-118 | main 使用 repository discovery 或實作工具前，即使使用者沒提 agent，也套用第一條符合的規則 | `core 同義`（`bootstrap-delegate-default`「Every edit goes to a write-capable role」） |
| G55 | L119-121 | 未知檔案或 symbol 的 repository search（含路徑未知的精確字串查找、廣泛或跨檔 discovery）前，MUST 先派 `scout` | `行為變更，移除`（core `local-search-direct`：只有兩個以上獨立 surface 才平行派 `scout`；「A single coupled trail that main is already following stays with main」） |
| G56 | L122 | 規格完整的多檔機械性工作前，MUST 先派 `applier` | `core 同義`（`bootstrap-delegate-default`、`mech-default`；core 範圍更廣，所有 edit 都交給寫入 role） |
| G57 | L123-124 | 需要局部判斷的非 security 有界實作前，MUST 先派 `executor` | `core 同義`（`bootstrap-delegate-default`、`delegate-cost-benefit`） |
| G58 | L126（direct） | 「The direct-work ... exceptions here still apply」中的 direct-work 例外 | `行為變更，移除`（同 L78） |
| G59 | L126（bug） | single-unknown-bug 例外仍適用 | `core 同義`（`single-bug-direct`） |
| G60 | L127-128（brake） | dispatch brake 可以把符合條件的單位排成序列，但不可默默轉成 main-session 工作 | `core 同義`（`delegate-cost-benefit`、`mech-direct-blocker`、`brake-per-call`） |
| G61 | L128 | 「Other delegation remains optional.」 | `行為變更，移除`（core 預設委派：所有 edit 與長指令交 `watcher`、決策性研究走兩個 `researcher`：`bootstrap-delegate-default`） |
| G62 | L130-131 | 強制的 `plan-critic` readiness gate 不是可選委派，不受 dispatch brake 或協調成本豁免 | `core 同義`（`risk-review-mandatory`；觸發範圍見 L7-9 後半） |
| G63 | L133-136 | delegation-planning layer 可以調整問題、拓撲、worker 數、ownership、順序、預算、停止條件；本 policy 對 named role 語意、leaf 邊界、核准 gate、verifier contract 仍具權威 | `core 同義`（`baton-dispatch`） |
| G64 | L136-138 | role TOML 與 agent 定義掌管 capability mode 與 reasoning-effort；選配的 `[subagents.models]` 掌管 model routing | `Grok 調校，移到 addendum`（接在 `model-routing` 之後） |
| G65 | L140-143（診斷） | 單一未知 bug 的 root-cause discovery、trace 除錯、緊耦合的 state 傳播留在 main；只有不擁有也不擋住診斷的有界旁支問題才用 `scout` | `core 同義`（`single-bug-direct`） |
| G66 | L142（修補） | 同一條推理鏈上的「first minimal fix」也留在 main | `行為變更，移除`（core `single-bug-direct`：「Once root cause and remedy are known, the fix is Execution work and is delegated」） |
| G67 | L145-146 | security-sensitive 工作走分開的 capability 邊界 | `core 同義`（`security-sensitive-routing`，required） |
| G68 | L146-149 | 派 `security-reviewer` 前先替受影響的 envelope 與當前 slice 指定穩定 ID；brief 列出每個確切 ID，並要求輸出逐一點名 | `core 沒有對應`（第 2 節 N11；輸出側的 `affected unit ID` 在 security-reviewer role 條款 `report-fields`） |
| G69 | L149-151 | 受影響 unit 第一次 readiness review 前先完成 `security-reviewer`，把 findings 與處置帶進 Plan，兩個 review 不並行 | `core 同義`（`security-reviewer-first`、`security-no-preapproval-write`，皆 required） |
| G70 | L151-152 | 受影響的 ID 改變或新增時，readiness 前重做 security review | `core 沒有對應`（第 2 節 N12） |
| G71 | L152-153 | 核准後把穩定 contract 交給 `security-executor` | `core 同義`（`security-executor-after-approval`，required） |
| G72 | L155 | 標題 `### Routing ownership` | `core 沒有對應`（只是標題，不是規則；第 2 節不列） |
| G73 | L157-160（model） | model 與 capability 路由由 named agent 與 role 定義掌管；派 named role 時不帶 invocation-level 的 `model`；只有沒有對應 role 的 ad-hoc agent 才覆寫 | `core 同義`（`model-routing`） |
| G74 | L158-159（capability） | 派 named role 時也不帶 `capability_mode` 覆寫 | `Grok 調校，移到 addendum`（接在 `model-routing` 之後；與 `16-subagents.md`「Capability mode is not a spawn argument」不一致，第 9 節 U4） |
| G75 | L162-164（核心） | 一次講完的 brief：goal、constraints、done criteria、relevant paths、rationale、budget | `core 同義`（`one-shot-spec`，工作樹版本含「file ownership, time budget」；`bootstrap-dispatch-brake`「State scope, stop, and a time budget」） |
| G76 | L162-164（多出） | brief 另含 output format、verification expectation | `core 沒有對應`（第 2 節 N13） |
| G77 | L164（便宜） | 先用最便宜的合格 role；失敗兩次後升一階 | `core 同義`（`one-shot-spec`） |
| G78 | L164-165（改邊界） | 失敗兩次後可「change the task boundary」 | `core 沒有對應`（第 2 節 N14；core 工作樹版本此處是「escalate tier or report to the user」） |
| G79 | L165-167（接手） | main 只能接手非 security-sensitive 的工作 | `行為變更，移除`（main 不改檔、role 不可用要回報使用者：`delegate-cost-benefit`、`mech-direct-blocker`、`bootstrap-delegate-default`、`one-shot-spec`「escalate tier or report to the user」；core 的 take over 字樣已在工作樹移除，見第 9 節 U10） |
| G80 | L166-167 | security-sensitive 的 slice 必須停下或改派 `security-executor` | `core 同義`（`security-sensitive-routing`、`security-executor-after-approval`） |
| G81 | L167-168 | scout findings 是輸入；承載決策的單一事實要 sanity-check | `core 同義`（`scout-inputs`） |
| G82 | L170 | 標題 `### Parallelism and long work` | `core 同義`（`parallel-heading`） |
| G83 | L172-173 | 依資料相依排程；有用時用 `background: true` 啟動獨立 agent | `core 同義`（`parallel-launch`；參數名稱衝突第 9 節 U1） |
| G84 | L173-174 | 寫入的 agent 要獨占檔案，或用 `isolation: "worktree"` | `core 同義`（`parallel-writers`；core 另加「requires Git」） |
| G85 | L174-176（行為） | agent 跑的時候 main 繼續做獨立工作；相依工作或最終答覆前收齊每個結果；沒收的 worktree 等於遺失的工作 | `core 同義`（`parallel-launch`、`parallel-writers`、`collect-results`） |
| G86 | L175（工具） | 收結果用 `get_command_or_subagent_output` | `Grok 調校，移到 addendum`（接在 `parallel-launch` 之後） |
| G87 | L178 | 長時間執行的 process 歸 main-session | `行為變更，移除`（core `watcher-long-commands`：交 `watcher`，main 不自己開背景 shell；`bootstrap-delegate-default`） |
| G88 | L178-182（leaf） | leaf agent 不可 detach；它們回報確切指令、絕對工作目錄或 worktree、環境、輸入路徑、完成判準 | `core 同義`（`leaf-cannot-finish`） |
| G89 | L180-182（誰跑） | orchestrator 用 `run_terminal_command`（需要時 `background: true`）自己跑，再把結果 re-task 給 leaf | `行為變更，移除`（core `leaf-cannot-finish`、`watcher-long-commands`：main 派 `watcher` 跑，再帶著捕捉到的輸出 resume 原 role） |
| G90 | L184-187 | `plan-critic` 與 `verifier` 不可互換；前者回 `READY`／`REVISE`，後者回 `CONFIRMED`／`REFUTED`／`INCONCLUSIVE`；兩者都不寫 Plan、不修 finding | `core 同義`（`review-verdicts`、`plan-gate`） |
| G91 | L189 | 標題 `### Verification adjudication` | `core 沒有對應`（只是標題，不是規則；第 2 節不列） |
| G92 | L191 | 最終判斷留在 main-session | `core 同義`（`main-session-owns`） |
| G93 | L191-195 | 逐一重新評估 verifier 結果：可重現、是否本次引入且在範圍內、與確切 claim 的關聯、嚴重度／優先級、信心 | `core 同義`（`verdict-authority`） |
| G94 | L195-196 | P0／P1 標籤需要同時證明嚴重度與 claim 關聯的可重現證據 | `core 沒有對應`（第 2 節 N15） |
| G95 | L196-197 | 實作引入的 regression 即使 brief 沒點名也算與 claim 相關 | `core 同義`（`verdict-authority`） |
| G96 | L196-198 | P0 凍結受影響的 slice 並暫停等使用者；自動工作只做 containment；P1 在核准範圍內修或暫停詢問 | `core 同義`（`verdict-authority`、`ask-questions-main`） |
| G97 | L198-201 | 引入的 P2 regression 仍為 blocking；其他 P2 只在有界、在 acceptance 與核准範圍內才修，否則附理由延後並縮小 claim | `core 同義`（`verdict-authority`） |
| G98 | L201-203 | 有文件記錄的 regrade 可以採用 verifier 引用的證據 | `core 沒有對應`（第 2 節 N16） |
| G99 | L203-205 | 沒有反證或沒有成功重測原本的失敗，不可默默延後、駁回、降級或宣稱 blocker 已修 | `core 同義`（`recheck-and-invalidate`、`verdict-authority`） |
| G100 | L205-206 | P3／P4 是非 blocking 的建議，回報或延後，不開專用的修復／重驗迴圈 | `core 同義`（`verdict-authority`） |
| G101 | L207-208 | `INCONCLUSIVE` 只在證據、前提、contract 或環境有實質變化後重試一次，否則暫停該 slice | `core 同義`（`recheck-and-invalidate`） |
| G102 | L210 | 標題 `### Verification recovery and long autonomous runs` | `core 同義`（`recovery-heading`） |
| G103 | L212-213 | recovery 預算與嚴重度規則適用每次驗證；AUTO／ASK 只適用可能很長的自主工作 | `core 同義`（`recovery-budget`） |
| G104 | L215-216 | 可能很長的自主工作前，宣告當前任務是 `AUTO` 或 `ASK` | `行為變更，移除`（core `auto-ask-selection`：「offer `AUTO` or `ASK` and wait」，由使用者選；legacy 是 agent 宣告） |
| G105 | L216-217 | 睡覺、吃飯、離開不構成授權 | `core 同義`（`auto-ask-selection`） |
| G106 | L217-218 | headless 的長時間 run 沒有明確模式時輸出 `PAUSED_NEEDS_USER` 並結束 | `core 同義`（`auto-ask-selection`） |
| G107 | L218-219（away） | 明確要求「使用者不在時繼續」就選 `AUTO`，並且必須宣告 | `core 同義`（`auto-ask-selection`） |
| G108 | L219（/goal） | 「`/goal` preserves only the objective.」 | `行為變更，移除`（core `auto-ask-selection`：使用者已給 `/goal` 或明確要求完成任務，即選定 AUTO） |
| G109 | L219-220 | 這些大寫標籤不會切換 Grok 的 `/auto` 或 permission mode | `Grok 調校，移到 addendum`（接在 `auto-ask-selection` 之後；`/auto` 是 Auto-review 權限模式，`04-slash-commands.md`） |
| G110 | L222-226 | AUTO 只允許核准範圍內可逆的工作與 main 的 P2 裁決；不含 commit／push／PR／merge、publish／release／install、credential、破壞性、外部變更、擴大範圍、花費；另行授予的權限仍有效 | `core 同義`（`auto-limits`，required） |
| G111 | L228-232 | ASK：只有 session 真的有原生提問工具才用；否則以 `PAUSED_NEEDS_USER`、一個問題、選項、建議結束 turn；headless 輸出暫停後結束，不輪詢、不重試、不猜、不繼續；只有 main 提問，child 不問 | `core 同義`（`ask-mode`、`ask-questions-main`、`bootstrap-questions`） |
| G112 | L234 | P0 凍結其 slice 與相依者；跨領域 P0 停下整個 program | `core 同義`（`ask-questions-main`） |
| G113 | L235-246 | blocking P1／P2 的修復／重驗最多五輪（1-2 正常、3-5 recovery），每輪需有實質變化；完整 tested identity 的 fingerprint；不重驗相同 identity；五輪後 `PAUSED_VERIFICATION`、擋住相依者，只在風險非跨領域時繼續無關 slice | `core 同義`（`recovery-budget`、`identity-fingerprint`） |
| G114 | L246-248 | blocking P2 計入同一預算並併入下一次整合邊界驗證；P3／P4 沒有專用迴圈 | `core 同義`（`recovery-budget`、`verdict-authority`） |
| G115 | L250-253 | 整個 run 只在跨領域 blocker、剩餘工作都依賴暫停的 slice、新權限或產品決策、破壞性／外部動作、預算或額度耗盡、環境不安全、原始範圍無法達成時才停 | `core 同義`（`ask-questions-main`） |
| G116 | L253-256 | 最終報告分開列出 confirmed、fixed、deferred、regraded 或 rejected、暫停的 slice 與相依者、inconclusive 或未跑的檢查、縮小的 claim、測試與 gate、成本、未採取的外部動作 | `core 同義`（`final-report`） |

### 1.1 標題與外框

L1-3 與 L257 的 marker 不是條款而是外框。installer 與測試依賴它們：
`tools/install_grok.py:50-51` 的 `BEGIN`／`END` 用來檢查既有 rules 檔的
marker 是否成對（`check_rules_markers`，`:317-327`），`verify()`（`:439-461`）
要求 `<!-- shoal-grok v<VERSION> -->` 恰好一行且等於 `hosts/grok/VERSION`。
Claude 的做法是把版本 marker 放在 `hosts/claude/policy-frames/bootstrap.md`；
Grok 要保留 begin／end marker 的話，也只能放在外框（core 條款不含 host 專屬
文字，`tests/test_role_contracts.py:155-177` 的 `HOST_SPECIFIC_TERMS` 禁止
`grok` 等字樣出現在條款裡）。

### 1.2 core 有、legacy 沒有的條款（切換後 Grok 新增的行為）

72 個 core 條款沒有任何 legacy 列對應到（124 個中，52 個被上表引用為同義、
調校接點或被取代者）。它們是切換後 Grok 多出來的行為，`shared-rules` A6 要求
對照表把行為變更逐項列出，這裡以群組列出 id：

| 群組 | 條款 id | 備註 |
| --- | --- | --- |
| 互動形狀與 risk trigger | `bootstrap-routing`、`interaction-shape`、`routing-heading`、`bootstrap-risk`（required）、`risk-triggers`（required） | legacy 沒有 `co_discover`／`explore_then_plan`／`execute` 的分流，也沒有 risk trigger 清單（`docs/specs/core-policy/SPEC.md:35-36`）。legacy 的 Plan gate 以任務大小觸發，不是以 risk trigger 觸發 |
| 結果延續 | `bootstrap-outcome` | 「清楚的修復請求是一個 outcome，做到 acceptance」 |
| 派工參數 | `bootstrap-effort`、`effort-per-delegation`、`bootstrap-kind-label`、`dispatch-kind-label` | 每次派工帶 effort、`description` 以 `fix:` 等開頭；effort 部分是否可行見第 3 節。`bootstrap-dispatch-brake` 的「不帶 model」對應 L158-159、「time budget」對應 L162-164 的 budget，已在第 1 節引用 |
| 回報與收集 | `bootstrap-collect`、`bootstrap-verify-report`、`subagent-final-message`、`liveness`、`followup-by-mode` | `bootstrap-verify-report` 是 shared-rules B1 的完成前檢查 |
| 委派擴充 | `research-fanout`、`mech-collect`、`discovery-scope-exclusive`、`plan-critic-gaps`、`outcome-verification`、`small-parallel-units` | `researcher` 兩個 arm、`watcher` 的前提是 legacy 沒有的 role 條款 |
| security 摘要 | `bootstrap-security`（required） | 內容已由 L145-153 涵蓋，只是常駐 bootstrap 的一行摘要 |
| skill 入口 | `bootstrap-load-skill`、skill 文件全部 9 條 | 見第 4 節 |
| 擴充規則 | extensions 文件全部 40 條，其中 `ext-no-authority`、`material-gates-first`、`explicit-approval-only` 是 required | continuation、review intent、discovery budget、decision checkpoint、task ledger、circuit breaker、direction checkpoint 等 |

required 條款裡，legacy 沒有對應的有六個：`bootstrap-risk`、`risk-triggers`、
`bootstrap-security`（見上，實質已涵蓋）、`ext-no-authority`、
`material-gates-first`、`explicit-approval-only`。它們不能 omit，切換後必然
出現在 Grok 的輸出。

## 2. core 沒有對應的規則

下列是 legacy 檔裡只存在於 Grok 文字、但不依賴 Grok 機制的通用規則。這裡只
記錄原文、為何看起來通用、刪掉會失去什麼，不決定去留。編號對應第 1 節
的「第 2 節 N#」。

| 編號 | 位置 | 原文（完整句子） | 為何看起來通用 | 刪掉會失去什麼 |
| --- | --- | --- | --- | --- |
| N1 | L7-9 | For every large, ambiguous, architectural, risky, or explicitly plan-first task, native Grok Plan Mode and a fresh `plan-critic` readiness pass are mandatory. | 觸發條件只看任務性質，不依賴 Grok 機制；Plan Mode 之外的「強制 `plan-critic`」在任何 host 都成立 | core 只對 risk-triggered unit 強制 `plan-critic`，且 `risk-triggers` 明寫「File count, model concern, routine docs/UI, bounded fail-soft bug alone do not trigger」。刪掉後，沒有 risk trigger 的大型或架構性任務不再被強制審 Plan。這是強制範圍與 core 的出入 |
| N2 | L16-19 | ...spawn a fresh `plan-critic` with `background: false`, the exact target readiness-unit ID and kind, the full Plan text, and relevant evidence paths. | 規定 brief 的內容，與 host 無關（`background: false` 是 Grok 參數，已另列為調校） | 刪掉後沒有規則要求 main 給 critic 完整 Plan 與 evidence 路徑；critic 是唯讀、fresh context，只能靠 brief |
| N3 | L19-20 | Format the target as a `## Target readiness unit` block with `- ID:` and `- Kind:` (`program envelope` or `execution slice`). | brief 格式；Grok 的 plan-critic addendum `brief-unit-kinds`（`hosts/grok/addenda/plan-critic.toml:18-23`）依賴這兩個 kind 詞 | 刪掉後 critic 收到的 unit 不一定帶 kind，該 addendum 失去對應的輸入；ID 的穩定性也失去格式約束 |
| N4 | L25-27 | For every initial review or fresh re-review of a security-affected unit, the brief must explicitly state that `security-reviewer` findings and dispositions were carried into the Plan; do not rely on the Plan text alone for that handoff. | security 交接的 brief 規則，與 host 無關 | plan-critic 的 role 條款 `security-prerequisite` 仍要求 critic 自己檢查 Plan 內有 findings；刪掉的是 main 必須在 brief 明說這件事 |
| N5 | L36-38 | For initial approval, fully specify only the next executable slice; keep later slices to stable IDs, outcomes, and prerequisites until they become current. | 限制 Plan 的詳細程度，與 envelope／slice 模型一致，core `plan-gate` 沒有這個限制 | 刪掉後 main 可能把所有 slice 完整展開，Plan 變長、審查範圍變大 |
| N6 | L49-52 | A broad initial request, or a request to skip planning, skip approval, start immediately, or continue until files change, does not waive this gate. | 防止使用者措辭繞過核准，不依賴 Grok（前半「broad initial request」core `approval-gate` 已有） | 刪掉後「跳過規劃」「立刻開始」「做到檔案改完為止」是否繞過核准，core 沒有明文 |
| N7 | L52-54 | Automatic permission grants, including always-approve or `bypassPermissions`, are not user approval of the Plan; an unattended run must stop after presenting the verified Plan. | 區分工具權限自動核准與 Plan 核准；Claude 也有 `bypassPermissions`。後半「停在呈現 Plan」core `risk-review-mandatory` 已有 | 刪掉後自動權限是否算核准沒有明文 |
| N8 | L57-59 | Findings from `security-reviewer` on a program envelope remain constraints on each affected slice, but the envelope itself is not an executable contract. | envelope 與 slice 的關係，通用 | 刪掉後 envelope 層的 security findings 是否繼續約束各 slice 沒有明文；envelope 可能被當成可執行 contract 交給 `security-executor` |
| N9 | L63-66 | The direct-work allowance, dispatch brake, coordination-cost heuristic, matching-role-optional rule, single-unknown-bug exception, and failed-attempt takeover rule do not waive this boundary. | 把所有繞道都列為不能豁免 security 邊界，通用 | 這句列舉的多數規則本身會被移除（G38、G52、G58、G79 等）；刪掉後仍需要保護的是 core 的 `#direct`（`direct-when-small` 沒有 security 例外，`security-sensitive-routing` 只說不用 general executors）。core 工作樹的 `one-shot-spec` 已不再有 take over |
| N10 | L67-69 | If implementation attempts fail, stop or retask through `security-executor`; neither the main session nor another role may take over the slice. | 失敗後的處置，通用 | core 工作樹的 `one-shot-spec` 是「escalate tier or report to the user」，已沒有 take over，也沒有「改派 `security-executor`」；刪掉後 security slice 失敗後的處置只剩升級或回報使用者 |
| N11 | L146-149 | Before spawning `security-reviewer`, assign stable IDs to the affected program envelope and current execution slice. Include every exact affected unit ID in its brief and require its output to name each one. | brief 規則；security-reviewer 的 role 條款 `report-fields` 已要求報告 affected unit ID | 刪掉後 main 不必先指定 ID 並放進 brief；role 側要報 ID，但可能沒有 ID 可報 |
| N12 | L151-152 | If an affected ID changes or is added, repeat security review before readiness. | 通用；core `security-reviewer-first` 只說 first readiness review 前先完成 | 刪掉後 Plan 拆分或新增 unit 時是否重做 security review 沒有明文 |
| N13 | L162-164 | Brief each worker in one shot with the goal, constraints, done criteria, relevant paths, rationale, output format, budget, and verification expectation. | brief 清單；core `one-shot-spec`（工作樹版本）列 goal、constraints、done criteria、relevant paths、rationale、file ownership、time budget | legacy 的 budget 與 core 的 time budget 同義（已在 G 列歸為 `core 同義`）；刪掉的是 output format 與 verification expectation 兩項 |
| N14 | L164-165 | After two failed attempts, change the task boundary or escalate one tier. | 失敗後出路；core 工作樹版本是「escalate tier or report to the user」 | 刪掉後少了「改變任務邊界」這個選項；legacy 也沒有 take over 這個選項（見 G79） |
| N15 | L195-196 | A P0/P1 label requires reproducible evidence of both severity and exact-claim relevance. | 驗證裁決的證據門檻，通用；core `verdict-authority` 要 main 檢查可重現性等，但沒有「P0／P1 標籤本身需要證據」 | 刪掉後 P0／P1 標籤不需同時證明嚴重度與 claim 關聯，就會觸發凍結或暫停 |
| N16 | L201-203 | A documented regrade may use the verifier's cited evidence when it establishes different impact. | 裁決時調整優先級的授權，通用；core `final-report` 提到 regraded，但沒有授權 | 刪掉後 main 是否可用 verifier 引用的證據重新分級沒有明文 |

## 3. core 條款在 Grok 上的可行性

### 3.1 placeholder

詞彙在 `core/policy/placeholders.toml`（16 個 key）；binding 必須全部提供值
（`tools/render.py:347-358` 的 `require_policy_complete`）。證據來源縮寫：
「legacy」是 legacy 檔、「docs」是 `~/.grok/docs/user-guide/`（本機文件）、
「hook」是 `hosts/grok/src/hooks/shoal-grok.json`、「E0」是
`docs/specs/dispatch-enforcement/E0-RESULTS.md`。

| key | Grok 值 | 證據 | 狀態 |
| --- | --- | --- | --- |
| `dispatch_tool` | `spawn_subagent` | legacy L107、L159；hook 的 matcher（`shoal-grok.json:52、62`）；E0 總表 L14；docs `16-subagents.md`；`hooks/shoal_guard.py:173` 的 `DISPATCH_NAME` | 確定 |
| `question_tool` | `ask_user_question` | docs `19-plan-mode.md`、`05-configuration.md`、`26-config-reference.md`（`features.ask_user_question` 預設 true）。legacy L228-229 只寫「native user-input or question tool ... actually exposed」，沒有名稱 | 本機文件有名稱；headless 是否提供未知（U6） |
| `named_roles` | `scout`、`plan-critic`、`security-reviewer`、`applier`、`executor`、`verifier`、`security-executor`、`watcher`、`researcher` | `hosts/grok/binding.toml:36-72` | 確定（legacy L70-73 少 `watcher`、`researcher`）。`Explore` 被 `config.snippet.toml:11-12` 停用，不是 named role |
| `shell_tool` | `run_terminal_command` | legacy L181；docs `20-background-tasks.md:9`、`10-hooks.md`（`Bash` 別名對應 `run_terminal_command`）。但 `14-headless-mode.md`、`08-skills.md` 寫 `run_terminal_cmd` | 名稱衝突（U2） |
| `write_tools` | `search_replace`、`write_file`、`write`（最小集合） | hook matcher 另列 `edit`、`multi_edit`、`create_file`；E0 L56-58 實測看到 `search_replace`、`write_file`、`write`；docs 別名 `Edit`／`Write`／`MultiEdit` 對應 `search_replace` | 完整清單未確認（U5） |
| `read_tools` | `read_file`、`grep`、`list_dir` 加 `run_terminal_command` | docs `10-hooks.md` 別名表（`Read`→`read_file`、`Grep`→`grep`、`Glob`／`ListDir`→`list_dir`）；repo 內沒有其他來源 | 只有本機文件 |
| `background_option` | legacy：`background: true`（spawn 用 `background`，L17、L172）；docs：`run_in_background`，預設 `true`（`16-subagents.md` 的 Spawning 表）；shell 的背景參數是 `background: true`（`20-background-tasks.md:9`） | 兩個來源對 `spawn_subagent` 的參數名稱不同 | 衝突（U1）。注意 docs 說省略時預設就是背景，所以前景呼叫（例如 L17 的 `background: false`）必須明寫 |
| `worktree_option` | `isolation: "worktree"` | legacy L174；docs `16-subagents.md`（`isolation` 為 `none` 或 `worktree`，需要 git） | 確定 |
| `model_param` | `model` | legacy L159；docs `16-subagents.md`「Model Selection by the Agent」 | 確定 |
| `effort_param` | 沒有找到 | role 的 effort 在 `roles/*.toml` 的 `reasoning_effort`（`binding.toml:12`）；docs 只提「Explicit spawn-time override」（`16-subagents.md` Persona Resolution），沒有參數名稱；legacy 完全沒提每次派工的 effort；使用它的條款是 `bootstrap-effort` 與 `effort-per-delegation` | 未確認（U3），見 3.3 |
| `label_param` | `description` | docs `16-subagents.md` Spawning 表（「A short label for the task (3-5 words)」）；legacy 沒提 | 本機文件有；`fix:` 等前綴是否與「3-5 words」衝突沒有證據 |
| `goal_command` | `/goal` | legacy L219；docs `04-slash-commands.md`「`/goal`」（「appears when goal mode is enabled for the session」） | 確定，但 session 可能沒開 |
| `skill_term` | `skill` | docs `08-skills.md` | 名稱確定；模型端如何載入 skill 的工具名稱未記載（U6） |
| `policy_doc` | 隨第 4 節的檔案配置 | — | 取決於第 4 節 |
| `extensions_doc` | 同上 | — | 取決於第 4 節 |
| `references_dir` | 同上（Claude 是 `references/`） | docs `08-skills.md` Best Practices 7：長參考資料放 skill 的 sibling files | 取決於第 4 節 |

### 3.2 假設某種能力的條款

| 條款 | 假設 | Grok 現況 | 狀態 |
| --- | --- | --- | --- |
| `explore-then-plan-boundary` | 第一個 turn 唯讀，禁止 `{{write_tools}}` 與會改檔的 `{{shell_tool}}` | Plan Mode 擋 edit 工具、不檢查 shell 寫檔（docs `19-plan-mode.md`「Bash commands are not inspected for file writes」）；`plan.md` 是 Plan Mode 唯一可寫檔 | 可行；`plan.md` 例外需要 Grok addendum（G09） |
| `bootstrap-delegate-default`、`watcher-long-commands`、`leaf-cannot-finish` | 有 `watcher` role、可背景派工、可收結果 | `watcher` 已綁定（`binding.toml:66-68`，`roles/watcher.toml`：`execute`）；背景完成會自動喚醒 parent，用 `get_command_or_subagent_output` 取輸出（docs `20-background-tasks.md`） | 可行 |
| `research-fanout`、`bootstrap-delegate-default` 的兩個 `researcher` | 有 `researcher` role、同一個 message 平行派兩個 | `researcher` 已綁定（`binding.toml:70-72`，唯讀）；同一個 message 平行發出兩個 `spawn_subagent` 沒有本機證據（U13） | role 可行，平行方式未驗證 |
| `parallel-writers` | 隔離 worktree、需要 Git | `isolation: worktree`（docs `16-subagents.md`） | 可行 |
| `discovery-scope-exclusive` | 後續讀取會「reject mixed commands touching any active-agent path」 | 沒有任何 hook 或 guard 規則實作這件事（`hooks/shoal_guard.py` 沒有 scope 相關邏輯，任何 host 都一樣） | 只能靠模型遵守，與其他 host 相同 |
| `ledger-split` | 「harness task or todo tool when available」 | Grok 有 todo pane（docs `16-subagents.md` 的 Tasks Pane、`Ctrl+T`），工具名稱未記載；條款本身是條件式 | 可行（條件式） |
| `checkpoint-*`、`ask-mode`、`bootstrap-questions` | `{{question_tool}}` 可用，不可用時以 `PAUSED_NEEDS_USER` 結束 | 同 `question_tool` 列；fallback 與 legacy L229-232 相同 | 可行 |
| `auto-ask-selection`、`cost-unbounded-continuation` | 使用者宣告長期目標的指令 | `/goal` 存在但需 goal mode；`cost-unbounded-continuation` 把 `` `/goal` `` 直接寫在條款文字裡（`core/policy/extensions.toml:381`，反引號包住所以逃過 `tests/test_core_policy.py` 的硬編碼檢查），Grok 值恰好相同 | 可行 |
| `direction-checkpoint` | verifier 支援 `direction_checkpoint` 並回 `CONTINUE`／`PIVOT`／`ROLLBACK` | `subagent_stop_gate.py:18` 的 token 已含這三個 | 可行 |
| `plan-critic-gaps` | plan-critic 支援 `mode: gaps` | `tests/test_delegation_default.py:226-243` 確認 Grok 的 plan-critic 含 `mode: gaps` | 可行 |
| `parallel-launch`、`bootstrap-collect`、`collect-results` | 背景 role 完成會通知 | docs `20-background-tasks.md`：「Completion wakes the parent automatically」 | 可行 |
| `bootstrap-load-skill`、skill 文件 | host 有 skill 機制並能載入 | 有（docs `08-skills.md`），但 shoal 目前不安裝 skill（第 4 節） | 取決於第 4 節 |
| `bootstrap-effort`、`effort-per-delegation` | 派工時可傳 effort | 見 3.3 | 未確認 |

### 3.3 可能要省略的條款，以及 required 條款是否受阻

- 目前能確定必須省略的條款：0 個。
- 待確認：`bootstrap-effort` 與 `effort-per-delegation` 兩條（都不是 required，
  都用 `{{effort_param}}`）。若 Grok 的 `spawn_subagent` 確定沒有每次覆寫 effort
  的參數，依 shared-rules A4 這是「做不到，省略」的理由，兩條要一起列入 `omit`。
  工作樹的 core 已把 effort 從 `bootstrap-dispatch-brake` 拆成獨立的
  `bootstrap-effort`（`core/policy/bootstrap.toml:77-85`），所以只省略 effort 不會
  連帶拿掉「不帶 model」「brief 寫 scope／stop／time budget」「`description` 前綴」
  （`bootstrap-dispatch-brake`、`bootstrap-kind-label`）。HEAD 版本的
  `bootstrap-dispatch-brake` 仍是四件事合在一條，若 core 退回該版本，就只能用
  addendum 的 `replace:`（`tests/test_core_policy.py:36` 的
  `EXPECTED_POLICY_REPLACES` 要同步鎖定）。
- required 條款（15 個）沒有任何一個因 placeholder 或能力而無法輸出：它們只用到
  `named_roles` 與 `dispatch_tool` 兩個 placeholder，值都已確定（3.1），
  **沒有 blocker**。
- 另一個與 required 有關的限制：required 條款分布在 orchestration（9 個）、
  extensions（3 個）與 bootstrap（3 個）。`render.py:347-358` 要求四份文件都有輸出路徑，
  而整份文件只有在所有條款都被 omit 時才不輸出（`render.py:361-387`），所以含
  required 條款的 orchestration 與 extensions 在 Grok 上一定要有落點（第 4 節）。

## 4. 文件對應

### 4.1 Grok 現況與機制證據

- Grok 今天只有一個常駐檔：`rules/shoal-grok.md`。`grok inspect` 的輸出（本機，
  只取含 rules 的行）：

  ```text
  $ grok inspect 2>&1 | grep -i -n "shoal-grok\|rules\|tokens"
  9:  └ /Users/miyago/.grok/rules/shoal-grok.md (global, ~4003 tokens)
  ```

  （完整輸出另有其他 rules 與設定行，這裡只取 shoal 的那一行。）

- **rules 沒有隨需載入機制。** `12-project-rules.md` 的 Rules Directories 一節：
  `$GROK_HOME/rules/`「Always scanned; applies to all projects」，目錄內每個
  `*.md` 都載入，同目錄依字母排序；「Grok loads each project instruction file in
  full; there is no character cap and no truncation」。唯一類似隨需的是「讀到其他
  目錄時才偵測該目錄的 AGENTS.md」，只適用專案目錄，不適用全域 rules。
- **skills 是隨需載入機制。** `08-skills.md`：skill 是含 `SKILL.md` 的目錄，
  frontmatter 有 `name`、`description`；「Grok activates a skill only when it
  applies to your current task」（比對 `description` 與 `when-to-use`），也可用
  `/<name>` 明確呼叫；skill 內容最多內嵌前 25,000 tokens，長參考資料放 sibling
  files。使用者層的位置是 `~/.grok/skills/`（本機該目錄已存在，內容是其他 skill
  的 symlink，沒有 shoal 的 skill）。
- shoal 目前不安裝 skill：`tools/install_grok.py:45` 的
  `INSTALL_TOPS = ("agents", "roles", "rules", "hooks")`；`:110`（`load_source`
  只收這四個頂層）與 `:543`（`do_restore` 拒絕其他頂層）同樣寫死。
  `hosts/grok/dist/config.snippet.toml:17-23` 還建議把 `[compat.claude]` 的
  `skills` 等全部設成 `false`，所以 Claude plugin 的 skill 不會被 Grok 讀到。
- renderer 的限制：`[policy.documents]` 不允許兩份文件輸出到同一個路徑
  （`tools/render.py:341-342`），所以「把四份文件合成一個檔」需要改 renderer，
  不是只改 binding。Claude 的做法（四份文件四個路徑，core 輸出取代 src 同路徑
  原文）見 `render.py:557-561`。

### 4.2 三種落點與大小

大小是用暫存目錄裡的 Grok binding 實際跑 `render.py --host grok
--policy-preview` 得到的（repo 沒有改動；placeholder 用 3.1 的暫定值、外框只有
marker 與標題、**不含任何 Grok addendum**，所以是 core 文字的下限）：

| 文件 | bytes | 行 |
| --- | --- | --- |
| bootstrap | 3,150 | 49 |
| skill | 1,694 | 36 |
| orchestration | 19,432 | 283 |
| extensions | 9,391 | 172 |
| 合計 | 33,667 | 540 |

對照：Grok 現行常駐 16,015 bytes、約 4,003 tokens（上方 `grok inspect`），約
4.0 bytes／token，所以 33,667 bytes 約 8,400 tokens（線性估算，不是量測）。
Claude 的 dist 同一批文件也在 33 KB 級（HEAD 版本 3,103 + 1,683 + 19,014 +
9,457 = 33,257 bytes）。

| 落點 | 內容 | 常駐大小 | 需要的變更 | 本機證據 |
| --- | --- | --- | --- | --- |
| A. 四份都常駐 | bootstrap 放 `rules/shoal-grok.md`，其餘三份各放 `rules/` 下另一個 `.md` | 33,667 bytes（現行的 2.10 倍；省略 skill 文件約 31,973） | binding 加 `[policy.*]`、外框、addenda；renderer 要支援 core；dist 增加 3 個檔（`GOLDEN_COUNT` 24→27）；installer 的 `rules` 頂層已涵蓋，但 `verify()` 只檢查 `rules/shoal-grok.md` 的 marker | rules 目錄的 `*.md` 全部載入（`12-project-rules.md`）。目錄內子目錄是否掃描未載明（U7） |
| B. bootstrap 常駐、其餘走 skill | bootstrap 放 `rules/shoal-grok.md`；skill、orchestration、extensions 放 `skills/shoal-orchestration/**`（同 Claude 的配置） | 3,150 bytes（現行的 20%） | 同 A，另加：`INSTALL_TOPS`（`install_grok.py:45、110、543`）、`tests/test_install_grok.py:145-150` 的 `installable()`、`sync_global.py` 隨 installer 自動涵蓋；`config.snippet.toml` 的 `[compat.claude] skills = false` 只影響 Claude 的 skill，不影響 `~/.grok/skills/` | skills 機制存在（`08-skills.md`），但 repo 內沒有任何 Grok skill 被實際載入的紀錄（U14） |
| C. 合成一個常駐檔 | 四份文件合成 `rules/shoal-grok.md` | 33,667 bytes | 需要改 renderer（`render.py:341-342` 目前禁止）；外框與跨文件連結（skill 文件的 `reference-*`、`ext-extend-policy`）在單檔內失去意義，可 omit 的只有非 required 的 skill 條款 | 同 A |

三種落點不在這裡選擇。與落點有關的事實：

- 選 B 時，常駐的只有 bootstrap：required 條款 `bootstrap-named-roles`、
  `bootstrap-risk`、`bootstrap-security` 常駐，其餘 12 個 required 條款
  （`intro-named-roles`、`risk-triggers`、`risk-review-mandatory`、`approval-gate`、
  `security-sensitive-routing`、`security-reviewer-first`、
  `security-executor-after-approval`、`security-no-preapproval-write`、`auto-limits`、
  `ext-no-authority`、`material-gates-first`、`explicit-approval-only`）變成隨需載入，
  與 Claude 現況相同。Grok legacy 把 Plan gate、核准、security 邊界、AUTO 限制
  全部常駐（legacy 檔 L5-69、L222-226），這是 B 與現況的差別。
- legacy 把「第一個 tool call 必須是 `enter_plan_mode`」放在常駐檔最前面
  （L5-13）。這類 Grok 調校（G04、G06 至 G09）要掛在 core 條款之後：
  `explore-then-plan-boundary`、`approval-gate`、`plan-gate` 都在 orchestration 文件；
  若要常駐，只能掛在 bootstrap 的條款（例如 `bootstrap-routing`、`bootstrap-risk`）
  之後，會增加 bootstrap 的大小。
- 沒有找到 Grok 的常駐大小上限：LOCK 沒有 Grok surface（`docs/specs/prompt-document-lock/LOCK.json`
  的 `surfaces` 沒有 grok 路徑，`grep -i grok` 無結果）、沒有測試釘住大小、docs 說
  rules「no character cap」。shared-rules A5 的「現有上限」對 Grok 沒有數字可依據（U15）。

## 5. 上游對照測試

### 5.1 `kind = "derived"` 的意思

`upstream.lock:2-7` 的定義：`derived` 是「原本是 vendored，`agents/` 的 role 文字
已改由 core 條款產生（不再逐字等於上游），`agents/` 以外的檔案仍逐字取自上游」。
`[grok]`（`upstream.lock:9-15`）：上游 `Nanako0129/pilotfish-grok` v1.0.6，
`source` 寫明「`rules/pilotfish-grok.md` 逐字取自上游 v1.0.6，只有 marker 由
`hosts/grok/VERSION` 產生」。渲染端 `tools/render.py:769-771` 的 `_grok_rules`
就是 `_versioned_rules(src, ...)`：逐字輸出 `hosts/grok/src/rules/shoal-grok.md`，
只替換 `<!-- shoal-grok v... -->` 那一行（`render.py:676-688`）。

### 5.2 哪些測試強制貼近上游

| 測試 | 位置 | 比對什麼 | 容許的差異 |
| --- | --- | --- | --- |
| `test_rules_equal_upstream_except_the_rename` | `tests/test_render_grok.py:68-76`（fixture：`tests/fixtures/grok/rules.pilotfish-grok.upstream-v1.0.6.txt`，257 行） | `render.RENDERERS["grok"](ROOT)["rules/shoal-grok.md"]` 逐字等於「fixture 經 `apply_rename` 加兩個 role 改名加 marker 版本」 | 只有 `docs/specs/shoal-rebrand/RENAME.md` 的名稱替換、`mech-executor`→`applier`、`plan-verifier`→`plan-critic`、版本 marker。實測 `diff` fixture 與 src 只差這些（marker、`pilotfish-grok`→`shoal-grok`、`plan-verifier`→`plan-critic`、`mech-executor`→`applier`）。加入 `watcher`、`researcher` 就會失敗 |
| `test_main_session_policy_text_is_unchanged_except_version_markers_and_role_rows` | `tests/test_delegation_default.py:201-214`（hash 在 `:106`） | Grok 輸出的 sha256 等於 v3.0.3（`fa90087`）時的值，且不含 `` `watcher` ``、`` `researcher` `` | 只有版本 marker |
| `test_vendored_files_are_copied_verbatim` | `tests/test_render_grok.py:24-31` | `src` 內 `agents`、`rules` 以外的檔案逐字複製 | 不涉及 rules，不受影響 |
| `UpstreamLockTests` | `tests/test_render_grok.py:133-150` | `upstream.lock` 的 `kind`、`upstream`、`version`、`marker_version` | 不比對 rules 內容，只在 lock 欄位被改時受影響 |
| golden | `tests/render_helpers.py:75-89`、`tests/golden/grok/rules/shoal-grok.md` | dist 與 golden 逐位元組相同 | 這是回歸基準（`SOURCE` 記 `shoal@300bc1d`，`dirty: true`），不是上游比對 |

### 5.3 改由 core 產生後

- `test_rules_equal_upstream_except_the_rename` 會失敗：輸出不再是上游文字，
  差異遠超出容許的替換。`test_main_session_policy_text_is_unchanged...` 的 hash 與
  `assertNotIn("`watcher`")` 也會失敗（core 條款含 `watcher`、`researcher`）。
- 選項（不選擇）：
  1. 刪除上游比對，保留 fixture 檔作為歷史紀錄（`tools/scan_legacy_names.py:53`、
     `tools/check_rename.py:47`、`tests/test_scan_legacy_names.py:109` 都只是以路徑
     豁免該 fixture，檔案留著不需要改它們）。`upstream.lock` 的 `source` 說明要改
     （`core-policy` 決策 2 已寫「只需更新 `source` 說明」）；`kind = "derived"` 與
     `GrokDocsTests`（`test_render_grok.py:153-170`，要求 README 有上游連結）不受影響。
  2. 只對「reference copy」保留比對：`policy_text = "core"` 時 `hosts/grok/src/rules/
     shoal-grok.md` 不再被輸出（類似 `render.py:557-561` 讓 core 輸出取代 src 同路徑
     原文，以及 role 的 legacy 快照做法，`tests/test_render_grok.py:105-111`），測試
     改成讀 src 檔本身對 fixture 比，而不是讀 render 結果。此時 src 檔同時是
     `policy_text = "legacy"` 的 rollback 來源（core-policy P4）。
  3. 兩者的共同後果：`binding.toml:15-21` 的註解、`upstream.lock` 的 `source`、
     `docs/specs/grok-workflow` 的決策 1（「rules 以 vendor 方式保留上游原文」）都
     需要加註記被 shared-rules D1 取代，但那些是文件，不是測試。

## 6. hooks 與 guard

### 6.1 目前 Grok 上有效的 shared guard 規則

hook 註冊（`hosts/grok/src/hooks/shoal-grok.json`，與 dist 相同）只有三類事件：
`SubagentStop`（三個 entry）、`UserPromptSubmit`（`shoal_guard.py`，env
`SHOAL_GUARD_HOST=grok`）、`PreToolUse`（`^spawn_subagent$` 的 `plan_mode_guard.py`，
以及 `^(search_replace|write|write_file|edit|multi_edit|create_file|spawn_subagent)$`
的 `shoal_guard.py`）。沒有 `Stop`、`SubagentStart`，也沒有 shell 工具的 matcher。

hook 的 env 只設 host，沒有設 `SHOAL_GUARD`，所以模式是 guard 的預設：
`HOST_DEFAULT_MODE["grok"] = "shadow"`（`hooks/shoal_guard.py:80-85`）。

| 規則 | Grok 現況 | 依據 |
| --- | --- | --- |
| LEAF（subagent 不可再派工） | 會判斷（Grok 是 role-aware host），shadow 下只記 `would_deny` | `shoal_guard.py:89`（`ROLE_AWARE_HOSTS`）；`adapt_grok` 用 `subagentType` 辨識（`:1595-1633`） |
| VERIFY_EDIT（`verifier`、`watcher` 不可改檔） | 同上 | `shoal_guard.py` 的 `ROLE_ACCESS`；matcher 含 edit 工具 |
| R1（main 改檔） | 只有 `classified` 模式：需要 turn 的 classification 檔，且只會 advise；不 deny | `resolve_r1` 對不在 `DECLARE_HOSTS`（`:113`）的 host 回 `classified`（`:466-475`）；deny 只給 `DENY_MAIN_HOSTS`（`:107`，claude） |
| R2（檔案數提醒） | 記 log，不輸出提醒 | `ADVISE_OUTPUT_HOSTS`（`:102`）不含 grok |
| G4、G5、strict（main 背景 shell、shell 寫檔、嚴格 R1） | 無：adapter 收不到 main 的 shell 呼叫 | hook 沒註冊 `run_terminal_command`；`adapt_grok` 沒有 `shell` 分支 |
| `#direct` | 不辨識：`adapt_grok` 沒有傳 `direct`；只有環境變數 `SHOAL_GUARD_DIRECT=1` 有效 | `shoal_guard.py:1595-1633`；`:1339` |
| B2、B3、B4 完成檢查 | 不啟用：`stop_enabled` 為 False；沒有 `Stop` 註冊；`adapt_grok` 對其他事件回 `None` | `shoal_guard.py:94`（`STOP_HOSTS`）、`:460-463`；`tests/test_shoal_guard.py:856-863、898-903`；`README.md:126-128`；`INSTALL.md:334` |

為何預設 shadow：`shoal_guard.py:79` 註解「grok/agy stay shadow (evidence pending
/ forced)」；`docs/specs/dispatch-enforcement/SPEC.md:274-275` 與 `TASKS.md:86` 記載
Miyago 2026-10-05 因免費額度用完而延後 Grok 的 enforce；重啟條件是 Open question 1
（`SPEC.md:286-288`）：shadow log 至少 20 筆決策、至少 1 筆 `would_deny`、誤擋 0、
`skip_reason` 比例 0。本機 guard log 的 Grok 紀錄（只取彙總，指令見下）：

```sh
python3 - <<'PY'
import json, collections, os
c = collections.Counter()
for line in open(os.path.expanduser("~/.local/state/shoal/guard/guard.jsonl"), errors="replace"):
    r = json.loads(line)
    if r.get("host") == "grok":
        c[(r.get("decision"), r.get("skip_reason"), r.get("rule"))] += 1
print(c)
PY
```

輸出重點：Grok 共 37 筆，其中 `state` 21、`allow` 11、`skip`（`missing_id`）4、
`would_deny`（`R2`）1，落在 2026-10-05 與 2026-10-06；決策（不含 `state` 狀態紀錄）16 筆，未達 20 筆，
skip 比例不是 0。`TASKS.md:67` 說明 `missing_id` 的 skip 發生在修正 `0fccdb8` 之前，
同一行也證明 hook 在 `grok -p`（headless）下會執行。

### 6.2 Grok 專屬 hooks 強制什麼

- `plan_mode_guard.py`：`permissionMode` 是 `plan` 時，拒絕 `spawn_subagent` 產生
  可寫入的 subagent（判斷順序：`toolInput.capability_mode`、role TOML 的
  `default_capability_mode`、內建 `explore`／`plan` 不可寫入、`general-purpose` 可寫入；
  任何解析失敗放行）。理由是 Plan Mode 不擋 subagent 的寫入（docs
  `19-plan-mode.md`：「Subagents are not covered by the parent session's
  plan-mode edit gate」）。deny 訊息列出 plan mode 內可用的唯讀 role：
  `scout`、`plan-critic`、`security-reviewer`、`researcher`
  （`plan_mode_guard.py:76-79`）。
- `subagent_stop_gate.py`：`verifier`、`plan-critic`、`security-reviewer` 的最後回覆
  格式檢查（verdict token、`READY`／`REVISE` 區塊四欄位、finding 的 severity 與
  `file:line`）；`stopHookActive` 為 true、解析失敗、role 未知一律放行。
- 沒有任何 hook 強制的 legacy 規則：第一個 tool call 是 `enter_plan_mode`、
  `plan-critic` `READY` 才能 `exit_plan_mode`、核准前不寫 source、security 邊界、
  AUTO 限制。這些在 legacy 與切換後都只是條款文字。

### 6.3 Grok 要啟用 strict 規則與完成檢查需要什麼

**strict（core「main 不自己改檔」的 guard 面）：**

1. 模式要是 `enforce`：改 `HOST_DEFAULT_MODE["grok"]`（`shoal_guard.py:80-85`）或由
   環境變數 `SHOAL_GUARD=enforce`；前提是上面 Open question 1 的 log 條件。
2. `strict` 要可選：`DECLARE_HOSTS`（`:113`）目前只有 claude、codex；該處註解說
   strict 需要 main 的 shell 呼叫事件，所以 hook 要註冊 `run_terminal_command` 的
   matcher，`adapt_grok` 要新增 `shell` 分支（帶 `command`），並處理背景參數。
3. `#direct`：`adapt_grok` 要用 `has_direct_token` 讀 `UserPromptSubmit` 的 `prompt`
   欄位（Grok payload 有該欄位，見 `tests/test_shoal_guard.py:1071-1073`）。E0 的結論是
   五個 host 都無法分辨使用者輸入與 model 排程的 prompt（`E0-RESULTS.md:18-19`）；
   claude 與 codex 之後仍採用 prompt 內的 `#direct` token（`has_direct_token`，
   `shoal_guard.py:132`），Grok 採用的話承擔同樣的限制。
4. 測試要改：`tests/test_shoal_guard.py:105-109`（`resolve_r1`）、`:167`
   （預設模式表）、`tests/test_grok_hooks.py:77、98-106`（hook 註冊）。

**完成檢查（B2 至 B4）：**

1. Grok 有文件記載的 `Stop` 事件，可阻擋並讓 agent 再跑一輪：docs `10-hooks.md`
   「Stop Decision Control」——輸入含 `stopHookActive`、`lastAssistantMessage`、
   `promptId`、`backgroundTasks`、`sessionCrons`；輸出 `{"decision":"block","reason":...}`
   或 exit 2；每個 turn 最多 8 次延續；hook 失敗時 fail-open；只管 main agent
   （subagent 走 `SubagentStop`）；session 結束時也會觸發一次 `Stop`（決策被忽略）。
2. 但 Grok 的 `Stop` payload 從未被實測記錄：`tests/fixtures/stop_payload_shapes.json`
   只有 `claude`、`codex` 兩組（`shoal_guard.py:91-93` 的註解同樣說 grok 沒有已記錄的
   結束事件）。shared-rules D5／D6 的做法是各用一次真實執行取得 payload，Grok 需要
   同樣一次（會用到模型額度）。
3. 需要的變更：在 `hosts/grok/src/hooks/shoal-grok.json` 註冊 `Stop`；`adapt_grok`
   新增 `stop` 事件（欄位是 camelCase，`stopHookActive` 而非 `stop_hook_active`）；
   `STOP_HOSTS`（`:94`）加入 grok；模式要是 `enforce`（shadow 下只記 `would_block`）。
   `changed` 的記錄已可運作（edit 工具與 `spawn_subagent` 事件都有送到）；`checked`
   可由派出 `verifier`／`watcher` 滿足；若要讓「main 的前景 shell 指令」也算檢查，
   需要上面 strict 第 2 點的 shell matcher。
4. shared-rules B4 目前只列 Claude 與 Codex 啟用，Grok 啟用要先修訂該條，
   並同步 `README.md:126-128`、`INSTALL.md:334` 兩處「Grok 沒有結束事件」的敘述。
5. 文件另記載 `PreToolUse` 可回 `additionalContext`（docs `10-hooks.md`），
   guard 因為沒有實測過而把 grok 排除在 `ADVISE_OUTPUT_HOSTS` 外；`UserPromptSubmit`
   在放行時 stdout 會被丟棄（「stdout of an allowing hook is discarded」）。

## 7. 測試影響

基準：改動前在本機跑 `cd tests && python3 -m unittest test_render_grok
test_grok_hooks`，結果 `Ran 56 tests ... OK`（含 `HostRenderCase` 繼承的測試）。

| # | 位置 | 釘住的內容 | 切到 core 後 |
| --- | --- | --- | --- |
| T1 | `tests/test_render_grok.py:68-76` | 輸出 rules 等於改名後的上游 fixture | 失敗；要刪除或改為對 reference copy 比較（第 5 節） |
| T2 | `tests/test_render_grok.py:95-101` | 改 `hosts/grok/src/rules/shoal-grok.md` 的 marker，render 要拒絕並提到 `marker`；測試內寫死版本字串的 marker 行（HEAD 是 `v3.4.0`，要與 src 檔一致） | 失敗：core 不讀這個檔，render 不會拒絕。要改成檢查 `policy-frames/bootstrap.md` 的 marker，或維持只在 legacy 時讀 |
| T3 | `tests/test_render_grok.py:61-66` | 輸出恰有一行 `<!-- shoal-grok v... -->` 且等於 `VERSION`；`assertEqual(version, ...)`（HEAD 是 `"3.4.0"`，工作樹已改 `"3.4.1"`） | marker 由外框提供即通過；字串隨每次版本 bump 要改 |
| T4 | `tests/test_render_grok.py:78-85` | 改 `VERSION` 後 `--check` 失敗並指出 `rules/shoal-grok.md`，`--write` 後 marker 更新 | 外框帶 marker 即通過 |
| T5 | `tests/test_render_grok.py:19` 加 `tests/render_helpers.py:75-81、88-89` | `GOLDEN_COUNT = 24`；dist 與 golden 逐位元組相同（`test_render_is_byte_identical_to_golden`、`test_committed_dist_matches_golden`） | 檔案清單改變（四份文件都要有輸出，+3 個檔，24→27）與 rules 內容改變，兩個測試失敗，直到 `python3 tools/refresh_golden.py --host grok --from-dist` 重建 golden 並改 `GOLDEN_COUNT` |
| T6 | `tests/render_helpers.py:83-86` | `tests/golden/grok/SOURCE` 的 `ref: shoal@<7 hex>` | 重建 golden 後仍符合 |
| T7 | `tests/test_render_grok.py:24-31` | `src` 內 `agents`、`rules` 以外的檔案逐字複製 | 不受影響 |
| T8 | `tests/test_render_grok.py:133-150` | `upstream.lock` 的 `kind = "derived"`、upstream 名稱、version `v1.0.6`、`marker_version == VERSION` | `kind`／upstream／version 不受影響；`marker_version` 隨版本 bump 要改 |
| T9 | `tests/test_delegation_default.py:101-107` 與 `:201-214`（`:106` 是 hash；`:210-212` 是 `assertNotIn` `watcher`／`researcher`；`:90` docstring 寫 D17「不接派工條款」） | Grok rules 的 sha256 等於 v3.0.3 的值；規則文字不含 `watcher`、`researcher` | 失敗；hash 表要移除 Grok 項，`assertNotIn` 的 Grok 部分要移除；docstring 的 D17 敘述與 shared-rules 不一致 |
| T10 | `tests/test_core_policy.py:32` 與 `:226-231` | `EXPECTED_POLICY_TEXT`：grok 是 `legacy` | 失敗，改為 `core` |
| T11 | `tests/test_core_policy.py:35-38` 與 `:232-239、240-254` | `EXPECTED_POLICY_OMITS`、`EXPECTED_POLICY_REPLACES`、`EXPECTED_POLICY_ADDENDA` 對 grok 都是空 | Grok 有 policy-addenda（必然，至少 Plan Mode 調校）時 `test_replace_lists_and_addenda_are_locked` 失敗，表要補；有 omit 時 `test_omit_lists_are_locked_and_every_omit_has_a_reason` 也失敗 |
| T12 | `tests/test_core_policy.py:408-415` | `test_core_is_rejected_for_hosts_that_are_not_ready` 把 grok 列入「core 會被拒絕」 | Grok 支援 core 後失敗；要把 grok 從元組移除（`tools/render.py:743` 的 `validate_grok` 改傳 `core_policy=True`、`render_grok` 要走 `policy_files`） |
| T13 | `tests/test_core_policy.py:293-298` | 只有 Claude 有「binding 涵蓋詞彙與文件」的測試 | 不會失敗；Grok 沒有對應測試，是缺口（新增，不是修改） |
| T14 | `tests/test_install_grok.py:145-150`（用於 `:219、:358`） | `installable()` 的頂層是 `agents`、`roles`、`rules`、`hooks` | 只有選落點 B（skills 進 `INSTALL_TOPS`）才需要改 |
| T15 | `tests/test_install_grok.py:179、223-224` | dry-run 輸出 `[新增] rules/shoal-grok.md`；安裝後 rules 內有 `<!-- shoal-grok v<VERSION> -->` | 外框帶 marker 即通過 |
| T16 | `tests/test_grok_hooks.py:77、98-106` | hook 註冊：`SubagentStop` 三個 matcher、`PreToolUse` 兩個 entry、matcher 字串 | 只有 hooks 變更（第 6 節）才受影響 |
| T17 | `tests/test_shoal_guard.py:105-109、167、856-863、898-903、1069-1110` | Grok 的 `resolve_r1`、預設模式表、`stop_enabled`、adapter | 只有 guard 變更才受影響 |
| T18 | `tests/test_scan_legacy_names.py:109` | 掃描器豁免 fixture 路徑 | 保留 fixture 檔則不受影響 |

統計：

- 切換時**必然失敗**的測試：T1、T2、T5（2 個）、T9（1 個）、T10、T11 的
  `test_replace_lists_and_addenda_are_locked`、T12，共 **8 個**。
- **有條件失敗**：T11 的 omit 鎖（Grok 有 `omit` 時）、T14（選落點 B 時，影響
  `test_install_grok.py` 內使用 `installable()` 的 2 個測試）、T16、T17（hooks 或
  guard 變更時）、T3 與 T8 的版本字串（S8 bump 時，2 處）。
- **不受影響**：T4、T6、T7、T15、T18，以及 `test_sync_global.py` 的 `GrokTests`
  （`:243-275`）、`test_rebrand_migration.py:428-527`、`test_role_rename_migration.py:89-135`
  （它們都以 committed dist 為輸入，只斷言具名檔案存在與 hash 一致，沒有釘住 rules
  內容或檔案清單）。
- 新增缺口：Grok 版的「binding 涵蓋詞彙與文件」測試（T13）、Grok policy 輸出不含
  未代入 placeholder 的測試（Claude 有，`test_core_policy.py` 的 `test_claude_core_preview_
  has_no_leftover_braces`）。

另外 `docs/specs/grok-workflow/TESTS.md` 的 AC-GW-001 至 AC-GW-005 描述的是舊
行為（rules 等於上游），屬歷史紀錄，不是會執行的測試。

## 8. 安裝與實測

**把新 Grok rules 放到機器上的指令：**

1. `python3 tools/render.py --host grok --write`（產生 `hosts/grok/dist/`，
   `--check` 驗證）。
2. commit。installer 只讀 committed HEAD（`git archive hosts/grok/dist` 與
   `hosts/grok/VERSION`，`install_grok.py:95-119`）；工作樹有未 commit 的變更時
   只提示「只安裝 committed 的內容」（`:626-629`）。
3. `python3 tools/install_grok.py`（dry-run，預設）看差異，確認後
   `python3 tools/install_grok.py --apply`；寫入前備份到
   `~/.grok/backups/shoal-<timestamp>/`；`--fix-toggles` 才會動 `config.toml`。
   安裝範圍是 `agents/`、`roles/`、`rules/`、`hooks/` 四個頂層（`:45`）。

**每日同步會刷新什麼：** `tools/sync_global.py`（dotfile 的 SessionStart hook 每日呼叫，
`README.md:130-131`）對 Grok 跑 `install_grok.py` 的 dry-run `--json` 計畫，有差異就
`--apply`（`sync_global.py:352-362`），不帶 `--fix-toggles`、不動 `config.toml`，來源
一律是 committed HEAD。所以**commit 之後，這台機器的 `~/.grok` 會在下一次每日同步
自動換成新 rules**；`~/.grok` 目前存在，且與 dist 相同（上方 `cmp`）。這影響實測前
的 rollout 控制：如果不想在實測前就套用到日常使用，要在 commit 前先決定（例如用
`--grok-home` 指到暫存目錄跑 installer，或先不 commit）。

**實測前必須跑、必須看的東西：**

- `python3 tools/render.py --host grok --check`（exit 0）；
  `cd tests && python3 -m unittest test_render_grok test_grok_hooks test_install_grok
  test_core_policy test_delegation_default`。
- installer dry-run 的輸出：沒有 `config.toml [subagents.toggle] 把 shoal role 設成
  false` 的警告（`install_grok.py:337` 的 `describe`）；安裝後的 `驗證通過` 行。
- `grok inspect`（免費、不開 session）：確認新的 rules 檔被列為 `global` 並看 token
  數（目前 `~/.grok/rules/shoal-grok.md` 約 4003 tokens）。
- 開新的 Grok session（`INSTALL.md:515`：agents、rules、hooks 在 session 啟動時讀取）。
- 帳號：`grok models` 輸出「You are logged in with grok.com」，預設 `grok-4.7`，另有
  `grok-4.7-build-fast`、`grok-4.6`、`grok-4.5`；額度是否足夠不明（U9）。

**headless 旗標（`grok --help`，grok 1.0.46）：** 有非互動模式。

| 旗標 | 用途 |
| --- | --- |
| `-p, --single <PROMPT>` | 單輪 prompt，輸出到 stdout 後結束（另有 `--prompt-file`、`--prompt-json`） |
| `--output-format plain｜json｜streaming-json｜streaming-messages-json` | `streaming-json` 是 NDJSON，可看到每個 tool call 的實際參數（解決 U1、U2、U3 要用這個） |
| `--permission-mode default｜acceptEdits｜auto｜dontAsk｜bypassPermissions｜plan` | 測 Plan Mode 用 `plan` |
| `--max-turns <N>` | 限制回合數（docs 標示 headless only） |
| `-m, --model`、`--effort <LEVEL>`、`--cwd <PATH>`、`-s, --session-id <UUID>` | 指定模型、effort、工作目錄、session id |
| `--tools`、`--disallowed-tools`、`--no-subagents`、`--rules`、`--agents <JSON>`、`--sandbox` | 限制工具、關閉 subagent、追加規則、內嵌 agent 定義、sandbox |
| `--always-approve` | 自動核准所有工具（docs 另稱 `--yolo`，`--help` 只列 `--always-approve`） |

hooks 會在 `grok -p` 下執行（`dispatch-enforcement/TASKS.md:67` 的 live 紀錄）。
這些旗標都需要模型額度，這次沒有執行任何 session。

## 9. 未決事項

本節是本機查不到、或查到互相矛盾的項目。每項寫查過哪裡、缺什麼證據。

| # | 項目 | 查過的地方 | 缺的證據 |
| --- | --- | --- | --- |
| U1 | `spawn_subagent` 背景參數的名稱：legacy 寫 `background`（L17、L172），docs 的參數表寫 `run_in_background` 且預設 `true` | legacy 檔、`16-subagents.md`、`20-background-tasks.md`、hook 設定、E0 | 實際 tool schema 或一次真實呼叫的參數（`grok -p ... --output-format streaming-json`）。影響 `background_option` 的值與 G11／G83 |
| U2 | 派 shell 的工具名稱：`run_terminal_command` 還是 `run_terminal_cmd` | legacy L181、`20-background-tasks.md`、`10-hooks.md`（前者）；`14-headless-mode.md`、`08-skills.md`（後者） | 同 U1 的真實呼叫。影響 `shell_tool`、`read_tools`、第 6 節 shell matcher |
| U3 | `spawn_subagent` 是否有每次覆寫 effort 的參數 | legacy、`16-subagents.md`（只有 persona 的「Explicit spawn-time override」，沒有名稱）、`04-slash-commands.md`（workflow 的 `--effort` 與此無關） | 同 U1。決定 `effort-per-delegation` 是否要省略 |
| U4 | `capability_mode` 與 `model` 是不是 spawn 參數：legacy L159 與 `plan_mode_guard.py:55`（讀 `toolInput.capability_mode`）假設是；docs 寫「Capability mode is not a spawn argument」 | 同上，加 `tests/test_grok_hooks.py` 的 AC-GW-021 | 同 U1。影響 G74 的 addendum 是否有意義，以及 `plan_mode_guard` 的第一順位判斷 |
| U5 | 檔案寫入工具的完整名稱清單 | hook matcher（6 個名稱）、E0 L56-58（實測 3 個）、docs 別名表 | 哪些 matcher 名稱真的存在。影響 `write_tools` |
| U6 | headless 下 `ask_user_question` 是否提供；模型端載入 skill 的方式（工具或僅自動比對） | docs `19-plan-mode.md`、`08-skills.md`、`26-config-reference.md` | 一次 headless 真實執行的工具清單。legacy 與 core 的 fallback 都已涵蓋「不可用」，所以不是 blocker |
| U7 | `$GROK_HOME/rules/` 的子目錄是否被掃描；多個檔案的載入順序是否影響優先序 | `12-project-rules.md`（只說同目錄依字母排序、`extra_rule_dirs` 不掃子目錄） | 落點 A 的檔名排序是否重要 |
| U8 | Grok `Stop` payload 的真實形狀（含 block 後重試的 `stopHookActive`） | `10-hooks.md`、`stop_payload_shapes.json`（沒有 grok） | 一次真實 Grok 執行（需額度） |
| U9 | 目前是否有足夠的額度做 live 測試 | `grok models`（已登入）；`dispatch-enforcement/SPEC.md:274-275`（2026-10-06 時額度用完） | 現在的剩餘額度。`grok usage` 需要 session id，沒有跑 |
| U10 | core 的 take over 字樣：HEAD 版本的 `one-shot-spec`（`orchestration.toml:285-287`）與 `cost-unbounded-continuation`（`extensions.toml:387-388`）寫「take over」／「main-session takeover」，與 `bootstrap-delegate-default` 的 main 不改檔相抵；工作樹的未 commit 修改已改成「report to the user」 | `git diff -- core/policy` | 這個修改是否會 commit。若退回 HEAD 版本，G79 與 N10 要回到「core 仍保留 take over」的樣貌 |
| U11 | 第 1 節 6 列 `行為變更，移除`（L41-42、L90-92、L119-121、L128、L215-216、L219）不在 owner 列出的四個例子內 | `shared-rules/SPEC.md` A3、D1 | owner 確認「一般原則：矛盾時 core 優先」是否涵蓋這六項 |
| U12 | L11「the verifier gate still applies」指 `plan-critic` 的 gate 還是 `verifier` | legacy L11、上游 fixture 同字（沒有被 role 改名改動） | 上游意圖。L46-47「applies to every native Plan Mode session, including user-initiated `/plan`」暗示是 readiness gate |
| U13 | Grok 是否能在同一個 message 平行發出多個 `spawn_subagent`（`bootstrap-delegate-default` 的「launched in the same message」） | docs 沒有明述；`get_command_or_subagent_output` 一次收多個 id（最多 20） | 真實呼叫紀錄 |
| U14 | 落點 B 的 skill 在 Grok 是否會被模型自動載入（description 比對）、在 headless 是否可行 | `08-skills.md` | 實測；repo 內沒有 Grok skill 的載入紀錄 |
| U15 | Grok 常駐檔的大小上限（shared-rules A5）要用什麼數字 | LOCK（無 Grok surface）、測試（無）、docs（no character cap） | owner 決定。現況 16,015 bytes |
| U16 | `enter_plan_mode`／`exit_plan_mode` 在 headless 的行為（`--permission-mode plan` 是否等同；工具是否需要使用者核准） | docs `19-plan-mode.md`（寫 `enter_plan_mode`「requires your approval」） | 一次 headless 執行。影響 G06 至 G08 的 Grok addendum 在無人值守下如何運作 |
