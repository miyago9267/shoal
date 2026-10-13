---
title: agy 舊條款與 core 條款對照（shared-rules S5 前置）
status: draft
created: 2026-10-13
updated: 2026-10-13
---

<!-- markdownlint-disable MD025 -->

# agy 舊條款與 core 條款對照（shared-rules S5 前置）

這份文件逐行列出 agy 現行的 main-session 條款（legacy），對照 `core/policy/` 的條款，是 shared-rules
S5（agy 改由 core 產生條款）的輸入。依據 `docs/specs/shared-rules/SPEC.md` 的 A1-A6、C1、D1-D6
與 Risks；格式沿用 `docs/specs/core-policy/equivalence/claude.md`。這份文件只做列舉與事實查證，不提出新
的條款文字，也不決定「core 沒有對應」的規則的去留。

範圍與方法：

- 查證基準：repo HEAD `5188257`（v3.4.0）。legacy 指 `hosts/agy/src/rules/shoal-agy.md`
  （35 行，下稱 `shoal-agy.md`）與
  `hosts/agy/src/skills/shoal-orchestration/SKILL.md`（124 行，下稱 `SKILL.md`）。兩者與
  `hosts/agy/dist` 內同名檔逐位元組相同（`diff` 無差異）。
- core 指 `core/policy/*.toml`，共 121 條：bootstrap 12、skill 9、orchestration 60、
  extensions 40；其中 15 條 `required`。
- 不在範圍：role 條款（`role_text = "core"`，已由
  `docs/specs/role-contracts/MAPPING-agy.md` 對照）；`hosts/agy/src/agents/*.md` 九
  個檔案（`hosts/agy/binding.toml:7` 讓它們不參與 render，只是 legacy 回退用）。
- 大小與組裝數字來自在 scratchpad 的 repo 副本上跑
  `python3 tools/render.py --host agy --policy-preview`（repo 內沒有改動）。agy 目前的
  binding 沒有 `[policy.placeholders]`，所以副本補了一份只為量測用的值；其中查不到證據的四個值
  （`question_tool`、`background_option`、`effort_param`、`label_param`）是占位字串，§5 會
  給長度敏感度。
- 引用格式：`file:行號範圍`。「agy 1.3.3 執行檔字串」指 `strings ~/.local/bin/agy` 的輸出，不是 repo 內
  容，也不是官方文件，只作為待驗證的線索，一律同時列入 §8。

## 1. 逐節對照

處置只有六種，加上一個「無法歸類」（只有 1 列，原因在 §8 第 1 項）。逐列的 core 條款 id 都是 `core/policy/*.toml`
內實際存在的 id。表格形式的角色清單（`shoal-agy.md:10-18`）逐 role 列出。

### 1.1 規則

**`shoal-agy.md`（常駐，21 列）**

| # | 舊條款位置 | 舊條款說什麼 | 處置 | core 條款 id 與備註 |
|---|---|---|---|---|
| R01 | `shoal-agy.md:5-6` | 本節只適用 agy 主 session；不在 agy 就忽略 | 無法歸類（見 §8） | 不是規則內容而是載入範圍的閘門，見 §8 第 1 項 |
| R02 | `shoal-agy.md:6` | `invoke_subagent` 與下列 role 不可用時，忽略整節（等於 main 自己做） | 行為變更，移除 | `mech-direct-blocker`、`delegate-cost-benefit`；A3：role 派不出去時回報使用者，不由 main 接手 |
| R03 | `shoal-agy.md:7-8` | 自己是這些 role 時忽略本節、自己做任務、不再派工 | core 同義 | `bootstrap-named-roles`、`intro-named-roles`；兩者都是 required |
| R04 | `shoal-agy.md:12` | scout：唯讀偵察，回報 file:line | core 同義 | `bootstrap-delegate-default`、`discovery-gate`、`local-search-direct`；表格形式本身 core 沒有，內容由條款加 role 定義承接 |
| R05 | `shoal-agy.md:13` | plan-critic：核准前挑戰 Plan，回 READY 或 REVISE | core 同義 | `bootstrap-risk`、`review-verdicts`；同上 |
| R06 | `shoal-agy.md:14` | security-reviewer：核准前唯讀的 security 證據 | core 同義 | `bootstrap-security`、`security-reviewer-first`；同上 |
| R07 | `shoal-agy.md:15` | applier：規格完整的機械式實作 | core 同義 | `bootstrap-delegate-default`、`mech-default`；同上 |
| R08 | `shoal-agy.md:16` | executor：需要局部判斷的有界實作 | core 同義 | `bootstrap-delegate-default`、`delegate-cost-benefit`；同上 |
| R09 | `shoal-agy.md:17` | verifier：完成後挑戰，回 CONFIRMED、REFUTED 或 INCONCLUSIVE | core 同義 | `bootstrap-risk`、`review-verdicts`；同上 |
| R10 | `shoal-agy.md:18` | security-executor：核准後的 security 敏感實作 | core 同義 | `bootstrap-security`、`security-executor-after-approval`；同上 |
| R11 | `shoal-agy.md:20-21` | main 保有 framing、Plan、架構、整合與最終判斷 | core 同義 | `bootstrap-ownership`、`main-session-owns` |
| R12 | `shoal-agy.md:21` | 小的、局部的、已穩定的工作直接做 | 行為變更，移除 | `bootstrap-delegate-default`、`direct-when-small`；A3：main 不自己改檔；只有使用者 prompt 含 `#direct` 才例外 |
| R13 | `shoal-agy.md:23-25` | 大型、模糊、架構、風險、跨面向、plan-first 任務前載入 skill 並遵守 | core 同義 | `bootstrap-load-skill`；觸發詞比 core 多（ambiguous、plan-first）；core 多一句「skill 不可用就守不變式、不宣稱完整驗證」 |
| R14 | `shoal-agy.md:25-26` | 「只對這些任務」：下列四道關卡只適用大任務，不適用小的局部修改 | 行為變更，移除 | `bootstrap-risk`、`bootstrap-delegate-default`；core 以 risk trigger 決定關卡（Risk precedes size），小修改也要派 write role；不在 A3 列舉，需確認 |
| R15 | `shoal-agy.md:28-29` | 沒有明確核准就不得寫 source；Plan 要先獲 fresh plan-critic 的 READY | core 同義 | `approval-gate`、`risk-review-mandatory`；「要求每個大任務都經 plan-critic READY」的範圍見 R16 |
| R16 | `shoal-agy.md:28-29` | plan-critic READY 適用所有大型、模糊、架構、跨面向、plan-first 任務 | 行為變更，移除 | `plan-gate`、`risk-triggers`、`risk-review-mandatory`；core 只對 risk-triggered 的 unit 要 plan-critic 與完成後 verifier（鬆於 agy 舊文字）；不在 A3 列舉，需確認 |
| R17 | `shoal-agy.md:29-30` | 自動核准的工具權限不算 Plan 核准 | core 沒有對應 | §2 第 1 項（SKILL.md:38-39 重複同一規則） |
| R18 | `shoal-agy.md:31` | 以 role 名稱派工；tier 與 tools 來自 role 定義 | core 同義 | `model-routing` |
| R19 | `shoal-agy.md:32` | 子 agent 不再派工 | core 同義 | `bootstrap-named-roles`、`intro-named-roles` |
| R20 | `shoal-agy.md:32` | plan-critic 與 verifier 不可互換 | core 同義 | `review-verdicts` |
| R21 | `shoal-agy.md:33-34` | 整合後由 fresh verifier 核對確切的 claim，才能報「完成」 | core 同義 | `verification-gate`、`risk-review-mandatory`、`bootstrap-verify-report`；範圍同 R16；core 另加「寫明本回合做了哪些驗證與沒做的檢查」（B1） |

**`SKILL.md`（按需，52 列）**

