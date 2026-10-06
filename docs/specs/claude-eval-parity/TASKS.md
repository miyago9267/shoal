# TASKS — claude-eval-parity

> Approved baseline（Miyago，2026-10-04）。本檔每步更新；付費 run 仍需
> 逐次核准。

## Batch 0 — specification review

- [x] Miyago 核准 `SPEC.md` 的 requirements、decisions 與成本上限
      （2026-10-04，plan-verifier REVISE 的修正已納入）。
- [x] Open questions 1、2、5 已於 2026-10-04 決定（lock renewal 同意、
      WORK-STATUS 限制解除、隔離執行保留訂閱登入）。
- [x] Open questions 6、7 已決定：`missed_risk` 以 per-case
      `risk_coverage < 1.0` 推導；沒有結論的 verifier 新增
      `verifier_inconclusive`。
- [x] Open questions 3、4 已決定：plan_review 比較 frontier 對 strong
      tier（smoke 上限 7 processes）；B5 只在 role 文字改動時重跑。

## Phase B0 — Claude prompt surface 加入 lock

- [x] VERSION gate 改為依 surface 所屬 host 判斷（Decision 6）：
      `validate_prompt_lock.py`、`LOCK.json` schema 與對應測試。
- [x] 給 Claude host 版本正式位置 `hosts/claude/VERSION`
      （`1.4.2-claude.2`），測試檢查與 `SKILL.md` 的 marker 一致
      （`5d38a3d`）。
- [x] Codex surface 一併改用 `hosts/codex/VERSION`（已採用；16 個 Codex
      surface 全部對應該檔，不再讀根目錄 `VERSION`）。
- [x] 依 Decision 2 為 11 個 Claude surface 訂出 `max_lines`、`max_bytes`、
      變更預算與 `required_fragments`；實際渲染一次「單一 core 條款同時
      改動所有 core agent」的情境，確認每個 surface 仍在預算內。結果：
      `executor`、`mech-executor`、`security-executor` 的
      `max_change_ratio` 訂為 0.35，其餘 0.2（SPEC Decision 2，2026-10-05，
      待 Miyago 確認）。
- [x] `.github/workflows/python-tests.yml`：`pull_request` 與 `push` 的
      `paths` 加入 `hosts/claude/**`（`1124088`）。
- [x] 實作 renewal 綠燈路徑（R2）：PR label `lock-renewal` 與 main push
      的 `Lock-Renewal: approved` trailer 才對 lock 檢查加
      `--allow-lock-update`；PR 的 `types` 加 `labeled`、`unlabeled`
      （`1124088`；離線測試 `tests/test_ci_workflow.py` 已過）。
- [x] 以一次 `--allow-lock-update` renewal 更新 `LOCK.json`，同一個
      commit 不改任何 prompt 內容（`git diff --name-only` 只含 lock、
      validator、版本檔與測試）；renewal 經上述路徑送出，CI 為綠。
  - 驗證程度：renewal commit `91a23e6` 只改 `LOCK.json`、validator 與測試，
    不含 prompt 內容，且帶 `Lock-Renewal: approved` trailer；離線已過。
    main push 的 trailer 路徑已由該 commit 的 CI 驗證（2026-10-05，
    Python tests 在 macos、ubuntu、windows 都是 success）。PR label 路徑
    沒有真實 PR 驗證過。
- [ ] 確認 `validate_prompt_lock.py` 對新 surface 生效：故意改動一個
      Claude agent 會被擋下，且只改 `hosts/claude/dist/agents/*.md` 的 PR
      會觸發 workflow。
  - 驗證程度：離線測試已過（Claude agent 超出預算、缺 required fragment、
    未 bump `hosts/claude/VERSION` 都會失敗並指出 surface）；`paths`
    觸發只由 `tests/test_ci_workflow.py` 檢查設定，尚未由真實 PR 驗證。
    第一次真實 renewal 或 Claude prompt PR 確認 CI 行為後再勾。
- [x] 更新 `docs/specs/prompt-document-lock/SPEC.md` 的 surface 清單與數量
      （27 個）。

