---
spec: text-first
created: 2026-10-22
---

# Progress: Text first

> Spec: `docs/specs/text-first/SPEC.md`

## Phase 0: Spec 與量測

> Status: in-progress

- 目標：記錄基準、確認每個消費者，取得 Miyago 對 Open Questions 的決定。
- 2026-10-23 量測（main `863943c`）：
  - 全套測試 1915 個、297 秒、OK（skipped=1）。
  - 死檔 53 個（155,618 bytes），粗暴刪除造成 35 個失敗或錯誤。
  - 移除 `bench/` 後 28 個測試模組無法 import。
  - 對 main archive 全部 host `--write` 後，9 個輸出目錄與 working tree
    `diff -r` 皆相同（等價證明的基準）。
- 2026-10-23 rebase 到 main `8da4d0f`（PR #34 只刪 `docs/archive`、
  `docs/assets/reel-*`；`tools/`、`tests/`、`hosts/`、`core/` 無變動，量測仍有效；
  `docs/benchmarks` 仍存在）。
- 2026-10-23 決定（Miyago）：P3b 納入本案，排在 P3a 之後（含 lock renewal 與
  dotfile 修改；R 的 push 前須告知 Miyago）；P4 bench 拆分已核准，最後執行
  （P1 到 P3b 輸出逐位元組相同之後）；CI paths 補齊與獨立 `render --check`
  放 P1。plan-critic REVISE 的三項 blocker 已併入 spec。
- 待決：無。

## Phase 1: 刪除死檔

> Status: complete（PR #35，CI 三平台綠燈，待合併）

- 目標：53 檔刪除、R3 防回歸、`render_equiv.py`。
- 基準雜湊（main `8da4d0f`，`render_equiv.py` 輸出）：
  - 預設（103 檔）：`f0a3f34becf2342d21322e0ecb60de411b088b924f9ccdfddb213c1c68a71057`
  - relay（27 檔）：`87d4a9a4aaed55028a9316573d91d5422370c42fa3dc24cb0c6ebdde4040ac59`
- 2026-10-23：`render_equiv.py --base 8da4d0f --head HEAD` 退出 0，兩組雜湊與基準相同；
  刪除 53 檔（155,618 bytes）；全套測試 1920 個、約 297 秒；lock（不帶旗標）通過。

## Phase 2: 文字搬到 `prompts/`

> Status: complete（PR #36，CI 三平台綠燈，待合併）

- 目標：R1、R2。
- 2026-10-23 `migrate_text.py` 的結果行（已於最後一個 commit 移除腳本）：

  ```text
  migrate_text: OK 54 files, 251 clauses, 133 addenda, 38 descriptions;
  (id, kind, sep, required, at, join, text) all equal
  ```

  腳本在乾淨的 origin/main 上重跑，產生的
  `prompts/` 與提交的檔案逐檔相同（差別只有 `git mv` 搬入的 frames、`relay/shell.md` 與手寫的
  `text.md`）。
- 2026-10-23 `render_equiv.py --base origin/main --head HEAD` 退出 0，兩組雜湊與 P1 基準相同：
  - 預設（103 檔）：`f0a3f34becf2342d21322e0ecb60de411b088b924f9ccdfddb213c1c68a71057`
  - relay（27 檔）：`87d4a9a4aaed55028a9316573d91d5422370c42fa3dc24cb0c6ebdde4040ac59`
- 全套測試 1942 個（P1 的 1920 加 `test_prompts_md` 的 22 個），約 297 秒；lock（不帶旗標）通過；
  `npm run lint:md` 通過（`#prompts` 排除）。
- 刪除：`core/policy/{bootstrap,extensions,orchestration,skill}.toml`、`core/contracts/*.toml`（保留
  `handback.schema.json`）、所有 `addenda`、`policy-addenda` 與 relay addendum 的 TOML、
  `codex/policy-frames/skill.md`（死檔）、四個 binding 內的 38 段 description。
