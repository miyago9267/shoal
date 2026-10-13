---
title: OpenCode 與 core 條款對照（shared-rules S6 前置）
status: draft
created: 2026-10-13
updated: 2026-10-13
---

<!-- markdownlint-disable MD025 -->

# OpenCode 與 core 條款對照（shared-rules S6 前置）

這份文件只列事實，是 S6（OpenCode 建立條款掛載點並改由 core 產生）實作計畫
的輸入。範圍是 shared-rules 的 A1–A6、C1、D1–D6 與 Risks
（[SPEC](../../shared-rules/SPEC.md)）。不挑掛載點、不提議條款文字。

查證基準：repo HEAD `5188257`（v3.4.0）、OpenCode CLI 1.18.31、
`~/.config/opencode`（symlink 到 `~/dotfile/config/opencode`）。

標記規則：

- 「有證據」：本機檔案或指令輸出直接顯示，附路徑與行號或指令。
- 「未驗證」：本機沒有證據，列在第 9 節，不當事實用。
- 「做不到」：附原因。
- 沒有跑任何 `opencode run`（沒有付費 model 呼叫、沒有開 session）。

固定的前提（owner 已決定，來自派工說明與 SPEC D1、A3、A4）：

- 規則共用；host adapter 只放工具與參數名稱、model 綁定、host 特有調校。
- core 贏過 host 習慣：main 不自己改檔；role 派不出去就回報使用者；長指令
  交給 `watcher`；影響決策的研究用兩個 `researcher`。
- host 只有「做不到」才可省略條款，且要記理由；`required` 條款不可省略。
- 大小上限不提高，validator 規則不改。

## 1. 現況

### 1.1 shoal 為 OpenCode 出貨的東西

- `tools/render.py:833-861`（`render_opencode`）只輸出三類檔案：
  `roles/<role>.md`、`catalog.json`、`routing.json`。沒有任何 main-session
  policy 文字，也不讀 `[policy]` 區塊。
- `hosts/opencode/binding.toml:15-17` 的 `[policy]` 只有 `policy_text = "legacy"`
  與 `omit = []`；沒有 `[policy.placeholders]`、`[policy.documents]`。
  `hosts/opencode/src/` 底下只有 `roles/`，沒有 legacy policy 原文。
  所以「legacy」在 OpenCode 的意思是「沒有 policy」。
- 指令輸出（本次執行）：

  ```text
  $ python3 tools/render.py --host opencode --explain-policy
  render 失敗: host opencode: [policy.documents] 缺少文件 bootstrap, extensions, orchestration, skill
  ```

- `tools/render.py:806-808`：`validate_opencode` 呼叫
  `validate_catalog(core, binding)`，沒有帶 `core_policy=True`，因此
  `policy_text = "core"` 目前會被擋（訊息「尚未支援這個 host」，
  `tests/test_core_policy.py:408-416` 鎖住）。
- 出貨的 role（`hosts/opencode/dist/roles/`）：`scout`、`executor`、`verifier`、
  `security-reviewer`、`security-executor`、`watcher`、`researcher`，共 7 個
  （`hosts/opencode/binding.toml:11`、`:45-74`）。`applier`、`plan-critic`
  不產生（第 4 節）。
- role 檔的 frontmatter 來自 `hosts/opencode/frames/<role>.md:1-10`，只有
  `description`、`mode: subagent`、`permission`（`edit`、`bash`、`task`、
  `webfetch`、`websearch` 的 deny 組合）。沒有 `model`、沒有 effort 欄位。
  model 只存在於 `dist/catalog.json` 與 `dist/routing.json`。
- plugin（`hosts/opencode/plugin/src/plugin/shoal-plugin.ts:268-281`）註冊兩樣
  東西：tool `shoal_route`，以及 guard 的兩個 hook（`chat.message`、
  `tool.execute.before`，`src/guard/opencode.ts:111-154`）。沒有註冊
  system prompt 相關的 hook、沒有 `event` hook。
- `shoal_route` 的 tool description（`shoal-plugin.ts:175-176`）：「Validate one
  customer-owned shoal role route ... it does not change the current session
  model」。也就是它回報路由收據，不會替 `task` 換 model。

### 1.2 真實安裝（唯讀檢視）

| 項目 | 觀察 | 來源 |
|---|---|---|
| shoal 安裝 manifest | state 為 enabled，10 個 entry：7 個 `agents/*.md`、`plugins/shoal-opencode.js`、`shoal/catalog.json`、`shoal/routing.json` | `~/.local/state/shoal/opencode-global/install.manifest` |
| 已裝內容 vs HEAD dist | 7 個 role、`catalog.json`、`routing.json` 與 `hosts/opencode/dist` 逐位元組相同（`cmp`） | 本次執行 |
| 使用者自己的 agent | `monika`、`quick-explorer`、`quick-mech`、`quick-reviewer`、`vault-librarian` | `~/.config/opencode/agents/` |
| 預設 agent | `default_agent = "monika"`（`mode: primary`） | `opencode.json:5`、`agents/monika.md:1-4` |
| `subagent_depth` | `1` | `opencode.json:6` |
| 全域 `permission.task` | `"ask"` | `opencode.json:181` |
| 全域 `permission.skill` | 白名單加 `"*": "deny"`；shoal 的 skill 不在名單 | `opencode.json:182` |
| `instructions` | 有，3 項：兩個 `~/.config/miyago-agent/...` 路徑（`AGENTS.md`、`personal-model/PROFILE.md`）與相對路徑 `AGENTS.md`；沒有 shoal 的項目 | `opencode.json:175` |
| 設定目錄 `AGENTS.md` | 55 行，3247 bytes，使用者自己的檔案 | `~/.config/opencode/AGENTS.md` |
| `provider` 區塊的 key | `openai`、`chatgpt-proxy`、`google`、`aluo`、`xai`、`grok-cli`（只記 key 名稱） | `opencode.json` |
| dotfile 狀態 | `config/opencode/agents/verifier.md` 相對 dotfile HEAD 是 modified（每日同步更新了 role） | `git -C ~/dotfile status --short config/opencode` |

`opencode.json` 沒有 shoal 相關的 `instructions` 項目，installer 也從不寫
`opencode.json`（`install_global.sh` 只讀它做 provider 檢查，
`install_global.sh:316-359`；`plugin/tests/installer.test.ts:34-40` 斷言原生
`opencode.json` 不被動）。

### 1.3 現在有什麼在告訴 OpenCode 的 main session 怎麼派工

shoal 出貨的部分：

- 每個 role 的 `description`（frames 第 2 行），例如 `watcher`：
  「Background watcher for long-running commands and CI runs」。main 看得到
  這些描述的方式（`task` 工具的 agent 清單）本機沒有證據，列第 9 節。
