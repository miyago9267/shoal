# cross-vendor-relay：PROGRESS

## 2026-10-21

- 建立 spec 草稿：SPEC.md、TASKS.md、TESTS.md。依據兩組 researcher
  （experiment / control）的 prior art 與反證結果。
- Miyago 決定：phase 1 維持開 subagent 的方式，shoal 繼續作為 Pilotfish
  的替代品；不做 MCP server 或 ACP。
- plan-critic 兩輪 REVISE，8 個 blocker 已全部處理；`security-reviewer`
  完成 T0.1（F1–F12 全部採納，寫入 SPEC.md）。
- 待 Miyago 核准後開始 T1.0。

## T1.0（2026-10-21）

環境：codex-cli 0.160.1（`~/.local/bin/codex`；`/opt/homebrew/bin/codex`
不存在，nvm 另有 0.162.1）。zsh alias `codex` 帶
`--dangerously-bypass-approvals-and-sandbox`，runner 必須用絕對路徑 exec。
探測在 throwaway repo + linked worktree、env allowlist、`</dev/null`、
`--ephemeral --strict-config`（約 12 次 model 呼叫）。巢狀 sandbox：Miyago
的 Claude settings 沒有 `sandbox`，不適用，未測。

| # | 項目 | 結果 | 證據 |
| --- | --- | --- | --- |
| 1a | D6 `-c` key | 全部有效：`approval_policy="never"`、`sandbox_workspace_write.{writable_roots=[],network_access=false,exclude_slash_tmp=true}`、`web_search="disabled"`、`shell_environment_policy.{inherit="core",ignore_default_excludes=false}`、`features.apps=false`；`--sandbox workspace-write` 與 `exclude_tmpdir_env_var` 另有 | `exec --strict-config -c k=v` 對未知 key 報 `unknown configuration field`；canary 行為見 2 |
| 1b | `features.multi_agent=false` | **BLOCKED（按 spec 寫法）**：key 有效、`codex features list -c ...` 顯示 false，但 `spawn_agent` 仍可呼叫（v2 模型 gpt-6-sol 與 v1 模型 gpt-5.6-luna 皆是；加 `features.multi_agent_v2=false`、`agents.max_depth=0` 也沒用）。工具是否出現由 model catalog 的 `multi_agent_version` 決定。有效替代：`codex debug models` 去掉 `multi_agent_version` 後以 `-c model_catalog_json=<f>` 載入，工具清單即無 `spawn_agent`（1 次實測，dedicated home） | 提示詞要求呼叫 `spawn_agent`：預設回 `task_name`；catalog 覆寫後回 NOTOOL 且工具清單無 collaboration.* |
| 1c | MCP | 無全域開關；`mcp_servers={}` 不會清空。config 定義的 server 用 `mcp_servers.<id>.enabled=false`（id 由 `codex mcp list --json` 列舉，未知 id 報 `invalid transport`）；plugin 提供的 server（computer-history、cua_repl）只能用 `features.plugins=false`；repo 內 `.codex/config.toml` 的 server 列不出來，只能靠 untrusted | `codex mcp list --json -c features.plugins=false` |
| 2 | S1.20 canary（real home、預設 trust、全 pin） | 寫 worktree 外、`/tmp`、`$HOME`、main repo `.git`、`wt/.codex`：全部 rc=1 且檔案不存在；`curl` rc=6、python socket 失敗；repo `.codex/hooks.json` 未觸發；`env` 名單無 KEY/SECRET/TOKEN（餵入的 `FAKE_TEST_TOKEN` 被 core 濾掉）；MCP 工具 none；**spawn_agent 未擋住（見 1b）**。`TMPDIR` 可寫（預期），但不得與 `-o`/brief 目錄同一個。worktree 內 `git commit` rc=128（main `.git` 在 writable root 外，原因未細查） | 單一 `canary.sh` 的 `aggregated_output`（`--json` 事件） |
| 3 | F3 trust | 判定看 exact path 或 worktree 的 main repo root，祖先目錄不繼承；`-c projects.X.trust_level` 無效（設 trusted/untrusted 都不影響載入）。`exec -s workspace-write` 在未登記的 repo 會**自動把 trusted 寫進 CODEX_HOME/config.toml**（read-only 不會）。config.toml 內明列 `untrusted` 會被尊重：repo config 不載入、workspace-write 仍有效、不被覆寫。hook trust 另存 `hooks.state`（key 含 hooks.json 路徑 + hash），repo hooks 未登記不會跑。**衝突 -> BLOCKED**：要強制 untrusted 必須用 dedicated CODEX_HOME，但其中 user 層 guard hook 因無 `hooks.state` 而不載入（hash 算法未解；`--dangerously-bypass-hook-trust` 屬 bypass 旗標，D6 禁用）；用真 `~/.codex` 則 guard 確認載入（`~/.local/state/shoal/guard/state/<thread_id>.json` 出現）但 repo config 會被信任 | `debug prompt-input` 比對 `developer_instructions` 標記；`env` 出現 repo 設定的 `REPO_CANARY` |
| 4 | `--ignore-user-config` | 丟掉：config.toml（MCP、plugins、model、trust、hooks.state，故 hooks 視為未信任）。保留：`$CODEX_HOME/AGENTS.md`（模型自述含 Monika/shoal bootstrap）、`spawn_agent`/collaboration 工具。MCP 在此模式不能再帶 `mcp_servers.*.enabled`（未知 id 報錯） | r8：模型自述 + 工具清單 |
| 5 | F6 | `forced_login_method="chatgpt"` 可 pin，無 API key 時走 ChatGPT 訂閱正常。**但 pin 加上 env 有 `OPENAI_API_KEY`/`CODEX_API_KEY` 時 codex 會自動 logout（刪 CODEX_HOME/auth.json）**；不 pin 時 fake key 直接 401（key 優先於 ChatGPT 登入）。建議不 pin，只靠 env allowlist + doctor 警告 | dedicated home 實測；真 `~/.codex/auth.json` 完好 |
| 6 | F12 `--ephemeral` | 不寫 `sessions/` rollout（真 home 4 次 ephemeral 無新檔）；不加則寫 `sessions/Y/M/D/rollout-*.jsonl`（完整 transcript）。state/logs sqlite 仍會更新（內容未檢查）。刪除用 `codex delete <id>`；dedicated home 可整個刪。ephemeral 下子 thread 會 `no rollout found`，但不可當 multi_agent 的控制 | `find ~/.codex/sessions -newer`；非 ephemeral 對照 |
| 7 | `--json` / `-o` / schema | JSONL 事件：`thread.started`、`turn.started`、`item.started/completed`（`agent_message`、`command_execution` 含 `aggregated_output`、`exit_code`；另有 `error` 警告項）、`turn.completed{usage}`。strict schema（全 required + `additionalProperties:false`）可用，`-o` 寫入合法 JSON；非 strict schema -> API 400、exit 1、無 `-o`。最終訊息為空 -> exit 0 且 `-o` 為 0 byte；被 timeout 殺 -> exit 124、無 `-o`、僅 2 個事件 | 各 1 次 |