| # | 舊條款位置 | 舊條款說什麼 | 處置 | core 條款 id 與備註 |
|---|---|---|---|---|
| S01 | `SKILL.md:8-10` | 七個 role 忽略本 skill，自己做、不再派工（舊清單不含 watcher、researcher） | core 同義 | `intro-named-roles`、`bootstrap-named-roles`；兩者都是 required；清單由 `named_roles` 代入 |
| S02 | `SKILL.md:16` | Discovery：穩定問題、範圍、證據格式、停止條件，唯讀，scout 分頭 | core 同義 | `discovery-gate`、`local-search-direct` |
| S03 | `SKILL.md:17` | Plan：main 寫一份 Plan（outcome、non-goals、scope、envelope、slices） | core 同義 | `plan-gate`、`envelope-then-slice`；core 的 slice 另要求 owners、rollback、budget、stops；plan-critic 範圍見 R16 |
| S04 | `SKILL.md:18` | Approval：每個必要 unit READY 後呈現 Plan，等 Miyago 明確核准 | core 同義 | `approval-gate`、`envelope-then-slice` |
| S05 | `SKILL.md:19` | Execution：已核准的契約帶 scope、獨占檔案、限制、done criteria | core 同義 | `execution-gate` |
| S06 | `SKILL.md:20` | Verification：整合後的結果帶確切 claim，交 fresh verifier | core 同義 | `verification-gate`；範圍同 R16 |
| S07 | `SKILL.md:22` | Miyago 切到 `/plan` 模式就留在其中直到核准 | agy 調校，移到按需文件的 addendum | `approval-gate`；agy 的 `/plan` 與 `agy --mode plan` 是 host 特有 |
| S08 | `SKILL.md:22-24` | 沒切 `/plan` 就當作有切：discovery 唯讀、核准前只寫 Plan 本身（回覆或 Plan artifact） | core 同義 | `approval-gate`、`explore-then-plan-boundary`；「Plan artifact」是 agy 用語；main 寫 artifact 與「main 不改檔」的關係見 §8 第 6 項 |
| S09 | `SKILL.md:28-30` | 給 plan-critic 的 brief 用 `## Target readiness unit` 區塊（ID、Kind）、完整 Plan、證據路徑 | agy 調校，移到按需文件的 addendum | `plan-gate`；對應 plan-critic 的 agy addendum `brief-unit-kinds`（hosts/agy/addenda/plan-critic.toml:18-23） |
| S10 | `SKILL.md:31-33` | READY 是單字；REVISE 帶 Blocker、Evidence、Minimum revision、Acceptance check；其他是 protocol failure，重派 | core 同義 | `review-verdicts`；REVISE 欄位格式已在 agy 的 plan-critic addendum `revise-shape`；「重派」在 core 受 `review-circuit-breaker` 限制為一次有界重試 |
| S11 | `SKILL.md:34-35` | REVISE 後實質修訂再交 fresh plan-critic；同一 unit 兩次自動 REVISE 後暫停並問 Miyago | 行為變更，移除 | `readiness-loop`；core 先由 main 對每個 blocker 判 FIX、DEFER、REJECT，只有未解的 P0/P1、產品或權限選擇才問使用者；不在 A3 列舉，需確認 |
| S12 | `SKILL.md:36-37` | 大型工作：先審 envelope 再只審下一個可執行 slice；後面的 slice 保持穩定 ID | core 同義 | `envelope-then-slice`、`plan-gate` |
| S13 | `SKILL.md:38-39` | 後續回合的明確核准前不得寫 source；籠統要求或「just start」不算核准 | core 同義 | `approval-gate`、`risk-review-mandatory` |
| S14 | `SKILL.md:39` | 自動核准的權限不能豁免核准 | core 沒有對應 | 同 R17（§2 第 1 項） |
| S15 | `SKILL.md:43-44` | security 保持基本與比例，目標是避免 tunnel vision，不縮減執行能力 | core 沒有對應 | §2 第 2 項；agy 的 security 三個 role 已有同義 addenda（role 層，非 policy 層） |
| S16 | `SKILL.md:46-49` | 碰 authn/authz、secrets、crypto、trust boundary 驗證、依賴弱點的工作：在第一次 plan-critic 前跑 security-reviewer，把發現帶進 Plan | core 同義 | `security-reviewer-first`、`security-sensitive-routing`；兩者都是 required |
| S17 | `SKILL.md:49` | 要告訴 plan-critic 已經跑過 security-reviewer | core 沒有對應 | §2 第 3 項 |
| S18 | `SKILL.md:50-51` | 派 security-reviewer 時要它看相鄰入口與副作用，不只看點名的邊界 | core 沒有對應 | §2 第 4 項 |
| S19 | `SKILL.md:52` | 已核准的 security 敏感 slice 交給 security-executor | core 同義 | `security-executor-after-approval`；required |
| S20 | `SKILL.md:52-53` | security-executor 失敗兩次就重切範圍或問 Miyago，不要悄悄接手 | core 沒有對應 | §2 第 5 項；core 的 `one-shot-spec` 反而寫「or take over」（見 §8 第 7 項） |
| S21 | `SKILL.md:54-55` | 只是靠近 security 面的一般工作不走這條路，用 executor，讓 verifier 探明顯的濫用情境 | core 沒有對應 | §2 第 6 項 |
| S22 | `SKILL.md:59-61` | 每次 `invoke_subagent` 前說明階段並套用 brake：證據在變、擁有權重疊、沒有整合者、協調成本高就不 fan out | core 同義 | `dispatch-brake`；`dispatch_tool` 代入 `invoke_subagent` |
| S23 | `SKILL.md:63-64` | 最小形狀：小的或緊密耦合的任務直接做 | 行為變更，移除 | `bootstrap-delegate-default`、`direct-when-small`；A3：main 不自己改檔 |
| S24 | `SKILL.md:64-65` | 有界的旁支任務一個 worker；只有獨立、低重疊的串流才平行 | core 同義 | `brake-per-call`、`parallel-launch` |
| S25 | `SKILL.md:67` | 不知道的檔案或符號、或廣泛的跨檔探索 → scout | 行為變更，移除 | `local-search-direct`、`bootstrap-delegate-default`；core 只把兩個以上獨立面向的偵察派給 scout，單一耦合的線索留在 main；不在 A3 列舉，需確認 |
| S26 | `SKILL.md:68` | 規格完整的多檔機械工作 → applier | core 同義 | `mech-default`、`bootstrap-delegate-default` |
| S27 | `SKILL.md:69` | 有界、非 security、需要判斷的實作 → executor | core 同義 | `delegate-cost-benefit`、`execution-gate` |
| S28 | `SKILL.md:71-72` | 單一未知 bug 的 root-cause discovery 留在 main | core 同義 | `single-bug-direct` |
| S29 | `SKILL.md:71-72` | 同一條推理鏈上的「第一個最小修正」也留在 main | 行為變更，移除 | `single-bug-direct`、`bootstrap-delegate-default`；A3：root cause 與補救確定後，修正是 Execution 工作並派工 |
| S30 | `SKILL.md:74-75` | 每個 worker 的 brief 只寫一次，含 goal、constraints、done criteria、relevant paths、rationale | core 同義 | `one-shot-spec` |
| S31 | `SKILL.md:75` | brief 另含 output format 與 verification expectation | core 沒有對應 | §2 第 7 項 |
| S32 | `SKILL.md:75-76` | 只用 role 名稱派工；tier 與 tools 來自定義 | core 同義 | `model-routing`；`Model` 欄位的實際行為未驗證，見 §8 第 4 項 |
| S33 | `SKILL.md:76-78` | 從最便宜的合格 role 開始；失敗兩次就改任務邊界或升一級 role | core 同義 | `one-shot-spec`；core 寫「escalate tier or take over」，沒有「改任務邊界」 |
| S34 | `SKILL.md:78` | 單一 scout 事實若承載決定就要做 sanity check | core 同義 | `scout-inputs` |
| S35 | `SKILL.md:82` | `invoke_subagent` 一次接受多個 entry 並行 | agy 調校，移到按需文件的 addendum | `parallel-launch`；core 的 `parallel-launch` 以 `background_option` 為前提；agy 的並行方式不同 |
| S36 | `SKILL.md:82-84` | 寫入的 worker 要獨占檔案，或用 workspace mode `branch` / `share` 隔離；唯讀 worker 用 `inherit` | agy 調校，移到按需文件的 addendum | `parallel-writers`；core 的 `parallel-writers` 寫 worktree 並要求 Git；agy 的選項與是否需要 Git 見 §3 |
| S37 | `SKILL.md:85-87` | 回收每個 worker 結果後才做相依工作或最終回覆；整合隔離的 workspace，沒回收的 branch 等於丟失 | core 同義 | `parallel-launch`、`parallel-writers` |
| S38 | `SKILL.md:88` | 長時間指令歸 main | 行為變更，移除 | `bootstrap-delegate-default`、`watcher-long-commands`；A3：長指令交給 `watcher`，main 不自己開背景 shell |
| S39 | `SKILL.md:88-89` | leaf 回報確切指令、工作目錄、環境、輸入與完成條件 | core 同義 | `leaf-cannot-finish`；core 另寫 main 以 `watcher` 接手再 resume role |
| S40 | `SKILL.md:93-95` | 不可互換 plan-critic 與 verifier；兩者都不寫 Plan 或修正發現 | core 同義 | `review-verdicts`、`verdict-authority` |
| S41 | `SKILL.md:97-99` | 最終判斷在 main；逐項重新檢查可重現性、是否本次引入、相關性、優先級、信心 | core 同義 | `verdict-authority` |
| S42 | `SKILL.md:101` | P0 凍結 slice 並暫停問 Miyago | core 同義 | `verdict-authority`、`ask-questions-main` |
| S43 | `SKILL.md:102-103` | P1 與本次引入的 P2 regression：在核准範圍內修正或暫停 | core 同義 | `verdict-authority` |
| S44 | `SKILL.md:104-105` | 其他 P2：有界且在範圍內才修，否則附理由延後並縮小 claim | core 同義 | `verdict-authority` |
| S45 | `SKILL.md:106` | P3/P4：回報，不開專門修正迴圈 | core 同義 | `verdict-authority` |
| S46 | `SKILL.md:107-108` | INCONCLUSIVE：證據、環境或契約實質改變後才重試一次 | core 同義 | `recheck-and-invalidate` |
| S47 | `SKILL.md:110-112` | P1/P2 recovery 合計最多五輪、每輪要有實質改變、不重驗相同候選；之後標 `PAUSED_VERIFICATION` | core 同義 | `recovery-budget`、`identity-fingerprint` |
| S48 | `SKILL.md:116` | 長時間無人看守的工作前「宣告」`AUTO` 或 `ASK` | 行為變更，移除 | `auto-ask-selection`；core 是「提供選項並等待」，使用者給 `/goal` 或直接命令才視為選 AUTO；不在 A3 列舉，需確認 |
| S49 | `SKILL.md:116-118` | `AUTO` 只含核准範圍內可逆的工作，不授予 commit、push、release、credential、destructive、external-mutation、擴大範圍 | core 同義 | `auto-limits`；required |
| S50 | `SKILL.md:118-120` | `ASK` 或需要 Miyago 決定時，以 `PAUSED_NEEDS_USER`、一個問題、選項、建議結束回合 | core 同義 | `ask-mode`、`checkpoint-unavailable`；core 在問答工具可用時走工具；agy 的問答工具未定，見 §3 |
| S51 | `SKILL.md:120-121` | 只有 main 發問 | core 同義 | `ask-questions-main` |
| S52 | `SKILL.md:123-124` | 最終報告分開 confirmed、fixed、deferred、paused、unrun、縮小的 claim、未做的外部動作 | core 同義 | `final-report` |