- `shoal_route` 的 tool description（上面）。
- guard 的拒絕訊息（只在違規時出現）：`LEAF`、`VERIFY_EDIT`，對象是 subagent
  （第 5 節）。main 的 `R2` 提醒只寫 log，不輸出
  （`core.ts:116` `ADVISE_OUTPUT_HOSTS` 不含 opencode）。

不是 shoal 出貨、但實際在影響 main 的部分（dotfile 擁有）：

- `~/.config/opencode/AGENTS.md:8-12`：「Small task 預設自己做 ... 可隨手用
  `@explore` / `@quick-explorer` ... 日常低風險 ... mechanical work 可交給
  `@quick-mech`」。
- `agents/monika.md:47-52`（Delegation Rules）：「Small task: do it directly
  unless `@explore` / `@quick-explorer` will clearly save context」。
- `agents/monika.md:6-24` 的 `permission.task`：`"*": deny`，只放行
  `general`、`explore`、`scout`、`quick-explorer`、`quick-reviewer`、
  `quick-mech`、`vault-librarian`、`executor`、`security-executor`、`verifier`、
  `security-reviewer`。**沒有 `watcher`、`researcher`**；`applier`、`plan-critic`
  不存在。`agents/monika.md:24` 還有 `skill: false`。
- `instructions[0]` 指向的共用契約（`~/.config/miyago-agent/AGENTS.md` →
  `~/dotfile/config/ai/AGENTS.md`）第 67 行：「delegation 只用於獨立、bounded、
  低耦合的工作」。
- 這三處（`AGENTS.md`、`monika.md`、共用契約）都沒有出現 `shoal`（`grep -n -i
  shoal` 在前兩個檔案無輸出）。

與 core 的直接衝突（不軟化）：

| core 條款 | 文字要點 | 這個 install 上的現況 |
|---|---|---|
| `bootstrap-delegate-default` | main 不自己改檔，每個 edit 交給可寫 role | `AGENTS.md:10`、`monika.md:49` 寫小任務自己做 |
| `bootstrap-delegate-default`、`watcher-long-commands` | 長指令交給 `watcher` | `monika` 的 `permission.task` 不放行 `watcher`，派不出去 |
| `bootstrap-delegate-default`、`research-fanout` | 影響決策的研究派兩個 `researcher` | `monika` 的 `permission.task` 不放行 `researcher` |
| `model-routing` | 「Named-role model routing lives in agent definitions」 | OpenCode 的 role 檔沒有 `model`（1.1），路由只在 `catalog.json` |

其中最後一列是條款前提在 OpenCode 上不成立，不只是缺 placeholder 值。

文件與現況的矛盾：`INSTALL.md:794` 寫「五個 role 到 `<config-dir>/agents/`」，
實際出貨與已裝都是 7 個（`dist/roles/` 與 manifest）。

## 2. 掛載點

下表是 shoal 的 policy 文字可能被 OpenCode 載入的位置。不選；只列證據、
常駐與否、誰擁有、要蓋什麼。

| 項目 | A. `opencode.json` 的 `instructions` | B. `AGENTS.md` | C. plugin 注入 system prompt | D. agent 定義 | E. skill |
|---|---|---|---|---|---|
| 本機證據 | SDK 型別 `Config.instructions?: Array<string>`，註解「Additional instruction files or patterns to include」（`hosts/opencode/plugin/node_modules/@opencode-ai/sdk/dist/gen/types.gen.d.ts:1156-1159`，裝的是 1.18.19，node_modules 未進版控）。使用者的實際設定正在用它（1.2）。是否真的進到 model 沒有開 session 驗證 | 使用者設定目錄有 `AGENTS.md`，且被列在 `instructions` 的第 3 項。OpenCode 是否另外自動讀 `AGENTS.md` 沒有本機證據 | plugin 型別 `Hooks["experimental.chat.system.transform"]`，輸入 `sessionID?`、`model`，輸出 `system: string[]`（`.../@opencode-ai/plugin/dist/index.d.ts:265-270`，1.18.19）。1.18.31 的 binary 含字串 `system.transform`（`grep -a -F -b`，3 處）。shoal 的 plugin 目前沒有註冊它 | shoal 已用這個機制：`agents/*.md` 的 7 個 role 在 live 載入（`plugin/tests/live/opencode-direct.test.ts:223` 用 `agent: "scout"` 建 session；E0 與 E3 的紀錄）。`mode: primary` 的 agent 存在（`monika.md:3`） | 使用者的 `skills/` 有 21 個 symlink（`ls`）；`opencode debug skill` 在 `opencode debug --help` 的指令清單。permission 與 tool 開關有 `skill`（`opencode.json:182`、`monika.md:24`） |
| 常駐或按需 | 從名稱推測常駐；未驗證 | 同左；未驗證 | 常駐（每次 request 的 system 陣列）；未驗證 | 該 agent 作用中時常駐 | 按需（要 `skill` 工具載入） |
| 對 subagent 的效果 | 未驗證是否也進 role 的 prompt | 同左 | 可用 `sessionID` 分辨 main 與 subagent（`opencode.ts:72-85` 已實作 `client.session.get`） | 只作用在該 agent | 只有被允許用 `skill` 的 agent |
| 現況誰擁有 | `opencode.json` 是 dotfile 的檔案（symlink）；installer 從不寫它 | 使用者的 dotfile | shoal installer 擁有 plugin 檔（`plugins/shoal-opencode.js`，dotfile 以 `.gitignore` 排除） | role 檔是 shoal 的；`monika` 是 dotfile 的 | `skills/` 是 dotfile 的 symlink 目錄；shoal 沒有寫過 |
| 要蓋什麼 | installer 新增一個要裝的政策檔；再決定誰把路徑加進 `instructions`（installer 改使用者的 JSON，或文件請使用者手動加）。`opencode.json` 可能是 JSONC（`install_global.sh:336` 的警告）。相對路徑 `AGENTS.md` 的解析基準未驗證 | 以 marker 區塊寫入使用者的檔案（Codex 的做法在 `CHANGELOG.md:530`），或請使用者引用；2026-10-06 的決定是「不碰使用者的 AGENTS.md」（`docs/specs/core-policy/SPEC.md:149-150`） | plugin 新 hook、policy 文字的取得方式（embed 進 bundle，或像 `catalog.json` 一樣由 installer 放進 `<config-dir>/shoal/` 再讀）、測試、live 驗證；該 hook 名稱有 `experimental.` 前綴 | 要有 shoal 擁有的 `mode: primary` agent 且使用者把 `default_agent` 改過去，或改 `monika.md`（dotfile）。agent 檔不能「疊加」給別的 agent | installer 新增 skill 目錄項目；`monika.md:24` 的 `skill: false` 與 `opencode.json:182` 的 `"*": "deny"` 都在 dotfile，需要同步放行 |
| 大小壓力 | 見第 6 節；常駐的位元組每個 session（可能含 subagent）都付 | 同左 | 同左，且可只對 main 注入 | 同左，只在該 agent | 只有被載入時才付 |

