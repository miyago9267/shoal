# Changelog

shoal 的產品版本紀錄，從 v1.0.0 開始。Codex host 在 v1.8.1 之前的完整歷史
在 [hosts/codex/CHANGELOG.md](./hosts/codex/CHANGELOG.md)。

## Unreleased

### Features

- core-policy P2：Claude host 的 policy 改由 `core/policy` 條款組裝
  （`policy_text = "core"`）；兩處「workflow」改為 procedure／policy 的
  用字，沒有預期的行為變更。claude host 版本 1.4.2-claude.4。

## v1.4.0

### Features

Claude plugin 與 host 中立 guard 補強（`docs/specs/generic-shoal/`）。

- guard M1：Claude 的接續回合沒有 `prompt_id` 時改用 session state；沒有
  id 的 prompt 會清掉 dispatched，避免上一輪的派工狀態被沿用。
- guard K3：`shoal:` namespace 白名單，plugin 版 role 以此前綴辨識。
- state K4：state 檔加 flock；plugin 版 guard 遇到全域已有 guard entry 時
  讓位，不重複註冊。
- Claude plugin 打包：新增 `claude-plugin/` 與
  `.claude-plugin/marketplace.json`，由
  `python3 tools/render.py --host claude-plugin --write` 產生，版本取自根目錄
  `VERSION`；安裝方式是 marketplace 加上 tag（見 INSTALL.md）。
- F2：agy 實測證據記錄在 spec，維持固定 shadow。

Prompt lock 與 orchestration policy（`docs/specs/core-policy/`）。

- P0：prompt lock 新增一次性 migration；PR label 路徑加 `--no-migration`，
  CI 觸發路徑加入 `core/**`、`claude-plugin/**`。
- P1：orchestration policy 抽成 `core/policy` 條款與組裝器。各 host 仍用
  舊版 policy，行為沒有變。

### Fixes

- smoke report 的 private root 在 Windows 路徑下正確 JSON escape。
- lock 的 repo 相對路徑判斷同時套用 Windows 語意。
- Claude live probe 在 Windows 上略過不適用的項目。

### 已知限制

- Grok、Codex 的 E6 仍是 shadow，等 shadow log 達標再切。
- agy 固定 shadow。
- policy 各 host 仍用舊版，要等 P2、P3 才切換。
- guard 在 Windows 為 no-op。

## v1.3.0

### Features

Dispatch 強制與權限補強（`docs/specs/dispatch-enforcement/`，E0-E5）。

- 新增 host 中立的 dispatch guard `hooks/shoal_guard.py`，取代 dotfile 的
  Claude 專用 guard。main session 沒派 write 等級的 role 就直接改到第 3 個
  檔案時 deny；有分類 provider 時，判定為 judgment 或 mechanical 的一輪
  直接改檔也會 deny。修正舊 guard 的 bypass：路徑先 realpath 再判斷豁免，
  派唯讀 role 不再解鎖，prompt 內的 `#direct` 改為環境變數
  `SHOAL_GUARD_DIRECT=1`。
- subagent 規則：write role 再派 subagent 時 deny（LEAF），verifier 用
  編輯工具時 deny（VERIFY_EDIT），只在能辨識 role 的 host 生效。
- adapter：Claude、Codex、Grok、agy 共用 Python 版；OpenCode 在 plugin 內
  以 TypeScript 移植，兩份實作重播同一份測試向量
  `tests/fixtures/guard_vectors.json`。
- 模式：`SHOAL_GUARD=enforce|shadow|off`。Claude、OpenCode 預設 enforce；
  Codex、Grok 預設 shadow，等 shadow log 達標再切；agy 無法辨識 subagent，
  固定 shadow。
- E6：OpenCode 依 shadow log（21 筆決策、4 筆 would_deny、誤擋 0、skip 0）
  切為預設 enforce；Grok、Codex 延後，agy 固定 shadow。
