# Claude Code 安裝

## Claude Code plugin

Claude Code 的第二條安裝路徑，給沒有 dotfile 的使用者。內容（10 個 role，含 `watcher`、`researcher`、
`shoal-orchestration` skill、policy bootstrap；dispatch guard 在另一個可選 plugin）全部由
`python3 tools/render.py --host claude-plugin --write` 從 claude host 的 render 結果、
`hooks/shoal_guard.py` 與根目錄 `VERSION` 產生，輸出在 `plugins/claude/`（`shoal`）、
`plugins/claude-guard/`（`shoal-dispatch-guard`）與
`.claude-plugin/marketplace.json`（兩個 plugin 同一個 marketplace）；
`--check` 擋住手改。Codex 的
`plugin/` 目錄與這條路徑無關。需要 Claude Code 2.1 以上與 `python3`。

```bash
# 1. 安裝最新穩定版（預設 branch，即 main）。
claude plugin marketplace add miyago9267/shoal
claude plugin install shoal@shoal
# dispatch guard 預設要裝；不要 guard 就省略這行（等於只有政策文字）。
claude plugin install shoal-dispatch-guard@shoal

# 想釘在某個版本：把 vX.Y.Z 換成實際存在的 tag。
# claude plugin marketplace add miyago9267/shoal#vX.Y.Z

# 升級：marketplace 的 source 不同會被拒絕，所以先移除再加回。
claude plugin marketplace remove shoal
claude plugin marketplace add miyago9267/shoal
claude plugin update shoal@shoal
claude plugin update shoal-dispatch-guard@shoal

# 解除安裝（只關 guard 就只跑第一行）。
claude plugin uninstall shoal-dispatch-guard@shoal
claude plugin uninstall shoal@shoal
claude plugin marketplace remove shoal

# 只在單一 session 試用（不寫任何 config）。
claude --plugin-dir ./plugins/claude --plugin-dir ./plugins/claude-guard
```

- `owner/repo#<ref>` 的 `<ref>` 是 branch 或 tag，由 `git clone --branch` 解析（在
  Claude Code 2.1.291 實測：ref 不存在時回報 `Remote branch ... not found`）。不寫
  `#<ref>` 會跟預設 branch（main，即最新穩定版）。要釘版本時，tag 沿用 repo 的
  `v<VERSION>`，必須包含 `plugins/claude/` 與 `.claude-plugin/marketplace.json`；該 tag
  發佈前，`#vX.Y.Z` 指令會失敗。`claude plugin tag plugins/claude` 也可以建
  `shoal--v<VERSION>` 形式的 tag，兩種擇一，marketplace 用哪個就 `#` 哪個。
- plugin 與 marketplace 的版本都等於根目錄 `VERSION`。
- 拆分（modular-install S4）：base `shoal` 帶 role、skill、policy 與 SessionStart 的 policy
  注入（`hooks/hooks.json` 只有 SessionStart），沒有任何 guard hook。`shoal-dispatch-guard`
  只有 `hooks/hooks.json` 與 `hooks/shoal_guard.py`，兩個 plugin 的 hook 在同一個 session
  合併執行；guard 看的是 hook payload 的 `agent_type`，與哪個 plugin 註冊無關，所以仍
  認得 `shoal:<role>`。`tools/shoal_install.py --host claude` 預設兩個都裝，
  `--without dispatch-guard` 不裝 guard plugin。
- dotfile updater 的契約（updater 在 repo 外，這裡只記規則）：從 shoal 升到有拆分的版本時，
  只更新 `shoal@shoal` 會讓 guard 消失（base 不再帶 hook）。updater 現在只 `git archive`
  三個路徑，要加上 `plugins/claude-guard/`
  （3.11.0 起 updater 改讀 manifest，由
  `tools/shoal_install.py --update` 處理）；
  並且在 `shoal@shoal` 之外，依
  `${XDG_DATA_HOME:-~/.local/share}/shoal/modules.json` 的 `claude.modules`
  決定：含 `dispatch-guard`（或沒有 manifest，沿用預設 ON）就 `claude plugin install` /
  `update` `shoal-dispatch-guard@shoal`；
  不含 `dispatch-guard` 而且 `chain` 沒有 `claude` 成員時，
  才 `claude plugin uninstall` 它（除非 `dispatch-guard` 被取消**且**chain 沒有 claude 成員，
  否則都要裝）。manifest
  的內容由 `tools/shoal_install.py` 維護；updater 不要自己改它。
- 相容檔（3.8.1）：3.8.0 的拆分讓升級前就開著的 Claude session 壞掉，因為它們保留舊的 hook 設定，
  仍指向基礎 plugin 的 `${CLAUDE_PLUGIN_ROOT}/hooks/shoal_guard.py`，檔案不見後每次工具呼叫都失敗。
  所以基礎 plugin 保留 `hooks/shoal_guard.py`，但它只是一個小 shim，**沒有**註冊在 `hooks/hooks.json`：
  用同樣的 argv 與 stdin 轉交給 guard plugin 的腳本（先找同一個 marketplace 的
  `../claude-guard/hooks/shoal_guard.py`，3.11.0 前的
  `../claude-guard-plugin/` 保留一個 release，再找 plugin cache 的
  `shoal-dispatch-guard`），
  找不到就以 0 結束、不輸出，永遠不會自己擋。新開的 session 用不到它；dotfile updater 不要刪它，
  也不要把它當 guard 的安裝證據。