補充事實：

- 2026-10-06 的決定（`docs/specs/core-policy/SPEC.md:68-69` 的 P5、`:149-150`
  的 Open question 2）是「`opencode.json` 的 `instructions`，不碰使用者的
  AGENTS.md」。P3 的「OpenCode 的 instructions 掛載實測」從未建置：同一天
  「持平優先」修訂讓 P3 取消（`:101-120`），OpenCode 保持沒有 policy。2026-10-13
  的 shared-rules 取代了那項取消，但沒有重新決定掛載點
  （`docs/specs/shared-rules/SPEC.md:83-89` C1：「OpenCode 目前沒有任何條款的
  掛載點，需要先建立」）。
- 每個掛載點的 prompt 都可能同時進入 role（subagent）。core 的
  `bootstrap-named-roles`、`intro-named-roles`（皆 required）就是讓 role 忽略
  這段文字。是否真的進入 role 的 prompt 未驗證（第 9 節）。
- bootstrap 的最後一句要求載入 `shoal-orchestration` skill
  （`core/policy/bootstrap.toml:114-121`）。若沒有 E 或等價的按需載入方式，
  完整 policy 與擴充規則沒有入口。

## 3. core 條款在 OpenCode 上的可行性

core 現況（`core/policy/*.toml`）：bootstrap 12、skill 9、orchestration 60、
extensions 40，共 121 條；`required` 15 條（`tests/test_core_policy.py:41`
`EXPECTED_REQUIRED` 鎖定）。以下統計由臨時腳本讀 `core/policy` 得到。

### 3.1 placeholder 與能力

render 規則：每個詞彙 key 都要有值（`tools/render.py:347-358`
`require_policy_complete`），即使使用它的條款被 omit 也一樣；omit 以整條為單位
（`tools/contracts.py:367-387`）。

| placeholder | 使用的條款（* = required） | OpenCode 的值 | 證據 | 狀態 |
|---|---|---|---|---|
| `dispatch_tool`（7） | `bootstrap-dispatch-brake`、`dispatch-brake`、`risk-review-mandatory`\*、`effort-per-delegation`、`dispatch-kind-label`、`watcher-long-commands`、`first-move-steps` | `task` | `opencode.ts:133,143-147`（`tool === "task"`、`subagent_type`）；`core.ts:198-204`（`DISPATCH_NAME`）；`E0-RESULTS.md:15` | 有證據 |
| `named_roles`（2） | `bootstrap-named-roles`\*、`intro-named-roles`\* | 7 個（`scout`、`security-reviewer`、`executor`、`verifier`、`security-executor`、`watcher`、`researcher`）；綁定第 4 節的兩個 role 後是 9 個 | `binding.toml:45-74` | 有證據 |
| `write_tools`（1） | `explore-then-plan-boundary` | `write/edit/multiedit/apply_patch` | `opencode.ts:18,132`；`E0-RESULTS.md:15` | 有證據 |
| `shell_tool`（2） | `explore-then-plan-boundary`、`review-verdicts` | `bash` | frames 的 permission key `bash`（`frames/scout.md:6`）；guard 沒有處理 shell 事件，所以 tool id 本身沒有直接證據 | 部分證據 |
| `read_tools`（1） | `discovery-scope-exclusive` | `read/glob/grep/bash`（暫定） | 只有 `read` 在 `opencode.json` 的 permission key（`:180` 之後）；`glob`、`grep` 的 tool id 沒有證據 | 未驗證（9-3） |
| `question_tool`（5） | `bootstrap-questions`、`checkpoint-default`、`checkpoint-unavailable`、`ask-mode`、`reference-extensions` | 無 | repo 與使用者設定都沒有 OpenCode 提問工具的紀錄；`checkpoint-unavailable`、`ask-mode` 自帶「工具不可用時」的文字 | 未驗證（9-3） |
| `skill_term`（3） | `bootstrap-load-skill`、`skill-intro`、`skill-bootstrap-authority` | `skill` | `monika.md:24`、`opencode.json:182`；`monika` 把它關了、全域 `"*": "deny"` | 有間接證據；此 install 上不可用 |
| `background_option`（4） | `bootstrap-delegate-default`、`parallel-launch`、`watcher-long-commands`、`leaf-cannot-finish` | 無 | 本機沒有 `task` 工具有背景參數的證據。`run_in_background` 在 1.18.31 binary 的限時字串掃描沒有命中（結果不完整，見 9-2） | 未驗證（9-2） |
| `worktree_option`（1） | `parallel-writers` | 無 | 同上，沒有證據 | 未驗證（9-2） |
| `model_param`（2） | `bootstrap-dispatch-brake`、`model-routing` | 無 | 見 1.3 最後一列：role 檔沒有 `model`；`live` 測試是在 API 的 message body 帶 `model`（`opencode-direct.test.ts:239-240`），不是 `task` 參數 | 條款前提不成立（9-4） |
| `effort_param`（2） | `bootstrap-dispatch-brake`、`effort-per-delegation` | 無 | `opencode run --help` 有 `--variant`（整個 run 的 reasoning effort）；`chat.message` hook 輸入有 `variant`；沒有證據顯示 `task` 逐次接受 effort | 未驗證（9-2） |
| `label_param`（2） | `bootstrap-dispatch-brake`、`dispatch-kind-label` | 無 | `task` 工具的欄位名稱本機只確認 `subagent_type` | 未驗證（9-2） |
| `goal_command`（1） | `auto-ask-selection` | 無 | `opencode --help` 與 `opencode run --help` 沒有 goal 相關指令；`--command` 是執行自訂 command | 未驗證（傾向沒有；9-5） |
| `policy_doc`、`extensions_doc`、`references_dir`（共 5 處） | `ext-extend-policy`、`reference-policy`、`reference-extensions` | 檔名與目錄由掛載點決定 | 無（取決於第 2 節的選擇） | 待掛載點 |

render 對「沒有」的處理：詞彙每個 key 都必須有值，沒有「不適用」這種值
（`tools/render.py:347-358`）。host 做不到的能力，只能 omit 使用它的條款並另給
一個不會被用到的值，或改詞彙；後者屬於 core 變更，不在本文件範圍。

### 3.2 不是 placeholder、但假設了能力的條款