- 安裝：Codex 由 `install/install.py` 註冊（獨立 projection
  `shoal-guard-v1`，安裝後要在互動 session 用 `/hooks` 核准一次）；Grok 由
  `tools/install_grok.py`；Claude 與 agy 由新的 `tools/install_hooks.py`；
  OpenCode 隨 plugin。
- 權限：Claude verifier 補擋 `MultiEdit`；OpenCode executor、
  security-executor 加 `task: deny`。
- 版本：codex 1.8.3、claude 1.4.2-claude.3、grok 1.0.6-shoal.2、
  OpenCode plugin 0.2.0。

### Fixes

- OpenCode plugin 入口只 export plugin 函式。先前入口多 export 了一個
  symbol 常數，OpenCode 1.18.31 載入時報 `Plugin export is not a function`，
  全域安裝實際沒有生效。

### 已知限制

- guard 在 Windows 為 no-op。
- guard 擋不住經 shell 寫檔，也擋不住同 uid 的 model 關掉 guard。
- Codex 0.160.0 的 subagent 繼承 main 的 sandbox 與網路，role 檔的
  `sandbox_mode`、`network_access` 不生效。
- agy 無法辨識 role，write role 再派 subagent 沒有強制手段。

## v1.2.0

### Features

審查列出隱含權衡與隱私檢查（`docs/specs/review-tradeoff-privacy/`，A1-A3）。
兩條 core 條款，五個 host 的 role 文字都會跟著變。

- verifier 新增 `implicit-tradeoffs`：`outcome_verification` 回報 `CONFIRMED` 或
  `REFUTED` 時，另列最多三項實作的隱含權衡（取捨了什麼、換到什麼），沒有就寫
  `none identified`。權衡不是 finding 或 advisory，不影響 verdict 與 priority。
- security-reviewer 新增 `privacy-check`：範圍涉及個人資料、識別資訊、記錄或保存的
  資料時，檢查收集與保存的最小化、資料流向、存取與刪除；不涉及時寫
  `privacy: not in scope`，且不取代 no-findings 聲明。
- Codex host 同步 bump 到 1.8.2（`hosts/codex/VERSION`、marker、`plugin.json`、
  `install/install.py`），安裝後的 marker 與 agent prompt 內容一致。

OpenCode 全域安裝（`docs/specs/opencode-global/`，O1-O2）。

- `hosts/opencode/plugin/install/install.sh` 新增
  `--global [--config-dir DIR] (--enable|--disable|--rollback)`：從 committed
  `HEAD` 把五個 role、plugin 與 `catalog.json`、`routing.json` 安裝到 OpenCode 的
  config dir（`--config-dir`，其次 `OPENCODE_CONFIG_DIR`，預設
  `~/.config/opencode`）。manifest 與備份放在
  `${XDG_STATE_HOME:-$HOME/.local/state}/shoal/opencode-global`。遇到使用者自己的
  同名檔案時中止且不寫入；安裝後對 `routing.json` 中未在 `opencode.json`
  （`provider` keys 與 `enabled_providers`）宣告的 provider 與已有專案 plugin 的目錄
  輸出警告。`--target` 的行為與輸出不變。
- plugin 查找設定改為兩層：專案 `.opencode/pilotfish/catalog.json` 存在就只用專案層，
  否則用全域 `<config-dir>/pilotfish/`，全域路徑同樣做穿越檢查。同一個 instance
  載入多份 plugin 時只註冊一次 `pilotfish_route`。

Prompt lock 依 host 判斷版本，並納入 Claude surface
（`docs/specs/claude-eval-parity/`，B0）。

- `LOCK.json` 升為 schema v2：每個 surface 有必填的 `version_file`
  （`hosts/<host>/VERSION`），`version_gate` 只剩
  `require_change_for_protected_surfaces`。protected surface 有變更時，只要求該
  surface 所屬 host 的版本檔變更，不再看根目錄 `VERSION`；Codex 的 16 個 surface
  對應 `hosts/codex/VERSION`。