- 已知取捨：TOML 檔頭與段間註解不搬（md 語法不允許 marker 之前有內容）。

## Phase 3a: 停止 commit golden、收斂測試

> Status: complete（PR #37，CI 三平台綠燈，待 Miyago 抽看 triage 表後合併）

- 目標：R4（golden）、R6。
- 基準（origin/main `802b981`）：全套 1942 個測試、約 297 秒、OK（skipped=1）。

### Triage 表（T3.1）

判準（SPEC D4）：測試的唯一 oracle 是 golden、另一份 render、或某句 prompt 是否存在，且該句不是 lock 的
`required_fragments` 以外的行為契約 -> drop；否則 keep。**有疑問就 convert**（改成結構斷言），不直接刪。

三種處置在這裡的意思：

- **drop**：刪除，理由欄寫明為何沒有回歸保護的損失。
- **convert**：原測試的 prose 斷言丟棄，只留下三類結構斷言：marker 等於 `VERSION` 這類結構；hook、guard、bench
  會解析的協定符號（狀態名、欄位名、lane 標籤、呼叫形狀）；lock 沒涵蓋、改掉會改變派工或核准行為的句子（每個契約
  一句）。這三類分別放在 `tests/test_render_check.py` 與 `tests/test_policy.py`。
- **keep**：不動（或只改類別名）。

被刪的文字回歸由三道關卡承擔：`render --check`（CI 有獨立步驟，
`test_render_check` 在本機跑同一組 host）、prompt lock（預算與
`required_fragments`）、上述結構斷言。`test_adapter_golden.py` 與
`fixtures/adapter_golden.json` 是 guard adapter 的 fixture，與 render golden
無關，保留。

未列入下表的測試模組沒有被動到（installer、guard、relay、access derivation、model catalog 等行為測試）。

#### test_render_agy（render_helpers.HostRenderCase）

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `test_render_is_byte_identical_to_golden` | drop | 唯一 oracle 是 tests/golden（隨本 phase 刪除） | `render --check`（CI 步驟與 test_render_check） |
| `test_golden_records_source` | drop | 只驗證 golden 的 SOURCE 檔 | - |
| `test_committed_dist_matches_golden` | drop | 唯一 oracle 是 tests/golden（隨本 phase 刪除）；dist 與 render 的一致性已由 `--check` 承擔 | `render --check` |

#### test_render_grok（render_helpers.HostRenderCase）

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `test_render_is_byte_identical_to_golden` | drop | 唯一 oracle 是 tests/golden（隨本 phase 刪除） | `render --check`（CI 步驟與 test_render_check） |
| `test_golden_records_source` | drop | 只驗證 golden 的 SOURCE 檔 | - |
| `test_committed_dist_matches_golden` | drop | 唯一 oracle 是 tests/golden（隨本 phase 刪除）；dist 與 render 的一致性已由 `--check` 承擔 | `render --check` |

#### test_render_opencode（render_helpers.HostRenderCase）

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `test_render_is_byte_identical_to_golden` | drop | 唯一 oracle 是 tests/golden（隨本 phase 刪除） | `render --check`（CI 步驟與 test_render_check） |
| `test_golden_records_source` | drop | 只驗證 golden 的 SOURCE 檔 | - |
| `test_committed_dist_matches_golden` | drop | 唯一 oracle 是 tests/golden（隨本 phase 刪除）；dist 與 render 的一致性已由 `--check` 承擔 | `render --check` |