| 條款 | 假設 | OpenCode |
|---|---|---|
| `bootstrap-delegate-default`、`direct-when-small`、`mech-direct-blocker`、`delegate-cost-benefit` | 使用者 prompt 內的 `#direct` 會被承認 | 條款是給 model 讀的，model 看得到 prompt；但 guard 不讀 prompt（5.1），所以強制面承認不了 `#direct`（有證據：`dispatch-enforcement/PROGRESS.md:176-179`） |
| `cost-unbounded-continuation` | 文字內固定寫了 `/goal`（不是 placeholder） | core 條款含 host 專屬的字面值；OpenCode 沒有已知的 `/goal` |
| `ledger-split` | 有 harness 的 task／todo 工具 | SDK 的 `Event` 聯集含 `EventTodoUpdated`（`types.gen.d.ts:449,602`）；工具本身未驗證 |
| `baton-dispatch` | 可能有 `baton-dispatch` skill | 條款自帶「不存在就不搜尋」 |
| `auto-ask-selection`、`ask-mode` | 無人互動的 run 會結束 | `opencode run` 是非互動（`opencode run --help`：「run opencode with a message」）；`permission.task = "ask"` 在無人時的行為未驗證（9-6） |
| `direction-checkpoint` | main 能把 `verifier` 當 checkpoint 派工 | `verifier` 有（含 B5、B6 的 contract 句子）；`monika` 放行它 |

### 3.3 若這些能力最後都「做不到」，會被省略的條款

臨時腳本交叉 3.1 的 5 個未驗證能力，最多 15 條可能被省略（全部非 required）：

- 背景：`bootstrap-delegate-default`、`parallel-launch`、`watcher-long-commands`、
  `leaf-cannot-finish`
- effort／label／model：`bootstrap-dispatch-brake`、`effort-per-delegation`、
  `dispatch-kind-label`、`model-routing`
- worktree：`parallel-writers`
- goal：`auto-ask-selection`
- question：`bootstrap-questions`、`checkpoint-default`、`checkpoint-unavailable`、
  `ask-mode`、`reference-extensions`

兩個結構問題（事實，不提解法）：

1. omit 是整條為單位。`bootstrap-delegate-default` 一條裡有四個 bullet：
   「main 不自己改檔」、scout 並行、`watcher` 背景、兩個 `researcher`。若因
   `background_option` 做不到而 omit 這一條，bootstrap 就沒有「main 不自己改檔」；
   同一規則在 `direct-when-small`（orchestration）還有，但那是按需載入的文件。
2. `bootstrap-dispatch-brake` 同時含 effort、model、label 三個能力。其中任何
   一個做不到，整條（含「state scope and stop」）都得整條省略。

**required 條款的狀況：**

- 15 條 required 用到的 placeholder 只有 `named_roles`（2 條）與 `dispatch_tool`
  （`risk-review-mandatory`），兩者在 OpenCode 都有值；沒有任何一條用到
  background、effort、label、model、worktree、goal、question、skill。所以沒有
  任何 required 條款因「placeholder 沒有 OpenCode 值」而無法 render。
- 但 `bootstrap-risk`（bootstrap）與 `risk-review-mandatory`（orchestration）
  兩條 required 明文要求派 `plan-critic`（第 4 節）。OpenCode 現在沒有這個
  role。這兩條可以 render，卻無法被遵守。見 3.4。

### 3.4 `applier` 與 `plan-critic`

| role | 點名它的條款 | required |
|---|---|---|
| `applier`（5 條） | `bootstrap-delegate-default`、`execution-gate`、`mech-default`、`delegate-cost-benefit`、`dispatch-kind-label` | 無 |
| `plan-critic`（8 條） | `bootstrap-risk`\*、`risk-review-mandatory`\*、`bootstrap-dispatch-brake`、`plan-gate`、`plan-critic-gaps`、`effort-per-delegation`、`review-verdicts`、`review-circuit-breaker` | 2 條（標 \*） |

直接後果（來自條款文字，`core/policy/bootstrap.toml:57-66`、
`orchestration.toml:326-339`、`extensions.toml:329-342`）：

- **阻擋項：**若 `plan-critic` 維持省略，`bootstrap-risk` 與
  `risk-review-mandatory` 要求「核准前 `plan-critic`」「mandatory」「no extra
  opt-in」，而且「Higher-priority prohibition → pause before edits, never direct
  fallback or waiver」。這兩條是 required，不能 omit。`review-circuit-breaker`
  把缺少的 `plan-critic` 當 service failure：重試一次後記 `WAITING_FOR_REVIEW`，
  「never substitute a main-session readiness judgment」。結果是 OpenCode 上每個
  觸發風險條件的工作單元都停在 `WAITING_FOR_REVIEW`，且條款文字不允許 main
  自己補位。
- `applier` 缺席沒有 required 條款擋住：`mech-direct-blocker` 規定「an
  unavailable worker is reported to the user, not worked around」；
  `bootstrap-delegate-default` 的「every edit」仍有 `executor` 可用。但
  `mech-default`（「defaults to one `applier`」）與 `dispatch-kind-label`
  （點名 `applier`）在 OpenCode 上指向不存在的 role。

## 4. role 缺口

### 4.1 為什麼省略

- 紀錄只有「OpenCode 沒有」，沒有技術原因：
  - 首次出現：`git show 9d07203:core/README.md` 第 19 行：「例如 opencode 沒有
    `mech-executor`、`plan-verifier`」，commit message 沒有理由。
  - `1836f59`（v3.0.0）把兩者改名為 `applier`、`plan-critic`，註解改為「OpenCode
    沒有 applier、plan-critic」（`hosts/opencode/binding.toml:10`），理由欄仍空。
  - `docs/specs/role-contracts/SPEC.md:102`：「OpenCode 只有 5 個 role，
    `omitted_roles` 不變」；`MAPPING-opencode.md:3-4` 相同。
  - `docs/specs/core-policy/SPEC.md:119`：「OpenCode 缺少 plan-verifier 與
    mech-executor，持平即 legacy」。
  - 推論（非紀錄）：OpenCode 最初從上游的 5 個 role 移植而來，之後沿用。
- 結論：沒有找到「OpenCode 技術上不能有這兩個 role」的證據。

### 4.2 要綁定它們需要什麼

臨時複本（`scratchpad`，未動 repo）實測：binding 移除 `omitted_roles` 並加
`[roles.applier]`、`[roles.plan-critic]` 後：

- 選模成功：`applier` → `deepseek/deepseek-v4-flash`（fast），`plan-critic` →
  `openai/gpt-5.6-sol`（frontier）；`required_capabilities` 都滿足
  （`python3 tools/render.py --host opencode --explain` 輸出）。