- Claude host 的 8 個 agent、`pilotfish-orchestration` 的 `SKILL.md` 與 2 份
  reference 共 11 個 surface 加入 lock（共 27 個）。`executor`、`mech-executor`、
  `security-executor` 的 `max_change_ratio` 為 0.35，其餘 0.2。
- CI `python-tests` 的 `paths` 加入 `hosts/claude/**`。lock renewal 有兩條綠燈
  路徑：PR label `lock-renewal`，或 main push 的 head commit 含
  `Lock-Renewal: approved`；兩者只放寬 `LOCK.json` 的變動，既有 surface 的預算與
  版本檢查照常。
- 新增 `hosts/claude/VERSION`，Claude host 版本 `1.4.2-claude.2`，測試檢查與
  `SKILL.md` marker 一致。

role-fitness 的 host adapter 與失敗分類
（`docs/specs/claude-eval-parity/`，B1-B3）。

- B1：content runner 的 stage 執行抽出 host 中立的介面
  `install/role_fitness_stage.py`（`StageRequest`、`StageOutcome`、
  `DispatchEvidence`、`StageAdapter`），Codex 改走此介面，輸出與重構前逐欄位
  相同。
- B3：content 層失敗分類，六個類別加 `unclassified`；`failure_taxonomy` 同時
  彙總 dispatch 與 `content.*`。報表在分數旁列各類別次數與佔比，R1-R3 分開列；
  public projection（`role-fitness-public-v1`）新增 `content_failure_counts`，
  仍拒絕 free text。runner 新增 `attempt` 與 `rerun_of`，只在操作者指定重跑時
  輸出，不自動重試。
- B2（離線）：新增 Claude stage adapter `install/role_fitness_claude.py`，以
  暫存專案目錄與全新的 `CLAUDE_CONFIG_DIR` 執行 `claude -p`，用 `Agent` 工具的
  `subagent_type` 當 dispatch evidence，並有累計成本的停止點。測試用的 stream
  樣本是 synthetic；token 環境變數名稱（`CLAUDE_CODE_OAUTH_TOKEN`）與
  `--max-budget-usd`、`--setting-sources project` 等旗標的效果尚未以 live
  驗證，adapter 也還沒接進 runner 的 case 函式。

### 已知限制

- 專案 plugin 的共存警告只檢查目前目錄與其 git root；`--target` 沒有集中記錄，
  無法偵測其他專案。
- 去重以 plugin 的 `input.directory` 為單位。OpenCode 在同一個 process 內重新初始化
  同一個目錄時（例如設定重新載入），是否會重新載入 plugin 尚未驗證。

## v1.1.0

role-only 路線的四步（模型目錄、權限推導、role 契約、新增 host）完成，並補齊
grok host 的 workflow（`docs/specs/grok-workflow/`）。新功能、沒有破壞性變更；
grok、agy、OpenCode、Claude 的 role 文字改由 core 條款產生，agent prompt 因此
有差異，細節見各段與 `docs/specs/role-contracts/MAPPING-*.md`。

### Features

grok host 補齊 orchestration policy、原生 hooks 與安裝路徑
（`docs/specs/grok-workflow/`，G1-G4）。

- 新增 `hosts/grok/VERSION`（`1.0.6-shoal.1`，衍生自上游
  `Nanako0129/pilotfish-grok` v1.0.6）與 `rules/pilotfish-grok.md`：上游
  orchestration rules 逐字放在 `hosts/grok/src/rules/`，renderer 只把 marker
  換成 `<!-- pilotfish-grok v<VERSION> -->`；上游原文另存為測試 fixture，
  測試確認兩者只差 marker 一行。
