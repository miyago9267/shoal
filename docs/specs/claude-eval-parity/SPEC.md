---
title: Claude host 的 eval parity 與失敗分類
status: approved
approved_by: Miyago
created: 2026-10-04
updated: 2026-10-05
---

<!-- markdownlint-disable MD025 -->

# Claude host 的 eval parity 與失敗分類

## Background

依 Andrew Ng《The AI Engineering Skills Map》（The Batch Issue 366）的實踐
清單：

- 「每次改 prompt／檢索／流程，都對同一組 eval set 重跑」。
- 「為 AI 功能寫失敗分類表（不只看平均分數）」。

現況（2026-10-04 查證，main `52689b7`；與基線 `747d871`、`VERSION`
1.1.0 相比，`hosts/claude`、lock 與 content runner 沒有差異）：

- **prompt 保護只涵蓋 Codex。** `docs/specs/prompt-document-lock/LOCK.json`
  有 16 個 surface（SPEC.md:79 寫的 15 是舊數字；B0 後為 27，見下方
  Decision 2、6），全部是 `templates/`、`plugin/` 與 `INSTALL_PROMPT.md`；
  沒有 `hosts/claude`。Claude host 的
  prompt 只受 `tests/test_render_claude.py` 與 golden 保護：能偵測「有沒有
  變」，但沒有變更預算與 `required_fragments`。
- **CI 不會擋 Claude 的變更。** `.github/workflows/python-tests.yml` 的
  `paths`（:5-35）只有 `hosts/codex/**`，沒有 `hosts/claude/**`，只改
  Claude agent 的 PR 不會觸發 workflow；而且 workflow 呼叫
  `validate_prompt_lock.py` 時不帶 `--allow-lock-update`（:67-70，
  `validate_prompt_lock.py:312-315` 在 `LOCK.json` 變動時拒絕），所以
  renewal 的 PR 預設是紅的。
- **Claude 的 role 文字已由 core 產生。** CHANGELOG v1.1.0（Phase 2b-2）
  起，Claude 的七個 core role 由 `tools/render.py` 從 core 條款渲染，
  `hosts/claude/dist/` 是產物；`Explore` 維持 legacy。一次 core 條款變更會
  同時移動最多 7 個 agent 的文字（dist 共 8 個 agent 檔）。
- **content 評分 runner 綁 Codex。** 真正做內容評分的是
  `install/run_role_fitness_content.py`：
  - `_native_review_command`（:321-339）組出 `codex exec ...`。
  - 從 `~/.codex` 複製 staged home、讀 `home/agents/<role>.toml`
    （:365-366、:389 等）。
  - prompt 寫死 `spawn_agent`、`wait_agent`（:309-318）。
  - 以 Codex rollout JSONL 證明 dispatch（`dispatch.inspect_dispatch`）。
  - `install/run_role_fitness_live.py` 只驗 dispatch 可用性，不評內容
    （自身 docstring :5-8）。
- **host 中立的部分已存在。** fixture 產生與驗證、`score_plan_review`、
  `install/role_fitness_scorecard.py` 的指標與 Wilson 下界、public
  projection 驗證都不依賴 Codex。
- **凍結 fixtures 可沿用。**
  `docs/benchmarks/role-fitness-v1-fixtures-manifest-v2.json` 有 30 個 case
  （plan_review 12，其中 4 個 clean control；mechanical_execution 12；
  split_workflow 6），manifest 只有 hash，fixture 內容是合成文字，沒有
  host 專屬字串。
- **失敗分類欄位存在但是空的。** run summary 與 stage 已有
  `failure_taxonomy`、`failure_class`（`install/benchmark_role_fitness.py`
  :112、:234-249、:474），但只涵蓋 dispatch 層（auth、preflight、
  `codex_exec_failed` 等），所有結果檔裡都是 `{}`。內容層的失敗只散落在
  `status`、`reason`、`false_escalation` 等欄位。

## Requirements (EARS)

### B1：Claude host 對同一組 eval set 重跑

