---
spec: text-first
batch: 1
created: 2026-10-22
---

# Tasks: Text first

> Spec: `docs/specs/text-first/SPEC.md`
> Batch: 1

每個 phase 一個 PR，順序見 SPEC「Lock 與 renewal 的位置」。狀態 `[ ]` 未做、
`[x]` 完成。所有 phase 的共同驗收（下稱「共同驗收」）：

1. `python3 -m unittest discover -s tests` 全綠（基準 1915 個、297 秒）。
2. `python3 tools/render_equiv.py --base origin/main --head HEAD` 退出 0。
3. `python3 install/validate_prompt_lock.py --base-ref origin/main`
   （不帶 `--allow-lock-update`）通過。
4. `npm run lint:md` 通過。
5. PR 的 CI 在 ubuntu、macOS、windows 全綠。

## 前置條件

- [ ] 確認 spec 已獲 Miyago 核准（2026-10-22 已核准方向；本文待確認）
- [ ] `bun install --frozen-lockfile`（取得 repo 釘住的 markdownlint 0.23.0）
- [ ] 每個 phase 從最新 `origin/main` 開分支（基準 `8da4d0f`，已含 PR #34）；
      不碰已結案 spec
- [ ] P3b（停止 commit `hosts/claude/dist`）已於 2026-10-23 核准，納入本案，
      排在 P3a 之後。lock renewal R 是 main 上單獨一個直接 commit（trailer
      `Lock-Renewal: approved`、不含 prompt 內容）；**push 前先告知 Miyago**
- [ ] P4 bench 拆分已於 2026-10-23 核准（含建立 private repo
      `miyago9267/shoal-bench`），最後執行：P1 到 P3b 全部合併且
      `render_equiv.py` 對基準輸出逐位元組相同之後才開始

## P1：刪除死檔

目標：沒有「可編輯但無效」的檔；R3 防回歸。

### 檔案

- 刪除（53 檔，155,618 bytes）：
  - `hosts/claude/src/agents/{applier,executor,plan-critic,researcher,scout,
    security-executor,security-reviewer,verifier,watcher}.md`（不含 `Explore.md`）
  - `hosts/claude/src/claude-md.bootstrap.md`
  - `hosts/claude/src/skills/shoal-orchestration/SKILL.md`
  - `hosts/claude/src/skills/shoal-orchestration/references/
    {orchestration-policy,workflow-extensions}.md`
  - `hosts/codex/src/agents/` 同上 9 個 role（不含 `sol-executor.md`）、
    `hosts/codex/src/agents-md.{bootstrap,orchestration}.md`
  - `hosts/agy/src/agents/` 同上 9 個 role、`hosts/agy/src/rules/shoal-agy.md`、
    `hosts/agy/src/skills/shoal-orchestration/SKILL.md`
  - `hosts/grok/src/agents/` 同上 9 個 role（保留 `src/rules`、`hooks`、
    `config.snippet.toml`）
  - `hosts/opencode/src/roles/` 同上 9 個 role
- 修改：`tools/render.py`（`render_agy` 移除 `_versioned_rules` 呼叫與對 src 的
  依賴；`merge_core_policy` 加檔案系統檢查：`[policy.documents]` 與
  `role_text = "core"` 的 role 輸出路徑只要 `src/<path>` 存在即 `RenderError`
  指名該路徑）、`tests/*`（見下）、`package.json`（lint 排除清單若引用被刪
  路徑）、`.github/workflows/python-tests.yml`（paths 補 `hosts/agy/**`、
  `hosts/grok/**`、`hosts/opencode/**`、`prompts/**`，pull_request 與 push 兩處；
  新增獨立的 `render --check` 步驟）。
- 新增：`tools/render_equiv.py`（等價證明工具，約 100 行，含 relay overlay 的
  第二組輸出）、其單元測試。`tests/fixtures/relay/relay.binding.toml` 已存在
  （與 `bench/ab/relay.binding.toml` 只差開頭註解），不必搬檔；T1.1 的工具直接
  使用它，這是 P4 移除 `bench/` 後仍能比對 relay 的前提。

### 任務

