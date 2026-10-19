# code-restructure：把最肥的程式整理成讀得懂的單元，行為不變

狀態：草案（待 Miyago 核准；guard 變更觸發 plan-critic，見 Risk）。2026-10-19 Miyago 決定：guard 不拆 package，維持單檔。

## Background

2026-10-19 量測（main `1ac98ce`）：

| 檔案 | 行數 | 問題 |
| --- | --- | --- |
| `hooks/shoal_guard.py` | 3181 | 一個檔 13 段（維持單檔）；`_Guard` 一個 class 980 行；三個 host adapter 各自手寫；9 個 key 的 state literal 在 `_locked` 內出現 3 次；docstring 78 行重複 spec |
| `install/install.py` | 2864 | `install()` 約 700 行、`_validate_committed_state` 約 460 行，各是單一函式 |
| `tools/render.py` | 1573 | claude / codex / agy / grok / opencode 的 `validate_*` / `render_*`（525-1113，約 590 行）形狀相同卻各寫一份 |
| `tools/install_hooks.py` + `install/hook_registration.py` + `install/install.py` + `tools/sync_global.py` | 651 + 696 + 2864 + 680 | hook 登記散在多處；Codex `hooks.json` 有兩條寫入路徑 |

痛點是「找不到東西、改一處要讀全檔」，不是功能不足。guard 在每個 tool call 都跑，
所以任何結構變動都要證明行為與延遲不變。

## Goal

1. 每個檔案有一個主題；最長函式降到約 120 行以下；重複的 table / literal 收斂成一份。
2. 行為不變：guard vectors、unittest、render `--check`、各 host 輸出逐位元組不變
   （P1 改了 guard 原始碼，所以 guard 的 dist 副本與其 `.sha256` golden 隨之更新，這是唯一允許的 golden 變動）。
3. hook 啟動延遲不增加（目標：p50 不高於重構前 +1ms）。
4. 淨行數下降，但這不是主要目標：預估合計約 -390 到 -490（guard -240、
   render -150 到 -200、install 0 到 -50；不含新增測試）。可讀性是主要驗收，行數只作回報。

## Non-goals

- 不改任何 policy 條款、role、lane、MESSAGES 文字、state 的內容與 key。
- 不改 `core/`、`hosts/*/binding.toml` 既有欄位的語意（D4 只在證明無副作用時新增）。
- 不動 `hooks/shoal_autoroute_gate.py`（1676 行，另案）、OpenCode 的 TS guard。
- 不新增功能、不新增 guard 規則、不改 CLI 參數。
- 不拆 `tests/` 的大檔（只改被結構綁住的部分，見「會被牽動的測試」）。

## Decisions

### D1 guard 單檔內整理

`hooks/shoal_guard.py` 維持單一檔，不拆 package、不改發佈單位、所有消費者（render、install_grok、
shoal_update、install_hooks、install.py）不動。只做 in-file 整理：

- **host 表**。host 集合（109-195，約 20 個 `frozenset`）改成一張表：
  `HOSTS = {"claude": HostInfo(default_mode="enforce", role_aware=True, stop=True, ...), ...}`，
  原本的 `ROLE_AWARE_HOSTS`、`STOP_HOSTS` 等名稱由表衍生並保留為模組屬性，
  讓 `guard.STOP_HOSTS` 這類測試引用不必改（O8）。
- **adapter 表**。`_adapt_claude` / `_adapt_codex` / `adapt_grok`（2626-2690、2713-2771、2772-2826）
  共同形狀：取 event 名稱 → 對應 tool kind → 抽 path / command / role / lane 描述。
  差異（tool 名稱表、payload key 路徑、Codex 的 `apply_patch` 與 lane 文字）放進每 host
  一張 `AdapterSpec`，共用一個 `adapt(spec, payload)`。`adapt_agy` 因為 payload 沒有事件名、
  多 conversation，維持獨立函式。已有 test 釘住 adapter 輸出（`tests/fixtures/*_shapes.json` 與 vectors），
  先在現有 code 產生 `tests/fixtures/adapter_golden.json`（全 host、全 payload 的 `adapt_*` 完整回傳）再重寫，P1 不得編輯該 golden（T0.3、T1.2）。