- **R1（prompt surface 保護）**：The prompt document lock shall 涵蓋
  Claude host 的 runtime prompt：`hosts/claude/dist/agents/*.md`（8 個）與
  `hosts/claude/dist/skills/pilotfish-orchestration/` 底下的 `SKILL.md`、
  `references/*.md`；每個 surface 有 `max_lines`、`max_bytes`、變更預算與
  `required_fragments`。
- **R2（lock 程序與 CI）**：Because `LOCK.json` 是 `manifest_immutable`，
  the new surfaces shall 以一次經 Miyago 明確核准的
  `--allow-lock-update` renewal 加入；renewal 本身不得同時改動任何 prompt
  內容（commit 的檔案清單只含 lock、validator、版本檔與測試）。The CI
  workflow shall 在 `pull_request` 與 `push` 的 `paths` 加入
  `hosts/claude/**`，並提供 renewal 的綠燈路徑：
  - `pull_request`：PR 帶有 label `lock-renewal` 時，workflow 才對
    `validate_prompt_lock.py` 加 `--allow-lock-update`（`types` 需含
    `labeled`、`unlabeled`）。
  - `push` 到 main：head commit message 含一行 `Lock-Renewal: approved`
    時才加。
  - 兩者都只放寬 `LOCK.json` 變動與新 surface；既有 surface 的預算與
    VERSION gate 照常檢查。沒有 label 或 trailer 時行為不變，仍是紅燈。
  - 本機重現：`python3 install/validate_prompt_lock.py --base-ref <base>
    --allow-lock-update` 通過，且不帶旗標時失敗。
- **R3（host adapter 介面）**：The content runner shall 把「執行一個 stage」
  抽成 host 中立介面：輸入 prompt、role、sandbox；輸出 final messages、
  usage、wall time 與 dispatch／binding evidence。Codex 實作的行為與輸出
  shall 與抽出前逐欄位相同。
- **R4（Claude adapter）**：The Claude adapter shall 以 `claude -p
  --output-format stream-json --verbose --setting-sources project` 在
  暫存目錄執行，`.claude/agents/` 由 committed 的
  `hosts/claude/dist/agents/` 複製而來；dispatch evidence 取自 stream 中
  `Agent` 工具呼叫的 `subagent_type`；usage 與 model 取自結果事件；
  prompt 不得使用 `spawn_agent`、`wait_agent`。
  - `--verbose` 為 `-p --output-format stream-json` 所需，`CLAUDE_CONFIG_DIR`
    隔離與 `--setting-sources` 的實際效果是 repo 外部事實，只有本機
    `claude --help` 佐證旗標存在；B2 必須實測（見 R6）。
- **R5（同一組 eval set）**：The Claude run shall 使用同一份 frozen
  manifest（v2）、同一份 rubric 與 scorecard 版本；不得重做或修改 fixtures。
- **R6（隔離）**：Each Claude stage shall 在全新的 private root 與暫存
  專案目錄執行，不讀寫 `~/.claude`；raw stream 與 session 資料用完即刪，
  刪除失敗視為 stage 失敗（沿用 role-fitness 的 Data and scoring
  boundary）。隔離機制：
  - `CLAUDE_CONFIG_DIR` 指向每個 stage 全新的暫存目錄；transcript、
    session 與 credential 相關檔案都寫進該目錄，刪除該目錄即清除，
    不會落到 `~/.claude`。
  - `--setting-sources project`，只載入暫存專案的設定，不載入 user 層的
    hook、skill、agent、memory。
  - 以上為 repo 外部事實：B2 要實測「不讀寫 `~/.claude`」（前後比對
    `~/.claude` 的檔案清單與 mtime）、`--verbose` 與 stream-json 的
    搭配，以及 `--setting-sources project` 是否擋掉 user 層內容。

### B2：失敗分類表

- **R7（content 層分類）**：The scorecard shall 為每個未通過或需要重試的
  content stage 指定一個 `content_failure_class`，值域固定為下表；無法
  歸類時為 `unclassified`，不得留空。分類器的輸入是 runner 的 stage dict
  （Decision 4）。
