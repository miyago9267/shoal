# 模組與安裝入口

## 模組

`tools/shoal_install.py` 是安裝入口，只包住既有的 installer（Codex 的
`install/install.py`、`tools/install_hooks.py`、`tools/install_grok.py`、OpenCode 的
`install.sh --global`），不重寫安裝邏輯。模組清單在 `install/modules.json`。

```bash
python3 tools/shoal_install.py --list [--host codex]       # 模組、依賴、預設與已安裝狀態
python3 tools/shoal_install.py --host codex                # dry-run（預設）：印出會執行的指令
python3 tools/shoal_install.py --host codex --apply        # 執行既有 installer 並寫 manifest
python3 tools/shoal_install.py --host codex --with jev-router --without codex-autoroute
python3 tools/shoal_install.py --host claude --only core,host-claude
```

| 模組 | 內容 | 預設 |
| --- | --- | --- |
| `core` | 各 host 共用的來源，隨 host 模組出貨，不單獨安裝 | 永遠 |
| `host-claude`、`host-codex`、`host-agy`、`host-grok`、`host-opencode` | 該 host 的 role、skill、政策文字 | 永遠 |
| `dispatch-guard` | 派工守門 hook；關掉等於只有政策文字 | 新裝 on |
| `codex-autoroute` | Codex autoroute gate | on |
| `jev-router` | Codex 的 Jev router plugin | 新裝 off |
| `claude-explore` | Explore agent，裝到 `~/.claude/agents/` | on |
| 外部模組 | guard chain 成員，從自己的來源安裝，經 manifest 的 `chain` 登記 | 自選 |

安裝結果記在 `${XDG_DATA_HOME:-~/.local/share}/shoal/modules.json`，`--apply` 才寫入。
沒有 manifest 的既有機器由實際檔案推導，行為和今天一樣；`sync_global.py` 在 manifest
有該 host 的紀錄時只同步選到的模組（codex 與 agy 沒選 `dispatch-guard` 就不跑 guard
hooks，grok 帶 `--no-guard`，沒選 `jev-router` 就不補裝），沒有紀錄時完全照舊。Claude 沒有可由這裡執行的
installer，`--apply` 只印出 `claude plugin` 指令並記錄模組。

預設不變：`dispatch-guard` 新裝與既有機器都是開，`jev-router` 新裝關、既有維持現狀。

### 哪些旗標真的生效（3.8.0 起）

`--without`、`--only` 對下面三個模組會真的略過，再跑一次不帶它們就只移除 shoal 自己的 entry，
不碰別人的 hook：

| 模組 | 關掉時 | 重跑時移除 |
| --- | --- | --- |
| `dispatch-guard` | Codex：`install.py --no-guard`；agy：`install_hooks --uninstall`；Grok：`install_grok.py --no-guard` | Codex：shoal 的 guard 群組與（有 state 證明是 shoal 裝的）`hooks/shoal_guard.py`，state 不再記 `guard_registration`；agy：`shoal-dispatch-guard` 群組裡的 shoal handler；Grok：`shoal_guard.py` 與 `shoal-grok.json` 裡指向它的 handler（`plan_mode_guard.py`、`subagent_stop_gate.py` 不動；內容被改過的腳本保留） |
| `codex-autoroute` | Codex：`install.py --no-autoroute` | autoroute 的 `UserPromptSubmit`／`Stop` 群組與（state 證明的）`shoal_autoroute_gate.py`，state 不再記 `hook_registration`；guard 不受影響 |
| `claude-explore` | Claude：不裝 Explore | `~/.claude/agents/Explore.md`，只在內容與 repo dist 逐位元組相同時才刪 |