副作用：探測期間 codex 自行在 `~/.codex/config.toml` 新增
`[projects."/private/tmp/claude-501/-Users-miyago-dotfile/9662e93b-f41d-41d1-90d3-a42fd412e160/scratchpad/t10/repo"]`（trusted），
我沒有手動改該檔，也未清除，請 Miyago 自行刪該 table。
待 Miyago 決定（T1.2 前）：F2/F4 改用 catalog 覆寫；F3 在「dedicated home
無 guard」與「真 home 被自動 trust」之間取捨（建議 runner 在 worktree 含
`.codex/` 時拒絕，或 hook trust hash 解出後用 dedicated home）；F6 不 pin。

- 2026-10-21 Miyago 決定：F2/F4 由 guard 擋 `spawn_agent`（不採 catalog
  覆寫）、F3 有 `.codex/` 就拒跑、F6 不 pin。`~/.codex/config.toml` 中 T1.0
  probe 自動加入的 scratch trusted table 已移除。

## T1.1、T1.2（2026-10-21）

- 新增 `core/contracts/handback.schema.json`（D4 欄位加 runner 欄位
  `reported_files`、`files_mismatch`、`reason`、`exit_code`、`stderr_tail`、
  `partial_output`；每層 `additionalProperties:false`、全 required、字串
  `maxLength`、陣列 `maxItems`）與 `core/vendors.toml`（codex 絕對路徑解析、
  access -> sandbox、T1.0 確認的 `-c` pin、`mcp_servers.<id>.enabled=false`
  加 `features.plugins=false`、`--ephemeral --strict-config`、min 0.160.1、
  env allowlist）。