### 1.2 處置統計

| 處置 | 列數 | 列編號 |
|---|---|---|
| core 同義 | 50 | R03、R04、R05、R06、R07、R08、R09、R10、R11、R13、R15、R18、R19、R20、R21、S01、S02、S03、S04、S05、S06、S08、S10、S12、S13、S16、S19、S22、S24、S26、S27、S28、S30、S32、S33、S34、S37、S39、S40、S41、S42、S43、S44、S45、S46、S47、S49、S50、S51、S52 |
| agy 調校，移到按需文件的 addendum | 4 | S07、S09、S35、S36 |
| 常駐改為按需 | 0 | 無 |
| 行為變更，移除 | 10 | R02、R12、R14、R16、S11、S23、S25、S29、S38、S48 |
| 做不到，省略 | 0 | 無 |
| core 沒有對應 | 8 | R17、S14、S15、S17、S18、S20、S21、S31 |
| 無法歸類（見 §8） | 1 | R01 |
| 合計 | 73 | 規則 21 + SKILL 52 |

「常駐改為按需」與「做不到，省略」都是 0 列：agy 舊文字沒有任何一條是因為搬到按需文件或 agy 做不到而處理的。常駐的四道關卡
（`shoal-agy.md:28-34`）在 core 裡仍是常駐的 bootstrap 條款。

### 1.3 行為變更明細

`行為變更，移除` 共 10 列。其中 A3 明列的預期變更是 R02、R12、S23、S29、S38 五列（main 不自己改檔、role 派不出去不由
main 接手、長指令交給 `watcher`）。其餘五列（R14、R16、S11、S25、S48）不在 A3 的列舉內，是切換到 core 條款後才出現的
差異，需要 Miyago 確認它們也算預期變更（A6 要求每一項都列出並標明）。

| # | 舊行為 | core 行為 | 方向 | 是否在 A3 列舉 |
|---|---|---|---|---|
| R02 | `invoke_subagent` 或 role 不可用時忽略整節 | 派不出去就回報使用者（`mech-direct-blocker`、`delegate-cost-benefit`） | 收緊 | 是 |
| R12、S23 | 小的、已穩定的工作 main 直接做 | main 不自己改檔，只有 `#direct` 例外（`direct-when-small`） | 收緊 | 是 |
| S29 | 單一 bug 的第一個最小修正留在 main | root cause 與補救確定後，修正派工（`single-bug-direct`） | 收緊 | 是 |
| S38 | 長時間指令歸 main | 交給 `watcher`，main 不自己開背景 shell（`watcher-long-commands`） | 收緊 | 是 |
| R14 | 關卡只適用大任務，小修改不適用 | 以 risk trigger 決定關卡，與大小無關（`bootstrap-risk`） | 兩面 | 否 |
| R16 | 每個大型、模糊、架構、跨面向、plan-first 任務都要 plan-critic READY 與完成後 verifier | 只有 risk-triggered 的 unit 才強制（`plan-gate`、`risk-triggers`、`risk-review-mandatory`） | 放寬 | 否 |
| S11 | 同一 unit 兩次 REVISE 後一律暫停問 Miyago | main 先判 FIX/DEFER/REJECT 並做一次 closing review，只有未解 P0/P1、產品或權限選擇才問（`readiness-loop`） | 放寬 | 否 |
| S25 | 未知檔案或符號、廣泛探索一律 scout | 兩個以上獨立面向才派 scout，單一耦合線索留在 main（`local-search-direct`） | 放寬 | 否 |
| S48 | 長時間工作前「宣告」AUTO 或 ASK | 提供選項並等待；`/goal` 或直接命令視為選 AUTO（`auto-ask-selection`） | 兩面 | 否 |

### 1.4 外框與標記（不是規則，不計入上表）

| # | 舊位置 | 內容 | core 側 |
|---|---|---|---|
| F01 | `shoal-agy.md:1` | 版本標記 `<!-- shoal-agy v3.4.0 -->`；現在由 `_versioned_rules` 依 `hosts/agy/VERSION` 改寫 | 外框（`policy-frames/bootstrap.md`）；Claude 的外框是字面版本，由 test_render_claude.py:67-73 對照 VERSION |
| F02 | `shoal-agy.md:2、shoal-agy.md:35` | `<!-- shoal-agy:begin -->`、`<!-- shoal-agy:end -->` 區段標記；repo 內沒有任何程式讀它們（grok、codex 的 installer 才讀自己的） | 外框；去留未決，見 §8 |
| F03 | `shoal-agy.md:3` | 標題 `## Shoal orchestration (agy only)` | 外框 |
| F04 | `SKILL.md:1-4` | frontmatter：`name`、`description`（觸發詞含 ambiguous、plan-first） | 外框（`policy-frames/skill.md`） |
| F05 | `SKILL.md:6` | 標題 `# Shoal orchestration (agy)` | 外框 |
| F06 | `SKILL.md:12、SKILL.md:26、SKILL.md:41、SKILL.md:57、SKILL.md:80、SKILL.md:91、SKILL.md:114` | 七個章節標題：Lifecycle、Plan gate、Security、Dispatch、Parallelism and long work、Verification adjudication、Long autonomous runs | 標題；core 的標題條款是 Routing and lifecycle、Dispatch and ownership、Recovery and authority、Parallel and runtime mechanics，另有 First move、References |

### 1.5 core 有、agy 舊文字沒有的條款

121 條 core 條款中，上面 73 列有引用 48 條；其餘 73 條對 agy 是新增的行為（含 `required` 者）。標題條款不計行為，列在
最後一列。這些切換後會第一次出現在 agy 的文字裡，不是「等價」切換的一部分，對照表需要讓 Miyago 知道。