Claude 與 OpenCode 的 guard 在 plugin 裡，沒有可拆的 hook 註冊。`--without dispatch-guard`
在這兩個 host
是持久開關：plugin 的檔案**照樣裝著**，manifest 的 host 紀錄沒有 `dispatch-guard` 時，guard 讀同一份 manifest，
以 `off` 模式執行；如果 manifest 的 `chain` 對這個 host 有成員，則改成「只跑 chain」（dispatch 規則關、
chain 照跑，deny 的模式沿用 host 本身的 `SHOAL_GUARD`／預設）。
`--with dispatch-guard` 再 `--apply` 即恢復。環境變數 `SHOAL_GUARD=off` 仍會連 chain 一起關掉；
其他值不能蓋過這個開關。
`--with jev-router` 維持原樣；關掉 `jev-router` 不會替你解除安裝 plugin。

**chain-only 模式**：`--without dispatch-guard` 但 manifest 的 `chain` 在該 host 有成員時，
shoal 仍會註冊同一個 guard hook（同一支 `shoal_guard.py`），讓 chain 能執行；guard 在這個狀態下只呼叫 chain
成員，不做 shoal 自己的判斷。所以 guard hook 要不要註冊，是「選了 `dispatch-guard`，或 chain 在該 host
有成員」。Codex、agy、Grok 的 `sync_global.py` 也照這條規則。Claude 同理：chain 有 claude 成員時，
即使 `--without dispatch-guard`，guard plugin 仍要裝，`--apply` 印出的 plugin 指令也會包含它。
`--chain-add`／`--chain-remove` 加 `--apply` 讓這個決定翻轉時（manifest 有該 host 的紀錄、沒選
`dispatch-guard`），會自動重跑該 host 的 guard 安裝步驟（Codex 的 `install.py`、agy 的
`install_hooks.py`、Grok 的 `install_grok.py`；dry-run 只印出指令）；Claude 的 plugin 由使用者安裝，
只會印出要執行的 `claude plugin install／uninstall shoal-dispatch-guard@shoal`。

**manifest 路徑**：和 guard 一致，`XDG_DATA_HOME` 必須是絕對路徑，空值、相對路徑或 `~` 開頭都會被忽略，
退回 `$HOME/.local/share`（XDG Base Directory spec），installer 與 guard 才會讀同一份檔案。

注意：dotfile 的 updater 若會自己把 `Explore.md` 裝回 `~/.claude/agents/`，要改成先讀 manifest。

### 登記 guard chain 成員