#### test_render_claude

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `GoldenTests.test_render_is_byte_identical_to_golden` | drop | 唯一 oracle 是 tests/golden（隨本 phase 刪除） | `render --check` |
| `GoldenTests.test_committed_dist_matches_golden` | drop | 唯一 oracle 是 tests/golden（隨本 phase 刪除） | `render --check` |
| `GoldenTests.test_golden_records_source` | drop | 只驗證 golden 的 SOURCE 檔 | - |
| `RefreshGoldenTests.test_reimports_from_a_git_repo` | drop | 測試 tools/refresh_golden.py，該工具隨本 phase 刪除 | - |
| `RefreshGoldenTests.test_from_dist_copies_own_dist_and_records_shoal_sha` | drop | 測試 tools/refresh_golden.py，該工具隨本 phase 刪除 | - |
| `RefreshGoldenTests.test_without_source_or_from_dist_is_rejected` | drop | 測試 tools/refresh_golden.py，該工具隨本 phase 刪除 | - |
| `HostVersionTests.test_skill_marker_equals_version_in_dist_and_golden` | convert | 同時比對 dist 與 golden；golden 部分失效 | test_render_check.test_markers_equal_the_host_version |
| `HostVersionTests.test_bootstrap_marker_equals_version_in_dist_and_golden` | convert | 同上 | test_render_check.test_markers_equal_the_host_version |

#### test_render_codex

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `GoldenTests.test_render_is_byte_identical_to_golden` | drop | 唯一 oracle 是 tests/golden（隨本 phase 刪除） | `render --check` |
| `GoldenTests.test_committed_templates_match_golden` | drop | 唯一 oracle 是 tests/golden（隨本 phase 刪除） | `render --check` |
| `GoldenTests.test_golden_records_source` | drop | 只驗證 golden 的 SOURCE 檔 | - |
| `GoldenTests.test_plugin_policy_mirror_is_rendered` | keep | mirror 等於 render 輸出，是結構斷言（只是原本放在 GoldenTests 類別）；改放 MirrorTests | 同時由 test_render_check 的 mirror 測試涵蓋 |

#### test_render_opencode

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `RefreshGoldenTests.test_imports_two_source_repos` | drop | 測試 tools/refresh_golden.py，該工具隨本 phase 刪除 | - |

#### test_claude_plugin

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `GoldenTests.test_render_is_byte_identical_to_golden` | drop | 唯一 oracle 是 tests/golden（隨本 phase 刪除） | `render --check --host claude-plugin` |
| `GoldenTests.test_committed_files_match_render` | keep | committed 檔等於 render 輸出（結構）；類別改名 CommittedOutputTests | - |
| `GoldenTests.test_claude_dist_is_not_changed_by_the_plugin_target` | keep | plugin 目標不改 claude dist 的檔案數（結構）；類別改名 | - |
| （其餘 53 個） | keep | plugin 結構、guard 副本、版本、hook 註冊、compat shim、quoting | - |

#### test_generic_hosts

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `test_generic_hosts_have_no_golden_and_a_dist_next_to_the_binding` | convert | 移除「沒有 golden」那一行（目錄已不存在，斷言無意義）；dist 位置斷言保留 | 改名 test_generic_hosts_have_a_dist_next_to_the_binding |
| （其餘 3 個） | keep | generic-md host 的 `--check` 與條款出現 | - |

#### test_render_equiv

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| （setUpClass 的 ignore_patterns） | convert | ignore 清單移除 `golden`（目錄已不存在）；測試本身不變 | - |

#### test_render_grok

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `test_agents_are_rendered_from_core_not_from_src` | drop | 迴圈走訪 `hosts/grok/src/agents/*.md`，P1 刪檔後該目錄不存在，測試空轉；R3 防回歸（P1）已涵蓋「src 不得蓋掉 core 輸出」 | P1 的 R3 測試 |

#### test_core_policy

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `RepoPolicyTests.test_claude_core_preview_keeps_lock_required_fragments` | convert | 斷言 claude 的 12 個 lock 片段；範圍小於 lock 且 P3b 後路徑會變 | test_render_check.test_every_lock_required_fragment_is_in_its_surface（涵蓋所有 surface） |
| （其餘 49 個）PolicyContractFormatTests、PlaceholderTests、OmitAndRequiredTests、RepoPolicyTests（鎖定 policy_text / omit / replace / addenda / required 集合）、PolicyRenderCase | keep | 機制與設定鎖定：格式驗證、placeholder、omit / required / replace、`--explain-policy`、`--policy-preview`；不比對 prompt 句子 | - |