| 群組 | 條款 id | 對 agy 新增什麼 | 含 required |
|---|---|---|---|
| interaction shape 與 routing | `bootstrap-routing`、`interaction-shape`、`bootstrap-outcome` | 三種 shape（`co_discover`、`explore_then_plan`、`execute`）與 outcome 連續執行；舊文字沒有（core-policy/SPEC.md:35-36 同樣記載） | 否 |
| Baton 組合 | `baton-dispatch` | 遇到大型任務且有 `baton-dispatch` skill 時先載入；agy 沒有該 skill，條款自帶「不存在就照本 policy」 | 否 |
| resident 派工與回收 | `bootstrap-collect`、`bootstrap-questions`、`collect-results`、`followup-by-mode`、`liveness`、`subagent-final-message` | 背景 role 回報後先回收一行、AUTO/ASK 的後續派工、活性判斷、subagent 最終訊息直接讀；多數以「background role」為前提（§3） | 否 |
| 派工細節 | `bootstrap-dispatch-brake`、`dispatch-kind-label`、`effort-per-delegation`、`plan-critic-gaps`、`research-fanout`、`discovery-scope-exclusive`、`collect-discovery`、`mech-collect`、`large-investigation` | 每次派工帶 effort 與標籤前綴（agy 做不到或未知，§3）、`mode: gaps`、兩個 `researcher`、discovery 範圍獨占與回收 | 否 |
| 驗證 | `outcome-verification` | 完成後 verifier 在最小可反駁的整合邊界跑一次；舊文字只有「整合後 fresh verifier」 | 否 |
| security 順序 | `security-no-preapproval-write` | 不同時跑兩個核准前審查、核准前不把工作交給可寫的 security executor | 是 |
| extensions 全部 | `ext-extend-policy` 等 31 條（見 `core/policy/extensions.toml`） | outcome continuation、review intent、discovery budget、decision checkpoint、task ledger、跨使用輸入的連續性、review-service circuit breaker、direction checkpoint、cost-unbounded continuation；agy 舊文字完全沒有 extensions 文件 | `ext-no-authority`、`material-gates-first`、`explicit-approval-only` |
| skill 導引 | `skill-intro`、`skill-bootstrap-authority`、`first-move-steps`、`references-intro`、`reference-policy`、`reference-extensions`、`reference-fail-soft` | First move 與 References 兩節；agy 舊 SKILL 是單檔，沒有 references | 否 |
| 標題條款 | `continuation-heading`、`review-intent-heading`、`discovery-budget-heading`、`checkpoint-heading`、`ledger-heading`、`input-heading`、`breaker-heading`、`direction-heading`、`routing-heading`、`dispatch-heading`、`recovery-heading`、`parallel-heading`、`first-move-heading`、`references-heading` | 只有標題 | 否 |

`required` 條款中舊文字完全沒有對應的是 `ext-no-authority`、`material-gates-first`、
`explicit-approval-only`、`security-no-preapproval-write`；其餘 required 都有第 1.1 節
的對應列。

## 2. core 沒有對應的規則

以下是只存在於 agy 文字、而且內容不含 agy 專屬的工具、參數或 model 綁定的規則。每項只列事實，不決定去留。第 2、4 項在 role 層已有
同義的 agy addendum（`hosts/agy/addenda/security-reviewer.toml:10-15`、
`security-executor.toml:3-8`、`plan-critic.toml:25-30`），policy 層沒有。

| # | 對應列 | 完整原句 | 為什麼看起來通用 | 丟掉會失去什麼 |
|---|---|---|---|---|
| 1 | R17、S14 | `shoal-agy.md:29-30`："Auto-approved tool permissions are not Plan approval."；`SKILL.md:38-39`："A broad request, "just start", or auto-approved permissions do not waive this." | 任何有「自動核准工具權限」功能的 host 都會遇到（agy 的 `--dangerously-skip-permissions`，見 `agy --help`）；core 的 `approval-gate` 只寫「Broad initial request is not approval of unseen Plan」。 | 丟掉後，模型可能把權限被自動核准當成 Plan 已核准；`approval-gate` 與 `risk-review-mandatory`（required）只擋「沒有明確核准」，沒有說自動核准算不算。 |
| 2 | S15 | `SKILL.md:43-44`："Keep security basic and proportionate; the goal is to avoid tunnel vision, not to shrink execution capability." | 沒有任何 agy 專屬名詞，是 security 路徑的總原則；與 Miyago 的「不要隧道視野」目標一致。 | 丟掉後，security 路徑只剩 core 的分流規則（`security-sensitive-routing` 等），沒有「比例」的約束；role 層的 addenda 仍在，但 main 的 brief 與判斷不受約束。 |
| 3 | S17 | `SKILL.md:49`："Tell `plan-critic` you did so."（指已先跑過 `security-reviewer` 並把發現帶進 Plan） | 任何 host 的 main 都會有這個動作；core 的 plan-critic contract 只要求 Plan 內有 findings（`security-prerequisite`），沒有要求 main 說明。 | 丟掉後 plan-critic 只能從 Plan 內容推斷 security review 是否已做。 |
| 4 | S18 | `SKILL.md:50-51`："Brief `security-reviewer` to look at adjacent entry points and side effects, not only the named boundary." | 是 brief 內容的規則，沒有 host 專屬名詞。 | 丟掉後 main 的 brief 可能只點名單一邊界；security-reviewer 的 role addendum 仍會自行擴大範圍，但 main 端不再被要求。 |
| 5 | S20 | `SKILL.md:52-53`："If it fails twice, re-scope or ask Miyago; do not quietly take the slice over." | security slice 失敗的處理，沒有 agy 專屬名詞。core 的 `one-shot-spec` 對所有 role 寫「after two failures, escalate tier or take over」，與此相反。 | 丟掉後 security slice 失敗兩次的處理退回 `one-shot-spec`，而 `one-shot-spec` 允許 take over（也與 `bootstrap-delegate-default` 的 main 不改檔互相矛盾，見 §8 第 7 項）。 |
| 6 | S21 | `SKILL.md:54-55`："Ordinary work that merely sits near a security surface does not need this track; use `executor` and have `verifier` probe the obvious abuse case." | 是 security 路徑的邊界與驗證要求，沒有 host 專屬名詞。 | 丟掉後，靠近 security 面但不屬於它的工作沒有明確出口，也沒有「verifier 探濫用情境」的要求；`security-sensitive-routing`（required）只定義哪些工作屬於 security。 |
| 7 | S31 | `SKILL.md:74-76` 中 "…rationale, output format, and verification expectation." 的後兩項（前面的 goal、constraints、done criteria、relevant paths、rationale 對應 `one-shot-spec`） | brief 內容清單，沒有 host 專屬名詞。 | 丟掉後 brief 不再被要求寫輸出格式與驗證期待；`one-shot-spec` 的清單少這兩項。 |

## 3. core 條款在 agy 上的可行性

證據欄只引用 repo 內的路徑；來源是 agy 執行檔字串的，明確標示並列入 §8，不當成事實。「可行」表示有 repo 內的證據；「未定」表示 repo
內沒有證據；「做不到」表示有證據顯示 agy 沒有這個能力。

### 3.1 placeholder