外部 guard 只經 chain 接入（見[前一節](./guard.md#guard-chain外部-guard-以設定掛上)），用安裝入口登記，**登記時不會執行成員**：

```bash
python3 tools/shoal_install.py --chain-add my-guard \
  --chain-command '["/usr/local/bin/my-guard","check"]' --chain-hosts claude,codex [--chain-events PostToolUse,SessionEnd] [--chain-order 10] [--apply]
python3 tools/shoal_install.py --chain-remove my-guard [--apply]
python3 tools/shoal_install.py --list          # 底部列出 chain
```

`--chain-command` 必須是非空字串組成的 JSON 陣列（argv，不經 shell），`--chain-hosts` 必須是已知 host；
和其他動作一樣預設 dry-run，加 `--apply` 才寫 manifest。同名再登記會就地取代並沿用原本的 order；
不給 `--chain-order` 時新成員排在現有最後。
`--chain-events` 是逗號分隔的事件（`PreToolUse`、`PostToolUse`、`UserPromptSubmit`、`SessionEnd`、
`Stop`），不認得的名字會中止；省略時不寫 `events`（等於只收 `PreToolUse`），同名再登記而且沒給
`--chain-events` 時沿用原本的 `events`。`--list` 會顯示每個成員的 `events`。

### 改名：`shoal-guard` 變成 `shoal-dispatch-guard`（3.8.0）

另一個獨立專案叫 `shoal-guard`，只經 chain 接入。為了不混淆，shoal 內建 guard 的 hook 註冊名稱全部改為
`shoal-dispatch-guard`：Codex projection `shoal-guard-v1`～`v5` 變成 `shoal-dispatch-guard-v1`（群組內容
與舊 v5 逐位元組相同），同一版再升為 `shoal-dispatch-guard-v2`（`PostToolUse` 的 matcher 加 `apply_patch`，
新增 `SessionEnd`，供 chain 成員訂閱）；agy 的 hooks 群組 `shoal-guard` 變成 `shoal-dispatch-guard`。腳本檔名
`shoal_guard.py` 不變。agy 的舊群組只有在裡面每個 handler 都是 shoal 自己的才會遷移；含有任何外部
handler（`shoal-guard` 也是外部專案的名字）就整組不碰，installer 印一行 notice，
uninstall 也不移除。舊安裝重跑 installer（或 `sync_global.py`）會原地遷移，重複執行結果不變。
Codex 的群組內容因為升到 `shoal-dispatch-guard-v2` 而改變，升級後要在互動 session 用 `/hooks`
重新核准一次。

## 更新（`--update`）

一個指令把本機 checkout 的 committed HEAD 同步到各 host，不依賴 dotfile，macOS、Linux、
Windows 行為相同（只用 Python stdlib，不用 bash、`tar`、`timeout`）。不含 `git pull`：
要最新的內容請先自己 pull；未 commit 的 WIP 不會被安裝。

```bash
python3 tools/shoal_install.py --update           # dry-run：只回報會做什麼
python3 tools/shoal_install.py --update --apply    # 實際更新
```

每步一行 `<step>: up-to-date | updated | skipped | failed`（dry-run 的 `updated` 行尾有
`[dry-run]`），任何一步 `failed` 則 exit 1。步驟依序為：

| 步驟 | 做什麼 |
| --- | --- |
| `cleanup` | 清掉上次殘留的 `claude-marketplace.old` 與暫存目錄；正式目錄不見（交換被中斷）時改為還原 `.old` |
| `marketplace` | 依 HEAD 的 `.claude-plugin/marketplace.json` 匯出 Claude marketplace 到 `${XDG_DATA_HOME:-~/.local/share}/shoal/` 的暫存目錄，與現有 `claude-marketplace` 逐檔比對 sha256；相同回報 `up-to-date`，不同才兩次 rename 交換（現有 -> `.old`、暫存 -> 正式） |
| `claude marketplace`、`claude plugin <id>` | `claude plugin marketplace add\|update`、`plugin install\|update`（`shoal@shoal`，以及依模組清單與 chain 決定的 `shoal-dispatch-guard@shoal`）。任何一步失敗，`.old` 改名還原並回報 `failed`，全部成功才刪 `.old` |
| `explore` | `claude-explore` 模組未被停用時，把 `Explore.md` 裝進 `~/.claude/agents/` |
| `codex marketplace` | 沿用 `install/install.py` 的匯出與登記，登記 `${XDG_DATA_HOME:-~/.local/share}/shoal/codex-marketplace`；內容與註冊都相同時 `up-to-date` |
| `sync <host>` | 呼叫 `tools/sync_global.py`（見下一節（每日同步）），逐 host 一行 |
| `verify <what>` | 已安裝的 marketplace、guard（`hooks/shoal_guard.py`）與 repo 逐位元組比對 sha256，不符為 `failed` |

`claude` 或 `codex` 不在 PATH 時該 host 的步驟回報 `skipped`，不失敗。Claude `settings.json`
的 `~` 還原，以及其他工具（remora、calico）的更新不屬於 shoal，留在 dotfile。

## 每日同步

`tools/sync_global.py` 把 committed HEAD 同步到 Codex、Grok、agy、OpenCode 的全域
安裝。dotfile 的 SessionStart hook（`agent-stack-auto-update.sh`，每個日曆日一次）
在 Claude 的步驟之後以 `--apply` 呼叫它。只用 Python stdlib；沒有差異時不寫檔、不建
備份，重複執行結果相同。

```bash
python3 tools/sync_global.py                      # dry-run，四個 host 各印一行
python3 tools/sync_global.py --apply              # 實際更新
python3 tools/sync_global.py --apply --host codex grok --strict
```

每個 host 一行：`<host>: up-to-date | updated (<內容>) | skipped (<原因>) | failed (<原因>)`；
dry-run 的 `updated` 行尾有 `[dry-run]`。exit 0，只有 `--strict` 且有 `failed` 才是 1。

| Host | 做什麼 |
| --- | --- |
| codex | `install_hooks.py --host codex`（guard 與 hook entry）。`templates/agents/*.toml` 對 `<CODEX_HOME 或 ~/.codex>/agents/`：相同就略過；與 HEAD 不同但位元組等於該 template 的歷史版本才取代（temp file 加 rename，保留 mode）；其他情況（自己改過、來源不明、symlink）不動並回報 `drift`。平常不跑 `install/install.py`；偵測到 2.0.0 之前的舊名安裝才跑（見下方「從舊名升級」）。 |
| grok | `install_grok.py` dry-run 有差異才 `--apply`；不帶 `--fix-toggles`，不動 `config.toml`。舊名的 rules、hooks 檔案（確認是 shoal 安裝的）會一起移除。 |
| agy | `install_hooks.py --host agy`；`~/.gemini/config/agents`、`skills` 是指向 `hosts/agy/dist` 的 symlink，只檢查沒有斷掉或改指（回報，不修）；唯一例外是指向本 repo 的舊名 skill symlink，會移除並改指新名。 |
| opencode | 需要 `bun`（沒有就 `skipped`）。照 `install_global.sh` 的步驟建出 HEAD 的 bundle，與全域 config dir 的 plugin、roles、`shoal/*.json` 逐位元組比對，有差異才 `install.sh --global --disable` 再 `--enable`。全域安裝尚未啟用或已停用就 `skipped`，不替使用者重新啟用。dotfile 的 harness copy（`OPENCODE_HARNESS_PLUGIN`，預設 `~/dotfile/config/opencode-harness/plugins/shoal-opencode.js`）只回報 `matches` 或 `differs`，不寫入。 |

`install_hooks.py` 與 `install_grok.py` 的 `--json` 會多印一行 `{"changes": ...}`
（寫入前是否有差異），這是 `sync_global.py` 判斷是否需要 `--apply` 的依據。

## 從舊名升級

2.0.0 把安裝出去的名稱全部換新（對照表：`docs/specs/shoal-rebrand/RENAME.md`）。installer
與 `sync_global.py` 會辨識自己以舊名安裝的檔案，移除後以新名安裝；不是 shoal 安裝的
舊名檔案不動，只回報。dry-run 的計畫只會有「移除舊名」與「安裝新名」兩類。

| Host | 辨識與移除 | 保留 |
| --- | --- | --- |
| codex | 與舊 projection 逐位元組相同的 hooks.json 群組、舊 gate 腳本（hash 等於舊 install state 的紀錄）、`AGENTS.md` 的舊 marker 區塊（換成新 marker）、舊 install state（封存成 `.pre-shoal-<時間>`）、`config.toml` 中指向本 repo `plugin/` 的舊 marketplace 與 plugin table（改名）、同一條件下的 plugin cache 與 jev 資料目錄（cache 移除，jev 目錄改名） | 你自己改過的舊 gate 腳本改名為 `.pre-shoal-<時間>` 備份並取消註冊；不指向本 repo 的 table、有 pending 的舊交易（要先處理，installer 會中止） |
| grok | `rules/`、`hooks/` 底下舊名檔案，且 rules marker 帶 `-shoal.N` 或有 shoal 專屬的 guard 腳本 | 舊名目錄裡其他檔案、沒有 shoal 記號的舊名檔案 |
| agy | 指向本 repo `hosts/agy/dist` 的舊 skill symlink（改指新名） | 指向別處或不是 symlink 的 |
| opencode | 舊 manifest 記錄的 plugin 與舊名控制目錄裡的檔案，用舊 manifest `--disable` 後再 `--enable`；專案層的 `.opencode/` 同理 | 被改過的檔案（整批不動） |

Codex 遷移後，新的 hook 路徑要在互動式 Codex 用 `/hooks` 再核准一次；plugin cache 由
`install/install.py` 的 `codex plugin add` 重建。Claude Code 的 plugin 更新到 2.0.0 後 skill
名稱自動換成 `shoal-orchestration`。