- render 成功但**沒有 frontmatter**：沒有 frame 時只輸出條款本文，OpenCode 的
  agent 檔需要 `description`、`mode: subagent`、`permission`。所以要新增
  `hosts/opencode/frames/applier.md`、`plan-critic.md`（`permission` 至少要有
  `task: deny`；`plan-critic` 是 read-only，比照 `scout` 的 deny 組合）。
- addenda：OpenCode 用「parent session」措辭，現有 7 個 replace
  （`tests/test_role_contracts.py:35-42`）；新 role 的 `no-spawn`／`no-delegate`
  等同樣要 replace；`security-reviewer` 目前已把「第一次 plan-critic review」
  改寫掉（`MAPPING-opencode.md:27-30`），綁定後該 replace 是否保留要重新判斷。
- guard：`ROLE_ACCESS` 已含 `applier: write`、`plan-critic: read-only`
  （`core.ts:166-177`），不用改。
- installer 與每日同步以 glob 取 `dist/roles/*.md`
  （`install_global.sh:232-235`、`tools/sync_global.py:583-585`），自動帶入。
- plugin：`DEFAULT_ROLE_DEFINITIONS` 目前 7 個（`src/role-contract.ts:105-153`；
  `tests/role-contract.test.ts:10` 斷言 7）。
- dotfile：`monika` 的 `permission.task` 不放行這兩個名字（`monika.md:7-22`），
  綁定後仍派不出去。
- 測試與 golden：第 7 節。

### 4.3 若維持省略，shared policy 必須處理什麼

- 第 3.4 節的阻擋項：兩條 required 點名 `plan-critic`，不能 omit。維持省略與
  「required 不可省略」要同時成立，條款文字本身就不能要求 OpenCode 沒有的
  role；這屬於 core 條款的改動，不是 binding 能解決的。依據：required 條款不可
  被 `omit`，也不可被 addendum `replace:`（`core/README.md` 的 policy 條款一節；
  `tools/render.py:288-345` 的 `validate_policy`）。本文件不評估該怎麼改。
- `applier`：5 條非 required 條款點名；其中 `bootstrap-delegate-default` 是
  bootstrap 裡四個 bullet 合一的單一條款，omit 單位太粗（3.3）。
- 兩者都不綁定時，`named_roles` 的清單是 7 個，條款內文仍會出現
  `applier`、`plan-critic` 兩個名字（指向不存在的 role）。

## 5. guard

來源：`hosts/opencode/plugin/src/guard/opencode.ts`、`core.ts`，向量
`tests/fixtures/guard_vectors.json`（Python 與 TypeScript 共用，R8）。`hooks/shoal_guard.py`
沒有 OpenCode adapter（`adapt_claude`/`adapt_codex`/`adapt_grok`/`adapt_agy`
在 `:1489-1656`，沒有 opencode）。

### 5.1 能看到什麼

| 能力 | OpenCode | 來源 |
|---|---|---|
| 一個 turn 的邊界 | `chat.message`（turn id = `messageID`） | `opencode.ts:111-123` |
| 區分 main 與 subagent | `client.session.get` 的 `parentID` 非空即 subagent，3 秒 timeout，失敗 fail-open | `opencode.ts:72-85` |
| subagent 的 role | session 的 `agent`，退而用該 session 第一則 message 的 agent | `opencode.ts:80,117` |
| 會被送進 guard 的工具 | 只有 `write`、`edit`、`multiedit`、`apply_patch`（編輯）與 `task`（派工）；其他工具直接 return | `opencode.ts:18,132-133` |
| 派工的 role | `task` 的 `subagent_type` | `opencode.ts:146` |
| main 的 shell 指令 | 看不到（adapter 不轉送 `bash`） | `opencode.ts:133`；`core.ts:119-133` 註解「The OpenCode adapter never produces such an event」 |
| prompt 內容 | 不讀（`#direct` 因此永遠不成立，只有 `SHOAL_GUARD_DIRECT=1`） | `core.ts:136-140`；`dispatch-enforcement/PROGRESS.md:176-179`：model 排程的 prompt 也觸發 `chat.message`，無法分辨 |
| 回合結束事件 | adapter 沒有；SDK 型別有 `session.idle`、`session.status` 事件（`types.gen.d.ts:405-417,602`）與 plugin `event` hook，但 `event` hook 回傳 `Promise<void>`，不能阻擋，也沒有記錄過 payload | `plugin/dist/index.d.ts` 的 `event?`；`tests/fixtures/stop_payload_shapes.json` 只有 claude、codex |
| 阻擋方式 | `tool.execute.before` 丟 `Error`（E0 實測有效） | `opencode.ts:153`；`E0-RESULTS.md:15` |

### 5.2 規則逐條

預設模式 enforce（`core.ts:93-99`）。

| 規則 | 在 OpenCode | 原因 |
|---|---|---|
| `LEAF`（subagent 不得派工） | 啟用，enforce | `core.ts:645-655`、`:1111-1118`（`ROLE_AWARE_HOSTS` 含 opencode） |
| `VERIFY_EDIT`（`verifier`、`watcher` 不得用編輯工具） | 啟用，enforce；shell 寫檔看不到 | 同上；frames 另有 `permission: edit: deny` |
| R1／`STRICT`（main 沒派 write role 就改檔，擋） | 不啟用 | `resolveR1`（`core.ts:509-514`）：不在 `DECLARE_HOSTS`（`:128`）的 host 一律 `classified`；`classified` 需要外部分類檔（`turns/<session>.json`），OpenCode 沒有任何程式寫它 |
| R2（改超過 2 個檔，提醒） | 只寫 log，不輸出 | `ADVISE_OUTPUT_HOSTS`（`core.ts:116`）不含 opencode；`core.ts:1046-1109`（`edit()`） |
| G4（main 開背景 shell，擋） | 不啟用 | `DENY_MAIN_HOSTS` 只有 claude（`:122`）；adapter 也不轉送 shell |
| G5（shell 指令寫檔，擋） | 不啟用 | 同上 |
| `DECLARE` | 不啟用 | 不在 `DECLARE_HOSTS` |
| `#direct` 放行 | 不支援 | 見 5.1 |
| B2（逐回合記錄 changed／checked） | 部分：main 的編輯與 write role 派工會寫 `changed`、verify role 派工會寫 `checked`；main 的前景 shell 看不到，所以 `checked` 缺最重要的那條來源 | `core.ts:1091`（main 編輯 `markChanged`）、`:871,874`（write／verify role 派工） |
| B3（結束前 gate） | 不啟用 | `STOP_HOSTS = {claude, codex}`（`:108`）；`stopEnabled` 對 opencode 恆為 false；`plugin/tests/stop-check.test.ts:19` 鎖住 |
| B4（適用 host） | OpenCode 在「有對應的結束事件」之前不啟用 | `docs/specs/shared-rules/SPEC.md:73-74` |