#### test_templates

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `test_policy_is_native_typed_and_post_hoc` | drop | oracle 是句子是否存在；與 test_policy 的 native spawn 測試重複 | token 見 ProtocolTokenTests |
| `test_policy_exposes_proactive_role_decision_cues` | drop | 純 prose 句子；與 test_policy 的 routing 測試重複 | - |
| `test_policy_exposes_adaptive_route_and_discovery_contract` | convert | prose 丟棄；backtick 協定符號（intent、change_impact、checkpoint、execution_scope 等）有 hook 與 bench 消費 | ProtocolTokenTests.test_codex_policy_keeps_its_protocol_tokens |
| `test_policy_preserves_risk_triggered_plan_review` | drop | prose；`Risk precedes size` 等句子不是 lock 片段也不是協定符號；`Two automatic REVISE` 一句保留在契約表 | BehaviourContractTests（REVISE x2） |
| `test_policy_preserves_parent_ownership_and_no_untyped_fallback` | convert | ownership 一句是 lock 片段；no-untyped-fallback 是行為契約，保留一句 | BehaviourContractTests（untyped fallback、delegation unavailable） |
| `test_verifier_uses_calibrated_outcomes` | convert | 逐句 regex 丟棄（verdict 定義已是 lock 片段）；保留 verdict 詞彙與 plan-critic / verifier 互不渗透 | RoleBoundaryTests |
| `test_verifier_supports_direction_checkpoint_contract` | convert | direction_checkpoint 協定符號 | RoleBoundaryTests.test_verifier_supports_the_direction_checkpoint_tokens |
| `test_runbook_is_native_only` | convert | runbook 句子丟棄；保留 stage_smoke_home.py 存在、NATIVE_OK 由 verify_dispatch 產生且 runbook 引用、沒有 ADAPTER_OK | 改名 test_runbook_names_the_native_smoke_flow |
| （其餘 5 個）exact_agents_table、role_manifest、model_routing、rejects_forced_adapter_keys、validator_rejects_nonpackaged_keys | keep | validator 行為與設定值（model / effort 由 tier 推導），不是 prompt 文字 | - |