- [x] T1.1 先寫 `tools/render_equiv.py` 與測試（Red：對刻意改一個位元組的 temp
  ref 必須非 0）；除了六個 host 的預設輸出，還要對每個 ref 的 relay root 執行
  `--host claude-plugin --write --overlay tests/fixtures/relay/relay.binding.toml`
  （兩個 ref 各一個獨立目錄，不與預設輸出共用），把 relay 輸出併入雜湊比較；
  測試另含「只改 relay 路徑（例如 `relay/shell.md` 一個位元組）也必須非 0」。
  在 main 對 main 自證退出 0
- [x] T1.2 新增測試（R3，Red 先行）：temp root 放入 `hosts/agy/src/rules/
  shoal-agy.md`，另一個放入 `hosts/claude/src/agents/scout.md`，render 皆須非 0
  結束且 stderr 含該路徑；再加 `hosts/claude/src/claude-md.bootstrap.md` 與
  opencode `hosts/opencode/src/roles/scout.md` 的案例；另一個案例確認真實樹
  （P1 刪檔後）render 退出 0，且 grok 的 `src/rules/shoal-grok.md`、claude 的
  `src/agents/Explore.md`、codex 的 `src/agents/sol-executor.md` 不觸發
- [x] T1.3 `merge_core_policy` 加檔案系統檢查（見上）；`render_agy` 移除
  `_versioned_rules`
- [x] T1.4 刪 53 檔
- [x] T1.5 修復 35 個因讀死檔而失敗的測試（粗暴刪除實測，10 個模組）：
  `test_render_agy`（12，改為 marker 取自 dist 並等於 `VERSION`）、
  `test_role_contracts`（8，legacy fixture 改用 `tests/fixtures/legacy-src/`
  最小樣本，不再複製 `hosts/claude/src/agents/scout.md`）、
  `test_access_derivation`（3）、`test_core_policy_hosts`（agy 3 個子案例）、
  `test_render_claude`（2，marker 測試改讀 dist）、`test_delegation_default`
  （2，`OtherHostsRoleTests` 不再讀 `hosts/codex/src/agents`）、
  `test_core_policy`（2，刪「core 等於 legacy」的比對測試）、
  `test_relay_render`、`test_generic_md_render`、`test_direction_milestone`
  （各 1，後者的 legacy 比對改讀 dist）
  實作紀錄（2026-10-23）：實際失敗為 `test_render_agy`、`test_role_contracts`（6）、
  `test_render_claude`（2）、`test_core_policy`（2）、`test_direction_milestone`、
  `test_render_opencode`（2，`hosts/opencode/src` 整個目錄消失）；其餘模組的失敗
  在 R3 與 render 修改後不再發生。legacy 樣本由 `TempHost.legacy_sources` 在測試內
  產生（含 grok 要求的 `model:` frontmatter），沒有新增 `tests/fixtures/legacy-src/`；
  `test_core_and_addenda_reassemble_the_legacy_text` 與 core 對 legacy 的 wording
  比對一併刪除（比對對象已不存在）。
- [x] T1.6 `docs/` 與 `core/README.md` 內提到上述路徑的說明更新
- [x] T1.7 `python-tests.yml`：paths 補 `hosts/agy/**`、`hosts/grok/**`、
  `hosts/opencode/**`、`prompts/**`（兩處），並新增獨立步驟，對六個 host 與
  claude-plugin 執行 `render --check`（失敗訊息直接，成本小於 5 秒；輸出在 P1
  不變，所以立即可用）
- [x] T1.8 共同驗收；PR 描述貼 `render_equiv.py` 的總雜湊（預設與 relay 各一）

### 驗收

共同驗收，加上：`git grep -n "hosts/.*/src/\(agents\|roles\|skills\)"` 只剩
`Explore.md`、`sol-executor.md`、grok `src/rules`、`hooks`、
`config.snippet.toml`；R3 測試綠，且把 `hosts/agy/src/rules/shoal-agy.md` 與
`hosts/claude/src/agents/scout.md` 放進 temp root 時 render 非 0 並印出該路徑，
真實樹不觸發。

### 風險

低到中。agy 的 marker 目前是 `policy-frames/bootstrap.md` 的手寫字面值，與
`VERSION` 的一致性原本由 src 路徑間接檢查，T1.5 必須補上對 dist 的直接檢查，
否則 `VERSION` 升版時不會被發現漂移。dotfile 沒有引用被刪路徑（已 grep）。
`hosts/codex/policy-frames/skill.md` 也是死檔（codex omit 了 skill 文件），但它
是 frame 而非 legacy 副本，本 phase 不刪，列入 P2 搬移時一併決定。