- guard hook 的 command 一律是
  `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/shoal_guard.py" --host claude --plugin`，
  路徑加引號，安裝路徑含空白也能跑；SessionStart 的 `emit-sessionstart.sh` 自己固定
  `PATH=/usr/bin:/bin`，把 `plugins/claude/policy/claude-md.bootstrap.md` 注入 session。
  如果全域 `CLAUDE.md` 已經有 shoal bootstrap，就不再注入。
- namespace：plugin 的 agent 名稱是 `shoal:<role>`（例如 `shoal:executor`），skill 是
  `shoal:shoal-orchestration`。實測 hook payload 的 `agent_type` 與 Agent 工具的
  `subagent_type` 都是 `shoal:executor`；guard 只認裸名稱與 `shoal:` 前綴。
- 與全域安裝共存：已經用 `tools/install_hooks.py --host claude` 裝過全域 guard 時，
  plugin 的 hook 帶 `--plugin`，只在 user `settings.json`（`CLAUDE_CONFIG_DIR` 或
  `~/.claude`，symlink 會解開）確實有指向
  `${XDG_DATA_HOME:-~/.local/share}/shoal/guard/shoal_guard.py` 的對應 event entry，
  而且那支腳本存在時才什麼都不做；其他情況（沒有全域安裝、腳本不見、settings 讀不
  懂）plugin 那份照常執行，不會變成零次。兩邊同時存在時每個事件只會有一筆 log。
  SessionStart 偵測到全域 guard 會印一行提示，僅供參考。
- 預設模式與全域安裝相同（Claude 是 enforce）；`SHOAL_GUARD=shadow|off` 照常有效。

資料與保留（K6）：plugin 與全域安裝共用同一個 state 與 log 目錄
`${XDG_STATE_HOME:-~/.local/state}/shoal/guard/`（`state/`、`turns/` 與
`guard.jsonl`、`chain.jsonl`）。兩個檔各自超過 1 MiB 就改名為 `.1` 後繼續寫（只留一代）。
`chain.jsonl` 只放 guard chain 每個 member 的 `chain_*` 紀錄
（`chain_allow`、`chain_report` 等，量大），
`guard.jsonl` 留給 deny／allow／declare／state 等決策紀錄。
`guard.jsonl` 每行的欄位：`ts`、`host`、`event`、`tool`、`rule`、`decision`、`file`
（只有檔名）、`skip_reason`、`mode`、`reason`；另外有 `agent_type`（subagent 的類型，
照 host 傳來的原樣，例如 `general-purpose`、`worker`、`shoal:applier`；main session
的事件沒有）、`agent_id`（host 有提供時才有）、`session` 與 `turn`（session id、
turn id 的 sha256 前 8 個小寫 hex，不是原始 id，只用來分辨不同 session 與 turn）。
log 不記 prompt、檔案內容。
`claude plugin uninstall` 與 `marketplace remove` 不會刪這個目錄；要清除時手動執行：

```bash
rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/shoal/guard"
```

目錄會在下次事件重建。這個目錄與全域安裝共用，清除前先確認沒有進行中的 session
要保留 guard 的 turn 狀態。

## Claude Code 的 dispatch guard

共用說明（Claude Code 與 Gemini/agy）見 [dispatch guard](../guard.md)。

```bash
# 1. Dry-run：列出腳本與 settings 的變更，不寫入。
python3 tools/install_hooks.py --host claude

# 2. 使用者核准 dry-run 後安裝。
python3 tools/install_hooks.py --host claude --apply

# 只移除 shoal 的 entry（腳本留著，claude 與 agy 共用）。
python3 tools/install_hooks.py --host claude --uninstall --apply
```

- `--host claude` 改 `settings.json`（`--home`，其次 `CLAUDE_CONFIG_DIR`，預設
  `~/.claude`）：`UserPromptSubmit`，以及 matcher 為
  `Edit|Write|NotebookEdit|MultiEdit|Agent|Workflow|Bash` 的 `PreToolUse`（`Bash`
  是 3.0.0 起為 G4 加的，舊安裝重跑一次就會換成這個 matcher），以及沒有 matcher 的
  `SubagentStart`（3.3.1 起，M11），以及沒有 matcher 的 `Stop`（3.4.0 起，
  完成檢查），以及 matcher 為 `Bash` 的 `PostToolUse`（3.6.0 起，完成檢查只算
  真的執行的指令）；舊的
  settings 重跑 `--apply` 會原地補上，你自己的 `Stop` 與其他 entry 不動。
  `settings.json` 若是 symlink（dotfile 管理）
  就寫進它指向的檔案，權限不變。Claude 預設 enforce。
- `~/.grok` 會讀 `~/.claude/settings.json` 的 hooks（Claude 相容掃描），所以 Claude 的
  entry 也會在 grok session 觸發；guard 的 Claude adapter 看到 grok 的 camelCase payload
  就放行，由 grok 自己的註冊處理。