| placeholder | agy 的值 | 證據 | 判定 | 使用它的條款 |
|---|---|---|---|---|
| `dispatch_tool` | `invoke_subagent` | `shoal-agy.md:6`；`SKILL.md:59,82`；`hooks/shoal_guard.py:174`；`docs/specs/dispatch-enforcement/E0-RESULTS.md:16` | 可行 | `bootstrap-dispatch-brake`、`dispatch-brake`、`risk-review-mandatory`、`effort-per-delegation`、`dispatch-kind-label`、`watcher-long-commands`、`first-move-steps` |
| `question_tool` | repo 內沒有工具名稱；舊文字用散文「ask Miyago」與 `PAUSED_NEEDS_USER`（`SKILL.md:35,53,119-121`） | 線索：agy 1.3.3 執行檔字串有 `ask_question`（阻塞式多選 modal），未驗證 | 未定（§8 第 2 項） | `bootstrap-questions`、`checkpoint-default`、`checkpoint-unavailable`、`ask-mode`、`reference-extensions`；`ask-mode` 與 `checkpoint-unavailable` 自帶「工具不可用就以 `PAUSED_NEEDS_USER` 結束」，`bootstrap-questions` 沒有 |
| `named_roles` | `scout`、`plan-critic`、`security-reviewer`、`applier`、`executor`、`verifier`、`security-executor`、`watcher`、`researcher` | `hosts/agy/binding.toml:39-103` 九個 `[roles.*]`；`README.md:33` | 可行 | `bootstrap-named-roles`、`intro-named-roles`（皆 required）；舊清單只有前 7 個 |
| `shell_tool` | `run_command` | `hosts/agy/binding.toml:33`；`docs/specs/role-contracts/MAPPING-agy.md:204`；`hosts/agy/addenda/applier.toml:1` | 可行 | `explore-then-plan-boundary`、`review-verdicts` |
| `write_tools` | `write_to_file`、`multi_replace_file_content`（`replace_file_content` 以子字串比對） | `hooks/shoal_guard.py:1668`；`tests/test_shoal_guard.py:1173-1175`；`E0-RESULTS.md:16`；`binding.toml:30` 的 write 等級沒有 allowlist，完整清單 repo 內沒有 | 部分可行（完整清單未定，§8 第 8 項） | `explore-then-plan-boundary` |
| `read_tools` | `view_file/grep_search/find_by_name/list_dir/run_command` | `hosts/agy/binding.toml:28,33` | 可行 | `discovery-scope-exclusive` |
| `background_option` | repo 內沒有 | 舊文字只有「一次接受多個 entry 並行」（`SKILL.md:82`）；`invoke_subagent` 是否立即回傳、結果如何回報，repo 內沒有記載 | 未定（§8 第 3 項） | `bootstrap-delegate-default`、`parallel-launch`、`watcher-long-commands`、`leaf-cannot-finish`；另有 `bootstrap-collect`、`collect-results`、`followup-by-mode` 以「背景 role 回報」為前提但不含 placeholder |
| `worktree_option` | workspace mode：`branch`、`share`（隔離）、`inherit`（共用） | `SKILL.md:82-84`；參數名 `Workspace` 與兩種模式的語意只在 agy 1.3.3 執行檔字串，未驗證 | 部分可行（取哪一個、是否需要 Git 未定，§8 第 5 項） | `parallel-writers` |
| `model_param` | `Model` | `E0-RESULTS.md:29-31`；`tests/test_shoal_guard.py:1163`（樣本 `"Model": "inherit"`） | 名稱可行；「省略」的行為未驗證（§8 第 4 項） | `bootstrap-dispatch-brake`、`model-routing` |
| `effort_param` | 做不到 | `hosts/agy/binding.toml:11` `supports_effort = false`；`tools/render.py:698-699,717-722` agent frontmatter 沒有 effort；`E0-RESULTS.md:29-31` 記錄的 `invoke_subagent` entry 只有 `Model`、`Prompt`、`Role`、`TypeName`；`agy --help` 的 `--effort` 是整個 session 的設定，不是逐次派工 | 做不到 | `bootstrap-dispatch-brake`、`effort-per-delegation` |
| `label_param` | repo 內沒有 | 已記錄的 entry 欄位（`Model`、`Prompt`、`Role`、`TypeName`）沒有描述或標籤欄位 | 未定（§8 第 3 項） | `bootstrap-dispatch-brake`、`dispatch-kind-label` |
| `goal_command` | repo 內沒有 | agy 有 slash command 與 `/plan`（`SKILL.md:22`；`agy --help` 的 `--disable-slash-commands`、`--mode plan`），沒有 `/goal` 的記載 | 未定（§8 第 3 項） | `auto-ask-selection` |
| `skill_term` | `skill` | `shoal-agy.md:24`；`SKILL.md:3` | 可行 | `bootstrap-load-skill`、`skill-intro`、`skill-bootstrap-authority` |
| `policy_doc`、`extensions_doc`、`references_dir` | 版面決定，不是 agy 能力 | §4 的檔案位置；技術上可行：skill 目錄是整個目錄的 symlink，子目錄會跟著出現（`ls -l ~/.gemini/config/skills/shoal-orchestration`；`tools/sync_global.py:367-384` 只檢查 `dist/skills/` 與 `dist/agents/` 的第一層項目） | 可行 | `ext-extend-policy`、`reference-policy`、`reference-extensions` |

renderer 的限制：`tools/render.py:347-358` 的 `require_policy_complete` 要求詞彙內每個 key
都有非空值（`tools/contracts.py:314-325`），即使用到它的條款全被 omit 也一樣。所以 agy 的
`effort_param` 即使兩條相關條款都省略，binding 仍要寫一個非空值。

### 3.2 不經 placeholder 的能力假設

| 假設 | 判定 | 證據 |
|---|---|---|
| 同一則訊息並行派多個 role（`bootstrap-delegate-default`、`research-fanout`） | 可行 | `invoke_subagent` 一次接受多個 entry（`SKILL.md:82`；`hooks/shoal_guard.py:1640-1653` 解析 `Subagents` 陣列） |
| `watcher`、`researcher` 兩個 role 存在 | 可行 | `hosts/agy/binding.toml:89-103`；`hosts/agy/dist/agents/watcher/agent.md`、`researcher/agent.md`；`~/.gemini/config/agents/` 已有兩個 symlink |
| `#direct` 出現在使用者 prompt 才允許 main 改檔 | 可行但不被強制 | `#direct` 是模型讀 prompt 的約定。agy 的 guard 固定 shadow（`hooks/shoal_guard.py:80-87`；`E0-RESULTS.md:26-27`：agy 無法分辨 main 與 subagent），所以 main 不改檔在 agy 只靠文字，沒有 hook 擋 |
| leaf「never spawn subagents」（required 的 `bootstrap-named-roles`、`intro-named-roles`） | 唯讀與 verify 等級由 tools allowlist 保證，write 等級只靠文字 | `hosts/agy/binding.toml:27-33` 的 allowlist 不含 `invoke_subagent`；`binding.toml:30` 的 write 等級沒有 allowlist（`executor`、`applier`、`security-executor`） |
| `plan-critic` 的 `mode: gaps`（`plan-critic-gaps`） | 可行 | `tests/test_delegation_default.py:232-245` 斷言 agy 的 plan-critic 帶 gap mode |
| main 以 `AskUserQuestion` 類的結構化問題提問 | 未定 | 見 3.1 `question_tool` |
| Stop gate（B3） | 不適用 | `docs/specs/shared-rules/SPEC.md` B4：agy 在有結束事件前不啟用；`hooks/shoal_guard.py:91-94` `STOP_HOSTS` 只有 claude、codex |
| task／todo 工具（`ledger-split` 的「when available」） | 有條件 | 條款自帶「when available」；agy 有無此工具 repo 內沒有記載 |

### 3.3 必須省略的條款與 required 檢查

| 條款 | required | 省略原因 | 狀態 |
|---|---|---|---|
| `effort-per-delegation` | 否 | agy 的 binding `supports_effort = false`，逐次派工不能帶 effort（`hosts/agy/binding.toml:11`） | 確定省略 |
| `bootstrap-dispatch-brake` | 否 | 同一條款同時含 effort、`Model` 省略、標籤前綴、「state scope and stop」（`core/policy/bootstrap.toml:76-87`）。條款不可分割：省略 effort 就得整條省略，連同其他三項在常駐文字中一起消失；除非以 addendum `replace:` 取代，而取代文字是新措辭 | 確定要處理，方式未決（§8 第 9 項） |
| `dispatch-kind-label` | 否 | agy 已記錄的 entry 沒有標籤欄位 | 未定（§8 第 3 項） |
| `bootstrap-delegate-default`、`parallel-launch`、`watcher-long-commands`、`leaf-cannot-finish`、`bootstrap-collect`、`collect-results`、`followup-by-mode` | 否 | 以 `background_option`／背景 role 為前提；agy 的 `invoke_subagent` 是否有對應行為未知 | 未定（§8 第 3 項）。`bootstrap-delegate-default` 承載 A3 的核心（main 不改檔、`watcher`、兩個 `researcher`），省略它會直接違反 A3 |
| `auto-ask-selection` | 否 | `goal_command` 未定 | 未定 |
| `bootstrap-questions`、`checkpoint-default`、`ask-mode`、`checkpoint-unavailable` | 否 | `question_tool` 未定；後三者自帶工具不可用的退路 | 未定 |

結論：目前查得到的、必須省略的只有 `effort-per-delegation` 與（整條處理的）`bootstrap-dispatch-brake`，兩
者都不是 `required`。15 條 `required` 之中，用到 placeholder 的只有三條
（`bootstrap-named-roles` 與 `intro-named-roles` 用 `named_roles`、
`risk-review-mandatory` 用 `dispatch_tool`），三個值都有證據，所以沒有發現「required 條款在 agy 上無法
render」的阻塞。未定項（§8）若最後變成「做不到」，涉及的條款也都不是 `required`。

## 4. 文件對應