## P2：文字從 TOML 搬到 `prompts/*.md`

目標：R1；輸出逐位元組不變（R2）。

### 檔案

- 新增：`prompts/`（目錄與語法見 SPEC Architecture）、
  `tools/migrate_text.py`（一次性，PR 最後一個 commit 移除）。
- 搬入（`git mv` 保留歷史）：`hosts/*/frames/*`、`hosts/*/policy-frames/*`、
  `hosts/claude/relay/shell.md`。
- 轉換後刪除：`core/policy/{bootstrap,extensions,orchestration,skill}.toml`、
  `core/contracts/*.toml`（保留 `handback.schema.json`）、
  `hosts/*/addenda/*.toml`、`hosts/*/policy-addenda/*.toml`、
  `hosts/claude/relay/policy-addenda/orchestration.toml`。
- 修改：`tools/contracts.py`、`tools/render.py`、`tools/new_host.py`、
  `hosts/{claude,codex,agy,grok}/binding.toml`（移除 description）、
  `core/README.md`、`docs/new-host.md`、`package.json`（lint 排除
  `#prompts`，並移除已搬走的 `#hosts/*/frames` 等）、
  `.github/workflows/opencode-plugin.yml`（paths 加 `prompts/**`；
  `python-tests.yml` 的已在 P1 補）、`tests/render_helpers.py`、`tests/repo_fixtures.py`、
  `tests/test_core_policy.py`、`tests/test_render_codex.py`、
  `tests/test_role_contracts.py`。

### 任務

- [ ] T2.1 先改測試 helper：`HostRenderCase.setUp` 與 `repo_fixtures` 複製
  `prompts/`；fixture 寫法改成 md（此時測試應紅，因 loader 尚未支援）
- [ ] T2.2 `contracts.py`：`parse_markdown_contract`、`parse_markdown_addenda`、
  `parse_markdown_blocks`（description / text），單元測試涵蓋：頭尾空行、
  內嵌空行、`sep` 預設、`required`、`join`、重複 id、marker 前有內容、
  正文含 marker 字串、含 CR、缺 `kind`、未知屬性
- [ ] T2.3 `migrate_text.py`：讀舊 TOML、寫 md、再用新 loader 讀回，逐條斷言
  `(id, kind, sep, required, at, join, text)` 全等；涵蓋 core policy、contracts、
  所有 host addenda、policy-addenda、relay addendum、binding description
- [ ] T2.4 `render.py` 切換 loader 與路徑；`explain_policy` 一併改
- [ ] T2.5 `render.py` 寫死的句子搬到 `prompts/hosts/claude/text.md`（`<!-- text:
  key -->`）：relay write rules、run step、
  relay description 後綴、plugin / marketplace / hook description；
  `render.py` 只留 key 名稱。run step 拆成兩個 placeholder：`{{timeout}}`
  （runner 的秒數）與 `{{bash_timeout_ms}}`（Bash 工具的毫秒數），後者由 render
  以 `(timeout + BASH_MARGIN_SECONDS) * 1000` 計算後代入（`render.py:656-659`、
  `:670-672`），文字內不得出現算式；`relay_shell` 的 values 多一個
  `bash_timeout_ms`，未替換 placeholder 檢查（`{{` 殘留）維持
- [ ] T2.6 role description 搬到 `prompts/hosts/<host>/descriptions.md`，
  `_frontmatter` 等改讀它；agy 的多行 description 保留尾端換行語意
- [ ] T2.7 搬 frames / policy-frames / relay；決定 `codex/policy-frames/skill.md`
- [ ] T2.8 移除 TOML 文字載入路徑、`migrate_text.py`；更新說明文件（`python-tests.yml`
  的 paths 與 `render --check` 步驟已在 P1 完成，此處只確認 `opencode-plugin.yml`
  的 paths 含 `prompts/**`）
- [ ] T2.9 共同驗收；PR 描述貼 `migrate_text.py` 的相等斷言結果與
  `render_equiv.py` 總雜湊

### 驗收

共同驗收，加上：`git grep -n "'''" -- core hosts/*/addenda hosts/*/policy-addenda`
無輸出；`git grep -nE "RELAY_WRITE_RULES|shoal policy bootstrap" tools/` 無輸出；
`prompts/` 以外沒有送進 model 的長文字（人工抽查 `render.py`）。