- **`_new_state`**。`_Guard._locked`（1817-1915）中 3 份 9-key state literal 收成 `_new_state(**overrides)`；
  key 順序必須與現在寫出的 JSON 相同（`test_state_file_*` 與 vectors 驗證）。
- **open helper 不合併**。`_open_private`（457）與 `_open_readable`（3087）維持分開（見 Security review F1）。
- **docstring**。檔頭 78 行 docstring 改成約 10 行：用途、入口、指向 `docs/specs/dispatch-enforcement`、
  `guard-declared-direct`、`guard-every-gate`。
- `_Guard` 類別維持原樣（不用 mixin、不搬方法）；只有上述三處與 docstring 會動。
- 延遲：單檔沒有新增 import，預期不變；仍以 P0 的 bench 在 P1 前後各量一次，p50 差 +1ms、p95 差 +3ms 內
  （O7）。
- Python 3.9：不使用 `match`、括號式 context manager、`X | Y` 的 runtime 求值；`test_py39_compat` 照舊涵蓋。

#### Rejected alternatives

- **P5 `render.py` 資料化（D4 查表化，2026-10-19 Miyago 決定丟掉）**。實作後查表化反而 +38 行，且沒有可讀性收益；`validate_*` / `render_*` 維持原狀。

- **D2 hook 登記收斂到 `install/hook_registration.py`（原 P3，2026-10-19 拿掉）**。原計畫讓 `apply_codex` 改呼叫 `merge_registration`，使 Codex `hooks.json` 只剩一條寫入路徑。否決原因：`apply_codex` 的 regex handler-level stripping 在 mixed group 內（`tools/install_hooks.py:181-210`、`255-277`）無法套用 `merge_registration` 的整 group 精確投影比對（`install/hook_registration.py:403-425`、`562-574`、`654-662`），要改就會改變行為（`tests/test_install_hooks.py:744-756`）；收益只約 50-80 行，不值得。因此 Codex 的兩條寫入路徑（`install.py` 與 `install_hooks.py`）維持現狀，不在本案範圍。

- **guard 拆成 `hooks/shoal_guard/` package**（約 14 個模組、薄入口、`guard_bundle.py`、bundle manifest golden、
  staging 加 rename 安裝、消費者表）。否決原因：消費者機制要多約 +150 行（render、install_grok、shoal_update、
  install_hooks、install.py、golden、測試輔助全部改成處理多檔），並引入舊 state fingerprint 升級與半套安裝的風險，
  換到的行數減少很有限（約再 -50）。同名 `shoal_guard.py` 與 `shoal_guard/` 的 import 解析、lazy import 的延遲取捨
  也隨之不需要。2026-10-19 由 Miyago 決定不採用。
- **由 package 產生單一檔再提交**：repo 內仍有 3000 行產物且需要 `render --check` 擋手改，沒有解決可讀性，同樣不採用。

### D3 `install/install.py`：拆函式，不拆檔

為什麼不拆檔：`tests/test_install.py` 大量 patch `installer.subprocess`、`installer.shutil` 等 module 屬性，
並以 `installer.install(...)` 驅動；拆檔會讓這些 patch 全部失效，重寫成本高於收益。拆成同檔內的具名函式即可達成可讀性。