| core 文件 | agy 的落點 | 常駐／按需 | agy 現況 |
|---|---|---|---|
| bootstrap（12 條） | `hosts/agy/dist/rules/shoal-agy.md` | 常駐。dotfile 的 `setup_gemini.sh` 把它 `cat` 進組合出的 `~/dotfile/config/ai/generated/gemini/GEMINI.md`（`~/.gemini/GEMINI.md` 是它的 symlink） | 35 行、1,648 位元組，來源 `hosts/agy/src/rules/shoal-agy.md` 逐字（只改 marker） |
| skill（9 條） | `hosts/agy/dist/skills/shoal-orchestration/SKILL.md` | 按需（agy 載入 skill） | 124 行、6,434 位元組，單一檔案，來源 `hosts/agy/src/skills/...` 逐字 |
| orchestration（60 條） | `hosts/agy/dist/skills/shoal-orchestration/references/` 下一個檔案（名稱由 `policy_doc` 決定） | 按需。agy 對 skill 資料夾的說明列有 `references/`（agy 1.3.3 執行檔字串，未驗證） | 沒有；舊 SKILL 把關卡、dispatch、裁決都放在同一個檔案 |
| extensions（40 條） | 同上，另一個檔案（名稱由 `extensions_doc` 決定） | 按需 | 沒有；agy 舊文字完全沒有 extensions |
| agy 調校 addenda | `hosts/agy/policy-addenda/orchestration.toml`（§1.1 的 S07、S09、S35、S36 四列，附在 `approval-gate`、`plan-gate`、`parallel-launch`、`parallel-writers` 之後） | 按需 | 沒有（`hosts/agy/` 底下只有 `addenda/`，那是 role 用的） |

renderer 與 binding 目前缺少的部分：

- `tools/render.py:725-735` 的 `render_agy` 不呼叫 `policy_files`、不看 `policy_text`；
  `render_claude`（`render.py:557-562`）才會用 core 文件取代 `src` 內同路徑的原文。
- `tools/render.py:696` 的 `validate_agy` 呼叫 `validate_catalog(core, binding)`，
  `core_policy` 預設 `False`，所以 `policy_text = "core"` 會被 `render.py:306` 以「尚未支援
  這個 host」拒絕（`tests/test_core_policy.py:409-415` 鎖定這個行為）。`render.py:1358` 的
  `explain` 也寫死 `core_policy=host == "claude"`。
- `render.py:733` 的 `_passthrough(src, out, {"agents", "rules"})` 會把
  `src/skills/**` 原樣帶進 dist；core 模式需要像 `render_claude` 一樣先移除同路徑的原文。
  `render.py:734` 的 `_versioned_rules` 依 `hosts/agy/VERSION` 改寫 marker；Claude
  的 marker 則是 `policy-frames/bootstrap.md:1` 的字面值，由
  `tests/test_render_claude.py:67-73` 對照 VERSION。agy 用哪一種未決。
- binding 缺 `[policy.placeholders]`（16 個 key）、`[policy.documents]`（4 份文件的輸出路徑）
  與 `omit` 的內容（`hosts/agy/binding.toml:15-17` 目前是 `policy_text = "legacy"`、
  `omit = []`）。
- `hosts/agy/policy-frames/`（bootstrap、skill 等外框）與 `hosts/agy/policy-addenda/`
  不存在。`package.json` 的 `lint:md` 已排除 `#hosts/*/policy-frames`。
- `--policy-preview` 與 `--explain-policy` 對 agy 已可用（`render.py:1405-1425` 以
  `core_supported=True` 呼叫），前提是 binding 補齊上面兩段；本文件的數字就是這樣取得的。
- prompt lock（`docs/specs/prompt-document-lock/LOCK.json`）沒有任何 agy 檔案，
  `install/validate_prompt_lock.py:21-50` 的 `REQUIRED_SURFACE_PATHS` 也沒有，所以不需要
  lock migration，也沒有 version gate。
- `upstream.lock:32-38` 的 `[agy]` 仍記 `kind = "fork-base"`、
  `path = "hosts/agy/src"`；切換後 `src/rules` 與 `src/skills` 只剩
  `policy_text = "legacy"` 的回退用途。沒有測試讀 agy 的這一段（`marker_version` 只被 claude 與
  grok 的測試檢查）。

## 5. 大小預算

以下位元組數都是 UTF-8。「占位值」指 §1 說明的四個查無證據的 placeholder 用占位字串（長度：`question_tool` 17、
`background_option` 21、`effort_param` 16、`label_param` 15），其他 placeholder 用 §
3.1 的 agy 值。

| 項目 | 位元組 | 行數 | 說明 |
|---|---|---|---|
| agy 現行 `rules/shoal-agy.md` | 1,648 | 35 | `wc -c`；含 marker、begin、end 與標題 |
| agy 現行 `SKILL.md` | 6,434 | 124 | `wc -c` |
| 組合後的 `generated/gemini/GEMINI.md`（現況） | 12,113 | - | 其中 shoal 區段 `188-222` 行 1,648；內含的 marker 是 v3.3.1，見 §7 |
| Claude 現行 `claude-md.bootstrap.md` | 3,103 | 49 | 含外框 106（`hosts/claude/policy-frames/bootstrap.md`） |
| core bootstrap 本文，12 條全部，占位值 | 3,034 | 46 | 不含外框 |
| 同上，四個占位值改成 Claude 的值長度 | 3,020 | 46 | `AskUserQuestion` 15、`run_in_background: true` 23、`effort` 6、`description` 11 |
| 同上，省略 `bootstrap-dispatch-brake` | 2,562 | 39 | 該條 471 位元組 |
| 同上，另省略 `bootstrap-collect` | 2,384 | - | 該條 177 位元組；只有在背景 role 確定做不到時才相關 |
| agy 舊外框（marker、begin、標題、end） | 109 | - | `shoal-agy.md:1-4` 86 加 `:35` 23；新外框內容未定 |
| core skill 本文 | 1,222 | 29 | Claude 的 skill 外框 482 |
| core orchestration 本文（60 條） | 19,107 | 278 | Claude 的外框 43 |
| 同上，省略 `effort-per-delegation` | 18,568 | 271 | 該條 538 位元組 |
| core extensions 本文（40 條） | 9,374 | 171 | Claude 的外框 100 |

敏感度：bootstrap 有八個 placeholder 各出現一次（`named_roles`、`dispatch_tool`、
`question_tool`、`background_option`、`effort_param`、`model_param`、`label_param`、
`skill_term`），所以任一實值比占位值每長（短）一個字元，總量就多（少）一位元組。on-demand 三份文件合計（省略
`effort-per-delegation`）約 29,164 位元組，是現行 SKILL 的 4.5 倍；這是按需載入的量，不是常駐。

**上限**

- repo 內沒有 agy 的大小上限：LOCK.json 與 `REQUIRED_SURFACE_PATHS` 都沒有 agy 的路徑；沒有測試斷言
  agy 檔案的大小。A5 所說的「host 現有的大小上限」對 agy 是「無」。repo 內唯一的 bootstrap 上限是 Codex 的
  3,000 位元組（LOCK.json 的 `bootstrap-policy`）。
- 作為參考，Claude 的 lock 上限是 skill 2,100、orchestration 19,600、extensions 9,600 位元組
  （`LOCK.json` 的 `claude-*` surface）；agy 的 core 輸出各自在這些數字以下，但這些上限不適用 agy。
- agy 自己的上限（agy 1.3.3 執行檔字串，未驗證）：每個 rules 檔 24,000 位元組、超過就在行界截斷；常駐 rules 共用
  20,000 token 的預算，超過的 rules 會被降級成檔案路徑指標。現況組合檔 12,113 位元組；換成新的常駐文字後約為 12,113 -
  1,648 + 3,143（含舊外框的全部 12 條）= 13,608，或 12,113 - 1,648 + 2,671（省略
  `bootstrap-dispatch-brake`）= 13,136，約為 24,000 的 55-57%。

## 6. 測試影響

假設 agy 的切換是：`policy_text = "core"`、bootstrap／skill 由 core 產生、orchestration 與
extensions 成為 skill 目錄下的兩個新檔案、golden 以
`python3 tools/refresh_golden.py --host agy --from-dist` 重建。我沒有執行測試；下表是逐檔閱讀的結果。
「必改」表示在這個假設下必然失敗或需要更新；「視設計」表示取決於 §4 未決的 marker 與 source 設計。