- 新增 grok 原生 hooks（`hosts/grok/dist/hooks/`，只用 Python 標準函式庫）：
  `SubagentStop` 格式 gate 檢查 `verifier`、`plan-verifier`、
  `security-reviewer` 的最後回覆（三個 entry 各自定錨 matcher），不合格式時
  退回重送，`stopHookActive` 時放行、任何解析錯誤 fail-open；`PreToolUse`
  防護在 plan mode 拒絕產生可寫入的 subagent（plan mode 本身不擋 subagent）。
- 新增 `tools/install_grok.py`：從 committed HEAD 安裝 agents、roles、rules 與
  hooks 到 grok home。預設 dry-run，`--apply` 才寫入；寫入前備份被取代的檔案
  與 `config.toml`；`--fix-toggles` 以最小文字編輯移除 `[subagents.toggle]`
  中停用 shoal role 的 key；`--restore` 逐位元組還原、`--uninstall` 只移除
  shoal 的檔案；安裝後驗證 hash 與 rules marker。不讀 credential、session、
  history。
- README 的 host 表、安裝方式與歸屬連結（`pilotfish-grok`）、`INSTALL.md` 的
  Grok Build 段落與 `upstream.lock` 反映 grok 由 shoal 安裝。

不寫程式碼新增 host（`docs/specs/new-host/`，N1-N3）。

- 新增 `renderer = "generic-md"`：binding 用 `[output]` 宣告輸出路徑與
  frontmatter 欄位（來源 `name`、`description`、`model`、權限欄位或固定值；
  編碼 `scalar`、`comma-list`、`block-list`、`folded`、`nested-map`），權限
  欄位以 `[output.permissions.<欄位>]` 宣告型別。`tools/render.py` 從
  `hosts/*/binding.toml` 探索這類 host，`--host <name>` 不用改 `tools/`；
  不支援 `[extra_roles]`，`role_text` 必須是 `core`。既有五個 host 仍用各自
  的 renderer，dist、`templates/` 與 golden 與之前逐位元組相同。
- 新增 `tools/new_host.py <name>`（產生 binding、`frames/default.md` 與
  `addenda/`，已存在則拒絕）、`tests/test_generic_hosts.py`（探索式檢查每個
  generic-md host）與 `docs/new-host.md`。用 `[output]` 宣告在測試中重現
  Claude 與 agy 的 `scout` 輸出，兩者逐位元組相同。
- generic-md 新增 frontmatter 來源 `role.<key>`（讀 `[roles.<r>].<key>`，例如
  `role.effort`）：key 要列在 `[output].role_fields`，role 缺值時 exit 2，
  欄位設 `optional = true` 則省略。Claude 的七個 role 因此全部逐位元組重現；
  `new_host.py` 的骨架含 effort 欄位。

role 條款統一到 core（`docs/specs/role-contracts/`，Phase 2a）。

- 新增 `core/contracts/<role>.toml` 的條款格式與 `tools/contracts.py`，
  以及 `hosts/<h>/frames/`（外框）與 `hosts/<h>/addenda/<role>.toml`
  （host 補充，定位語法 `start` / `end` / `after:` / `before:` / `replace:`）。
  兩個目錄放在 `src/` 之外，不會進 dist。
- 每個 `binding.toml` 新增 `role_text = "legacy" | "core"`，並可用
  `[roles.<name>].role_text` 逐 role 覆寫。目前五個 host 都是 `legacy`，
  沒有任何 core 條款，輸出與之前逐位元組相同。
- Phase 2b-1：從 Codex 1.8.1 的原文切出七個共同 role（scout、mech-executor、
  executor、plan-verifier、verifier、security-reviewer、security-executor）
  的 `core/contracts`，Codex 切到 `role_text = "core"`；Codex 專屬的句子在
  `hosts/codex/addenda/`。`templates/agents/*.toml` 與切換前逐位元組相同，
  prompt lock、VERSION 與 marker 都不變。其他四個 host 仍是 `legacy`。
