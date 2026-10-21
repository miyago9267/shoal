# cross-vendor-relay：讓 role 交給別家的 agent 執行

狀態：Miyago 2026-10-21 核准。

## Background

shoal 目前把同一份 role 定義 render 到五個 host，每個 host 用自己的模型。
這層換誰都做得出來，產品區隔不夠。Miyago 2026-10-21 提出方向：在一個
host 裡，把某個 role 交給別家的 agent 產品執行。

2026-10-21 兩組 researcher（experiment / control）的結論：

1. 跨家 CLI 互叫已經是 commodity：PAL `clink`、OpenAI 官方 `codex-plugin-cc`、
   mco、ACP orchestrator 都做得到。transport 本身沒有區隔。
2. 沒有工具做到的四件事：按 role 宣告 vendor、跨家一致的 guard、統一的
   hand-back 與驗收規則、寫入隔離（clink 預設繞過 sandbox，mco 與
   codex-plugin-cc 共用 checkout）。這四件正是 shoal 已有的能力。
3. 混用的效益不能預設。arXiv 2607.21656（preprint，116 題）：Claude 審
   Codex 71.6% -> 89.7%，反方向退步，Claude 單獨 91.4% 高於所有組合。
   賣點定為「role 交給合適的家，加上強制驗收」，不是「多家一起比較強」。
4. 風險：訂閱帳號被程式呼叫的 ToS 限制（Google 2026-02 停權、Anthropic
   限定 ordinary use）、巢狀 sandbox 失敗、headless 輸出脆弱（stdin 未關
   會卡住、exit 0 但沒有輸出）。

## Goal

在 shoal 現有的 subagent 派工模型裡，讓 binding 能把某個 role 改由別家
agent CLI 執行；role 名稱、lane、guard、hand-back 與驗收規則不變。
Phase 1 只做 Claude host 把 `executor`、`applier` 交給 Codex。

## Principles

1. 維持開 subagent 的方式，shoal 仍是 Pilotfish 的替代品；relay 是 role 的
   另一種執行方式，不是新的派工機制。Phase 1 不做 MCP server，也不做 ACP。
2. role 名稱不變：main 照舊派 `executor`，由 binding 決定它在誰家跑。guard、
   lane 前綴與 brief 規則因此不用改。
3. 只呼叫官方 binary、用使用者自己登入的帳號；shoal 不讀、不轉送任何
   token 或 credential。
4. 失敗要明說：外部 agent 沒輸出、逾時或格式不符，一律回報失敗，不默默
   改回 native 執行。
5. 效益靠量測：bench/ab 加一組 relay arm，沒贏就不擴大範圍。

## Decisions（附建議）