| 位置 | 釘住的內容 | 會發生什麼 | 分類 |
|---|---|---|---|
| `tests/test_render_agy.py:12` | `GOLDEN_COUNT = 11`（9 個 agent、rules、SKILL） | 新增兩個 references 檔後變 13；`tests/golden/agy/rules/shoal-agy.md` 與 `skills/.../SKILL.md` 內容要更新，另新增兩個 golden 檔（`render_helpers.py:75-81,88-89` 的位元組比對） | 必改 |
| `tests/test_delegation_default.py:107-110` | `POLICY_SHA256["agy"]` 兩個 sha256（rules 與 SKILL，v3.0.3 的 marker 正規化後） | 內容改變後兩個雜湊必然不符；要刪掉 agy 的兩筆或換新值 | 必改 |
| `tests/test_delegation_default.py:209-212` | `for host in ("grok", "agy")`：policy 檔不得出現 `` `watcher` ``、`` `researcher` ``（共 agy 2 檔 × 2 role = 4 個斷言） | core bootstrap 一定會寫這兩個 role 名稱，4 個斷言全部失敗；`:91` 的類別說明「不接派工條款」也不再成立 | 必改 |
| `tests/test_core_policy.py:32` | `EXPECTED_POLICY_TEXT`：agy 為 `"legacy"` | 改為 `"core"`；`:226-228` `test_policy_text_is_locked_per_host` 隨之 | 必改 |
| `tests/test_core_policy.py:35` | `EXPECTED_POLICY_OMITS["agy"] = []` | 改為實際省略清單（至少 `effort-per-delegation`，另依 §8 決定）；`:230-238` 檢查每項 omit 有理由且清單相符 | 必改 |
| `tests/test_core_policy.py:36`、`:38` | `EXPECTED_POLICY_REPLACES`、`EXPECTED_POLICY_ADDENDA` 的 agy 為空 | agy 有 policy addenda 後要列出 addendum id 與被 replace 的條款；`:240-254` 讀 `hosts/agy/policy-addenda/*.toml` 比對 | 必改 |
| `tests/test_core_policy.py:409-415` | `test_core_is_rejected_for_hosts_that_are_not_ready` 迴圈含 `"agy"`，預期 `policy_text = "core"` 被「尚未支援」拒絕 | agy 要從元組移除，否則失敗 | 必改 |
| `tests/test_render_agy.py:18-22`、`:43` | marker 由 `hosts/agy/VERSION` 產生；斷言版本等於 `"3.4.0"` | 若版本號隨切換變動就要改兩處；marker 來源若改為外框字面值，`:18-22` 要重寫 | 視設計 |
| `tests/test_render_agy.py:24-31` | 改 VERSION 為 2.0.1 後 `--check` 回 1 並指出「內容不同: rules/shoal-agy.md」，`--write` 後 dist 帶新 marker | 只有 marker 仍由 VERSION 改寫時才成立 | 視設計 |
| `tests/test_render_agy.py:40-48` | `src/rules/shoal-agy.md` 必須恰有一行 marker，否則 render 拒絕且訊息含 `marker` | 若 rules 不再取自 `src/rules`，這個測試要刪或改 | 視設計 |
| `tests/render_helpers.py:111-115`（`test_check_fails_when_source_changes_without_rewriting_dist`，`test_render_agy.py:15` 指定 `SRC_FILE = "rules/shoal-agy.md"`） | 在 `src/rules/shoal-agy.md` 尾端加一行後 `--check` 必須回 1 | core 模式下 rules 不取自 src，檢查會通過，測試失敗；需把 `SRC_FILE` 換成仍參與 render 的來源 | 視設計 |
| `tests/test_generic_md_render.py:668` | `_compose` 把 binding 內的 `policy_text = "core"` 換成 `"legacy"` 再做 generic-md 比對（agy 的 role 位元組比對在 `:701-713`） | agy binding 多了 `[policy.*]` 表，legacy 模式下仍會驗證格式；預期不受影響，但要實跑確認 | 預期無影響 |
| `tests/test_sync_global.py:283-312`、`tests/test_rebrand_migration.py:530-600`、`tests/test_role_rename_migration.py:140-200` | 以 `hosts/agy/dist/agents`、`skills` 第一層項目建 symlink；`sync_global.py:403-408` 的舊名遷移取 `dist/skills/` 第一個項目當新名 | `references/` 是 skill 目錄內的子目錄，不改變第一層；只有新增第二個 skill 目錄才會影響遷移邏輯與這些測試 | 預期無影響 |

未列入的 agy 相關測試（`test_shoal_guard.py` 34 處、`test_install_hooks.py`、
`test_access_derivation.py`、`test_model_catalog.py`、`test_role_contracts.py`、
`test_check_rename.py`、`test_new_host.py`、`tests/fixtures/guard_vectors.json`）
釘的是 guard 行為、hook 安裝、role 工具清單與 model 對照，不釘 policy 文字或檔案清單，我逐一讀過相關段落，沒有發現依賴。
`tests/test_role_contracts.py` 的 agy addenda 清單（`EXPECTED_ADDENDA`）只在 role
addendum 改動時才受影響，見 §8 第 10 項。

合計：必改 7 列（`test_delegation_default.py` 2 列、`test_core_policy.py` 4 列、
`test_render_agy.py:12` 1 列），對應 9 個測試程式的編輯點（雜湊 2 處、`assertNotIn` 迴圈 1 處〔4 個斷言〕、
`EXPECTED_*` 常數 4 處、`:409` 迴圈 1 處、`GOLDEN_COUNT` 1 處），另有 4 個 golden 檔（2 個更新、2
個新增，由 `--from-dist` 重建）；視設計 4 列；預期無影響 2 列。

## 7. 安裝與實測

### 7.1 事實

- dist 在 repo：`python3 tools/render.py --host agy --write`，之後 `--check`；golden：
  `python3 tools/refresh_golden.py --host agy --from-dist`。
- skill 與 agents 在機器上是指向工作樹 `hosts/agy/dist` 的 symlink
  （`ls -l ~/.gemini/config/skills/shoal-orchestration` 與
  `~/.gemini/config/agents/*`；dotfile 的 `script/common/setup_gemini.sh` 的註解：維持
  symlink 到工作樹）。所以 dist 一寫入，skill 與 references 立刻生效，不需要 commit，也不需要
  `sync_global`。
- 常駐文字不是 symlink：`setup_gemini.sh` 的 `compose_active_rules` 把
  `$SHOAL_AGY_SRC/rules/shoal-agy.md` `cat` 進
  `~/dotfile/config/ai/generated/gemini/GEMINI.md`，`~/.gemini/GEMINI.md` 指向它。要
  讓新的常駐文字上機，執行 `bash ~/dotfile/script/common/setup_gemini.sh`。
- 每日同步不會更新常駐文字：`tools/sync_global.py:478-492` 的 `sync_agy` 只做
  `install_hooks.py --host agy`（guard hook）、檢查 `dist/agents` 與 `dist/skills` 第
  一層的 symlink、移除舊名 symlink。實際證據：現在組合檔的 marker 是 `<!-- shoal-agy v3.3.1 -->`
  （`~/dotfile/config/ai/generated/gemini/GEMINI.md:188`），dist 是 v3.4.0。
- agy 讀 `~/.gemini/GEMINI.md` 當全域 rules：線索是 agy 1.3.3 內嵌的 changelog 文字提到
  `~/.gemini/GEMINI.md`、`~/.gemini/AGENTS.md` 與其 `~/.gemini/config/` 對應檔作為全域
  rules（執行檔字串，未驗證）。

### 7.2 live 測試前要做與檢查

1. `python3 tools/render.py --host agy --check` 回 0，且 `git status` 顯示 dist 與
   golden 的變更是預期的。
2. 執行 `bash ~/dotfile/script/common/setup_gemini.sh`，然後確認
   `grep 'shoal-agy v' ~/.gemini/GEMINI.md` 是新版本、`wc -c ~/.gemini/GEMINI.md` 小
   於 24,000。
3. 確認 symlink 仍指向工作樹的新 dist：
   `readlink ~/.gemini/config/skills/shoal-orchestration`，並確認 references 檔案在該路
   徑下可見。
4. 確認 guard 已註冊：`python3 tools/install_hooks.py --host agy`（dry-run 應無變更）；agy
   固定 shadow，不會擋 main 改檔（§3.2），驗收要看 model 行為，不能靠 hook。
5. 用全新的 agy conversation 測試，不續接舊的（`--continue`、`--conversation` 會帶舊 rules 狀態，是
   否重新載入未驗證）。

### 7.3 `agy --help`（1.3.3）的非互動模式

`agy --version` 回 `1.3.3`。`agy --help` 有非互動模式：`-p`／`--print`（別名 `--prompt`）
「Run a single prompt non-interactively and print the response」。headless 測試會用到的
旗標：