### 5.3 OpenCode 要啟用 strict 規則與完成檢查需要什麼

這是需求清單，不是設計。

strict／G5：

1. adapter 要把 main 的 `bash` 呼叫轉成 shell 事件，需要知道 `bash` 的 tool id
   與參數名（`command`？）；本機沒有證據（9-7）。
2. `core.ts` 的 `DECLARE_HOSTS`（`:128`，決定 `resolveR1` 能不能選 `strict`）與
   `DENY_MAIN_HOSTS`（`:122`，決定 R1／G4 能不能 deny）要加入 opencode；Python
   核心也要同步（R8 共用向量）。
3. 「出口只有兩個：派 `executor`／`applier`，或請使用者加 `#direct`」
   （`README.md:115`；`core.ts:227` 的 `STRICT` 訊息）。OpenCode 的
   adapter 不認 `#direct`（5.1），所以 `#direct` 這個出口今天對 OpenCode 不成立；
   `applier` 這個出口也不存在（第 4 節）。啟用 strict 前這兩個出口是矛盾，不是
   細節。
4. 使用者的 `monika` 要能派 `executor`（目前放行，`monika.md:16`）。

完成檢查（B3）：

1. 需要一個可靠的「main 要結束一個回合」訊號。候選是 plugin 的 `event` hook
   收到 `session.idle`（型別存在，payload 與觸發時機沒有任何紀錄；`session.idle`
   會不會對 subagent session 也發也未知）。
2. `event` hook 不能阻擋；要「擋一次」只能在 idle 後主動送一則後續訊息
   （SDK 有 `session.prompt`、`session.promptAsync`，`types.gen.d.ts:2244,2329`；
   live 行為未驗證），而且沒有 `stop_hook_active` 這類「這是被擋後的重試」旗標，
   B3 的「host 表示是重試時放行」要自己記狀態。
3. D5 的規則：實作前先取得真實 payload 形狀（Claude、Codex 各一次真實執行）。
   OpenCode 沒有這份紀錄（`tests/fixtures/stop_payload_shapes.json`），要先取得。
4. B2 的第三個來源（main 的前景 shell）依賴上面 strict 的第 1 點。

## 6. 大小與 lock

量法：臨時複本把 Claude 的 14 個 placeholder 值原樣填入 OpenCode binding
（只為量測），`python3 tools/render.py --host opencode --policy-preview DIR`。
沒有外框，只有條款本文。OpenCode 的實際值與外框（第 2 節的掛載點決定）會讓位元組
有幾十 bytes 的差異。

| 文件 | 行數 | bytes | Claude 現況（含外框，`wc`） |
|---|---|---|---|
| bootstrap | 45 | 3002 | 49 行、3103 bytes（`hosts/claude/dist/claude-md.bootstrap.md`） |
| skill（`SKILL.md`） | 28 | 1206 | 36 行、1683 bytes（含 frontmatter） |
| orchestration | 277 | 18981 | 279 行、19014 bytes |
| extensions | 170 | 9356 | 172 行、9457 bytes |
| orchestration + extensions | 447 | 28337 | 451 行、28471 bytes |

- OpenCode 沒有任何大小上限：`docs/specs/prompt-document-lock/LOCK.json` 的 31 個
  surface 沒有 `hosts/opencode/` 路徑（`grep -n -i opencode LOCK.json` 無輸出）；
  Codex 的 bootstrap 上限 3000／48 行（surface 0）、Claude 的 skill／orchestration
  ／extensions 上限 44／2100、293／19600、180／9600（surface 28-30）不適用。
  Claude 的 `claude-md.bootstrap.md` 本身也不是 lock surface。
- 因此 A5 對 OpenCode 沒有現成的上限可守；若 S6 要訂，是新增 surface，屬於 lock
  變更（本任務固定「不提高上限、不改 validator」，新增 surface 不在已決範圍，列
  第 9 節）。
- 掛載點若是常駐（第 2 節 A、B、C），每個 session 都付 bootstrap 的 3 KB；若連
  orchestration 與 extensions 一起常駐則約 31.3 KB（3002 + 28337）。差別是
  按需載入（E）才不付。
- 不論掛載方式，OpenCode 多出的 dist 檔案會讓 `tests/golden/opencode/` 的檔案數
  從 9 增加（第 7 節）。

## 7. 測試影響

「強制」= 只做 S6 的 policy 渲染（保持 7 個 role）就會失敗或必須修改。「條件」=
視第 4、5 節的選擇。

### 7.1 Python

| # | 位置 | 現在釘住什麼 | 影響 | 類別 |
|---|---|---|---|---|
| 1 | `tests/test_render_opencode.py:17` | `GOLDEN_COUNT = 9`（7 role + 2 json） | 每個渲染進 dist 的 policy 檔都加 1（最多 +4）；golden 要補 | 強制 |
| 2 | `tests/golden/opencode/`（9 檔加 `SOURCE`） | dist 的位元組副本 | 新增 policy 檔；`SOURCE` 的 ref 更新（`tools/refresh_golden.py`） | 強制 |
| 3 | `tests/test_delegation_default.py:111`（`POLICY_SHA256["opencode"] = {}`）與 `:90-92`、`:201-212` | OpenCode 沒有 policy 文字；D17「只接 role 不接派工條款」 | `{}` 代表「無 policy 檔」；S6 之後這個前提與 docstring 不成立，要改 | 強制 |
| 4 | `tests/test_core_policy.py:32` | `EXPECTED_POLICY_TEXT`：只有 claude 是 core | opencode 改 `core` | 強制 |
| 5 | `tests/test_core_policy.py:35-38` | `EXPECTED_POLICY_OMITS`、`REPLACES`、`ADDENDA` 皆空 | 任何 omit、replace、addendum 都要先登記 | 條件（有 omit 或 addendum 時） |
| 6 | `tests/test_core_policy.py:408-416` | 迴圈 `("codex", "agy", "grok", "opencode")` 設 `core` 必須被拒 | 移除 opencode；`tools/render.py:806` 要改成傳 `core_policy=True` | 強制 |
| 7 | `tests/test_render_opencode.py:25-29` | role 集合是那 7 個，`applier.md`、`plan-critic.md` 不得存在 | 綁定後反轉 | 條件（第 4 節） |
| 8 | `tests/test_render_opencode.py:34` | 迴圈 7 個 role 的 `task: deny` | 加 2 個 | 條件 |
| 9 | `tests/test_render_opencode.py:48-59` | 三個測試依賴 `omitted_roles = ["applier", "plan-critic"]` 這串字面值，並斷言綁定 `applier` 會被拒 | 綁定後三個測試要重寫 | 條件 |
| 10 | `tests/test_delegation_default.py:130-131` | `opencode["omitted_roles"] == ["applier", "plan-critic"]` | 同上 | 條件 |
| 11 | `tests/test_delegation_default.py:244` | `roles/plan-critic.md` 不在 OpenCode 輸出 | 同上 | 條件 |
| 12 | `tests/test_role_contracts.py:35-42` | OpenCode 的 7 個 replace（`EXPECTED_REPLACES`） | 新 role 的 replace 要登記 | 條件 |
| 13 | `tests/test_role_contracts.py:61-62` | `EXPECTED_CORE_HOSTS["opencode"]` 去掉兩個 role | 加回 | 條件 |
| 14 | `tests/test_role_contracts.py:130-` | `EXPECTED_ADDENDA["opencode"]` | 新 role 的 addendum | 條件 |
| 15 | `tests/test_role_contracts.py:541-553` | `omitted == ["applier", "plan-critic"]` | 重寫 | 條件 |
| 16 | `tests/test_install_opencode_global.py:25` | `ROLES` 7 個 | 加 2 個 | 條件 |
| 17 | `tests/test_install_opencode_global.py:173,184,271` | 已裝檔數 `len(ROLES) + 3`（plugin + 兩個 json） | 每個新增的安裝檔 +1 | 條件（若 installer 多裝檔） |
| 18 | `tests/test_shoal_guard.py:105`、`:898` | opencode 的 `resolve_r1` 恆為 `classified`；`stop_enabled` 恆為 false | 若第 5.3 節的規則啟用就要改 | 條件 |