| # | 問題 | 建議 |
| --- | --- | --- |
| D1 | relay 設定放哪 | `hosts/<host>/binding.toml` 新增 `[relay.roles]`，例如 `executor = "codex"`；沒寫的 role 一律 native。vendor 的指令與權限對應放 `core/vendors.toml`，host 中立 |
| D2 | 被 relay 的 role 在 host 裡長什麼樣 | render 照樣產出同名 subagent（`executor.md`），內容換成 relay 外殼：組 brief、呼叫 runner、轉交 hand-back。外殼只負責轉手，模型由 binding 的 `[relay] shell_model` 釘住（Claude 為 `haiku`，與 applier 現行的 pin 一致），不經 core tier 解析 |
| D3 | runner | `tools/shoal_relay.py`，一支 Python 腳本（與 repo 其他工具一致）。輸入 vendor、role、cwd、brief 檔；負責組指令、關 stdin、逾時、收輸出、驗 schema，stdout 只印正規化後的 hand-back JSON。`[relay.roles]` 非空時（與 D3a 同一個條件），render 才把它打包進 plugin（`plugins/claude/tools/shoal_relay.py`），外殼以 `${CLAUDE_PLUGIN_ROOT}/tools/shoal_relay.py` 呼叫；安裝後的 host 不依賴 repo checkout |
| D3a | relay 條款放哪 | relay 專用的 policy 條款放在 relay-only addendum，只有 `[relay.roles]` 非空時才併入 dist；沒開 relay 的 host，dist 與變更前位元組相同 |
| D4 | hand-back 格式 | `core/contracts/handback.schema.json`：`status`（done / blocked / failed）、`summary`、`changed_files`、`checks`（cmd、exit、decisive_line）、`unverified`、`vendor`、`session_id`、`usage`。Codex 用 `--output-schema` 加 `-o` 取得；exit 0 但檔案空或不合 schema 視為 failed |
| D5 | 寫入隔離 | write role 一律在 worktree 執行：Claude 端用 Agent 的 `isolation: "worktree"`，外殼與外部 CLI 都在該 worktree 裡跑；main 照現行方式整合。read-only role 不開 worktree |
| D6 | 權限對應 | `read-only` -> Codex `--sandbox read-only`；`write`、`verify` -> `--sandbox workspace-write`（限 worktree）。每次呼叫都明確帶上 `-c approval_policy="never"`、`-c sandbox_workspace_write.writable_roots=[]`、`-c sandbox_workspace_write.network_access=false` 並關閉 MCP，不讓使用者的 `~/.codex/config.toml` 放寬邊界（實際 key 名以 T1.0 實測為準）。永不使用 `danger-full-access` 或 bypass 類旗標。security role 在 phase 1 不得 relay（render 時拒絕） |
| D7 | 防止外部 agent 再派工 | Codex 也裝了 shoal，外部 session 會讀到 `~/.codex/AGENTS.md` 的 bootstrap 而開始派工。主要做法：runner 在 brief 開頭注入 role 標記（「你是 shoal named role `<role>`，只做被指派的事，不派 subagent」），named role 本來就會忽略 orchestration 段落。備援：runner 設 `SHOAL_RELAY_ROLE=<role>`，guard 讀到時把整個 session 當成該 named role。`--ignore-user-config` 會丟掉什麼（AGENTS.md、hooks、`spawn_agent`）由 T1.0 實測後再決定要不要用 |
| D8 | 認證與計費 | runner 不動 credential。`shoal doctor` 檢查 vendor binary 存在、已登入，並在環境裡有 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 時警告「會改用 API 計費」 |
| D9 | 外部失敗時 | 回 `status: blocked` 或 `failed` 加原因，由 main 決定改派 native 或停下；phase 1 不做自動 fallback |
| D10 | 逾時與預算 | 每個 role 有預設 wall-clock 上限（applier 10 分鐘、executor 25 分鐘，可在 binding 覆寫）；逾時就 kill，回 failed 加已取得的部分輸出。Codex 只回 token usage，phase 1 記 token、不換算美元 |
| D11 | 驗收 | bench/ab 新增 `shoal-relay` arm（Claude main，executor/applier 走 Codex，verifier 留 Claude），跑 v2 任務：通過數 ≥ shoal arm、時間 ≤ shoal 的 1.5 倍；成本分兩家各自記錄。relay arm 的 plugin 由 bench 專用的 relay binding overlay render 到該 arm 自己的 plugin-dir，`shoal` arm 維持 relay 關閉作為對照。`hosts/claude/binding.toml` 要等 bench 達標才開 relay；未達標就停在 phase 1 檢討，不進 phase 2 |

## Security review

2026-10-21 `security-reviewer` 審 D5–D8 與 guard 變更（T0.1）。全部採納；
標「實測」的項目由 T1.0 確認，確認不了就停下回報，不放寬。此節與上方
Decisions 衝突時，以此節為準。