## Phase B1 — host adapter 介面

- [x] 從 `install/run_role_fitness_content.py` 抽出 stage 執行介面
      （prompt、role、sandbox → messages、usage、wall、evidence）。
  - 介面在 `install/role_fitness_stage.py`（`StageRequest`、`StageOutcome`、
    `DispatchEvidence`、`StageAdapter`），不 import 任何 host。
- [x] Codex 實作改走新介面；既有 content runner 測試全數通過，輸出逐欄位
      相同。
  - 證據：`tests/test_run_role_fitness_stage_characterization.py` 的 21 個
    case 在重構前（HEAD `789c27c` 的乾淨 clone）與重構後都通過，斷言相同。
  - 已知差異：split executor 的 timeout 與 evidence 失敗原本就不 catch，
    例外型別改為 `StageTimeout`、`StageEvidenceError`；repo 內沒有呼叫者
    依賴舊型別。

## Phase B2 — Claude adapter（offline）

- [x] 實作 Claude adapter：暫存專案目錄、`.claude/agents/` 由 committed
      dist 複製、`claude -p --output-format stream-json --verbose
      --setting-sources project`，`CLAUDE_CONFIG_DIR` 指向每 stage 全新的
      暫存目錄，加 `--max-budget-usd <amount>`。
  - `install/role_fitness_claude.py` 的 `ClaudeStageAdapter`。離線實作後，
    以下各點已於 2026-10-05 以 live probe 驗證（結果見本節最後一項）：
    - token 的環境變數名稱暫定 `CLAUDE_CODE_OAUTH_TOKEN`
      （常數 `SUBSCRIPTION_TOKEN_ENV`）；沒有 token 時不啟動，也不退回
      `~/.claude` 或 keychain。
    - spec 之外另加的旗標與環境：`--permission-mode`（`read-only` 對
      `manual`、`workspace-write` 對 `acceptEdits`）、
      `--permission-prompts none`、`--strict-mcp-config`；prompt 由 stdin
      傳入；子行程環境是 allowlist，`HOME`、`TMPDIR` 指向 stage 的暫存目錄。
    - `--max-budget-usd` 超額時是否中止、`--setting-sources project` 與
      `CLAUDE_CONFIG_DIR` 的隔離效果。
- [x] 以 `Agent` 工具呼叫的 `subagent_type` 作為 dispatch evidence。
  - stream 樣本（`tests/fixtures/claude_stream/`）的形狀已依 2026-10-05 的
    live 結果校正，值仍是 synthetic；解析器遇到不認得的事件形狀就讓 stage
    失敗。結果事件不指出
    subagent 用哪個 model，所以只有整個 run 用單一 model 時才回報 model；
    `child_usage` 等於整個 stage 的 usage。
- [x] Claude 版 prompt 不使用 `spawn_agent`、`wait_agent`。
  - `claude_dispatch_prompt` 與 `claude_native_review_prompt`。四個 native
    case 函式仍只接 Codex，Claude 的接線留到 B4。
- [x] 實作 runner 的累計停止：admission 預留 per-stage 上限，累計成本
      加預留值超過 $30 就不放行下一個 stage。
  - `CostAdmission` 與 `AdmittedStageAdapter`；成本不明的 stage 以預留值
    計，回報成本高於預留值就停止放行。8,000,000 weighted tokens 與 HTTP 429
    的停止（AC-CE-031、032）不在這一項。
- [x] 以錄製的 stream 樣本做 offline 測試，不呼叫模型；測試斷言 adapter
      組出的 argv 與 env，不只檢查複製的 agents。
  - `tests/test_role_fitness_claude.py`（AC-CE-011 到 017）；樣本的形狀
    來自 live，值是 synthetic，不是錄製檔。

已知限制（B2 離線部分，B4 接線前需留意）：

- stream 樣本的形狀已依 2026-10-05 的 live 實測校正（不再只是 synthetic
  推定），但值仍是手工填的假值，不是錄製檔。
