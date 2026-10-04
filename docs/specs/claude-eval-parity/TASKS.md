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

- [ ] VERSION gate 改為依 surface 所屬 host 判斷（Decision 6）：
      `validate_prompt_lock.py`、`LOCK.json` schema 與對應測試。
- [ ] 給 Claude host 版本正式位置（例如 `hosts/claude/VERSION`），並檢查
      與 `SKILL.md` 的 marker 一致。
- [ ] 決定 Codex surface 是否一併改用 `hosts/codex/VERSION`（該檔已存在，
      1.8.1；目前 gate 仍讀根目錄 `VERSION`）。
- [ ] 依 Decision 2 為 11 個 Claude surface 訂出 `max_lines`、`max_bytes`、
      變更預算與 `required_fragments`；實際渲染一次「單一 core 條款同時
      改動所有 core agent」的情境，確認每個 surface 仍在預算內。
- [ ] `.github/workflows/python-tests.yml`：`pull_request` 與 `push` 的
      `paths` 加入 `hosts/claude/**`。
- [ ] 實作 renewal 綠燈路徑（R2）：PR label `lock-renewal` 與 main push
      的 `Lock-Renewal: approved` trailer 才對 lock 檢查加
      `--allow-lock-update`；PR 的 `types` 加 `labeled`、`unlabeled`。
- [ ] 以一次 `--allow-lock-update` renewal 更新 `LOCK.json`，同一個
      commit 不改任何 prompt 內容（`git diff --name-only` 只含 lock、
      validator、版本檔與測試）；renewal 經上述路徑送出，CI 為綠。
- [ ] 確認 `validate_prompt_lock.py` 對新 surface 生效：故意改動一個
      Claude agent 會被擋下，且只改 `hosts/claude/dist/agents/*.md` 的 PR
      會觸發 workflow。
- [ ] 更新 `docs/specs/prompt-document-lock/SPEC.md` 的 surface 清單與數量。

## Phase B1 — host adapter 介面

- [ ] 從 `install/run_role_fitness_content.py` 抽出 stage 執行介面
      （prompt、role、sandbox → messages、usage、wall、evidence）。
- [ ] Codex 實作改走新介面；既有 content runner 測試全數通過，輸出逐欄位
      相同。

## Phase B2 — Claude adapter（offline）

- [ ] 實作 Claude adapter：暫存專案目錄、`.claude/agents/` 由 committed
      dist 複製、`claude -p --output-format stream-json --verbose
      --setting-sources project`，`CLAUDE_CONFIG_DIR` 指向每 stage 全新的
      暫存目錄，加 `--max-budget-usd <amount>`。
- [ ] 以 `Agent` 工具呼叫的 `subagent_type` 作為 dispatch evidence。
- [ ] Claude 版 prompt 不使用 `spawn_agent`、`wait_agent`。
- [ ] 實作 runner 的累計停止：admission 預留 per-stage 上限，累計成本
      加預留值超過 $30 就不放行下一個 stage。
- [ ] 以錄製的 stream 樣本做 offline 測試，不呼叫模型；測試斷言 adapter
      組出的 argv 與 env，不只檢查複製的 agents。
- [ ] 實測 repo 外部事實（一次最小 live 呼叫，消耗訂閱用量，執行前要
      Miyago 核准；token 經 credential broker 注入）：
  - 注入 token 用的環境變數名稱，以及全新 `CLAUDE_CONFIG_DIR` 下 token
    可用（Open question 5）。
  - `--verbose` 與 `-p --output-format stream-json` 的搭配。
  - 隔離：前後比對 `~/.claude` 的檔案清單與 mtime 沒有變化；
    `--setting-sources project` 擋掉 user 層的 hook、skill、agent；
    transcript 只在暫存 config dir，用完整個刪除。
  - `--max-budget-usd` 在超額時確實中止（用極小金額測）；證明不了就把
    B4、B5 維持 dry-run。

## Phase B3 — 失敗分類

- [ ] runner 新增並輸出 `attempt` 與 `rerun_of`（R11）：只由操作者指定
      重跑時填入，不自動重試；測試涵蓋「首次不輸出」「指定重跑才輸出」。
- [ ] 實作 `content_failure_class` 推導（Decision 4，輸入為 runner stage
      dict）：六個類別加 `unclassified`。
- [ ] 把 `docs/benchmarks/` 的既有結果檔依 `TESTS.md` 的對應表手動轉成
      recorded runner-format stage 當 fixture，餵給分類器，確認每個類別都
      能重現 spec 表中的案例；`missed_risk` 的 per-case `risk_coverage`
      以 private root ledger 重新計分確認。
- [ ] `failure_taxonomy` 同時彙總 dispatch 與 content 層。
- [ ] 報表在分數旁列出各類別次數與佔比，R1–R3 分開列。
- [ ] 新 key 加入 `role-fitness-public-v1` allowlist；public projection
      測試仍拒絕 free text。

## Phase B4 — Claude smoke（付費，需核准）

- [ ] 備妥核准單：每 stage 上限（`--max-budget-usd` 金額）、依 arm 數算出
      的 process 總數（每 arm process 數 × arm 數）、累計停止點。
- [ ] Miyago 核准 smoke。
- [ ] 每個 cohort 1 個 case，process 數不超過核准單上的總數。
- [ ] 回報實測單次成本、時間，以及完整 run 的外推成本。

## Phase B5 — Claude R1–R3（付費，逐次核准）

- [ ] Miyago 核准 R1；依停止點執行。
- [ ] R1 結果審過後，再各自核准 R2、R3。
- [ ] 產出 Claude 與 Codex 的 scorecard 對照，含失敗分類表。