| # | 區域 / 嚴重度 | finding | 處置 |
| --- | --- | --- | --- |
| F1 | D5 / High | 任何 Bash 都能直接呼叫 runner，`-C` 填錯會寫進 main checkout | runner 在 `realpath(cwd)` 不是 linked worktree（`git rev-parse --git-dir` 等於 `--git-common-dir`）時回 `blocked`、不 spawn；只接受 `executor`、`applier` |
| F2 | D6 / High | 只 pin sandbox 不夠：`multi_agent` 預設開、apps 流量繞過 proxy、`web_search` 預設 cached、`/tmp` 與 `$TMPDIR` 可寫、MCP 沒有全域開關 | 加 pin `features.multi_agent=false`、`features.apps=false`、`web_search="disabled"`、`sandbox_workspace_write.exclude_slash_tmp=true`；`TMPDIR` 設成每次新建的 mkdtemp；MCP 關法以實測生效的 key 為準。T1.0 跑 canary（寫 worktree 外、寫 `/tmp`、`curl`、`spawn_agent`、列 MCP tools）全部要失敗 |
| F3 | D6 / Medium | trusted project 會載入 repo 的 `.codex/config.toml`、hooks、rules，未 pin 的 key 由 repo 決定 | 實測 worktree 的 trust 判定；能做到就強制 relay 為 untrusted，並確認 user 層 shoal guard hook 仍載入；repo 內的 `.codex/hooks.json` 不得觸發 |
| F4 | D7 / Medium | brief 標記只是 prompt；codex host 預設 enforce，沒有 `SHOAL_RELAY_ROLE` 時 relay session 被當成 main，R1 會擋它改檔 | 主要控制改為 `multi_agent=false`；`SHOAL_RELAY_ROLE` 從備援改為必要條件（S1.11） |
| F5 | guard / Low | env 可能被拿來削弱 guard（風險與既有 `SHOAL_GUARD_DIRECT` 同級） | 只在 host 為 codex、值屬於 {executor, applier}、且 guard_dir（0700）下有 runner 建立的 `SHOAL_RELAY_NONCE` 檔時採用；runner 結束時刪除；採用與忽略都寫 log |
| F6 | D8 / High | runner 繼承整個 env，Codex 預設讓指令看得到含 KEY/SECRET/TOKEN 的變數，會進 transcript 與 `~/.codex/sessions` | spawn 只給 env allowlist（`PATH`、`HOME`、`USER`、`LANG`、`TERM`、新 `TMPDIR`、`CODEX_HOME`、`SHOAL_RELAY_*`）；pin `shell_environment_policy.inherit="core"`、`ignore_default_excludes=false`；拿掉 API key 等於固定走訂閱，`forced_login_method` 能否 pin 由實測確認 |
| F7 | D8 / Low | 部分輸出、stderr、`login status` 可能帶出 secret | 輸出前遮蔽名稱符合 KEY/SECRET/TOKEN/PASSWORD 的 env 值並限制 byte 數；doctor 只解析登入方式，不轉印原始輸出；同時檢查 `CODEX_API_KEY` |
| F8 | hand-back / Medium | hand-back 是外部模型寫的資料，可能注入保有 Write/Edit 的外殼 | `changed_files` 由 runner 以 `git status --porcelain -z` 計算，與自報不一致時標出；schema `additionalProperties:false` 加 `maxLength`；外殼 tools 只給 `Bash`；addendum 寫明 hand-back 是資料，write relay 後一律派 fresh verifier |
| F9 | D10 / High | Claude Bash 單次上限 10 分鐘，短於 executor 25 分鐘；runner 被殺後 codex 成為孤兒繼續寫 worktree | runner 攔 SIGTERM/HUP/INT 時 killpg、偵測 parent 死亡就結束、收尾清掉所有後代程序；D10 上限必須小於外殼傳給 Bash 的 timeout，否則外殼用 `run_in_background` |
| F10 | 巢狀 sandbox / Medium | 為了讓巢狀 sandbox 能跑而放寬過頭 | `excludedCommands` 只放 runner 的確切路徑，不放 `codex`、`python3`；Codex sandbox 套用失敗回 `failed`，絕不以無 sandbox 重跑 |
| F11 | 路徑 / Low | brief、`-o`、schema 路徑可被替換 | `-o` 與 brief 副本放 runner 自建的 0700 mkdtemp（worktree 外）；brief 以 `O_NOFOLLOW` 開、須為一般檔案且有大小上限；schema 從 `${CLAUDE_PLUGIN_ROOT}` 讀；argv 用 list，不用 `shell=True` |
| F12 | privacy | `~/.codex/sessions` 會留下 relay 的完整 transcript | T1.0 確認 `codex exec --ephemeral` 的實際效果與保留、刪除方式，寫入 PROGRESS.md |

### T1.0 後的決策（Miyago 2026-10-21）