- `install()`（2073-2773）拆成依序執行的步驟，共用一個 `@dataclass _Plan`（writes、removals、notes、state 欄位）取代現在的區域變數：
  `_resolve_context` → `_plan_config` → `_plan_roles` → `_plan_policy` → `_plan_hooks`
  → `_plan_plugin` → `_commit_plan`（呼叫既有 `_commit`）→ `_record_state` → `_post_commit_removals`。
  每步不超過約 120 行；`install()` 本體只剩串接與 dry-run 判斷（約 60 行）。
  順序、交易邊界（先備份、全部成功才提交、post-commit 才刪舊 role）、錯誤訊息一字不改。
- `_validate_committed_state`（897-1359）依 state 區塊拆：
  `_check_state_keys`、`_check_policy_ownership`、`_check_hook_projection`、`_check_guard_script`、
  `_check_role_inventory`、`_check_plugin_record`…，每個回傳錯誤或丟 `InstallAbort`，原有的檢查順序保留。
- 先寫 characterization：對每個 `InstallAbort` 訊息（grep 出的字串）確認至少有一個 test 觸發，缺的先補（Red 在前）。

### D4 `tools/render.py`：host 差異資料化

- 抽出 `HostSpec`（dataclass）：`validate`（共同 `validate_catalog` + `derive_permissions` + read-only tool 檢查）、
  `frontmatter(name, spec, perm, model)`、`forbidden_tools`、`models` 白名單、`extra_files(core, binding, src)`、`rules_path`。
  共同流程 `render_roles(spec, core, binding, src)` 取代五份「迴圈 role → role_body → 組 frontmatter → passthrough → merge_core_policy」。
- 完全適用：claude、agy。部分適用：grok（多 `roles/*.toml`）、codex（root 與 `[agents]` toml）；
  opencode 的 plugin 輸出維持自己的函式，只共用 validate。誠實預期：不是五個都能變 table，約 -150 到 -250 行。
- 常數（`AGY_MODELS`、`READ_ONLY_FORBIDDEN_TOOLS` 等）先放 `HostSpec`，**不**搬進 `binding.toml`：
  搬進去會改 binding 格式，而 `render_generic`（已是 binding 驅動）與 TS plugin 是否讀這些欄位需另行確認。
  搬 binding 列為 O4，不在本案階段內。
- 驗收是 `render --check` 五個 host 輸出逐位元組不變（golden 全綠，不更新任何 golden）。

## Phases（每階段可單獨出貨）

| 階段 | 內容 | 預估行數變化 | 驗收（每階段都要） |
| --- | --- | --- | --- |
| P0 | 量測基準：`tests/bench_hook_latency.py`（P1 前後各量一次）；補 characterization tests（adapter golden、`InstallAbort` 訊息） | +200（測試） | 在現有 code 上全綠，baseline 數字存 PROGRESS.md |
| P1 | D1：guard 單檔內整理（host 表、adapter 表、`_new_state`、docstring）。**仍是單一檔** | guard -240 | 見下方共同驗收；guard 的 dist 副本與 `.sha256` golden 隨之更新；沒有發佈單位變動，風險最低 |
| P4 | D3：`install.py` 拆函式 | 約 0 到 -50，最長函式 ≤ 120 行 | 共同驗收；`test_install` 全綠且不改斷言 |
| P5 | D4：`render.py` table 化 | -150 到 -200 | 共同驗收；golden 全部不變 |

順序理由：P1 先在單檔內降低 guard 的複雜度，且不動任何消費者；
P4、P5 彼此獨立，可以平行或依序。
階段編號刻意不重排（P2 已移除），讓既有引用穩定。

**行數合計**：P1 -240、P4 0 到 -50、P5 -150 到 -200，約 **-390 到 -490**（不含 P0 新增的約 200 行測試）。

**實際結果（2026-10-19）**：P1 guard 3181 -> 3080 行（-101）。P4 `install.py` 2773 -> 3067 行（+294），`install()` 692 -> 70 行、`_validate_committed_state` 404 -> 44 行，以行數換可讀性。P5 不做（+38 行，無可讀性收益，見 Rejected alternatives）。

**共同驗收**：