- 新增 `tools/shoal_relay.py`（`security-executor`）：F1 linked worktree
  根目錄檢查、F3 `.codex` 拒跑（worktree 任何層級、main checkout 根、HOME
  以外的祖先）、F5 nonce 檔 `<guard_dir>/relay-<nonce>`（沿用
  `hooks/shoal_guard.py` 的 `_guard_dir`、`_open_private`，以子程序 env 計算，
  結束時刪除；內容 `{"role","pid"}`，供 T1.4 讀取）、F6 env allowlist、F7
  遮蔽、F8 `git status --porcelain -z` 比對、F9 程序樹清理、F10 sandbox 失敗
  不重跑、F11 brief/`-o`/schema 處理。
- 交給 codex 的 `--output-schema` 是 schema 的 vendor 子集（status、summary、
  changed_files、checks、unverified），只留 T1.0 實測可用的 strict 關鍵字；
  `maxLength`/`maxItems` 由 runner 收到輸出後檢查，超出即 failed。
  `maxLength` 在 Codex strict 模式是否被接受未實測。
- 測試：`tests/test_relay_contract.py`、`tests/test_relay_runner.py` 共 32
  個（假 codex binary，不呼叫真 codex），全套 `unittest discover` 1798 個 OK
  （skipped 1）；`render.py --check` 六個 target 全過，dist 無變動（S0.3）。
  S1.18 另做 mutation 檢查：關掉後代追蹤時 setsid 孫程序測試會失敗。
- 已知限制：macOS 沒有 subreaper，setsid 後立刻被遺棄的孫程序只能靠每 0.5
  秒的 `ps` 掃描抓到，在掃描間隔內就脫離的程序可能漏掉；Linux 用
  `PR_SET_CHILD_SUBREAPER` 補上。

## T1.3–T1.5 整合（2026-10-21）

- 2026-10-21：`feat/cross-vendor-relay` 合併 7e5ba4c（guard `SHOAL_RELAY_ROLE`，
  T1.4）與 b489b54（render 外殼與 doctor，T1.3、T1.5）。整合修正：plugin 的
  `hooks/shoal_guard.py` 是 compat shim，沒有 `_guard_dir`/`_open_private`，
  打包的 runner 建 nonce 失敗；render 在 relay 開啟時另打包
  `plugins/claude/tools/shoal_guard.py`（`hooks/shoal_guard.py` 的副本，納入
  `render --check` 與 golden `.sha256`），runner 先用同目錄副本、再退回
  `hooks/shoal_guard.py`，載入後確認函式存在，建 nonce 的任何失敗都回
  `blocked`。逾時改為 executor 540、applier 300 秒，render 拒絕
  `[relay.timeouts]` 大於 540，外殼一律前景執行（Bash timeout = N+60 秒），
  移除 `run_in_background` 分支。已知限制：runner F9 在 macOS 沒有 subreaper，
  後代掃描有間隔漏洞；guard 只檢查 nonce 的 pid 是否存活，不檢查程序祖先關係；
  codex `hooks.json` 的 matcher 在 collaboration 工具中只涵蓋 `spawn_agent`。
- 2026-10-21：fresh verifier 對 T1.1–T1.5 回 CONFIRMED（1866 tests OK；
  S0.1–S0.4、S1.1–S1.12、S1.14–S1.19 逐項有 evidence）；advisory A1 已以 S0.3
  範圍說明處理；未驗：grok host 帶有效 nonce 時沒有 relay log（行為不變）。

## T1.6 bench 結果（2026-10-22）

- 數字（`bench/ab/results/relay-v2.json`，8 任務 x 2 rep，shoal vs shoal-relay）：
  shoal 14/16，median 89 s，$0.323/run；relay 13/16，median 173 s（1.94x），
  $0.331/run Claude + avg 150,724 input（137,360 cached）/ 2,378 output Codex
  tokens；relay runs with codex>0: 7，pass 6，median 207 s；on the four tasks
  where relay used Codex (a,c,d,h): shoal 7/8 median 138 s $0.426，relay 7/8
  median 193 s $0.344。
