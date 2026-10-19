# generic-shoal 進度

## F2 agy subagent 辨識實測（2026-10-06，完成：維持 shadow）

agy 1.2.16，main 建一個檔案後以 `invoke_subagent` 派 `mech-executor`。probe 只記錄
路徑形狀（home 換成 `~`、UUID 換成 `<uuid>`）與欄位名稱。

| conversation | `initialNumSteps`（第一次 invocation） | `transcriptPath` 形狀 | `artifactDirectoryPath` 形狀 | 欄位集合 |
|---|---|---|---|---|
| main | 1 | `~/.gemini/antigravity-cli/brain/<uuid>/.system_generated/logs/transcript_full.jsonl` | `~/.gemini/antigravity-cli/brain/<uuid>` | 相同 |
| subagent | 0 | 同上 | 同上 | 相同 |

- 單一 payload 內沒有可區分 main 與 subagent 的正向證據：兩者的路徑形狀與欄位集合完全相同。
- 唯一差異是 conversation 第一次 invocation 的 `initialNumSteps`（main 1、subagent 0），三筆
  樣本（含 dispatch-enforcement E0 的兩筆）一致，但工具事件不帶這個欄位，且只在
  conversation 建立時可見；以它判斷需要跨事件記憶，樣本也不足以證明可靠。
- 決定：依 F2「判斷不明一律當 main」，agy 維持 R5 的固定 shadow。

## K Claude plugin（2026-10-06，K1、K2、K4 plugin 側、K5、K6 文件完成）

Claude Code 2.1.291，未 commit。plugin 目錄用 `claude-plugin/`，與 Codex 的
`plugin/` 分開；marketplace 在根目錄 `.claude-plugin/marketplace.json`
（source `./claude-plugin`）。plugin 與 marketplace 的版本都取根目錄
`VERSION`（1.3.0）。

- **K1 產生**：`python3 tools/render.py --host claude-plugin --write|--check`。
  它不是第六個 host，不在 `RENDERERS`，`hosts/claude/dist` 的 13 個檔案不變。
  agents、skill、policy 取自 claude 的 render 結果，`hooks/shoal_guard.py`
  是逐位元組副本，`emit-sessionstart.sh` 的來源是
  `hosts/claude/plugin-src/`。golden 在 `tests/golden/claude-plugin/`
  （17 個檔案）。`tests/test_claude_plugin.py` 35 項：byte identity、
  1 byte 變動、多出或缺少檔案、`--write` 修復、VERSION 連動。
  `claude plugin validate`（含 `--strict`）對 marketplace 與 plugin 都通過；
  `claude plugin details` 列出 8 agents、1 skill、3 hooks。
- **K2 hooks**：`UserPromptSubmit` 與 `PreToolUse`（matcher
  `Edit|Write|NotebookEdit|MultiEdit|Agent|Workflow`）執行
  `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/shoal_guard.py" --host claude --plugin`。
  `SessionStart` 執行
  `/bin/sh "${CLAUDE_PLUGIN_ROOT}/hooks/emit-sessionstart.sh"` 注入
  bootstrap。測試在路徑含空白的 plugin 根目錄實際執行這三個 command。
- **K4 互斥**：guard 新增 `--plugin`（`defer_to_global`，Python 專屬；grok
  dist 副本與 golden 已同步）。符合以下全部條件才 no-op：user
  `settings.json`（`CLAUDE_CONFIG_DIR` 或 `~/.claude`，解開 symlink）在同一個
  event 有 command 指向
  `${XDG_DATA_HOME:-~/.local/share}/shoal/guard/shoal_guard.py`
  （realpath 相同，接受 `$HOME`、`${HOME}`、`~` 寫法）並帶
  `--host claude`；PreToolUse 的 matcher 要涵蓋該工具；該腳本是存在的檔案。
  其他情況照跑，不會變成零次。判斷看 settings 檔位置與腳本路徑，不看 `OWNED`
  regex；測試確認 plugin 自己的 command 符合 `OWNED` 卻不算全域 entry。
  單元測試涵蓋：只有 plugin、plugin 加全域、plugin 加壞掉的全域（腳本不見、
  settings 壞掉、腳本是目錄、event 或 matcher 不涵蓋、路徑不同）、symlink、
  預設 config dir 與相對路徑 fallback。沒有全域 entry 的臨時
  `CLAUDE_CONFIG_DIR` 需要登入才能 live 驗，改由這些單元測試覆蓋。
  SessionStart 偵測到全域 guard 時印一行提示（僅供參考），全域 `CLAUDE.md`
  已有 bootstrap 時不重複注入。state 的 `flock` 先前已完成。
