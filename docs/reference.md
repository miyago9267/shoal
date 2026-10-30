# 參考資料

## 從 README 移入的參考資料

README 改成產品首頁後，下列細節移到這裡。內容照搬舊 README（3.6.0），未改動事實。

### 概述與 render 流程

一份 host 中立的 role catalog，render 成 5 個 host 的 agent 設定：
Claude Code、Codex CLI、Gemini/agy、Grok Build、OpenCode。

shoal 只維護一份 role 定義（`scout`、`executor`、`verifier` 等）。每個 host
用自己的 binding 決定 model、effort，並把 role 的存取等級對應成該 host 的權限欄位，再由 renderer 產生該 host
要安裝的檔案。產物由 `render --check` 與 CI 擋住手改，改動一律看得到 diff。

![render 流程：core 與 host binding 經 render.py 產生五個 host 的 dist](./assets/shoal-render-pipeline.svg)

### 選模與 watcher、researcher

role 只寫 tier，不寫模型。resolver 在每個 host 的模型目錄裡排除 capability 不到門檻的模型，再依 tier 規則挑一個；
grok 設為 `inherit`，沿用 grok 自己的選模。用
`python3 tools/render.py --host <host> --explain` 可以看到每個 role 的候選、排除原因與結果。

core 另有兩個 role，五個 host 都綁定並安裝：

| Role | 存取 | Claude 預設 | 用途 |
| --- | --- | --- | --- |
| `watcher` | 可跑不可寫 | haiku / low | 在背景盯指令、build、測試、CI 到結束，回摘要 |
| `researcher` | 唯讀加 web | opus / high | 論文、外部文件、上游專案分析；研究結論會影響決策時平行派實驗組與對照組 |

其他 host 只提供 role（名稱、contract 文字、存取等級、tier 解出的 model、支援 effort 的 host
再加 effort 與 description），model 不手動指定：

| Host | `watcher` | `researcher` | 存取限制的寫法 |
| --- | --- | --- | --- |
| codex | gpt-6-luna / low | gpt-6-sol / high | `sandbox_mode` 與 `web_search`；`watcher` 是 `workspace-write`，不改檔靠 contract |
| grok | inherit / low | inherit / high | `default_capability_mode`：`watcher` 是 `execute`，`researcher` 是 `read-only` |
| agy | flash | pro | `tools` allowlist：`watcher` 有 `run_command`，`researcher` 有 `read_url_content`、`search_web` |
| opencode | deepseek-v4-flash | gpt-5.6-sol | frame 的 `permission`：`watcher` 禁 `edit`、`task`；`researcher` 再禁 `bash` |

派工條款（`watcher-long-commands`、`researcher` 的 A/B 規則等）與 guard 的 R1、G4、G5 仍只在
Claude 的 policy 渲染；其他 host 的 main-session policy 文字不變（spec D17）。

![選模矩陣：圖中七個 role 在五個 host 選出的模型（不含 watcher、researcher）](./assets/shoal-model-routing.svg)

### 呼叫鏈

main session 先判斷互動形態與風險。已有穩定契約的實作、互不相干的偵察與長指令預設派工；只有寫 brief 的成本高於直接改時才自己做。
有風險或大型工作才走五道關卡，依階段派唯讀、審查或寫入的 role。每次派工都帶 effort，可寫 role 的 description 以 `fix:`、
`feat:` 這類類型開頭（目前只有 Claude 的 policy 渲染這些條款）。完整規則在各 host 的 orchestration
policy（例如
`plugins/claude/skills/shoal-orchestration/references/orchestration-policy.md`）
。

![呼叫鏈：互動形態、風險判斷、五道關卡與各 host 的執行時機制](./assets/shoal-call-chain.svg)

### 目錄結構