- S1.13 未達標（通過數 13 < 14、時間 1.94 倍 > 1.5 倍），依 D11 停在 P1 檢討，
  不進 T1.7。
- 診斷 `codex.calls = 0` 的 9 個 run：直接讀原 run 留在 `~/.claude/projects/
  *shoal-ab-v2-*-shoal-relay-*` 的 transcript（含 subagents/），對照 guard.jsonl
  的 `relay_adopt`（Codex 端事件，每個 Codex session 一組 session hash）。
  - b-bug-hunt x2、g-feature-across-layers x2：H1 成立。main 完全沒派工，用
    `python3 - <<EOF` 的 Bash heredoc 自己改檔（bootstrap 要求 main 不編輯，除非
    `#direct`）；guard 對這些 main session 只記到 prompt state，沒有 tool 事件。
    relay 的 shell 根本沒被觸發。b rep2 的 736 s、$0.135：main 的收尾指令
    `rm /tmp/t.json` 卡在互動確認，被丟背景，`claude -p` 等到該 shell 結束才收尾，
    屬 wall 虛增，與 relay 無關。
  - e-security-hardening x2：預期內，派 `security-reviewer` 路徑的
    `security-executor`，不走 relay。
  - h rep2：H1 + H2。main 先自己改完 `pool.py`，再派 applier 改測試但沒帶
    `isolation: worktree`，runner 回 `blocked: cwd is not a linked worktree`，main 沒重派
    就停下來問使用者；Codex 未執行（無 `relay_adopt`）。
  - f-refactor-split x2：計數器漏算（H3 的窄版）。Codex 其實跑了（hand-back 的
    usage 為 393,636 / 363,852 input，`relay_adopt` 兩個 session 對得上）。runner
    回 `status: blocked, files_mismatch: true`；`blocked` 是 Codex 自己回報的（rep1
    環境沒有 pytest，rep2 想 git commit 被 sandbox 擋），不是 runner 的 files_mismatch
    造成（更正：見 fix/relay-mismatch）。runner 以 exit 1 結束，Bash tool_result 變成
    `Exit code 1\n{...}`，`relay_handbacks()` 的 `json.loads` 失敗而略過。
    以去掉前綴的方式重跑計數器可得 1 筆/run。
  - H3 的寬版（stream-json 不暴露 subagent 的 Bash 結果）不成立：a、c、d、h rep1
    共 8 筆乾淨 JSON hand-back 全被計到，和 `relay_adopt` 的 10 個 bench session
    扣掉 f 的 2 個後剛好一致。
- 修正後的 codex>0 run 是 9 個，不是 7 個（a x2、c x2、d x2、f x2、h rep1）。
- 附帶觀察：第一次派 executor/applier 沒帶 `isolation: worktree` 而被擋，發生在
  c rep2、d x2、f x2、h x2（共 7 run），多數會重派，每次多繳一輪（d rep1 812 s）。
  f 的 score 用 `git diff` 計 files_changed：rep1 改動留在 worktree 故 0 且 fail；
  rep2 main 已 commit 合併，故也是 0 但 pass，bench 低估 commit 後的改動量。
- 建議修正（皆未實作，本任務不動 relay/runtime）：(1) `relay_handbacks()` 先剝
  `Exit code N\n` 前綴，並只計有 `session_id` 或 `usage` 的 hand-back（避免把
  worktree 拒絕算成呼叫）；(2) 已修：runner 比對前剝 ` (deleted)` 類註記
  （7522f1d），brief 開頭寫明不碰 git、check 跑不了回 `done` 加 `unverified`；
  (3) bootstrap/agent 描述把 `isolation: worktree` 寫成必填，或 guard 在派工時直接
  deny 缺少 isolation 的 relay role；(4) bench 的 relay arm 對 main 直接改檔的
  run 標記 `no_dispatch`，並在 prompt 或 guard 補上 Bash 寫檔偵測，否則小任務
  永遠繞過 relay；(5) 重跑 relay arm 前先決定 S1.13 是否改成只比有派工的任務。

## T1.6 bench 公平性修正（2026-10-22，`fix/relay-bench-fair`）