#### test_policy

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `PolicyTests.test_stamp_and_roles_remain_consistent` | keep | marker 等於 VERSION、每個 role 都列在政策（結構） | StructureTests |
| `PolicyTests.test_native_spawn_policy_is_typed_bounded_and_no_override` | convert | typed spawn 的呼叫形狀是協定符號；`agents.spawn_agent` 不得出現；never-retry-untyped 是行為契約 | ProtocolTokenTests、BehaviourContractTests |
| `PolicyTests.test_policy_proactively_routes_suitable_work_and_parallel_surfaces` | drop | prose 路由句子；role 名稱由 StructureTests 保證；無協定符號 | - |
| `PolicyTests.test_low_risk_work_uses_one_targeted_acceptance_check_without_verifier` | convert | 行為契約（低風險不加 verifier），單句 | BehaviourContractTests |
| `PolicyTests.test_policy_automatically_escalates_judgment_work_without_user_dispatch` | drop | prose；model 對應由 tier 推導與 test_render_codex 的 CatalogTests 保證 | - |
| `PolicyTests.test_bootstrap_automatic_route_does_not_wait_for_role_request` | drop | prose | - |
| `PolicyTests.test_bootstrap_dispatches_bounded_roles_without_fragmenting_outcomes` | drop | prose；`A clear request to fix or finish is one outcome` 與 `does not edit files itself` 已是 bootstrap 的 lock 片段 | lock |
| `PolicyTests.test_policy_keeps_mechanical_roles_on_the_luna_baseline` | drop | prose；model 對應由 tier 推導保證 | - |
| `PolicyTests.test_policy_defines_general_mode_decision_checkpoint_contract` | convert | checkpoint schema 欄位名與 `shoal-decision-checkpoint-v1` 是協定符號（bench/decision_checkpoint.py 解析）；其餘 prose 丟棄 | ProtocolTokenTests |
| `PolicyTests.test_policy_defaults_to_autonomous_decisions_and_escalates_only_material_choices` | drop | prose；`not a step-by-step approval workflow` 等無協定符號 | - |
| `PolicyTests.test_policy_runs_clear_outcomes_and_stops_at_explicit_boundaries` | convert | `Outcome-level continuation`、`execution_scope`、`phase boundary is progress reporting`、`presence gates` 已是 lock 片段；其餘為 token | ProtocolTokenTests（execution_scope、continuation_mode、stop_condition） |
| `PolicyTests.test_attended_clear_scope_task_does_not_ask_for_a_mode` | drop | 兩句 prose | - |
| `PolicyTests.test_policy_keeps_parent_accountability_without_local_edit_escape_hatch` | convert | 行為契約：main 不改檔、不得 untyped fallback、role 不可用就回報；removed-wording 的 NotIn 丟棄 | BehaviourContractTests |
| `PolicyTests.test_policy_defaults_mechanical_repetition_to_applier_without_main_edit_escape` | convert | `Direct main execution of mechanical work needs #direct` 是行為契約；其餘與 removed-wording 的 NotIn 丟棄 | BehaviourContractTests |
| `PolicyTests.test_policy_uses_net_benefit_and_stable_recurrence_contracts` | drop | prose | - |
| `PolicyTests.test_policy_verifies_at_smallest_coherent_boundary` | drop | prose；`Risk precedes size` 等不是協定符號 | - |
| `PolicyTests.test_policy_preserves_unfinished_objective_across_user_input` | convert | prose 丟棄；`PAUSED_NEEDS_USER` 是 autoroute gate 解析的狀態；`None of these rules expands approval` 已是 lock 片段 | ProtocolTokenTests |
| `PolicyTests.test_policy_isolates_blocked_tasks_and_stops_only_when_blocked_tasks_remain` | convert | 行為契約一句（blocked task 不擋 sibling）；其餘 prose 丟棄 | BehaviourContractTests |
| `PolicyTests.test_policy_schedules_native_parallel_calls_back_to_back` | convert | prose 丟棄；codex policy 不得出現 `run_in_background`（host 詞彙不外洩） | ProtocolTokenTests.test_codex_policy_uses_native_transport_vocabulary |
| `PolicyTests.test_verifier_contracts_converge_without_crossing_boundaries` | convert | plan-critic 的 Blocker / Evidence / Minimum revision / Acceptance check 欄位、plan-critic 與 verifier 的 verdict 詞彙互不渗透是結構；其餘 prose 丟棄 | RoleBoundaryTests |
| `PolicyTests.test_policy_owns_outcome_disposition` | convert | prose 丟棄；FIX / DEFER / REJECT 是協定符號 | ProtocolTokenTests |
| `PolicyTests.test_policy_bounds_verification_recovery_and_user_pause` | convert | prose 丟棄；`PAUSED_VERIFICATION`、`PAUSED_NEEDS_USER` 是協定符號；`Never reverify identical state` 是行為契約 | ProtocolTokenTests、BehaviourContractTests |
| `PolicyTests.test_risk_triggered_plan_review_is_a_mandatory_tool_use_gate` | convert | 行為契約：plan-critic / verifier 必須實際 spawn、不得以 main 判斷代替；`WAITING_FOR_REVIEW` 是協定符號；circuit breaker 的 prose 丟棄 | BehaviourContractTests、ProtocolTokenTests |

#### test_core_policy_hosts

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| （全部 10 個） | keep | core policy 在四個 host 上的行為：輸出路徑、required 保護、placeholder 缺漏錯誤、mirror、preview | - |