- **K5**：文件寫明
  `claude plugin marketplace add miyago9267/shoal#v<版本>`。`#<ref>` 的證據：
  binary 的錯誤訊息把 `#` 後面當 git ref，實測 `miyago9267/shoal#v1.3.0`
  回報 `Remote branch v1.3.0 not found`（tag 尚未建立，失敗是預期的）。
  升級要先 `marketplace remove` 再用新 tag 加回（source 不同會被拒絕）。
  **發佈前要建 `v1.3.0` tag**（現有 tag 只到 v1.1.0）。SessionStart script
  固定 `PATH=/usr/bin:/bin`，所有路徑加引號。
- **K6**：INSTALL.md 與 README 安裝表寫明共用目錄
  `${XDG_STATE_HOME:-~/.local/state}/shoal/guard/`、log 1 MiB 上限（停止寫入，
  不輪替）、uninstall 不刪、清除指令。

### Namespace 實測

`claude -p --plugin-dir claude-plugin`，真實登入、不安裝，測試專案在
`~/.cache`。probe hook 只記 hook_event_name、tool_name、agent_type、
subagent_type 與 file basename。

| 事件 | tool | agent_type | tool_input.subagent_type |
|---|---|---|---|
| `SubagentStart` | | `shoal:executor` | |
| `PreToolUse` Agent（main） | Agent | 無 | `shoal:executor` |
| `PreToolUse` Write（subagent，帶 agent_id） | Write | `shoal:executor` | |

- init 的 agents 清單：`shoal:executor`、`shoal:Explore`、
  `shoal:mech-executor`、`shoal:plan-verifier`、`shoal:scout`、
  `shoal:security-executor`、`shoal:security-reviewer`、`shoal:verifier`，
  另有內建的裸名 `Explore`。skill 是 `shoal:pilotfish-orchestration`，與全域的
  `pilotfish-orchestration` 並存。結論：名稱就是 `shoal:<role>`，與 K3 白名單
  相符，K3 不需調整。
- Run A（全域 install_hooks entry 存在，plugin 載入）：main 寫 ka1、ka2 allow
  （count），ka3 deny（R2，`ka3.txt` 未建立），派 `shoal:executor` allow
  （dispatch），subagent 寫 ka4，main 寫 ka5 allow（dispatched）。
  `guard.jsonl` 中 ka1、ka2、ka3、ka5 與 Agent 事件各剛好一筆；兩個
  UserPromptSubmit 各一筆 `state`。log 不含 session id，另有一筆早 2 秒的
  prompt 來自其他並行 session，以 debug 時間戳排除。deny 來自全域腳本
  （debug 記錄的 hook command 是
  `python3 ~/.local/share/shoal/guard/shoal_guard.py --host claude`）。
- Run B（對照）：同樣載入 plugin，但 `XDG_DATA_HOME` 指向空目錄，plugin 找不到
  全域腳本。每個事件兩筆 log（prompt、kb1、kb2 各 2 筆），證明 plugin 的 hook
  有註冊且會執行，Run A 的單筆來自 deferral。
- Run A 成本約 0.35 USD，在 1 USD 上限內；暫存的 debug log 與輸出已刪除。

### 未完成與提醒

- 發佈前建立 `v1.3.0` tag，並在 plugin 實際從 GitHub 安裝後再驗一次
  `marketplace add ...#v1.3.0`。
- CI（`.github/workflows/python-tests.yml`）屬另一位 executor 的檔案，沒有動；
  `claude-plugin` 的 `--check` 由 `tests/test_claude_plugin.py` 涵蓋。
- README 的版本表仍寫產品版本 1.2.0，與 `VERSION` 1.3.0 不符（既有落差，
  未處理）。
- CHANGELOG 尚未記 plugin，待發版時一起寫。