```text
core/roles.toml            host 中立的 role 定義
hosts/<host>/binding.toml  可用 model、access 對應的權限、effort
hosts/<host>/src/          該 host 的 policy 與 skill 原文
hosts/<host>/dist/         render 產出，已 commit（codex 產出在 templates/）
plugins/codex/             Codex plugin shoal-codex（skill、policy 鏡像）
plugins/jev-router/        Codex 選用 plugin shoal-jev-router
plugins/claude/            Claude plugin shoal（role、skill、policy），render 產出（--host claude-plugin），不手改
plugins/claude-guard/      Claude plugin shoal-dispatch-guard（guard hook），同上
.claude-plugin/            Claude marketplace manifest，同上
tools/render.py            renderer 與 --check
tools/install_grok.py      由 committed HEAD 安裝 grok host（預設 dry-run）
tools/check_links.py       文件相對連結檢查
install/                   安裝器與其依賴（install.sh、install.py、AGENT-INSTALL.md 等）
tests/fixtures/install-history/previous/  舊版 role 位元組，供升級測試當 fixture
upstream.lock              各 host 對應的上游與版本
```

`hosts/codex/` 另含 `VERSION`、`README.md`、`CHANGELOG.md`，是 Codex host 自己的文件。安裝腳本
`install/`、`INSTALL.md` 留在 repo 根目錄。

### render

```bash
# 檢查：dist 與 core、binding、src 是否一致，不一致 exit 1
python3 tools/render.py --host claude --check

# 寫入：重新產生該 host 的 dist
python3 tools/render.py --host claude --write
```

`--host` 可選 `claude`、`codex`、`agy`、`grok`、`opencode`，以及 binding 設
`renderer = "generic-md"` 的 host。另有 `--host claude-plugin`：產生 Claude plugin
（`plugins/claude/`、`plugins/claude-guard/`、
`.claude-plugin/marketplace.json`），不是第六個 host。
修改 core 或 binding 後先 `--write`，再跑
`python3 -m unittest discover -s tests` 確認輸出差異是預期的。

### 新增 host

輸出格式是「每個 role 一個 Markdown 檔加 frontmatter」的工具，不用寫程式碼：
`python3 tools/new_host.py <name>` 產生骨架，填 `[models]` 與工具對應表後
`--write`。步驟見 [docs/new-host.md](./new-host.md)。

### 安裝入口與 dispatch guard 摘要