1. `python3 -m unittest discover -s tests` 全綠（Windows-only 的 skip 照舊）。
2. `python3 tools/render.py --check --host <claude|codex|agy|grok|opencode>` 五個全綠；claude-plugin 同。
3. `tests/fixtures/guard_vectors.json` 全部 vectors 通過（`tests/test_shoal_guard.py::VectorTests`）。
4. hook 延遲（P1）：`tests/bench_hook_latency.py` 重構後的 p50 / p95 與 P0 baseline 比較，在 D1 容許範圍內。
5. `tests/test_py39_compat.py` 綠。
6. 沒有 golden 內容變動（P1 的 guard dist 副本與 `.sha256` 除外）。

## Security review（P1）

P1 由 `security-executor` 實作，完成後 fresh `verifier`。F2、F3、F6 的測試必須先在現有 code 寫好且全綠（P0），才可改 P1 code。證據行號為 `hooks/shoal_guard.py` 現況。

| # | 嚴重度 | 證據 | 處置 | 測試 |
| --- | --- | --- | --- | --- |
| F1 | High | `_open_private`（457-472：O_NOFOLLOW、0600、fstat S_ISREG+uid、fchmod 0600）對 `_open_readable`（3087-3099：O_RDONLY + S_ISREG）；呼叫端 2342 `dispatch_guard_selected`、2374 `chain_members`、3063 settings.json。合併會 fail-open（symlink 的 modules.json 使 chain 被靜默略過）或改動使用者檔案權限 | 自 P1 移除：兩個 helper 維持分開（只省約 10 行，不值得） | S1.4 |
| F2 | High | `dispatched_role` 只來自 claude `Agent`、grok `spawn_subagent`、codex `spawn_agent` / `collaborationspawn_agent`；claude `Workflow` 得 None（2685） | 不變式：Workflow 無論 tool_input（含 `subagent_type:"executor"`）一律 None | S1.5 |
| F3 | High | 依內容分類必須維持 predicate、不進 name table：claude Bash `run_in_background=True` 先判 background_shell 再 shell（2664）；Post/PostFailure 排除背景 Bash（2658）；codex Bash/Post 要 str command（2741、2756）；grok `run_terminal_command` 要 str（2798）；grok stop 在 reason != end_turn 或來自 subagent 時回 None（2792） | 保留 predicate；上述案例明列進 adapter golden 輸入 | S1.6 |
| F4 | Med | is_subagent：claude/codex `bool(agent_id)`、grok `subagentType is not None`（2637、2715、2779）；SubagentStart tid：claude=prompt_id，codex/grok None | 逐 host 保持 | S1.7 |
| F5 | Med | 未知 tool 維持 other（2688、2769、2824 -> skip no_path，2133）；edit-name 集合不變（claude 4、grok 6；grok path-key 順序 file_path, path, target_file, filePath；codex apply_patch 走 patch_paths）；prompt 文字只供 direct/fast 判斷，不寫入 event 或 log（2649） | 保持；edit-name 集合凍結為 literal | S1.8 |
| F6 | Med | host 表成員與現況相同：`HOST_DEFAULT_MODE` 維持 4 個 key（109-114）；opencode 只在 `PROMPT_DIRECT_HOSTS` 與 `DECLARE_HOSTS`（141、161），不照抄 TS port 的集合；START_UNLOCK 最敏感（1899-1903）；`set(ADAPTERS)` 維持 {claude, codex, grok, agy}（3163） | 每個舊集合名稱在 P0 凍結為 literal，P1 比對 | S1.9 |
| F7 | Med | `_new_state` 只填固定預設、不合併舊 state；prompt boundary 重設 dispatched/declared/changed/checked/stop_blocked 為 False、pending 為 0（1832-1835、1849-1851）；keep 分支保留 edited+turn_id；第三處以 `is True` / `_pending()` 強制轉型（1867-1878）；role_changed/role_running 只在 changed 時寫（1879-1882）；fast 來源依路徑不同；direct_turns/agents/post_seen 經 `_carry_agents`（670） | 不得讓 `_new_state` 吃舊 state | S1.3、S1.10 |
| F8 | Low | docstring 縮短；無 `__doc__` 使用 | 接受 | 無 |
| F9 | Low（既有，範圍外） | `_open_*` 無 O_NONBLOCK（FIFO 可卡住 hook）；chain manifest 無 uid 檢查卻驅動指令執行（2387） | P1 不變更；另開 security follow-up | 無 |