- 事件順序不固定：同一個 `dispatch` stage 連跑兩次，事件相同但順序不同
  （第一個 `result` 可能在第二輪 `system/init` 之前，也可能兩個 `result` 連在
  最後）。Adapter 不依賴順序（commit `690088d`），只要求最後一個事件是
  `result`。
- `StageOutcome.messages` 取 child 自己的 `assistant` 訊息；`Agent` 的
  `tool_result`（實測 1130 字元）是啟動回條，不是回答（child 回答實測 5
  字元）。
- `StageOutcome.events` 在 Claude adapter 一律回空清單，raw stream 不保留，
  runner 的 `event_shapes` 診斷因此是空的。
- frozen manifest 的檢查只在 `open_claude_run`；直接建立
  `ClaudeStageAdapter` 不會檢查，B4 接線必須走 `open_claude_run`。
- 四個 native case 函式尚未接上 Claude adapter（併入 B4）。
- hooks 的隔離無法判定：init 事件沒有列出 hooks，stream 看不到 user 層的
  hook 有沒有被載入。
- 額度被拒時的 `rate_limit_event` 實際值尚未見過；adapter 的規則（`status`
  以 `allowed` 開頭才繼續，其他值或 `isUsingOverage` 為 true 就停止後續
  stage）由 `allowed_warning` 反推。
- argv 傳 `--permission-mode manual`，但 init 事件回報的 `permissionMode`
  是 `default`，原因未查；實測 `permission_denials` 為 0，沒有造成工具被擋。
- `workdir`、`scratch` 必須是絕對路徑且不含 `..`，否則啟動前就拒絕。
- stage 結束後會掃描 workdir 的檔案內容找 token（上限 1000 個檔案、
  單檔 1 MiB、合計 32 MiB）；找到 token 或超出上限，stage 失敗並清空
  workdir。
- 保護清單同時涵蓋帳號資料庫的 home 與 `HOME`／`USERPROFILE` 推得的
  `.claude`，以及繼承到的 `CLAUDE_CONFIG_DIR`。
- [x] 實測 repo 外部事實（一次最小 live 呼叫，消耗訂閱用量，執行前要
      Miyago 核准；token 經 credential broker 注入）：
  - 2026-10-05 由 main session 執行 `install/claude_live_probe.py`，CLI
    2.1.289，共 7 次，API 等值成本累計約 0.29 USD。
  - [x] 注入 token 用的環境變數名稱，以及全新 `CLAUDE_CONFIG_DIR` 下 token
    可用（Open question 5）：`CLAUDE_CODE_OAUTH_TOKEN` 正確；在全新
    `CLAUDE_CONFIG_DIR` 與假 `HOME` 下可登入（`claude setup-token` 產生的
    訂閱 token）。`--model haiku` 可用，實際模型為
    `claude-haiku-4-5-20251001`。
  - [x] `--verbose` 與 `-p --output-format stream-json` 的搭配：加上
    `--setting-sources project` 後可用。
  - [x] 隔離（hooks 除外）：transcript 只出現在暫存 config 目錄，執行後整個
    刪除，home 底下 0 個檔；使用者 `projects/` 沒有對應項目；穩定的使用者
    config 項目在子行程存活期間沒有變動；init 事件列出的 agents、skills、
    plugins、MCP servers、slash commands 都沒有 user 層獨有的名稱（user 層
    三十多個獨有名稱的 skill 一個都沒出現）。**hooks 無法判定**：init 事件
    沒有列出 hooks，列入「已知限制」。
  - [x] `--max-budget-usd` 在超額時中止：用 `0.001` 測，CLI 以
    `result/error_max_budget_usd`（`is_error: true`）結束，exit code 1，只
    跑了 1 個 turn，實際成本 0.0181 USD。上限在一個 turn 結束後才檢查：能
    阻止繼續執行，但管不到單一 turn 的花費，實際成本可能遠高於上限值。
    因此 B4、B5 不必維持 dry-run，但預算必須依此限制編列（見 B4）。
  - 實測單價：`auth` stage（單 agent）每次約 0.017 USD；`dispatch` stage
    （parent 為 haiku、派出一個 `scout`）每次約 0.034 USD。

