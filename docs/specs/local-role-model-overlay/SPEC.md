# local-role-model-overlay：本機為個別 role 換模型（Mythos 用於 security-reviewer）

狀態：Miyago 2026-11-14 核准；P3 於同日追加。

## Background

Miyago 2026-11-14 以個人方案取得 CVP（Cyber Verification Program）Defense
Access。查證結果（[Help Center](https://support.claude.com/zh-TW/articles/14604842)、
[Fable/Mythos 5.2 發布頁](https://www.anthropic.com/claude-fable-and-mythos-5-2)）：

1. 個人只能申請 Defense Access：SOC、事件回應、惡意軟體分析、偵測工程、
   漏洞分類與驗證。Red Team（攻擊工具、exploit 開發）限 Team、Enterprise、
   API 組織。
2. CVP 各層級包含 Mythos 5.2、Mythos 5.1、Opus 5.5、Sonnet 5.5。
3. Mythos 與 Fable 是同一個底層模型，差在 safeguards。Fable 5.2 "will block
   most cybersecurity-related tasks"，被擋的 cyber 請求改由 Opus 4.8 回答。
4. Mythos 5.2 對 Opus 5.5：CVE Rediscovery 89.6% 對 81.3%，CyScenarioBench
   76.3% 對 67.6%（Anthropic 自報）。價格與 Fable 相同（$8 / $40 per M tokens）。
5. 本機 Claude Code 2.1.325，model catalog 有 `claude-mythos-5-2`
   （`early_access`，最低 2.1.290）。

現況（main `76454d0` 查證）：

- `security-reviewer`、`security-executor` 是 strong tier，resolver 選 opus。
  fable 帶 `refuses_defensive_security`，security role 選不到它。
- shoal 是公開 repo，dist 進版控；`tools/shoal_update.py` 用 `git archive HEAD`
  匯出 marketplace，再以 sha256 比對安裝結果。repo 內沒有任何本機覆寫機制，
  gitignored 檔案也不會進入安裝內容。

## Goal

讓單一使用者在本機替指定 role 換模型，不改 repo 的預設 dist。Phase 1 只做
Claude host，用來把 `security-reviewer` 換成 `claude-mythos-5-2`。

## Non-goals

- 不把 Mythos 寫進 `core/models.toml`，dist 也不指定 Mythos：CVP 綁帳號，別人直接
  安裝會指定到用不了的模型。P3 只在 binding 的 `[probe.roles]` 列為探測候選。
- 不改 `security-executor`：它照已核准的 contract 實作，嚴謹度在 review 關卡。
- P1 不改 `plan-critic`（Fable 與 Mythos 一般能力相同）；P3 由 Miyago 決定加入探測，
  理由是 Fable 會把資安相關的 Plan 內容擋給 Opus 4.8。
- 不新增紅隊 role：Defense Access 不涵蓋攻擊性工作。
- PMS 的資安補強不在本 spec；它是 P2 的第一個實際使用案例，在 PMS repo 另開工作。

## Decisions

- D1 覆寫檔放在 repo 外：`${XDG_CONFIG_HOME:-~/.config}/shoal/claude.local.toml`。
  不放 repo 內，避免換 checkout 時遺失，也避免誤 commit。格式：

  ```toml
  [roles.security-reviewer]
  model = "claude-mythos-5-2"
  ```

  phase 1 只接受 `[roles.<name>].model`，其他 key 一律報錯。
- D2 在安裝時套用，不在 render 時套用。`ShoalUpdate.export()` 匯出 marketplace
  之後、計算 `tree_digest` 之前，改寫 stage 內 `agents/<name>.md` frontmatter 的
  `model:` 行。`verify()` 對 fresh export 做同一個轉換再比 sha256，兩邊用同一個
  函式。repo 的 dist、golden 與 `render.py --check` 完全不變。
- D3 驗證：role 必須是 `core/roles.toml` 或 claude binding `[extra_roles]` 的名稱
  （同時擋掉路徑型 key，例如 `../x`、`./security-reviewer`、絕對路徑）；model 值只允許
  `[a-z][a-z0-9.-]*(\[[a-z0-9]+\])?`，避免寫出會改變 YAML 型別的值；security role 的
  model 以 `-`、`.`、`[`、`]` 切開後，任何一段等於帶 `refuses_defensive_security` 的
  alias（例如 `fable`、`fable[1m]`、`claude-fable-5-2`）都拒絕。違反時 update 以非零 exit
  失敗，不安裝。
- D4 覆寫檔不存在時，行為與變更前位元組相同。
- D7 marketplace 內容改變但 plugin 版本相同時，改成 `claude plugin uninstall` 再
  `install`。2026-11-14 實測：版本相同時 `claude plugin update` 回報 already at the
  latest version，不刷新 cache，overlay 的新增與移除都到不了 Claude Code。
- D5 `--update` 的輸出在套用覆寫時加一行 `overlay: applied (security-reviewer=claude-mythos-5-2)`，
  讓覆寫在 log 中可見。

## P3 預設升級（安裝時探測）

Miyago 2026-11-14 決定：Mythos 寫進 shoal 預設，但不是每個人都有，所以要能退回。
security role 退回 opus，frontier role（plan-critic）退回 fable。

- D8 claude binding 新增 `[probe.roles]`：role -> 候選模型清單。目前
  `security-reviewer`、`plan-critic` 為 `["claude-mythos-5-2"]`；`security-executor`
  維持 Non-goal，不升級。dist 不變，仍是 opus 與 fable。
- D9 `shoal_install.py --update`（含 dry-run）對每個候選模型探測一次：
  `claude -p --model <id> --tools "" --setting-sources "" --strict-mcp-config --max-turns 1
  --output-format json "Reply OK"`，在空的 temp cwd、timeout 60 秒。exit 0、`is_error`
  為 false、`modelUsage` 含該 ID 才算可用；其餘（含 timeout、overload）都算不可用。
  `--setting-sources ""` 避開使用者的 `fallbackModel`，否則不可用的 ID 會被靜默換掉。
  一次約 $0.056（2026-11-14 實測）。
- D10 優先序：本機 overlay > 探測結果 > dist。沒跑 `--update` 的人（直接從 marketplace
  安裝）就是 dist，等於自動退回。
- D11 `[probe.roles]` 的 role 與 model 用 D3 同一套驗證，探測前先驗整張表。security role
  另外拒絕間接 alias（`best`、`inherit`、`opusplan`、`default`）。
- D12 探測結果分三種：可用、明確不可用（回覆含 "issue with the selected model"）、無法判定
  （timeout、overload、非 JSON）。無法判定時沿用目前已安裝的 model，不翻轉、不 reinstall；
  首次安裝就沿用 dist。避免一次網路問題觸發無人值守的 uninstall／install。
- D13 使用者 settings 有 `availableModels` 且不含候選時，直接視為不可用，不探測。
- 探測加 `--no-session-persistence`，不留 session transcript。
- 隱私：`plan-critic` 升級後，所有 risk-trigger 的 Plan 都會進入 CVP 的資料保留範圍。
  不想要的人用 overlay 把它 pin 回 `fable`。
- 失去資格後，下一次 `--update` 探測失敗，依 D7 reinstall 回到 dist。兩次 update 之間
  仍會落到 Claude Code 的全域 `fallbackModel`，由 D6 處理。

## Open questions

- O1 個人方案用 Mythos 的計費方式（訂閱額度或 usage credits）查不到官方說明。
  `security-reviewer` 是 effort high，若消耗過快，改成 effort medium 或只在
  明確的資安任務才手動指定。T0.2 實測後決定。
- O2（T0.1 已確認）完整 model ID 可用：`claude-mythos-5-2` 的 subagent 實際以
  該 ID 執行。不可用的 ID 不會報錯，會依 `fallbackModel` 改用 Sonnet 5.5，只在
  agent 回覆前加一行 "This agent switched to Sonnet 5.5 because its earlier model
  could not be used."。

## Fallback 降級

CVP 資格失效或 Mythos 下架時，`security-reviewer` 會降到 Sonnet 5.5，低於
strong tier，比預設的 opus 更差。D6：main 收到 `security-reviewer` 回覆時，
若含上述 fallback 提示，視為 INCONCLUSIVE，改用未覆寫的 opus 重派。phase 1
寫進 orchestration policy 的 security 條款；是否由 guard 自動偵測，P1 後再評估。

## Risks

- 覆寫讓本機安裝內容與 HEAD 不同；D2 讓 verify 一起轉換，避免誤判為損壞。
- CVP 要求資料保留：派給 Mythos 的內容會被 Anthropic 保留以監控濫用。PMS
  的 secret 與客戶資料不得放進 brief（沿用 shared contract 的 secret 規則）。
- 本機的 `SHOAL_ROOT` 未設定，`agent-stack-auto-update.sh` 預設的
  `~/Project/Active/shoal` 不存在，自動更新目前會失敗；P1 驗收前需先修正，
  否則覆寫不會被套用。