- **R8（進入 scorecard）**：The run summary 的 `failure_taxonomy` shall
  同時彙總 dispatch 層與 content 層的類別計數（例如
  `content.false_escalation: 3`）；既有 dispatch 層類別名稱不變。
- **R9（進入報表）**：The report shall 在平均分數旁列出每個 arm 的各類別
  次數與佔比；同一 arm 的 R1–R3 分開列，不只列平均。
- **R10（公開邊界）**：The public projection shall 只輸出類別 enum 與
  計數，不含 free text、prompt、fixture 內容或路徑；新 key 必須加入
  `role-fitness-public-v1` 的 allowlist。

- **R11（人工重跑欄位）**：The content runner shall 在 stage dict 新增並
  輸出 `attempt`（從 1 起算）與 `rerun_of`（被重跑的 INCONCLUSIVE stage，
  格式 `<case_id>#<attempt>`；首次執行不輸出）。`rerun_of` 只由操作者明確
  指定重跑時填入；runner 不得自動重試
  （role-fitness `SPEC.md:534-535`：no automatic retries），人工重跑是
  另行核准、有自己上限的 run，仍計入成本與 process 數。分類器沒有這個
  欄位就不得判為 `verifier_retry`。

#### 失敗類別（每類皆有既有資料佐證）

| 類別 | 定義 | 既有案例 |
|---|---|---|
| `false_escalation` | clean control 被回報為有 blocking 問題 | `content-plan-cohort.json:13,20`（Luna 3、Sol 4 次 clean false escalation；direct_model_proxy 的 aggregate，沒有 per-case 資料）；`native-content-plan-r1.json:9` plan-review-01 |
| `missed_risk` | risk case 的 per-case `risk_coverage` 小於 1.0 | `native-content-plan-r1.json:11` plan-review-06（`supported_findings: 1`、`quality_score: 42.5`；檔內只有 aggregate `risk_coverage` 0.5，:17）；`content-plan-cohort.json:12,19` 的 aggregate 0.6875 與 0.5 只當期望總數 |
| `unparseable_output` | 派工成功，但 final response 無法機器解析，不給品質分 | `native-content-probe.json:11-12` |
| `executor_no_artifact` | executor 沒有產出可被接受的 artifact，verifier 未執行 | `native-split-v2.json:9`；`native-split-v5.json:11-12` |
| `verifier_retry` | verifier 第一次 `INCONCLUSIVE`，人工重跑後才有結論（stage 有 `rerun_of`） | `native-mechanical-verifier-r2.json:10`（`retry_after_initial_inconclusive: true`，手工標註；runner 目前不產生） |
| `verifier_inconclusive` | verifier stage 是 `inconclusive` 且沒有人工重跑 | `native-mechanical-verifier-r1.json:10-12` |

以上檔案皆在 `docs/benchmarks/` 下，檔名省略前綴 `role-fitness-v1-`。
資料中沒有出現過的類型（越權、拒絕工作、timeout）不列為類別；timeout 的
inconclusive 路徑（`run_role_fitness_content.py:379`）歸入 `unclassified`，
若日後出現，再依資料新增類別。
`content-paired-v8.json:7` 的品質退步（`quality_delta -7.1`）是 arm 之間的
比較結果，不是單一 stage 的失敗，放在報表的比較段，不列為類別。

## Non-goals

- 不重做或擴充 fixtures、rubric 與 scorecard 公式。
- 不改任何 role 的 prompt 內容（那是 review-tradeoff-privacy 等 spec 的事）。
- 不把 agy、grok、OpenCode 納入本次 parity；介面設計保留擴充空間即可。
- 不在本 spec 核准範圍內執行任何付費 live run（見「Live run 與成本」）。

## Decisions

1. **Claude surface 範圍**：只納入 Claude Code 實際載入的檔案（agents 與
   skill）；`hosts/claude/dist/claude-md.bootstrap.md` 與
   `settings.snippet.json` 不由 dotfile 安裝，不納入。