| Host | 目前的安裝方式 |
| --- | --- |
| Codex CLI | 本檔前半的 Codex 章節，腳本在 `install/install.sh` |
| Claude Code | 取用 `plugins/claude`，由 dotfile auto-update 安裝；dispatch guard：`python3 tools/install_hooks.py --host claude`（預設 dry-run，`--apply` 才寫入），見 [本檔](./guard.md#claude-code-與-geminiagy-的-dispatch-guard) |
| Claude Code plugin | `claude plugin marketplace add miyago9267/shoal#v<版本>` 再 `claude plugin install shoal@shoal`（釘 tag；與全域 guard 同時存在時只判斷一次；state 與 log 在 `${XDG_STATE_HOME:-~/.local/state}/shoal/guard/`，uninstall 不刪），見 [本檔](./install/claude.md#claude-code-plugin) |
| Gemini/agy | `hosts/agy/dist`，由 dotfile `setup_gemini.sh` 連結；dispatch guard：`python3 tools/install_hooks.py --host agy`，見 [本檔](./guard.md#claude-code-與-geminiagy-的-dispatch-guard) |
| Grok Build | `python3 tools/install_grok.py`（預設 dry-run，`--apply` 才寫入），見 [本檔](./install/grok.md#grok-build) |
| OpenCode | 專案：`hosts/opencode/plugin/install/install.sh --target DIR --enable`；全域：`install.sh --global --enable`，見 [本檔](./install/opencode.md#opencode) |

Claude Code、Gemini/agy 的 role 檔案安裝步驟仍依賴 dotfile 的腳本；Grok Build 由
`tools/install_grok.py` 安裝 agents、roles、rules 與原生 hooks，不再手動複製。dispatch
guard（`hooks/shoal_guard.py`）在五個 host 的安裝方式：Codex 由 `install/install.py`
一併註冊（需在 Codex 內用 `/hooks` 核准一次），Grok 隨 `install_grok.py` 安裝，Claude Code 與 agy 由
`tools/install_hooks.py` 安裝，OpenCode 的 guard 在 plugin 內。Claude、Codex、Grok 與 agy
預設 enforce（agy 以 conversation 的事件順序推斷 main 與 subagent，是推斷不是事實，細節見 INSTALL.md；
agy 沒有 `#direct`），`SHOAL_GUARD=off` 關閉。R2（檔案數）在所有 host 都只提醒；subagent 的 LEAF、
VERIFY_EDIT 會擋。五個 host 上（預設：Claude `declare`，其餘 `strict`；agy 沒有 `#direct`）
main 沒派 write role、使用者也沒有 `#direct` 就改檔
（R1，或用 shell 指令字面上寫檔的 G5：`>`、`>>`、`tee`、`sed -i`）會被擋，不需要任何分類來源；
`strict` 的出口只有兩個：派 `executor`／`applier`，或請使用者在 prompt 加 `#direct`。main
自己宣告的出口（`: shoal-direct "<理由>"`，3.2.x 的 `declare`）在 live gate 中被 Claude 每次拿來自己做，
3.3.0 一度拿掉；2026-10-25 起 Claude 改回預設 `declare`（簡單工作宣告後自己改，
見 `docs/specs/main-small-edits`），可用 `SHOAL_GUARD_R1=strict` 還原，其他 host 仍預設 `strict`。
main 自己開背景 shell（G4，只有 Claude）同樣被擋；R2
仍只提醒。`SHOAL_GUARD_R1` 的值：`strict`、`declare`（Claude 預設）、`classified`（3.1.0 的行為：
只在外部分類來源標出實作工作時擋）、`off`。`SHOAL_GUARD_SUBAGENT_WRITE` 控制 E1：擋下不是 shoal 可寫 role 的
subagent 改檔（五個 host 預設 `on`；Claude、Codex、Grok、OpenCode 上啟動該工作的 prompt 帶
`#direct` 可放行，agy 沒有 `#direct`，其餘出口見 INSTALL.md）。
`SHOAL_GUARD_LANES=off` 關閉派工 lane 標籤檢查（預設 `on`；
缺少或與角色不符的 `[fast]`／`[complex]`／`[rigorous]` 會被 deny）。分類檔是公開的選用介面，見
[本檔](./guard.md#claude-上-guard-的行為300-起)。Codex 的 hook 註冊在 3.2.1 升到
`shoal-guard-v2`（matcher 加 `Bash`），3.4.0 升到 `shoal-guard-v3`（加 `Stop` 群組），之後升到
`shoal-guard-v4`（加 `SubagentStart` 群組），3.6.0 升到 `shoal-guard-v5`（加
`PostToolUse` 群組，完成檢查改以指令真的執行為準；每次新增群組都要在 Codex 用 `/hooks` 再核准一次）。3.8.0 起
這組註冊改叫 `shoal-dispatch-guard-v1`，群組內容與 `shoal-guard-v5` 逐位元組相同，舊 id 重跑 installer
會原地換成新 id。Claude 從
3.3.1 起、Codex 從 `shoal-guard-v4` 起，Grok、agy、OpenCode 從 3.6.0 起，在 role
真的啟動（`SubagentStart`／`subagent_start`／agy 的新 conversation
`SessionStart`／OpenCode 的 `session.created`）後才放行派工，guard 腳本與 hook 註冊必須一起更新；沒有
host 還在派工呼叫當下放行（見 INSTALL.md）。3.4.0 起 Claude 與 Codex 多一道完成檢查：guard 逐回合記下 main
有沒有改檔、改檔之後有沒有跑過檢查（派出 `verifier`／`watcher`，或 main 執行任何不寫檔的前景 shell 指令），
回合結束時若改過檔卻沒有任何檢查，`Stop` 會擋一次，要求補做驗證，或在回報中明寫未驗證；同一回合只擋一次，讀不到資料或 payload
不合預期時一律放行。`SHOAL_GUARD_STOP=off` 關閉（預設 `on`，對 Claude、Codex、Grok、agy 有效）；Grok 的
`stop` 事件（`reason == end_turn`）已掛上，但它的 block 輸出還沒有 live 驗證，預設只記 `would_block`，
`SHOAL_GUARD_STOP=enforce` 才真的擋，agy 的 `Stop` 同樣預設只記 `would_block`；OpenCode
沒有已記錄的結束事件，不啟用。

Codex、Grok、agy、OpenCode 的全域安裝由 `python3 tools/sync_global.py [--apply]`
每日從 committed HEAD 同步（dotfile SessionStart hook 呼叫），見 [本檔](./modules.md#每日同步)。

### 版本

| 項目 | 版本 |
| --- | --- |
| shoal（產品） | 3.13.0-beta |
| codex host | 3.13.1-beta（`hosts/codex/VERSION`） |
| claude host | 3.14.3-beta（`hosts/claude/VERSION`） |
| agy host | 3.13.0-beta（`hosts/agy/VERSION`） |
| grok host | 3.13.0-beta（`hosts/grok/VERSION`） |
| opencode host | 3.13.0-beta（`hosts/opencode/plugin/package.json`） |

產品版本記在根目錄 `VERSION`，各 host 版本另外維護，互不連動。2.0.0 起
shoal 是獨立產品，不再沿用上游衍生的版本號；上游版本只記在 `upstream.lock`。

### 版本 channel

shoal 目前是 beta。beta 的 minor 版本可能有破壞性變更；正式版（stable）從
1.0.0 開始，而且正式版一律比任何 beta 新。

- beta：`X.Y.Z-beta`，以及沒有後綴、不超過 3.11.1 的舊版本。
- stable：沒有後綴的 `X.Y.Z`。repo 頂層有 `CHANNEL` 檔且內容是 `stable` 才算
  stable；沒有這個檔就是 beta。
- 比較時先比 channel（beta < stable）再比數字，所以
  1.0.0 > 3.13.0-beta > 3.11.1 > 3.0.0。規則在 `install/shoal_version.py`。
- `--update` 從 beta 換到 stable 時，Claude 與 Codex plugin 會先移除再重裝：
  兩邊的 plugin manager 用純 SemVer，會把 1.0.0 當成比 3.13.0-beta 舊。

### 驗證

```bash
python3 -m unittest discover -s tests
python3 tools/check_links.py
bun install --frozen-lockfile && bun run lint:md
```

### 已知限制

- 各 host 的 policy 文字尚未合併成一份，目前只有 role 與 binding 共用（規劃中）。
- Codex、grok 與 OpenCode 有 shoal 自己的 installer；Claude Code、agy 的 role 檔案安裝仍在
  dotfile，只有 dispatch guard 由 `tools/install_hooks.py` 安裝。
- dispatch guard 不防同 uid 的 model 經 shell 竄改 state、設定或環境變數，也不擋 shell
  寫檔；agy 的 main 與 subagent 是由 conversation 順序推斷（混合派工時類別 unknown，不擋）。完整列表見
  [docs/specs/dispatch-enforcement](./specs/dispatch-enforcement/SPEC.md)。

Codex host 的完整說明與歷史紀錄在 [hosts/codex/README.md](../hosts/codex/README.md)
與 [hosts/codex/CHANGELOG.md](../hosts/codex/CHANGELOG.md)。

Codex host 的完整說明與歷史紀錄在
[hosts/codex/README.md](../hosts/codex/README.md) 與
[hosts/codex/CHANGELOG.md](../hosts/codex/CHANGELOG.md)。