- Phase 2b-2（agy）：agy 的七個 role 文字改由 core 條款產生，這會改變 agy
  agent 的 prompt（`role_text = "core"`）：標題在 `hosts/agy/frames/`，工具限制
  與 agy 專屬句子在 `hosts/agy/addenda/`；四個 role 的 `foreground-timeout`
  以 agy 原本的「每個指令 10 分鐘內」措辭 replace。agy 因此新增取得 verifier 的
  `direction_checkpoint`、plan-verifier 的 blocker 定義等 Codex 條款，並移除
  scout 的最終訊息格式（Decision 3）。對照表在
  `docs/specs/role-contracts/MAPPING-agy.md`。
- Phase 2b-2（grok）：grok 的七個 role 文字改由 core 條款產生，這會改變 grok
  agent 的 prompt（`role_text = "core"`）：frontmatter 在 `hosts/grok/frames/`，
  `${{ tools.* }}` 模板行與 capability 說明在 `hosts/grok/addenda/`，沒有
  replace。`agents/*.md` 不再逐位元組等於上游 v1.0.6，`upstream.lock` 改記
  `derived`（Decision 7）；`roles/*.toml` 與 `config.snippet.toml` 不變。移除
  scout 的最終訊息格式（Decision 3）。對照表在
  `docs/specs/role-contracts/MAPPING-grok.md`。
- Phase 2b-2（OpenCode）：OpenCode 的五個 role 文字改由 core 條款產生，這會
  改變 OpenCode agent 的 prompt（`role_text = "core"`）：frontmatter、標題與
  permission 在 `hosts/opencode/frames/`，OpenCode 專屬句子在
  `hosts/opencode/addenda/`；`no-spawn`、`no-delegate`、`orchestrator-owns`、
  `main-session-carries` 共 7 處以 parent session 用語 replace。verifier 新增
  `INCONCLUSIVE` 與 P0 到 P4（Decision 2），移除六欄與五項回報格式及
  `READY`/`REVISE` 格式（Decision 3）。plugin 的 TS 與測試不變。對照表在
  `docs/specs/role-contracts/MAPPING-opencode.md`。
- Phase 2b-2（Claude）：Claude 的七個 core role 文字改由 core 條款產生，這會
  改變 Claude agent 的 prompt（`role_text = "core"`，`Explore` 維持 legacy，
  Decision 8）：agent body 沒有外框，frontmatter 仍由 binding 產生；Agent /
  Workflow 工具停用、allowlist、Bash `timeout`（毫秒）與 `run_in_background`
  等 Claude 專屬句子在 `hosts/claude/addenda/`，沒有 replace。移除電報體、
  `mis-routed` 用語（Decision 3）與 plan-verifier 的「remains blocking」
  （Decision 1）；verifier 的 direction checkpoint 條款改採 Codex 原句。
  對照表在 `docs/specs/role-contracts/MAPPING-claude.md`。

權限由存取等級推導（`docs/specs/access-derivation/`）。

- `core/roles.toml` 的 role 可加 host 中立的 `capabilities = [...]`（目前只有
  `"web"`，`security-reviewer` 使用）；各 host 的 `binding.toml` 新增
  `[access.<level>]` 與 `[capabilities.<name>]` 對應表，權限欄位（Claude
  `tools` / `disallowedTools`、Codex `sandbox_mode` / `web_search`、agy
  `tools`、grok `capability_mode`、OpenCode `required_capabilities`）由對應表
  推導。role 層級的同名欄位變成選用覆寫，目前只剩 OpenCode
  `security-reviewer` 的 `required_capabilities`。
- 驗證改成對推導後的結果做：read-only role 不可被對應表或覆寫變成可寫，
  違反時 exit 2；role 用了 binding 沒有對應的 capability 也 exit 2。
- `render --host <h> --explain` 每個 role 多印權限推導：`access`、
  `capabilities`、套用的對應表、覆寫與推導出的欄位。
- 五個 host 的 dist、`templates/` 與 golden 與之前逐位元組相同。