## Risk

| 風險 | 緩解 |
| --- | --- |
| guard 變更是 security / trust 邊界（dispatch enforcement） | 依 Risk trigger：P1 實作前以 `plan-critic` 審 plan 並取得 Miyago 核准，完成後以 fresh `verifier` 驗一次；改動走 `security-reviewer` → 核准 → `security-executor`，不用一般 executor |
| P1 的表衍生名稱與舊 frozenset 不一致 | T1.1 逐 host 比對舊成員；保留舊名稱 |
| adapter 表化改變 normalized event | T0.3 先產生 adapter golden，T1.2 逐項 assertEqual；golden 不得編輯 |

## Rollout

- 每個 phase 一個 PR，各自過共同驗收。P1、P4、P5 純內部、不改已安裝檔案配置，可併入 patch 或累積成批再發。
- 只修改 `hooks/shoal_guard.py`、`install/`、`tools/`、`tests/` 與 render 產物（guard 副本）；`docs/specs/code-restructure/` 的 TASKS.md 每步更新，
  PROGRESS.md 每 phase 記延遲數字。

## 會被牽動的測試（重寫，不是刪除）

| 測試 | 為什麼綁結構 | 處理 |
| --- | --- | --- |
| `tests/test_shoal_guard.py`（1860 行） | `import shoal_guard as guard`，約 150 處使用 `guard.adapt_*`、`MESSAGES`、`resolve_mode` 等 | 保留公開名稱，不用改；462、643 行附近的測試掃的是 guard_dir 的 state/log 檔，不是原始碼文字，T1.5 不需改斷言 |
| `tests/render_helpers.py`、`GOLDEN_HASHED` 的 guard `.sha256` | guard 副本內容隨 P1 改變 | 重新產生 guard 副本與 `.sha256`（唯一允許的 golden 變動） |
| `tests/test_hook_registration.py`、`test_install_hooks.py` | `apply_*` 位置 | 位置不變，斷言不變 |
| `tests/test_access_derivation.py`、`test_core_policy*.py`、`test_claude_plugin.py` 等 | 直接呼叫 `render.validate_*` / `render_*` | P5 保留這些名稱為薄包裝，所以不需要改 |

## Open questions

已解決：

- ~~O1 package 名稱~~：已解決，不拆 package，無此問題（2026-10-19 Miyago 決定）。
- ~~O2 發佈單位~~：已解決，維持單檔，消費者不動（同上）。
- ~~O5 `merge_config_text` 歸屬~~：已解決，是 Codex `config.toml` routing 而非 hook 登記。
- ~~O3 Codex 兩條路徑~~：已解決（P3 拿掉）：兩條路徑維持現狀，不在本案。
- ~~O6 mixin vs 單一 `guard.py`~~：已解決，`_Guard` 不搬動、不用 mixin。

待決：

- O4 `AGY_MODELS`、forbidden tools 等常數是否搬進 `binding.toml`（需確認 `render_generic` 與 OpenCode TS plugin 是否讀取）。本案預設不搬。
- O7 hook 延遲容許值（p50 +1ms、p95 +3ms）是我的估計，沒有歷史資料；P0 量完後可能要調整。
- O8 `guard.STOP_HOSTS` 等舊名稱由表衍生並保留，是否值得（保留省測試改動，但留下兩種寫法）；建議保留一個 release 後再清。
