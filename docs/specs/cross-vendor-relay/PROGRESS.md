# cross-vendor-relay：PROGRESS

## 2026-10-21

- 建立 spec 草稿：SPEC.md、TASKS.md、TESTS.md。依據兩組 researcher（experiment / control）的 prior art 與反證結果。
- Miyago 決定：phase 1 維持開 subagent 的方式，shoal 繼續作為 Pilotfish 的替代品；不做 MCP server 或 ACP。
- plan-critic 兩輪 REVISE，8 個 blocker 已全部處理；`security-reviewer` 完成 T0.1（F1–F12 全部採納，寫入 SPEC.md）。
- 待 Miyago 核准後開始 T1.0。

## T1.0（2026-10-21）

環境：codex-cli 0.160.1（`~/.local/bin/codex`；`/opt/homebrew/bin/codex` 不存在，nvm 另有 0.162.1）。zsh alias `codex` 帶 `--dangerously-bypass-approvals-and-sandbox`，runner 必須用絕對路徑 exec。探測在 throwaway repo + linked worktree、env allowlist、`</dev/null`、`--ephemeral --strict-config`（約 12 次 model 呼叫）。巢狀 sandbox：Miyago 的 Claude settings 沒有 `sandbox`，不適用，未測。

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

副作用：探測期間 codex 自行在 `~/.codex/config.toml` 新增 `[projects."/private/tmp/claude-501/-Users-miyago-dotfile/9662e93b-f41d-41d1-90d3-a42fd412e160/scratchpad/t10/repo"]`（trusted），我沒有手動改該檔，也未清除，請 Miyago 自行刪該 table。
待 Miyago 決定（T1.2 前）：F2/F4 改用 catalog 覆寫；F3 在「dedicated home 無 guard」與「真 home 被自動 trust」之間取捨（建議 runner 在 worktree 含 `.codex/` 時拒絕，或 hook trust hash 解出後用 dedicated home）；F6 不 pin。
- 2026-10-21 Miyago 決定：F2/F4 由 guard 擋 `spawn_agent`（不採 catalog 覆寫）、F3 有 `.codex/` 就拒跑、F6 不 pin。`~/.codex/config.toml` 中 T1.0 probe 自動加入的 scratch trusted table 已移除。