- `--output-format text|json|stream-json`（預設 text）；
  `--input-format text|stream-json`（後者要求 `--output-format stream-json`）；
  `--json-schema`。
- `--print-timeout`（0 表示等到回合結束）；`--log-file`。
- `--mode accept-edits|plan`；`--agent`、`--model`、
  `--effort low|medium|high|xhigh|max`（整個 session，不是逐次派工）。
- `--sandbox`、`--dangerously-skip-permissions`（自動核准所有工具權限；會讓
  `shoal-agy.md:29-30` 那條規則的情境成真）、`--add-dir`、`--project`、`--new-project`、
  `--conversation`、`-c`／`--continue`、`--disable-slash-commands`（說明寫「in print
  mode」）。
- `--help` 沒有說明 print mode 是否載入 `~/.gemini/GEMINI.md`、skills 與
  `~/.gemini/config/agents` 的 subagent；這需要一次會呼叫付費模型的 live 實測，本次沒有做（§8 第 11 項）。

## 8. 未決事項

每項格式：問題；查過的檔案；缺少的證據。第 1、9 項同時是「固定決策在文字面上做不到」的情形。

| # | 問題 | 查過的檔案 | 缺少的證據或需要的決定 |
|---|---|---|---|
| 1 | 規則 `shoal-agy.md:5-6` 的閘門句（"This section applies only to the agy (Antigravity CLI) main session. If you are not in agy … ignore it."）無法依六種處置歸類。原因：常駐文字會被 `setup_gemini.sh` 併進 `GEMINI.md`，而 Gemini CLI 也讀同一個檔案（`setup_gemini.sh` 註解「Gemini CLI 沒有這些 subagent 角色」）；core 條款沒有這種範圍句。固定決策要求 host 調校放按需文件、常駐文字最多四行指標，但這句的用途正是讓常駐文字在非 agy 環境失效，放到按需文件就沒有作用。 | `hosts/agy/src/rules/shoal-agy.md`、`~/dotfile/script/common/setup_gemini.sh`、`core/policy/bootstrap.toml` | 需要 Miyago 決定：這句算不算「四行指標」、是否放進外框，或是否不再需要（若 Gemini CLI 不載入此檔）。repo 內沒有 Gemini CLI 是否載入 `~/.gemini/GEMINI.md` 的證據 |
| 2 | agy 的結構化提問工具名稱。 | `hosts/agy/src/**`、`hosts/agy/binding.toml`、`core/policy/placeholders.toml`、dotfile `config/ai/gemini/` | repo 內沒有。線索：agy 1.3.3 執行檔字串有 `ask_question`（說明為阻塞式多選 modal、「(Recommended)」放第一個），未經 live 驗證 |
| 3 | `invoke_subagent` 的背景語意（`background_option`）、標籤欄位（`label_param`）、`/goal` 是否存在（`goal_command`）。影響 `bootstrap-delegate-default`、`parallel-launch`、`watcher-long-commands`、`leaf-cannot-finish`、`dispatch-kind-label`、`auto-ask-selection` 與 `bootstrap-collect` 等，其中 `bootstrap-delegate-default` 承載 A3。 | `SKILL.md:82`、`hooks/shoal_guard.py:1640-1653`、`E0-RESULTS.md:29-31`、`tests/test_shoal_guard.py:1162-1163` | repo 只記錄 entry 欄位 `Model`、`Prompt`、`Role`、`TypeName`（還有 `Subagents` 陣列），沒有立即回傳或回報機制的記載。需要一次 live 實測 |
| 4 | `Model` 欄位：core 的 `model-routing` 要求具名 role 派工時省略 model 參數，以免覆蓋 role 定義的 `flash`／`pro`。 | `hosts/agy/dist/agents/*/agent.md` frontmatter、`E0-RESULTS.md:29-31`、`tests/test_shoal_guard.py:1163` | 已記錄的樣本帶 `"Model": "inherit"`；agy 1.3.3 執行檔字串另有「Default the Model argument to 'inherit' unless the user explicitly requests a different model」的內建指引。省略後 role 的 model 會不會被套用，需要 live 驗證 |
| 5 | `worktree_option` 該取 `branch` 還是 `share`，以及是否需要 Git。core 的 `parallel-writers` 寫「requires Git；without Git, never fan out」。 | `SKILL.md:82-84` | repo 只說「exclusive files, or workspace mode `branch` / `share`」。執行檔字串說 `branch` 是新的隔離 clone、`share` 類似 git worktree，未驗證 |
| 6 | S08 的「Plan artifact」：main 為 Plan 寫 artifact 檔，與 `bootstrap-delegate-default` 的「main 不自己改檔」是否衝突。 | `SKILL.md:22-24`、`core/policy/bootstrap.toml:26-38` | core 沒有規定 Plan 的承載方式；需要 Miyago 決定 Plan artifact 算不算 main 的改檔 |
| 7 | core 內部不一致：`one-shot-spec`（`core/policy/orchestration.toml:285-287`）寫「after two failures, escalate tier or take over」，與 `bootstrap-delegate-default`（main 不自己改檔）及 `delegate-cost-benefit`（worker 不可用不是改檔的理由）互相矛盾。這影響所有 host，不只 agy；agy 舊文字（S20、S33）沒有「take over」。 | `core/policy/orchestration.toml`、`core/policy/bootstrap.toml` | 需要決定 core 側的修正；agy 的對照表無法替它決定 |
| 8 | `write_tools` 的完整清單。 | `hosts/agy/binding.toml:30`、`hooks/shoal_guard.py:1668` | write 等級沒有 allowlist；repo 只出現 `write_to_file`、`multi_replace_file_content` 與子字串 `replace_file_content` |
| 9 | `bootstrap-dispatch-brake` 是不可分割的一條，同時含 effort、`Model` 省略、標籤前綴與「state scope and stop」。固定決策：只有做不到才省略。agy 做不到的只有 effort，但省略一條 non-required 條款只能整條省略；要保留其他三項就得用 addendum `replace:`，而 replace 的文字是新措辭，且 bootstrap 是常駐文件，與「調校放按需文件」衝突。 | `core/policy/bootstrap.toml:76-87`、`tools/contracts.py:367-387`（`compose_policy`） | 需要 Miyago 決定：拆分 core 條款（改 core，不是 agy 的調校）、整條省略並接受 `Model` 與標籤規則只留在 orchestration 的 `model-routing` 與 `dispatch-kind-label`，或接受常駐 replace。這是 A4 與「常駐／按需」兩條固定決策之間的缺口 |
| 10 | agy 現有 role addendum 與 core policy 的一致性：`plan-critic` 的 `slice-inherits-envelope`（`hosts/agy/addenda/plan-critic.toml:45-50`）宣稱「在這個 host 的 Plan，slice 不帶自己的 budget 與 stop conditions」，而 core `plan-gate`（`core/policy/orchestration.toml:99-106`）要求 slice 帶 budget 與 stops。`brief-unit-kinds`（同檔 `:18-23`）則對應 S09 的 `## Target readiness unit` brief 格式。 | 上述兩檔、`docs/specs/role-contracts/MAPPING-agy.md:84` | 切換後這個 addendum 與 policy 互相矛盾；要不要改 role addendum（會動到 `tests/test_role_contracts.py` 的 `EXPECTED_ADDENDA`）需要決定 |
| 11 | `agy -p` 是否載入 `~/.gemini/GEMINI.md`、skills 與自訂 subagent，以及 headless 時 `invoke_subagent` 與問答工具的行為。 | `agy --help`（只讀，未開 session） | `--help` 沒寫。需要一次 live 實測；spec C1 預估 agy 5 次以內 |
| 12 | agy 自己的 rules 大小上限（24,000 位元組／檔、20,000 token 共用預算）只出現在 agy 1.3.3 執行檔字串。 | `strings ~/.local/bin/agy` | 沒有官方文件或 repo 內的記載；§5 的百分比只作參考 |
| 13 | A3 的 5 列額外行為變更（R14、R16、S11、S25、S48）是否也算預期變更。 | §1.3 | A3 只列舉 main 不改檔、role 派不出去回報、長指令歸 `watcher`、研究用兩個 `researcher` 四類；其餘需要 Miyago 確認（尤其 R16、S11、S25 方向是放寬） |
| 14 | `shoal-agy:begin/end` 區段標記（F02）的去留。 | 全 repo grep：沒有程式讀它；dotfile 的 `setup_gemini.sh` 只 `cat` | 標記是否有人工用途不明 |

結束。