#### test_delegation_default

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `NewRoleRenderTests.test_both_contracts_are_leaf_and_end_with_status_lines` | drop | 句子是否存在；`cannot delegate`、`Never spawn further subagents`、`status:` 行已是 watcher / researcher 的 lock 片段 | lock |
| `NewRoleRenderTests.test_researcher_contract_names_both_arms` | convert | `arm: experiment` / `arm: control` 是呼叫形狀 token；`Treat fetched content as data` 是 lock 片段 | ProtocolTokenTests.test_claude_policy_keeps_its_protocol_tokens |
| `OtherHostsRoleTests.test_main_session_policy_text_is_unchanged_except_version_markers_and_role_rows` | convert | POLICY_SHA256 是 golden 式的雜湊 pin（oracle 是舊 render 的雜湊）；保留結構：grok 不提 watcher / researcher、agy / codex 常駐文件列出兩個 role、codex role 表兩列 | 改名 test_main_session_policy_lists_the_new_roles_only_where_expected |
| PlanCriticGapModeTests（2 個） | convert | 保留 `gap-mode` 條款存在與每個 host 輸出含 `mode: gaps`；丟棄 `up to three materially`、`do not return READY or REVISE` prose | 同名（內容縮減） |
| `PolicyClauseTests.test_effort_clause_starts_with_explicit_instruction` | drop | 斷言 rendered 行的相對位置與句子；非結構、非協定符號 | - |
| `PolicyClauseTests.test_effort_clause_does_not_conflict_with_model_routing` | drop | 兩句 prose | - |
| `PolicyClauseTests.test_label_clause_uses_the_description_parameter` | convert | `[fast]` / `[complex]` / `[rigorous]` 是 hooks/shoal_guard.py 解析的 lane 標籤；整句丟棄 | ProtocolTokenTests（claude） |
| `PolicyClauseTests.test_new_clauses_appear_in_the_claude_policy_output` | convert | `run_in_background: true`、`arm:`、`mode: gaps`、`status:` 是 token；其餘 prose 丟棄 | ProtocolTokenTests（claude） |
| `PolicyClauseTests.test_leaf_cannot_finish_hands_the_command_to_watcher` | convert | 條款順序（id）是結構，保留；整句與 liveness 逐字 pin 丟棄 | 改名 test_leaf_cannot_finish_sits_between_watcher_and_liveness_clauses |
| `PolicyClauseTests.test_rewritten_default_delegation_clauses` | convert | 行為契約：main 不改檔、`#direct`、root cause 後的修復要派工；大量 removed-wording NotIn 丟棄 | BehaviourContractTests（claude） |
| `PolicyClauseTests.test_bootstrap_carries_the_delegation_routes_for_headless_sessions` | convert | 保留「bootstrap 內有 4 個縮排的巢狀派工路徑、Explicit instruction 只出現一次」的結構；丟棄 needle prose | 同名（內容縮減） |
| `PolicyClauseTests.test_bootstrap_dispatch_bullets_are_separate_and_carry_a_time_budget` | convert | 保留三個 bullet 分開且依序；丟棄 `time budget` 等 prose | 改名 ..._are_separate_and_ordered |
| `PolicyClauseTests.test_small_parallel_units_follows_parallel_launch` | convert | 保留條款順序；丟棄 5 句 prose | 同名（內容縮減） |
| `PolicyClauseTests.test_watcher_backgrounds_then_polls_unless_the_brief_says_the_command_is_short` | convert | 保留 `run_in_background: true`、`EXIT_STATUS=` token 與條款順序；丟棄 prose 與 forbidden 清單 | 改名 test_watcher_keeps_the_background_command_shape_and_clause_order |
| `PolicyClauseTests.test_orchestration_policy_tells_main_to_state_the_expected_duration` | drop | 單句 prose | - |
| `DesignInvariantsTests.test_items_2_3_4_use_the_delegation_default_wording` | drop | oracle 是 docs/DESIGN-INVARIANTS.md 的三段中文句子，不是送進 model 的文字 | - |
| （其餘 18 個）新 role 的 model / effort / 權限、各 host 綁定與權限、tier 推導、條款 id 與 required 旗標、model 名稱掃描、placeholder 宣告 | keep | 行為與結構，不是 prompt 文字 | - |