模型目錄與自動選模（`docs/specs/model-catalog/`，M1-M3）。

- 新增 `core/models.toml`（模型目錄）、`core/tiers.toml`（tier 選模規則）與
  `tools/resolve.py`；各 host 的 `binding.toml` 改以 `[models]` 宣告可用模型，
  手寫的 `[tiers]` 移除（現在只在要手動覆寫時才寫）。grok 改用
  `selection = "inherit"`。
- 新增 `render --host <h> --explain`，印出每個 role 的 tier、候選模型、
  被排除的原因與結果。沒有模型滿足規則時 exit 2，並指出 host 與 role。
- 移除 `security_avoid_frontier`：security role 改為排除帶
  `refuses_defensive_security` 旗標的模型（Claude 的 fable）。
- security role 被手動指定到帶 `refuses_defensive_security` 旗標的模型時，
  render 失敗。
- 五個 host 的 dist、`templates/` 與 golden 與之前逐位元組相同。
- 新增 [docs/model-catalog.md](./docs/model-catalog.md)：登記新模型與換模型的步驟。

### Fixes

- `tools/install_grok.py` 取代既有檔案時保留原本的權限，不再把 `config.toml`
  放寬成 0644；備份目錄改為 0700、備份檔 0600。
- grok 的 rules 與 agents 不再靠手動複製：先前 `~/.grok/rules` 可停在上游舊版
  （v1.0.4）而沒有被發現；現在由 installer 從 committed dist 安裝並驗證 hash
  與 marker。
- grok config 的 `[subagents.toggle]` 把 shoal role 設成 `false` 時，installer
  會標示出來，`--fix-toggles` 可只移除那幾個 key。
- 測試避開 Python 3.12 才支援的 f-string 寫法，修正 3.11 的 CI。
- role 文字審查後的調整：grok 補上 slice 沿用 envelope 的 addendum、agy 補回
  do-not-start 子句，並修正 grok、agy、OpenCode 的對照表。

### Known limitations

- grok hook 的 `command` 直接指向 `.py` 腳本，依賴 shebang 與執行權限；在
  Windows 上的 Grok Build 是否能直接執行未經驗證。
- `tools/install_grok.py` 不處理上游 AGENT-INSTALL 的 Claude 相容隔離
  （`[compat.claude]`、`[plugins] disabled`）與 Grok 版本下限檢查；既有設定
  原樣保留。
- hooks 只在 stdin／stdout 層級測試過，尚未在 Grok Build 的實際 session 中
  觀察到觸發。

## v1.0.0

shoal 首次發布：把 pilotfish-codex 擴成 host 中立的 role catalog。

- 新增 `core/roles.toml` 與 `hosts/<host>/binding.toml`，由
  `tools/render.py` 產生 Claude Code、Codex CLI、Gemini/agy、Grok Build、
  OpenCode 共 5 個 host 的輸出，並提供 `--check` / `--write`。
- 5 個 host 的首次 render 與原本的安裝來源逐位元組相同（golden 測試）。
- 產品版本與 host 版本分開：根目錄 `VERSION` 為 1.0.0，codex host 版本改記在
  `hosts/codex/VERSION`（1.8.1），其他 host 版本見 README。
- Codex 的 `README.md`、`CHANGELOG.md` 搬到 `hosts/codex/`，相對連結已改寫；
  新增繁體中文的根目錄 `README.md` 與本檔。
- 新增 `tools/check_links.py` 與 `tests/test_links.py`，檢查文件的相對連結。
- 安裝來源改為 `miyago9267/shoal`（`install/install.sh`、`install/install.ps1`、
  `INSTALL.md`、`install/AGENT-INSTALL.md`）。v1.0.0 之前的 pinned ref 仍需使用
  `miyago9267/pilotfish-codex`。
- `upstream.lock` 記錄各 host 的上游與版本。

已知限制：policy 尚未合併成一份；grok 仍由外部安裝。