### 風險

中到高：這是全計畫最大的改動面（約 3.4k 行 TOML 轉換、loader 重寫、5 個 host
的路徑）。位元組漂移是主要風險，由 `migrate_text.py` 的相等斷言與
`render_equiv.py`（含 relay overlay 輸出，relay 外殼的 run step 就在這個 phase
被搬動）雙重把關。fixture 複製漏 `prompts/` 會造成大量假失敗，所以 T2.1 先做。

## P3a：停止 commit golden，收斂文字測試

目標：R4（golden 部分）、R6；輸出不變。

### 檔案

- 刪除：`tests/golden/`（107 檔、337,521 bytes）、`tools/refresh_golden.py`。
- 修改：`tests/render_helpers.py`（移除 `golden_files`、`golden_view`、
  `assert_golden_equal`、`GOLDEN_HASHED` 及 `HostRenderCase` 的三個 golden 測試）、
  `tests/test_render_{claude,codex,agy,grok,opencode}.py`（移除
  `GoldenTests`、`RefreshGoldenTests`）、`tests/test_templates.py`、
  `tests/test_policy.py`、`tests/test_core_policy.py`、
  `tests/test_core_policy_hosts.py`、`tests/test_delegation_default.py`、
  `tests/test_direction_milestone.py`（依 triage 表）、`package.json`
  （移除 `#tests/golden`）。獨立的 `render --check` CI 步驟已在 P1 加入，本
  phase 只需確認它涵蓋 `test_render_check.py` 的同一組 host。
- 新增：`tests/test_render_check.py`（六個 host 的 `render --check` 與結構斷言）。
- 保留：`tests/test_adapter_golden.py` 與 `tests/fixtures/adapter_golden.json`
  （guard adapter 的 fixture，與 render golden 無關）。

### 任務

- [ ] T3.1 逐檔 triage 表寫入 PROGRESS.md：每個候選測試標 keep / drop /
  convert，並寫理由（判準見 SPEC D4）；Miyago 抽看後再刪
- [ ] T3.2 先寫 `tests/test_render_check.py`（Red -> Green）：
  六個 host `render --check` 退出 0；agy、grok、claude 的 marker 等於各自
  `VERSION`；codex 的 mirror 與其來源相等；所有輸出不含 `{{`；每個 core role
  在每個提供它的 host 都有輸出；frames 與 addenda 不出現在 dist；
  每個 lock `required_fragments` 存在於其 surface
- [ ] T3.3 刪 golden 資料與基礎設施，修 import
- [ ] T3.4 依 triage 表刪文字內容測試
- [ ] T3.5 確認 P1 加的 `render --check` 步驟仍涵蓋全部輸出（golden 移除後它是
  唯一直接指出「輸出與來源不符」的 CI 步驟）；故意改 `prompts/` 一個字而不
  `--write`，該步驟必須變紅
- [ ] T3.6 共同驗收；PR 描述貼測試數與行數變化

### 驗收

共同驗收，加上：測試總數與行數下降且每個被刪的測試都在 triage 表有理由；
行為測試清單（validation、`--check` / `--write`、權限推導、installer、guard、
relay、plugin）數量不減；故意改 `prompts/` 一個字而不 `--write` 時，
`render --check` 與 CI 變紅。

### 風險

中。刪測試是不可逆的判斷，所以 triage 表先給 Miyago 看。若某個 wording 測試
其實保護的是 lock 沒涵蓋的行為契約，會失去回歸保護；保守原則：有疑問就轉成
結構斷言而不是刪。

## R + P3b：停止 commit `hosts/claude/dist`

2026-10-23 Miyago 核准，排在 P3a 之後、P4 之前。順序：dotfile 修改 -> R（直接
push 到 main）-> P3b PR。

### Lock renewal R（先上 main）

- [ ] TR.1 `LOCK.json`：13 個 claude surface 的 `path` 由
  `hosts/claude/dist/...` 改為 `plugins/claude/...`（`id`、預算、
  `required_fragments`、`version_file` 不變）
- [ ] TR.2 同 commit 更新 `install/validate_prompt_lock.py` 的
  `REQUIRED_SURFACE_PATHS` 與 `tests/test_prompt_document_lock.py`、
  `tests/test_core_policy.py:444` 的路徑引用；**不含**任何 prompt 內容、
  `VERSION` 或輸出檔