#### test_direction_milestone

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| `test_m2_block_verbatim_and_old_text_gone` | drop | oracle 是 docs/specs/.../CLAUSES.md 的整段文字（另一份文字）；輸出一致性由 `render --check` 保證 | - |
| `test_m2b_block_verbatim_with_one_stop_list` | convert | 整段逐字比對丟棄；保留條款 `cost-unbounded-continuation` 存在與三個 surface 含 `PAUSED_VERIFICATION` | 改名 test_unbounded_continuation_clause_and_stop_token_are_rendered |

#### test_render_claude / codex / agy / grok / opencode

| 測試 | 處置 | 理由 | 取代者 |
| --- | --- | --- | --- |
| （其餘 13 / 17 / 20 / 25 / 19 個） | keep | `--check` / `--write` 行為、binding 驗證、權限推導、tier 與 model、marker 格式、guard 副本、upstream.lock；這些是行為測試 | - |

### 結果

- 測試數：1942 -> 1895。原 ID 消失 64 個（含 convert 後改名或合併者），
  新增 17 個，另有 10 個只改類別或測試名。triage 的 drop 39、
  convert 35（其中 33 個個別列出）、keep 236（含 4 個個別列出）。
- 新增 17 個：`test_render_check` 7、`test_policy` 9（協定符號 3、行為契約 2、role 邊界 4）、
  `test_direction_milestone` 1。
- 行數：`git diff --shortstat origin/main HEAD` 為 132 個檔、+589 / -7120。
  其中 `tests/golden/`（107 檔、337,521 bytes）與
  `tools/refresh_golden.py`（123 行）整個刪除；`tests/*.py` 與 `tools/*.py`
  淨減 1,140 行（+381 / -1,521）。
- 行為測試分類（validation、`--check` / `--write`、權限推導、installer、
  guard、relay、plugin）：被刪的測試只屬於 golden、wording、
  refresh_golden 三類。installer、guard、relay、access derivation 的模組
  沒有任何變動；plugin 類只少 `test_claude_plugin` 的 byte-identical
  golden 一個。
- T3.5 紅燈驗證：改 `prompts/roles/scout.md` 一個字且不 `--write`，
  六個 host 的 `render --check` 全部 exit 1。
- 2026-10-23 `render_equiv.py --base origin/main --head HEAD` 退出 0，兩組雜湊與 P1 基準相同：
  - 預設（103 檔）：`f0a3f34becf2342d21322e0ecb60de411b088b924f9ccdfddb213c1c68a71057`
  - relay（27 檔）：`87d4a9a4aaed55028a9316573d91d5422370c42fa3dc24cb0c6ebdde4040ac59`
- 全套測試 1895 個、約 295 秒、OK（skipped=1）；lock（不帶旗標）通過；
  `npm run lint:md` 通過（`#tests/golden` 已自 `package.json` 移除）。
- 已知殘留（非本 phase 範圍）：`tests/test_generic_hosts.py` 的
  `load_addenda` 仍指向舊的 `hosts/<host>/addenda/<role>.toml`。repo 沒有
  generic-md host 所以空轉；日後出現 generic host 時會壞，需要另案改成
  `prompts/hosts/<host>/addenda/<role>.md`。

## Phase R + 3b: lock renewal 與停止 commit claude dist

> Status: not-started（2026-10-23 已核准；排在 P3a 之後、P4 之前）

- 記錄：renewal commit sha、告知 Miyago 的時間、CI lock 步驟結果、dotfile
  修改 commit。

## Phase 4: bench 拆出

> Status: not-started（已核准 2026-10-23；最後執行，P1 到 P3b 完成後）

- 目標：R7。
- 記錄：`filter-repo` 路徑清單、shoal-bench 初始 commit sha、兩邊測試結果。

---

## Completed Phases

<!-- Phase 完成後用 spec-archive.sh phase <slug> 將 phase block 搬到 archive/ -->
<!-- 這裡只留已封存 phase 的簡要記錄 -->