另外：`tools/sync_global.py:583-590`（`build_opencode`）的 expected 檔案集合是寫死
的（plugin、roles、`catalog.json`、`routing.json`），`install_global.sh:232-240`
與 `install.sh` 也各有安裝計畫；新增安裝檔要同時改這三處，`tests/test_sync_global.py`
的 OpenCode 測試（`:316-` 起）目前斷言的是狀態字串與 snapshot，沒有釘檔案數，需要
補新檔的覆蓋。`LOCK.json` 沒有 OpenCode surface，`tests/test_prompt_document_lock.py`
不受影響。

### 7.2 bun（`hosts/opencode/plugin/tests/`）

| # | 位置 | 現在釘住什麼 | 影響 | 類別 |
|---|---|---|---|---|
| 19 | `role-contract.test.ts:10` | `DEFAULT_ROLE_DEFINITIONS.length === 7` | 綁定新 role 時 +2 | 條件 |
| 20 | `stop-check.test.ts:19` | `opencode` 的 `stopEnabled` 恆為 false | B3 啟用時改 | 條件 |
| 21 | `guard-vectors.test.ts:275`、`:287-294` | 向量數 ≥ 95、`ROLE_ACCESS` 與 Python 表一致 | 新向量需同步；Python 表也要同步 | 條件 |
| 22 | `guard-opencode.test.ts`、`plugin-seam.test.ts` | adapter 與 plugin 註冊行為 | 新增 hook（第 2 節 C）或轉送 shell 事件時補測試 | 條件 |
| 23 | `installer.test.ts:24,39` | 只檢查 `watcher`、`researcher` 的存在 | 不會因綁定新 role 而失敗；要覆蓋新 role 需新增斷言 | 不強制 |

### 7.3 合計

- Python 表 #1–#18 共 18 列：強制 5 列（#1、#2、#3、#4、#6），條件 13 列。
- 條件列依原因分：綁定 `applier`、`plan-critic` 10 列（#7–#16）；registry 登記
  omit、replace、addendum 1 列（#5）；installer 多裝檔 1 列（#17，3 個斷言點）；
  guard 啟用 strict 或完成檢查 1 列（#18，2 個斷言點）。
- bun 表 #19–#23 共 5 列：強制 0 列；條件 4 列（綁定 role 1 列、guard 與 plugin
  3 列）；不強制 1 列（#23）。
- 全部合計 23 列：強制 5 列、條件 17 列、不強制 1 列。
- 只做 policy 渲染而不綁 role、不動 guard、不多裝檔，會失敗的測試就是強制的
  5 列；其餘是選擇的結果。

## 8. 安裝與實測

### 8.1 今天用哪個指令安裝

- 全域：`sh hosts/opencode/plugin/install/install.sh --global --enable`
  （`INSTALL.md:787-789`）；停用／還原用 `--disable`、`--rollback`。專案層
  `--target DIR`。
- 每日同步：`python3 tools/sync_global.py [--apply]`，由 dotfile 的 SessionStart
  hook 每個日曆日呼叫一次（`INSTALL.md:820-841`）。OpenCode 的步驟：需要 `bun`；
  用 committed HEAD 建 bundle；與 config dir 的 plugin、roles、`shoal/*.json`
  逐位元組比對；有差異才 `--disable` 再 `--enable`；安裝未啟用就 `skipped`
  （`tools/sync_global.py:604-650`）。
- 重點：兩者都吃 **committed HEAD**（`git archive HEAD hosts/opencode`），
  不吃工作樹。而且它們只認得 plugin、`dist/roles/*.md`、`catalog.json`、
  `routing.json`；`dist/` 裡新增的 policy 檔今天不會被安裝
  （`install_global.sh:232-240`、`sync_global.py:583-590`）。
- 已裝的 dotfile 是版控目錄：新增的安裝檔會在 dotfile 出現為未追蹤變更，
  `opencode-global` 的 R7 要求以獨立 commit 處理（`docs/specs/opencode-global/SPEC.md:71-74`）。
  `plugins/shoal-opencode.js` 靠 dotfile 的 `.gitignore` 排除。

### 8.2 live 測試前要先確認什麼

讓新 policy 文字真的被測到，要全部成立：

1. 變更已 commit（安裝與同步只看 HEAD）。
2. `python3 tools/render.py --host opencode --check` 通過（dist 與 render 相同）。
3. installer 與 `sync_global.py` 已認得新檔，並已實際安裝：
   `python3 tools/sync_global.py` dry-run 顯示 `opencode: up-to-date`，且
   `cmp` 已裝檔與 `hosts/opencode/dist` 一致（本次對現有 10 個檔案做過）。
4. 掛載點本身已生效：若走 `instructions`，`opencode.json` 已有該路徑；若走
   plugin，已裝 bundle 與 HEAD build 一致；若走 skill，`monika` 的 `skill: false`
   與 `opencode.json` 的 `"*": "deny"` 已放行。
5. 測試用的 agent 真的帶有該 policy，且 `permission.task` 放行要派的 role：
   `monika` 目前不放行 `watcher`、`researcher`（1.3），這兩個題目會測出「派不
   出去」而不是「政策有效」。