- [ ] TR.3 本機驗證：`validate_prompt_lock.py --base-ref origin/main
  --allow-lock-update` 通過；不帶旗標時失敗並指出 `LOCK.json changed`
- [ ] TR.4 單一 commit，message 含獨立一行 `Lock-Renewal: approved`，無 AI
  署名；**push 前先告知 Miyago**（P3b 已核准，但這是 main 歷史上不可逆的一步），
  再直接 push 到 main；確認 push 事件的 CI lock 步驟綠

### P3b

- 檔案：刪 `hosts/claude/dist/`（15 檔）；修改 `tools/render.py`
  （claude host 的 `--check` 只驗證不比對 dist，committed 形態由
  `--host claude-plugin --check` 驗證）、`tools/shoal_install.py:49`、
  `tools/shoal_update.py`、`install/modules.json:53`（`EXPLORE_DIST` 改指
  `plugins/claude/agents/Explore.md`）、`tests/test_shoal_update.py:208`、
  `tests/test_generic_md_render.py:691-699`、`tests/test_render_claude.py`、
  `.gitignore`；repo 外：dotfile `script/common/check_agent_rule_sync.sh:239`
  改指 `plugins/claude/skills/shoal-orchestration/SKILL.md`。
- [ ] TB.1 dotfile 修改先上（舊路徑在 P3b 前仍存在，所以順序安全）：在
  `~/dotfile` 把 `script/common/check_agent_rule_sync.sh:239` 改指
  `plugins/claude/skills/shoal-orchestration/SKILL.md`。動手前以
  `grep -rn "claude/dist" ~/dotfile`（排除 `docs/specs`）重新確認讀取者；
  2026-10-23 實測只有這一處，`setup_gemini.sh` 讀的是 agy dist，不受影響。
  dotfile commit 無 AI 署名；`check_agent_rule_sync.sh` 在 shoal 舊路徑仍存在時
  必須通過
- [ ] TB.2 repoint `EXPLORE_DIST` 與測試
- [ ] TB.3 刪 `hosts/claude/dist/`，調整 claude host 的 `--check` / `--write`
- [ ] TB.4 共同驗收；`shoal_install.py --update`（dry-run）在 temp HOME 通過

### 驗收

共同驗收；renewal 後 lock 在 push 事件綠；`git grep "claude/dist"` 只剩
說明文件的歷史敘述。

### 風險

中。renewal 是不可逆的 main 歷史；trailer 放錯位置會紅燈。dotfile 與 shoal
分屬兩個 repo，順序錯誤會讓 `check_agent_rule_sync.sh` 短暫失敗，所以先改
dotfile。收益小（15 檔），這也是列為選配的原因。

## P4：bench 拆成 `miyago9267/shoal-bench`

目標：R7。

已核准（Miyago 2026-10-23），最後執行：P1 到 P3b 全部合併且 `render_equiv.py`
對基準輸出逐位元組相同之後才開始。

### 檔案

- 移出（shoal 刪除）：`bench/`（440 檔）與 28 個 bench 專用測試模組：
  `test_adaptive_routing`、`test_astra_routing`、`test_benchmark_role_fitness`、
  `test_benchmark_routing`、`test_claude_eval_smoke`、`test_claude_live_probe`、
  `test_decision_checkpoint`、`test_evaluate_dispatch`、`test_execution_contract`、
  `test_intent_review_matrix`、`test_intent_runtime_matrix`、
  `test_quality_cost_frontier`、`test_review_intent_contract`、
  `test_role_fitness_adjudicator_live`、`test_role_fitness_adjudicator_matrix`、
  `test_role_fitness_claude`、`test_role_fitness_content_failure`、
  `test_role_fitness_content_report`、`test_role_fitness_content_rerun_counting`、
  `test_role_fitness_fixtures`、`test_role_fitness_routing_matrix`、
  `test_role_fitness_scorecard`、`test_run_ab_relay`、`test_run_role_fitness_content`、
  `test_run_role_fitness_live`、`test_run_role_fitness_rerun`、
  `test_run_role_fitness_stage_characterization`，以及只被它們使用的
  `tests/fixtures`（T4.2 以 grep 確認）。