## Phase B3 — 失敗分類

- [x] runner 新增並輸出 `attempt` 與 `rerun_of`（R11）：只由操作者指定
      重跑時填入，不自動重試；測試涵蓋「首次不輸出」「指定重跑才輸出」。
  - 操作者以 case 函式的 `attempt`（>= 2）與 `rerun_of`
    （`<case_id>#<attempt>`）參數指定；沒有 CLI 入口，runner 自己不會重跑。
    測試：`tests/test_run_role_fitness_rerun.py`（AC-CE-029）。
- [x] 實作 `content_failure_class` 推導（Decision 4，輸入為 runner stage
      dict）：六個類別加 `unclassified`。
- [ ] 把 `docs/benchmarks/` 的既有結果檔依 `TESTS.md` 的對應表手動轉成
      recorded runner-format stage 當 fixture，餵給分類器，確認每個類別都
      能重現 spec 表中的案例；`missed_risk` 的 per-case `risk_coverage`
      以 private root ledger 重新計分確認。
  - 已完成：fixture 回放與每個類別的案例重現（`tests/test_role_fitness_content_failure.py`）。
  - **未完成**：`missed_risk` 的 per-case `risk_coverage` 尚未以 private
    root ledger 重新計分確認。目前 plan-review 風險 case 的值是由檔內
    aggregate `risk_coverage` 推論，不是重新計分的結果；此項在確認前維持未勾。
- [x] `failure_taxonomy` 同時彙總 dispatch 與 content 層。
- [x] 報表在分數旁列出各類別次數與佔比，R1–R3 分開列。
  - `role_fitness_scorecard.content_failure_report` 與
    `render_content_failure_report`；content probe 的報表以 `failure_report`
    輸出，`--repeat-label` 指定該次 run 屬於哪個 R。測試：
    `tests/test_role_fitness_content_report.py`（AC-CE-026）。
- [x] 新 key 加入 `role-fitness-public-v1` allowlist；public projection
      測試仍拒絕 free text。
  - key 為 `content_failure_counts`（arm -> repeat -> 類別 enum -> 計數）。
    測試：同上檔案（AC-CE-027）。

已知限制（B3b 獨立驗證，暫不修，B4 之前需留意）：

- public projection 的 arm 名稱接受任意 32 字內的小寫詞
  （`[a-z][a-z0-9_]{0,31}`），計數沒有上限。
- `public_content_failure_counts` 與 summary 的 `content_stages` 目前沒有
  production 呼叫端，重跑也沒有 CLI 入口；R9、R10 只在函式層成立，要等 B4
  接上後驗一次端到端輸出。
- runner 不檢查 `rerun_of` 指向的 stage 是否真的是 INCONCLUSIVE，只檢查格式
  與 attempt 順序。
- 取代關係只作用於 verifier INCONCLUSIVE（reason 為
  `verifier_did_not_confirm`）：其他失敗（含 verifier timeout）被重跑後，
  初次 stage 仍照自己的類別計一次。

## Phase B4 — Claude smoke（付費，需核准）

- [ ] 備妥核准單：每 stage 上限（`--max-budget-usd` 金額）、依 arm 數算出
      的 process 總數（每 arm process 數 × arm 數）、累計停止點。
  - 前置：`--max-budget-usd` 只在一個 turn 結束後才檢查（2026-10-05 實測，
    上限 0.001 時實際花了 0.0181 USD），不能直接把它的值當成每 stage 的
    花費上限。排預算時，每個 stage 的預留額以「單一 turn 可能的最大花費」
    計。
- [ ] Miyago 核准 smoke。
- [ ] 每個 cohort 1 個 case，process 數不超過核准單上的總數。
- [ ] 回報實測單次成本、時間，以及完整 run 的外推成本。

## Phase B5 — Claude R1–R3（付費，逐次核准）

- [ ] Miyago 核准 R1；依停止點執行。
- [ ] R1 結果審過後，再各自核准 R2、R3。
- [ ] 產出 Claude 與 Codex 的 scorecard 對照，含失敗分類表。