2. **預算訂法**：比照既有 Codex surface 的比例：`max_lines` 與
   `max_bytes` 約為目前大小的 1.2 倍，變更預算約為目前行數的 20%、
   比例 0.2；`required_fragments` 取各 role 的 identity 句與 verdict 字串。
   `hosts/claude/dist/` 是 `tools/render.py` 的產物（CHANGELOG v1.1.0），
   一條 core 條款的改動會同時落到最多 7 個 core 渲染的 agent（`Explore`
   為 legacy）：預算要以「單一 core 條款同時改動所有 core agent」為情境
   驗算，不能只看單檔。B0 在訂預算時要實際渲染一次典型的 core 條款改動，
   確認每個 surface 仍落在預算內。lock 只保護 dist；來源（`core/`、
   `hosts/claude/addenda/`）仍由 `render --check` 與 golden 保護。
   - **實作結果（2026-10-05，main session 決定，待 Miyago 確認）**：
     模擬「單一 core 條款同時改動所有 core agent」後，`executor`、
     `mech-executor`、`security-executor` 三個 surface 的
     `max_change_ratio` 訂為 0.35（validator 的 hard ceiling
     `HARD_MAX_CHANGE_RATIO`），其餘 8 個維持 0.2。原因：validator 以行為單位
     計算，Claude 的段落是單一長行，改一句會把整段算兩次（一行刪、一行
     增），0.2 會擋掉正常的單一條款修改。這偏離上面「比例 0.2」的預設，
     Miyago 若不同意，需重訂這三個 surface 的預算。
3. **介面先抽、行為不變**：先重構 Codex 路徑並證明零行為變化，再加
   Claude adapter，避免兩件事混在同一個 diff。
4. **失敗分類以 runner stage dict 推導**：分類器的輸入是
   `install/run_role_fitness_content.py` 的 stage 回傳 dict
   （inconclusive 見 `:379`、`:394`、`:401-404`、`:524`、`:628`、`:711`；
   accepted 見 `:428-442`），不是 `docs/benchmarks/` 的 JSON。那五份是手工
   整理的摘要，schema 各不相同（`native-split-v2.json:9` 用
   `executor.accepted_artifact`，`native-split-v5.json:11-12` 用字串
   `"INCONCLUSIVE"`，`native-content-probe.json:11` 用
   `review_json_valid`），不能直接當輸入。benchmark JSON 只當期望值來源；
   TESTS 逐檔寫出欄位對應，轉成 recorded runner-format stage 再餵給
   分類器。使用的欄位：`status`、`reason`、`dispatch_status`、
   `native_role`、`false_escalation`、`risk_coverage`、
   `score.expected_decision`、`rerun_of`（R11）。不新增需要模型判斷的欄位。
   規則依序比對，先中先贏：
   - `false_escalation`：accepted 且 `false_escalation` 為 true。
   - `missed_risk`：accepted、risk case（`score.expected_decision` 為
     `REVISE`）且 per-case `risk_coverage < 1.0`。runner 已輸出
     `risk_coverage`（`:442`）。不看 `supported_findings`。
   - `unparseable_output`：`reason` 為 `invalid_native_review_output`
     或 `invalid_review_output`，且 `dispatch_status` 為 `NATIVE_OK`
     （direct 路徑沒有該欄位時也成立）。
   - `executor_no_artifact`：`reason` 為
     `invalid_split_executor_acceptance` 或
     `invalid_native_mechanical_acceptance`，且 `dispatch_status` 為
     `NATIVE_OK`。
   - `verifier_retry`：verifier stage 為 accepted 且有 `rerun_of`。
   - `verifier_inconclusive`：`reason` 為 `verifier_did_not_confirm`，
     且沒有其他 stage 以它為 `rerun_of`；被人工重跑取代的初次 stage 由
     重跑 stage 計一次，不重複計。
   - 其他一律 `unclassified`（含 timeout、dispatch 層失敗）。