- F2/F4：`features.multi_agent=false` 實測無效（spawn_agent 仍可呼叫）。
  改由 guard 強制：relay session（S1.11 條件成立）的 PreToolUse 拒絕
  `spawn_agent` 與任何派工工具；不採用 `model_catalog_json` override。T1.4
  須先確認 codex 的 PreToolUse 會對 `spawn_agent` 觸發，否則停下回報。
- F3：relay 使用真實 `~/.codex`（guard hook 才會載入）。worktree 內存在
  `.codex/`（任何層級的追蹤或未追蹤檔）時，runner 回 `blocked`、不 spawn。
  另記錄：`codex exec -s workspace-write` 會自動把未登記的 repo 以 `trusted`
  寫入 `~/.codex/config.toml`（依 main repo root 判定），runner 不改使用者
  config，doctor 列出 relay 造成的項目供使用者清理。
- F6：不 pin `forced_login_method`（pin 時若環境有 API key，codex 會登出並刪除
  auth.json）；靠 env allowlist 排除 `OPENAI_API_KEY`、`CODEX_API_KEY`，doctor
  警告。
- 其他：runner 以絕對路徑執行 codex（`core/vendors.toml` 記錄解析方式），
  不經 shell alias（使用者的 `codex` alias 帶 bypass 旗標）；`--ephemeral`
  一律開啟（F12：不寫 sessions rollout）；MCP 以
  `mcp_servers.<id>.enabled=false`（id 由 `codex mcp list --json` 取得）加
  `features.plugins=false` 關閉；`--output-schema` 必須是 strict schema；exit 0
  且 `-o` 為 0 byte 視為 failed、逾時 exit 124 視為 failed。
- P1 relay 逾時上限 540 秒（executor 540、applier 300），外殼一律前景執行；超過 Bash 600 秒上限的長任務留待之後評估。

## Phases

- P0：`security-reviewer` 審 D5–D8 與 guard 變更。
- P1：Claude host -> Codex，role 限 `executor`、`applier`。runner、schema、
  render 外殼、guard 的 `SHOAL_RELAY_ROLE`、doctor、bench arm；bench 達標後
  才在 `hosts/claude/binding.toml` 正式開啟。
- P2（P1 達標後另行核准）：Codex host -> Claude（`claude -p --output-format json
  --json-schema`），優先 `verifier`，對應 researcher 找到的「Claude 審 Codex」
  方向。
- P3（另行核准）：改用 ACP 作為共同 transport，加入 OpenCode、Grok；
  Gemini/agy 等 ToS 狀況明朗再評估。

## Scope

- 新增：`core/vendors.toml`、`core/contracts/handback.schema.json`、
  `tools/shoal_relay.py`、relay 外殼的 render 模板、`tests/test_relay*.py`、
  bench/ab 的 `shoal-relay` arm。
- 改：`tools/render.py`（讀 `[relay.roles]`，產出外殼、拒絕 security role）、
  `hosts/claude/binding.toml`、`hooks/shoal_guard.py`（`SHOAL_RELAY_ROLE`）、
  bootstrap 條款、`tools/shoal_install.py` 的 doctor。

## Non-goals

- MCP server、ACP、A2A（P3 再評估）。
- 多家同時跑同一題再比較（best-of-n）。
- 自動 fallback、跨家 session resume、美元成本換算。
- 改動既有 role 名稱、lane 或 guard 規則。

## Risks

- ToS：只用官方 binary 與使用者自己的登入；大量自動化是否仍算 ordinary use
  無法確認，bench 只在 Miyago 本機、低頻跑。
- 巢狀 sandbox：macOS 上 Codex 在 Claude sandbox 內可能出現
  `sandbox_apply: Operation not permitted`。P1 第一個任務就是實測，失敗時
  記錄需要的 `excludedCommands` 設定。
- 輸出脆弱：stdin 一律關閉、`-o` 與 schema 同時檢查、逾時強制結束，都要有
  測試覆蓋（TESTS.md S1.3–S1.6）。
- CLI 版本漂移：`core/vendors.toml` 記錄驗證過的最低版本，doctor 比對。