6. 沒有舊的 session 干擾（用新 session，不用 `-c`／`-s`）。

不花付費呼叫就能先驗證的方法（本機已有）：`plugin/tests/live/opencode-direct.test.ts`
以 `SHOAL_OPENCODE_LIVE=1` 啟用，起一個本機假 provider（`@ai-sdk/openai-compatible`
指向 `127.0.0.1`），provider 會收到 OpenCode 送出的 request body，能看到 `tools`
清單（測試現在檢查 `shoal_route`，`:42-45`）。同樣的做法可以記錄 system 訊息與
`task` 工具的參數 schema，驗證掛載點與 9-2、9-3 的未驗證項，不需要付費 model。
限制：這個測試用暫存 HOME 與專案層設定（`:131-160,191-192`），不會載入使用者真實的
`instructions` 與 `monika`。

### 8.3 headless 測試的 flags（`opencode run --help`，1.18.31）

- `opencode run [message..]`：「run opencode with a message」，非互動。
- `--agent <name>`、`-m provider/model`、`--variant`（provider 的 reasoning
  effort，例如 high、max、minimal）、`--format default|json`（json 為 raw 事件）、
  `--dir <path>`、`--title`、`-f/--file`、`--print-logs`、`--log-level`。
- `--auto`：「auto-approve permissions that are not explicitly denied
  (dangerous!)」；`--pure`：「run without external plugins」（會連 shoal 的
  plugin 一起關掉，測 guard 時不能用）；`-c`、`-s`、`--fork`：延續 session；
  `--attach`、`--port`：接既有 server。
- 沒有「指定 config 目錄」的 flag；plugin 與 installer 認 `OPENCODE_CONFIG_DIR`
  （`shoal-plugin.ts:64-69`、`INSTALL.md:798-799`），OpenCode 本身是否認未驗證（9-8）。
- `opencode run --help` 沒有顯示 `--auto` 之外控制 `ask` 權限的方式；全域
  `permission.task = "ask"` 在無人互動時怎麼處理未驗證（9-6）。

## 9. 未決事項

| # | 項目 | 找過的地方 | 缺的證據 |
|---|---|---|---|
| 1 | `instructions`／`AGENTS.md` 的檔案是否真的進 system prompt、是否進 subagent、相對路徑 `AGENTS.md` 以誰為基準、是否常駐 | `opencode --help`、`opencode run --help`、SDK 型別（只有欄位說明）、使用者的 `opencode.json`（有設定但沒有載入結果） | 一次 session 的 request body（可用 8.2 的假 provider 取得）。外部文件在本機沒有，未查 |
| 2 | `task` 工具的完整參數（`description`、`prompt`、是否有 background、effort、model、worktree）、`task` 呼叫是否阻塞、同一訊息的多個 `task` 是否並行 | repo（guard 只讀 `subagent_type`）、SDK 型別（不含內建工具）。1.18.31 binary 的 `grep -a -F -b`：`The type of specialized agent` 命中一處（offset 66033951）；`run_in_background` 沒有輸出，但掃描有 100 秒時限，不能當成確定沒有。想讀命中位置前後的內容時，該指令被權限系統拒絕，沒有改用其他方式繞過 | `task` 的 JSON schema（假 provider 收到的 `tools[]`） |
| 3 | 提問工具的名稱與是否存在；`glob`／`grep` 的 tool id；`bash` 的 tool id 與參數名 | repo、使用者設定、frames | 同上，`tools[]` 清單 |
| 4 | OpenCode 的 role 實際用哪個 model：dist 的 role 檔沒有 `model`；`catalog.json` 只供 `shoal_route`；subagent 在沒有 model 欄位時是否繼承 main | `frames/*.md`、`shoal-plugin.ts:175-176`、`opencode-direct.test.ts` | 一次 `task` 派工後 session 的 model 欄位；這決定 `model-routing` 條款（「Named-role model routing lives in agent definitions」）在 OpenCode 上是否為真 |
| 5 | OpenCode 有沒有類似 `/goal` 的內建指令 | 兩份 `--help` | 內建 slash command 清單（TUI 內才看得到，未開） |
| 6 | `permission.task = "ask"` 在 `opencode run`（無人）下的行為（等待、拒絕或自動允許）；`subagent_depth = 1` 的語意（該 key 不在 1.18.19 的 SDK 型別，較新版本才有） | `opencode.json:6,181`、`--help` | 一次無 `--auto` 與一次有 `--auto` 的 headless 派工 |
| 7 | main 的 `bash` 事件在 `tool.execute.before` 的 `args` 欄位名稱（`command`？） | guard adapter 只處理編輯與 `task` | hook 實際收到的 `args` |
| 8 | OpenCode 本身是否認 `OPENCODE_CONFIG_DIR`；要用隔離的設定目錄跑真實設定的測試要怎麼做 | `INSTALL.md`、plugin 原始碼（那是 plugin 自己的解析） | 一次實測或官方文件（本機沒有） |
| 9 | `session.idle` 的 payload、是否對 subagent session 也觸發、plugin 在 idle 後送 prompt 的行為（B3 的候選機制） | SDK 型別（欄位有、行為無） | 一次 live 實測；D5 要求實作前先取得 |
| 10 | 為什麼最初沒有 `applier`／`plan-critic`（`mech-executor`／`plan-verifier`） | `git log -- hosts/opencode/binding.toml`、`git show` 9d07203、1836f59、b099238、`docs/specs/role-contracts`、`core-policy` | 沒有技術理由的紀錄；上游移植來源的 role 數是推論，不是紀錄 |
| 11 | OpenCode 的大小上限要不要新增（LOCK surface），以及新增是否算「提高上限」 | `LOCK.json`、shared-rules A5 | Miyago 的判斷 |
| 12 | `docs/specs/core-policy/equivalence/claude.md` 是 2026-10-06 的版本，bootstrap 9 條、不含 3.x 新增的條款（`bootstrap-delegate-default`、`plan-critic-gaps`、`research-fanout` 等）；不能當作現行 core 的清單 | 本文件第 3 節用現行 `core/policy/*.toml` 重算 | — |
| 13 | `opencode agent list`、`opencode debug agent monika` 可能顯示有效的 agent 與權限，但會載入使用者的 plugin；本任務只允許 `--help`，沒有執行 | `opencode debug --help` | 需要 Miyago 同意後跑 |

---

驗證基準的指令（本次執行）：`opencode --version`（1.18.31）、`opencode --help`、
`opencode run --help`、`opencode debug --help`、`opencode agent --help`、
`python3 tools/render.py --host opencode --explain-policy`（失敗，見 1.1）、
臨時複本內的 `--explain`、`--write`、`--policy-preview`（repo 未被修改）。