5. **順序**：review-tradeoff-privacy 若先合併，Claude surface 的預算以
   合併後的大小為基準；若本 spec 先合併，該 spec 對 Claude surface 的
   變更也必須落在本 spec 的預算內。
6. **lock 對應各 host 自己的版本**（Miyago，2026-10-04）：原話是「對應
   版本需要 lock，跨版本時以這個對齊」，並確認選擇「每個 host 看自己的
   版本號」。受保護 surface 有變更時，只要求該 surface 所屬 host 的版本
   號變更，不要求根目錄 `VERSION` 變更；這符合 README「各 host 版本另外
   維護，互不連動」。理由：在 repo 或 fork 裡客製單一 host 的 prompt，
   不應該推動整個 shoal 的產品版本。
   - 原況：`install/validate_prompt_lock.py` 的 VERSION gate 寫死根目錄
     `VERSION`（`_validate_lock_shape`）。**已實作（B0，2026-10-05）**：
     `LOCK.json` 升為 schema v2，每個 surface 有必填的 `version_file`
     （格式 `hosts/<host>/VERSION`），validator 依 surface 逐一檢查所屬
     host 的版本檔相對 base 是否變更；`version_gate` 只剩
     `require_change_for_protected_surfaces`。
   - Claude host 的版本原本只是 `SKILL.md` 裡的 marker 註解。**已實作**：
     正式位置為 `hosts/claude/VERSION`（目前 `1.4.2-claude.2`），測試檢查
     與 marker 一致。
   - Codex surface 一併改用 `hosts/codex/VERSION`：**已採用並已實作**，
     16 個 Codex surface 全部對應該檔，不再看根目錄 `VERSION`，讓所有
     host 行為一致。

## Live run 與成本

付費 live run 不在本次範圍；以下為核准後的執行上限。

- **次數**：依 role-fitness 的 Repeated-run protocol，一次完整 run 的上限
  是 60 arms、108 processes；R1–R3 重複三次的上限為 324 processes。
  `run_role_fitness_live.py` 的 `MAX_REPEAT_COUNT = 3`。
- **單價**：repo 內只有 Codex 模型的反推單價
  （`docs/benchmarks/usage-routing-v1/live-v6-summary.json`），**沒有
  Claude 的單價資料**。Claude 的成本以 `claude -p` 結果中的
  `total_cost_usd`（API 等值金額）計算；在 Max 方案下實際消耗的是用量
  額度，不是帳單金額。
- **每 stage 上限**：role-fitness `SPEC.md:535-539` 要求付費 run 前先
  證明 per-stage 的上游上限並在 admission 預留，否則只能 dry-run。Claude
  的做法：
  - 每個 stage 以 `claude -p --max-budget-usd <amount>` 限額（旗標存在於
    本機 `claude --help`，說明為「only works with --print」；實際
    執行時是否會在超額時中止，**尚未驗證**，B2 必須以最小呼叫實測）。
  - runner 在 stage 之間做累計停止：admission 時預留該 stage 的上限，
    累計 `total_cost_usd` 加上預留值會超過 $30 就不再放行下一個 stage。
  - B2 若證明不了 `--max-budget-usd` 會強制中止，B4、B5 維持 dry-run。
  - 金額由 Miyago 在 B4 核准單列出，spec 不預設數字。
- **上限**：
  - 先跑 smoke：每個 cohort 1 個 case，用來實測單次成本與時間。process
    上限 = 每 arm 的 process 數 × arm 數（plan review 1、mechanical 2、
    split 3），不是固定 6：每個 case 只跑 1 個 arm 時為 6，每個 case 2 個
    arm 時為 12。依 Open question 3，只有 plan review 跑 2 個 arm，smoke
    上限為 2 + 2 + 3 = 7；B4 核准單列出每 stage 上限與這個 process 總數。
  - smoke 後以實測值外推完整 run 的成本，回報 Miyago，核准後才跑 R1。
  - 每次 run 沿用既有停止點：API 等值 $30 或 8,000,000 weighted tokens，
    先到者停止；遇到用量上限（HTTP 429）立即停止並保留已完成 stage。
  - R2、R3 在 R1 的結果審過後才各自核准。