- 隔離：render 對 write role（executor、applier）的 relay 外殼 frontmatter 輸出
  `isolation: worktree`，caller 不必再記得帶。已用 plugin-dir 實測（relay overlay render 後
  `claude -p --plugin-dir`，main 派 `shoal:applier` 不帶 isolation）：外殼在
  `<repo>/.claude/worktrees/agent-*` 的 linked worktree 內執行，runner 沒有回
  「not a linked worktree」，Codex 實際執行（有 `session_id`、`usage`），`hello.txt` 出現在該
  worktree，主 checkout `git status` 乾淨。plugin agent 會遵守此欄位，故不需要外殼自檢 fallback。
- bench 計數（`bench/ab/run_ab.py`）：`relay_handbacks()` 先剝 `Exit code N\n`；只有帶
  `session_id` 或 `usage` 的 hand-back 算 relay call，其餘記入 `relay_blocked`（含原因）；每個
  run 記 `dispatches`（main 的 Agent/Task 依 `subagent_type`）、`main_edits`，並在 main 改了檔
  卻沒派 write role 時標 `no_dispatch: true`（所有 arm）；所有 arm 改用 stream-json 以取得這些事件；
  `--summarize` 另印兩個 shoal arm 都派了 write role 的 (task, rep) 子集、relay call/blocked 數與
  `no_dispatch` 計數。
- `bench/ab/results/relay-v2.json` 沒存事件流，沒有 `dispatches` 與 blocked 原因，無法離線重算；
  需重跑 relay arm 才有新欄位。

## 2026-10-22 relay 改動落地到 primary checkout（`fix/relay-landing`）

- 診斷（`bench/ab/results/relay-v2b.json`）：relay 外殼 frontmatter 帶 `isolation: worktree`，Codex 在
  `.claude/worktrees/` 下的 linked worktree 改檔，回 `done` 後改動只留在該 worktree，要 main 自己合併。
  7 個失敗的 relay run 中有 5 個是 Codex 回 `done`（或已派 executor），primary checkout 的
  `files_changed` 卻是 0、hidden tests 失敗；`shoal` arm 的 executor 直接改 primary checkout，兩個 arm
  不可比。
- 修正：`tools/shoal_relay.py` 在 status 為 `done` 且 `changed_files` 非空時，用暫存 index
  （`GIT_INDEX_FILE` 在 runner 的 0700 private dir）`read-tree HEAD`、`add -A`、`write-tree` 取得
  worktree 快照，`git diff-tree -r --no-renames --binary --full-index` 產生 patch，再於 primary worktree
  （`git worktree list --porcelain` 第一筆，須為同一 repo 的非 bare main worktree）跑 `git apply`。
  兩邊都不 commit，worktree 與 primary 的 index 都不動。路徑任一元件是 `.git`、`.codex`、`.claude`
  （不分大小寫）、絕對路徑或 `..`，或含 symlink、submodule 時整份拒絕。不用 `--3way`：它隱含
  `--index`，primary 有未提交改動時直接失敗，衝突時還會留下 conflict marker；一般 `git apply`
  全有或全無。結果寫在 hand-back 新欄位 `landing`（`landed`、`reason`、`worktree`），只屬 runner
  輸出，不在交給 Codex 的 strict schema；落地失敗不改 status，reason 只帶 git 的第一行 `error:`
  （路徑，不含檔案內容），並經 redaction。
- 外殼與 relay-only addendum：`landed` 為 true 時告訴 main 改動已在 primary checkout，不要再合併；
  false 時給 `landing.worktree` 與合併指令（`refused` 時先檢查 worktree）。repo binding 沒開 relay，
  relay-off dist 位元組不變（S0.3）。
- bench：`codex.handbacks` 逐次記 status、reason（≤200 字）、`landed`、`landing_reason`；新增
  `--keep-failed`，只保留沒通過的 run 的工作目錄。
- 測試：`tests/test_relay_runner.py` 的 `RelayLanding`（tracked edit、新檔含 binary、刪檔、拒絕路徑、
  apply 衝突維持 done 且 landed false、非 done 不落地）、`test_relay_contract.py` 的 `LandingPaths`、
  render 與 bench 的對應測試。relay arm 需重跑才能看到效果。