- 修改（shoal）：`.github/workflows/python-tests.yml`（paths 移除 `bench/**`；
  `py_compile` 行移除 `bench/evaluate_dispatch.py`）、`package.json`（移除
  `#bench/...` 排除）、`tests/test_{templates,install,install_hooks,
  stage_smoke_home,prompt_document_lock}.py` 的 `sys.path.insert(... "bench")`
  殘留、`tests/test_relay_render.py`（`OVERLAY` 由
  `bench/ab/relay.binding.toml` 改指 `tests/fixtures/relay/relay.binding.toml`，
  測試保留不刪；兩個檔內容相同，只差開頭註解）、`docs/reference.md:73` 與 README 的 bench 敘述、`install/routing_contract.py`
  docstring、各 `docs/specs/*benchmark*` 加一行指向新 repo。
- 新增（shoal-bench）：`bench/shoal_root.py`、`README.md`（說明
  `SHOAL_ROOT`、`SHOAL_AB_PLUGIN_REF`）、`.github/workflows/tests.yml`
  （checkout shoal 到 `../shoal`，跑搬出的測試）。

### 任務

- [ ] T4.1 在 shoal 的 temp clone 上驗證：移除 `bench/` 與 28 個模組後，其餘
  測試全綠（nobench 實測已知：只有這 28 個 import 失敗與 1 個 overlay 測試）
- [ ] T4.2 列出只被搬出測試使用的 fixture（grep），一併納入路徑清單
- [ ] T4.3 `git filter-repo`（fresh clone）：保留 `bench/`、28 個測試與 fixture
  的歷史；驗證 `git log --follow bench/ab/run_ab.py` 的 commit 數不少於 shoal
  中該檔（bench 目錄共 18 個 commit）
- [ ] T4.4 shoal-bench：新增 `shoal_root.py`，替換所有以 `parents[1]` 推 shoal
  路徑的 `sys.path` 組合與 `run_ab.py` 的 `ROOT`（`export_tree` 對 `SHOAL_ROOT`
  做 `git archive`）。`docs/benchmarks` 是相容面（SPEC D5）：
  `benchmark_routing.py:39`、`claude_eval_smoke.py:72`、`role_fitness_claude.py:50`
  與測試 `test_claude_eval_smoke.py:645`、`test_role_fitness_content_failure.py:26`、
  `test_role_fitness_claude.py:1224` 全部改經 `shoal_root.py` 取路徑
  （`shoal_root.BENCHMARKS`、`shoal_root.SHOAL_ROOT`），不再用 `ROOT / "docs"`；
  `tests/fixtures/benchmark_routing`（`benchmark_routing.py:38`）依 T4.2 的結果
  同樣處理。在 shoal-bench 跑搬出的 28 個模組全綠，其中 `SHOAL_ROOT` 指向 shoal
  main
- [ ] T4.5 建立 private repo 並 push（已核准 2026-10-23）
- [ ] T4.6 shoal 側刪除與修改；共同驗收；PR 描述貼兩邊的測試結果

### 驗收

共同驗收，加上：shoal 內 `git grep -n "bench/"` 只剩 CHANGELOG 與歷史
spec 的敘述；shoal-bench 的 CI 在 `SHOAL_ROOT` 指向 shoal main 時全綠；
`SHOAL_AB_PLUGIN_REF=<branch>` 能對 shoal 的 branch 出 plugin；shoal-bench 內每個
`docs/benchmarks` 引用都經 `shoal_root.py` 解析
（`grep -rn "docs.*benchmarks"` 在 shoal-bench 只命中 `shoal_root.py` 與說明文字），
且 shoal-bench 測試在 `SHOAL_ROOT` 指向 shoal main 時全綠。

### 風險

中。bench 需要 shoal 的 `install/`、`hooks/`、`tools/`，shoal 的這些檔改名或
搬動會讓 shoal-bench 的 CI 紅，需在 shoal 的 CHANGELOG 註明相容面。`filter-repo`
會改寫 hash，只在 fresh clone 做，不動 shoal 本身的歷史。

## 驗證

- [ ] 所有 phase 的 PR 合併
- [ ] 測試通過（見 TESTS.md）
- [ ] 文件更新（`core/README.md`、`docs/new-host.md`、`docs/reference.md`）

## 備註

<!-- Batch 完成後用 spec-archive.sh tasks text-first 封存 -->