## Phases

詳細步驟見 `TASKS.md`，驗收條件見 `TESTS.md`。

| Phase | 內容 | 是否付費 |
|---|---|---|
| B0 | Claude prompt surface 加入 lock（一次核准的 renewal）；VERSION gate 改為依 host 判斷；CI paths 加 `hosts/claude/**` 並定義 renewal 綠燈路徑 | 否 |
| B1 | content runner 抽出 host adapter 介面，Codex 行為不變 | 否 |
| B2 | Claude adapter（offline：以錄製的 stream 測試）；隔離與 `--max-budget-usd` 實測 | 否；登入、隔離與 budget 驗證的最小呼叫除外，需核准 |
| B3 | runner 新增 `rerun_of`；content 層失敗分類（以 runner 格式 stage 測試）、scorecard 與報表、public allowlist | 否 |
| B4 | Claude smoke（process 上限 = 每 arm process 數 × arm 數） | 是，需核准 |
| B5 | Claude R1–R3 | 是，逐次核准 |

## Open questions

1. **（已決定，2026-10-04）B0 的 lock renewal**：Miyago 同意把 11 個
   Claude surface 加入 lock（見 Decision 6）。`--allow-lock-update` 在本
   spec 核准、進入 B0 時執行。
2. **（已決定，2026-10-04）WORK-STATUS 的 Claude 限制**：Miyago 決定解除
   限制，Claude 不鎖版本（`docs/WORK-STATUS.md:247-251`）。
3. **（已決定，2026-10-04）Claude 的 arm 怎麼配**：plan_review 比較
   plan-verifier 的現行 binding（frontier）對 strong tier，用來回答
   frontier 值不值得。mechanical 與 split 各跑現行 binding 一個 arm。
4. **（已決定，2026-10-04）B5 的頻率**：只在 role 文字改動時重跑，不做
   固定週期；每次重跑仍逐次核准。
5. **（已決定，2026-10-04）隔離下怎麼登入（R6）**：Miyago 決定保留訂閱
   登入，不走 API key。`claude --bare` 因此不能用（它不讀 OAuth 與
   keychain）。候選做法：全新的 `CLAUDE_CONFIG_DIR`（沒有 user 層的 hook、
   skill、agent），加上 `claude setup-token` 產生的長效 token（該指令的
   help 寫明 requires Claude subscription）。token 是 secret：由 Miyago
   親自產生，經 credential broker 以環境變數注入，不得寫入檔案、指令參數
   或 log。尚未驗證的兩點列為 B2 的第一個工作：注入 token 用的環境變數
   名稱；全新 config dir 下 token 可用，且不載入 `~/.claude` 的任何內容。
6. **（已決定，2026-10-04）`missed_risk` 怎麼推導**：risk case 且 per-case
   `risk_coverage < 1.0`（Decision 4）。plan-review-06 的
   `supported_findings` 是 1 仍然漏掉風險，只看 `supported_findings == 0`
   會漏判，還會誤中 clean control（plan-review-01 也是 0）；clean control
   的 `risk_coverage` 在 `score_plan_review` 為 1.0，不會中。
   `native-content-plan-r1.json` 沒有 per-case `risk_coverage`（只有 :17 的
   aggregate 0.5），B3 的 fixture 值由 aggregate 與 05、06 相同的
   `supported_findings`、`quality_score` 推論，並須以 private root 的
   ledger 重新計分確認。
7. **（已決定，2026-10-04）沒有結論的 verifier**：新增類別
   `verifier_inconclusive`（verifier stage 為 `inconclusive` 且沒有人工
   重跑）。`native-mechanical-verifier-r1.json:10-12` 即此類，不屬於
   `verifier_retry`，也不歸入 `unclassified`。
