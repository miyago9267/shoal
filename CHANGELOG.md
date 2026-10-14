# Changelog

shoal 的產品版本紀錄，從 v1.0.0 開始。Codex host 在 v1.8.1 之前的完整歷史
在 [hosts/codex/CHANGELOG.md](./hosts/codex/CHANGELOG.md)。

## v3.6.0

guard 的每個閘門都接上（[`docs/specs/guard-every-gate`](./docs/specs/guard-every-gate/SPEC.md)）。
各 host 的事件形狀都有實測紀錄，尚未實測的項目列在
[PROGRESS.md](./docs/specs/guard-every-gate/PROGRESS.md)。

### Changes

- 新規則：不是 shoal 可寫 role 的 subagent（例如 Codex 內建的 `worker`、Claude 的
  `general-purpose`、預設的 Workflow child、OpenCode 的 `general`），改檔或用 shell 寫檔會被擋。
  出口：
  - 改派 shoal 的可寫 role。
  - `SHOAL_GUARD_WRITE_AGENTS`（agent 類型白名單，逗號分隔）。
  - `SHOAL_GUARD_DIRECT=1`。
  - 在 prompt 加 `#direct`（agy 不支援 `#direct`）。
  - 開關：`SHOAL_GUARD_SUBAGENT_WRITE=off` 可關掉這條規則。
- shell 寫檔偵測新增 `perl -i`；偵測為逐字比對，直譯器寫檔不在範圍內。
- verify 類 role（`watcher`、`verifier`）用 shell 寫到 repo 內的路徑會被擋；
  寫到 `/tmp`、`$TMPDIR`、scratchpad 不受影響。
- 「role 真的啟動才放行」擴大到更多 host：Codex（`SubagentStart`）、OpenCode
  （`session.created`）、Grok（`subagent_start`）、agy（subagent conversation 的
  `SessionStart`）都改成以啟動為準，派工失敗不放行。
- Codex 的 hook 註冊升到 `shoal-guard-v4`，升級後要用 `/hooks` 重新核准新增的
  `SubagentStart`；核准前，以可寫 role 的第一次工具呼叫作為啟動依據。
- OpenCode、Grok、agy 的 guard 預設由只記錄（shadow）改為 enforce，main 自己改檔預設被擋
  （與 Claude、Codex 相同）；要回到只記錄可設 `SHOAL_GUARD=shadow`。
  OpenCode 開始檢查 `bash` 與 `apply_patch`。
- agy 的 main／subagent 與 role 由 conversation 的順序推論；判不出來時不擋，只記錄。
- 完成檢查：Grok、agy 以只記錄方式接上（`SHOAL_GUARD_STOP=enforce` 才擋）；
  OpenCode 的結束事件沒有回傳值，無法擋，所以沒有接。
- 設計不變式第 3 條新增：有 harness 的 host 必須把每個能當閘門的事件都接上 guard，
  接不了的要列出原因與證據。
- guard log 多記 `agent_type`、`agent_id` 與 session／turn 的短雜湊。

## v3.5.0

### Changes

- Codex 的 main-session policy 改由 `core/policy/` 渲染，Codex 專屬的調校移到
  `hosts/codex/policy-addenda/` 與隨需載入的 extensions 文件。agy 也已改用 core 渲染的 policy。
- Codex 行為變更：
  - main 不再自己改檔；改檔交給可寫入的 role，除非 prompt 含 `#direct`。
  - role 不可用時回報，不由 main 接手。
  - 長時間指令交給 `watcher`。
  - 決策型研究用兩個 `researcher` 分頭做。
- 低風險、本機、可逆的工作維持「main 做一次針對性驗收，不另派 verifier」，
  以 Codex addendum `pending-shared-low-risk-targeted-check` 保留。

## v3.4.2

### Changes

- `background_option` placeholder 改為完整片語，各 host 可以自己寫出 role 怎麼在背景執行；
  Claude 的措辭不變，只有兩條條款的換行位置不同。

## v3.4.1

前置調整（[`docs/specs/shared-rules`](./docs/specs/shared-rules/PROGRESS.md)
的「前置：條款拆分與派工單位」）。只改共用條款文字，行為與 hook 不變。

### Features

- 條款拆分：bootstrap 的 `bootstrap-dispatch-brake` 拆成 `bootstrap-effort`、
  `bootstrap-dispatch-brake`、`bootstrap-kind-label` 三條（皆非 required），
  host 可以單獨省略 effort 或 label，不影響其他兩條。
- 派工單位：brief 要寫時間預算，到預算的 role 回報手上已有的結果；one-shot
  spec 加上 file ownership 與時間預算；新增 `small-parallel-units`，派工切小、
  依 file ownership 分開，ownership 不重疊的派工一起啟動（writer 各用自己的
  worktree），共用檔案（版本、產生的輸出、lock）只在獨立的整合步驟改一次；並行的
  worker 只跑自己檔案的檢查，完整測試只在整合時跑一次。
- 移除剩下的「main 接手」措辭：兩次失敗後與 cost-unbounded continuation 的
  升級路徑改為「升 executor tier 或回報給使用者」。

## v3.4.0

規則共用的第一步（[`docs/specs/shared-rules`](./docs/specs/shared-rules/SPEC.md) 的 S1 到 S3，Miyago
2026-10-13 核准）：文件改為「規則由 core 定義、所有 host 共用」，加上「宣告完成前要有驗證」的條款
與 guard 的完成檢查。Codex、agy、OpenCode、Grok 改由 core 產生條款是後續切片（S4 起），本版沒有改
它們的行為。

### Features

- 文件（S1）：`docs/DESIGN-INVARIANTS.md` 第 4 條改為「規則與策略由 core 定義，所有 host 共用；adapter
  只放工具與參數名稱、model 綁定、該 host 特有的調校參數」。`core-policy` 與 `milestone-direction-check`
  加註記：2026-10-06 的「持平優先、不做 P3」被 shared-rules 取代，「同質化」指的是抹平 role 形狀與工具綁定，
  不是共用規則。`core/README.md` 改指向 shared-rules，渲染器對非 Claude host 的限制保留到 S4。
- 條款（S2，B1）：常駐 bootstrap 新增一條（非 required）：回報完成前，寫明本回合跑過的驗證與結果、沒跑的
  檢查，沒有證據的說法標為未驗證。為了放得下，同時縮短了 bootstrap 內其他條款的措辭（規則不刪）。
- Contract（S2，B5、B6）：`verifier` 的方向檢查（`direction_checkpoint`）在 brief 附上 main 的回報草稿時，
  逐句對照 repo 與 brief 內的證據，列出沒有證據或講過頭的句子與實際證據；並且每次多回答一題：已核准的設計
  中哪個前提最可能是錯的、用什麼便宜的方法驗證。Policy 的方向檢查條款寫明多切片工作收尾時 main 把回報草稿
  交給這個檢查、修正後才回報。這是 core 文字，所有渲染 core role 的 host 都會帶到（Claude、Codex、Grok、
  agy、OpenCode 的 `verifier`）。
- Guard（S3，B2 到 B4）：逐回合記錄 `changed` 與 `checked`。main 的改檔被放行且目標非豁免、或可寫的 role
  算已派工（Claude 在 `SubagentStart` 釋放待啟動派工時，其他 host 在派工呼叫）為 `changed`；之後派出或
  啟動 `verifier`／`watcher`，或 main 執行不寫檔、也不是 `: shoal-direct` 宣告的前景 `Bash`，為 `checked`；
  再次 `changed` 會清掉 `checked`。Claude 與 Codex 的 `Stop`：同一回合、`changed` 且未 `checked`、
  `stop_hook_active` 恰為 `false`、enforce、這回合還沒擋過，輸出一次 `{"decision":"block","reason":...}`；
  其餘情況（別的回合、state 讀不到、id 缺漏、subagent、shadow 記 `would_block`、`SHOAL_GUARD=off`）
  一律放行。沒有改檔的回合，前景 `Bash` 不碰 state。
- 開關：`SHOAL_GUARD_STOP=on|off`，預設 `on`，只對 Claude 與 Codex 有效。Grok、agy、OpenCode 沒有已記錄的
  結束事件 payload，永遠不擋。
- Log 只有新的值：決定 `block`／`would_block`、規則 `STOP`；欄位沒有新增。
- 註冊：Claude plugin 的 `hooks.json` 與全域
  `tools/install_hooks.py --host claude` 新增沒有 matcher 的 `Stop`（plugin 與全域
  並存時 plugin 讓出），重跑冪等，舊的 settings 原地補上，你自己的 `Stop` 不動。
  Codex 的 guard projection 升為 `shoal-guard-v3`（多一個 `Stop` 群組）；`v1`、`v2` 仍在允許清單，升級時
  原地補上，autoroute gate 自己的 `Stop` 群組與使用者的項目不動。

### 限制

- **Claude 對 Stop block 輸出的處理沒有實測。** 輸出採用 Claude Code 文件的 `decision: "block"` JSON；格式
  不被接受時只是照常結束（失敗開放）。Stop payload 的形狀已實測
  （`tests/fixtures/stop_payload_shapes.json`）。S3 的 live 驗收（改檔後直接結束被擋一次、有檢查時不擋）
  尚未執行。
- 常駐 bootstrap 渲染後 3103 bytes（3.3.1 為 3046），沒有達到 spec 要的 2900；Codex 切到 core 條款（S4）
  前要再處理。
- guard 腳本與 hook 註冊必須一起更新；只更新腳本的安裝沒有完成檢查，其他規則不受影響。

### 版本

- 產品與 claude、codex、grok、agy、opencode 各 host 版本一律是 3.4.0。
- prompt lock：`LOCK.json` 沒有變動，commit 不需要 `Lock-Renewal: approved`。

### 升級

- 用 plugin 的使用者：`claude plugin marketplace remove shoal`，再用 `#v3.4.0` 加回並更新。
- 全域 guard：重跑 `python3 tools/install_hooks.py --host claude --apply`（會補上 `Stop`）。
- Codex：重跑 installer（或 `tools/install_hooks.py --host codex --apply`）後，
  **在互動 session 用 `/hooks` 再核准一次**新的 `Stop` hook；沒核准時完成檢查不會執行，其他行為不變。

## v3.3.1

M11（派工要真的啟動）在 Claude 上實作。live 重測時 Claude 的 `SubagentStart` payload 取得後（
`session_id` 與 main 相同，另有 `agent_id`、`agent_type`、`prompt_id`；形狀記在
`tests/fixtures/claude_subagent_start_shape.json`），v3.3.0 留下的限制可以補上。

### Features

- Claude：派工呼叫不再直接放行改檔，只記一筆待啟動的 write 派工（log：`allow`／`dispatch_pending`，
  呼叫本身仍然永遠放行）。同一個 session 的 `SubagentStart`，其 `agent_type`（`normalize_role`，含
  `shoal:` 前綴）是 write 等級 role 且有待啟動派工時，才設為已派工（log：`state`／`dispatch_started`），
  一次事件釋放一筆。read-only 或 verify 等級的啟動、沒有待啟動派工的啟動不改變任何東西。待啟動
  派工隨回合重置。`strict`、`declare`、`classified` 一視同仁。
- 對應規則：以 session 為準；事件的 `prompt_id` 與 guard 記錄的本輪不同時仍然釋放，並在 log 的
  `skip_reason` 寫 `prompt_id_mismatch`，讓之後的實測可以確定兩者是否相等。壞 payload 失敗開放，
  不改狀態。log 欄位沒有新增，只有新的值。
- 註冊：plugin 的 `hooks.json`（`tools/render.py`）與全域的
  `tools/install_hooks.py --host claude`
  新增沒有 matcher 的 `SubagentStart`，重跑冪等，舊的 settings 原地補上，其他 entry 不動。測試固定
  「guard 以啟動事件解鎖時，plugin 一定註冊該事件」。
- 其他 host 不變：Codex 與 grok、agy、opencode 仍在派工呼叫時放行（沒有已記錄的啟動事件）。

### 限制

- **guard 腳本與 hook 註冊必須一起更新。** 沒有註冊 `SubagentStart` 的 Claude 安裝（只更新了腳本）
  收不到事件，派工後會一直被擋，只剩 `#direct`；沒有加時間啟發式。更新 plugin
  （`#v3.3.1`）或重跑 `install_hooks.py --host claude --apply` 即可。
- 沒有量過：role 啟動失敗時是否仍發出 `SubagentStart`（若仍發出，失敗的啟動也會放行）；`prompt_id`
  是否等於 guard 看到的本輪 id。

### 版本

- 產品與 claude、codex、grok、agy、opencode 各 host 版本一律是 3.3.1。
- prompt lock：`LOCK.json` 沒有變動，commit 不需要 `Lock-Renewal: approved`。

### 升級

- 用 plugin 的使用者：`claude plugin marketplace remove shoal`，再用 `#v3.3.1` 加回並更新。
- 全域 guard：重跑 `python3 tools/install_hooks.py --host claude --apply`。Codex 不需要任何動作
  （hook 註冊沒有變，不用重新核准）。

## v3.3.0

live gate（`docs/benchmarks/guard-declared-direct-gate/`）顯示 Claude 在每次改檔前都先宣告，
包含兩個三檔小功能，一次也沒派工；自己給自己的出口不會改變行為。Miyago 2026-10-12 決定預設拿掉
（M9 到 M12、D6，見
[`docs/specs/guard-declared-direct`](./docs/specs/guard-declared-direct/SPEC.md)）。

### Features

- `SHOAL_GUARD_R1` 新增 `strict`，並成為 Claude 與 Codex 的預設（未設定、空字串、無法辨識的值都用它）。
  enforce 時 main 的改檔工具與 shell 寫檔一律 deny，除非本輪派出了 write role、使用者的 prompt 有
  獨立的 `#direct`（或 `SHOAL_GUARD_DIRECT=1`），或目標是豁免路徑。`: shoal-direct ...` 在這個模式只是
  普通的空指令（不寫 state、不寫 log、不放行），分類檔（含 `parent_local`）沒有作用。deny 訊息（英文與
  zh-TW）只列兩個出口。shadow 記 `would_deny`；R2、G4 與硬規則不變，被 deny 的呼叫不計入 R2。
  `declare`、`classified`、`off` 保留為可選，行為與 3.2.1 相同。Python 與 TypeScript mirror 重放同一份
  向量（`guard_vectors.json` 新增 42 筆 strict 向量，原本依賴預設的 declare 向量改成明確選 `declare`）。
- Claude policy（M12）：`bootstrap-direct-declare` 條款移除；
  `bootstrap-delegate-default` 改為「main 不自己改檔，改檔一律派可寫的 role
  （`executor`／`applier`），除非使用者的 prompt 有 `#direct`；讀檔、
  執行指令、診斷、整合與判斷留在 main」，`scout`、`watcher`、`researcher` 的路徑不變。
  orchestration 的 `direct-when-small`、`delegate-cost-benefit`、`mech-direct-blocker`、
  `single-bug-direct`、`parallel-writers` 對齊：main 直接改只存在於 `#direct`，診斷留在 main、修正
  派工，「worker 不可用」不再是自己改的理由（回報使用者）。其他 host 的 policy 不變。
- `docs/DESIGN-INVARIANTS.md` 第 2、3 條改為 D6 的字句。

### 限制

- M11（派工要真的啟動）沒有實作：guard 仍在派工呼叫發出時放行，role 沒能啟動時放行仍然有效（live
  gate 中 Codex 就是這樣）。Claude Code 有 `SubagentStart`，但 repo 只記錄過它帶 `agent_type`，不足以
  安全地把它對應到 main 的那一輪，也不知道啟動失敗時事件會不會出現；Codex 沒有已記錄的啟動事件。
  需要補的 payload 見 `docs/specs/guard-declared-direct/PROGRESS.md`。
- hook 註冊沒有變動（沒有新事件、Codex matcher 不變），不需要在 Codex 重新核准 hook。

### 版本

- 產品與 claude、codex、grok、agy、opencode 各 host 版本一律是 3.3.0。
- prompt lock：`LOCK.json` 沒有變動（`claude-orchestration-policy` 的單次變動在預算內），commit
  不需要 `Lock-Renewal: approved`。

### 升級

- 想維持 3.2.x 的宣告行為：設 `SHOAL_GUARD_R1=declare`；只想要提醒：`classified`。
- 用 plugin 的使用者：`claude plugin marketplace remove shoal`，再用 `#v3.3.0` 加回並更新。

## v3.2.1

Codex 啟用 `declare`（M7，見
[`docs/specs/guard-declared-direct`](./docs/specs/guard-declared-direct/SPEC.md)）。
v3.2.0 因為 repo 沒有 Codex shell 工具的記錄而沒有啟用；這次在 codex-cli 0.160.1
實跑一次 `codex exec`（探針 hook，matcher `.*`，隔離的 `CODEX_HOME`）取得 payload 後補上。

### Features

- 證據：shell 工具的 `tool_name` 是 `Bash`，`tool_input` 只有一個字串欄位 `command`（`echo ok`
  與 heredoc 寫檔都一樣），沒有 `run_in_background`，main session 的呼叫沒有 `agent_id`，
  `turn_id` 在 prompt 與 tool 事件上相同。只記 key 與型別的 fixture：
  `tests/fixtures/codex_payload_shapes.json`。
- `adapt_codex` 把 `Bash` 且 `tool_input.command` 是字串的呼叫轉成 shell 事件（宣告與 shell 寫檔判斷）；
  其餘不變。`SHOAL_GUARD_R1` 在 Codex 預設 `declare`，`classified`（3.1.0 的提醒行為）與 `off` 可選。
  subagent 的呼叫（有 `agent_id`）不受影響；既不是宣告也沒寫檔的 `Bash` 沒有意見、不寫 state 與 log。
  G4 仍只在 Claude（Codex 沒有 `run_in_background`）。
- Codex hook 註冊升為 `shoal-guard-v2`：`PreToolUse` 的 matcher 變成
  `^(apply_patch|spawn_agent|collaborationspawn_agent|Bash)$`。`shoal-guard-v1`
  （3.2.0 以前）仍在允許清單，`install/install.py`、
  `tools/install_hooks.py --host codex` 與 `tools/sync_global.py` 會把它原地換成 v2，
  只替換 shoal 自己的群組，使用者自己的 `Bash` matcher 等其他 entry 位置與內容不變；
  重跑不產生差異。
- 向量：`tests/fixtures/guard_vectors.json` 取代 3.2.0 的 Codex「維持原行為」向量，
  新增 23 筆 Codex 向量
  （declare、宣告、heredoc、不跨輪、`#direct`、派工、subagent、`classified`、`off`、shadow）；
  `tests/test_hook_registration.py` 測 v1 到 v2 的升級。

### 升級

- Codex 使用者：重跑 `python3 tools/install_hooks.py --host codex --apply`、
  `install/install.py` 或
  `tools/sync_global.py`，然後在互動式 Codex 用 `/hooks` **重新核准一次**被改動的 hook；未核准前
  Codex 不會執行它。想維持提醒就好，設 `SHOAL_GUARD_R1=classified`。
- 用 plugin 的使用者：`claude plugin marketplace remove shoal`，再用 `#v3.2.1` 加回並更新。

### 版本

- 產品與 claude、codex、grok、agy、opencode 各 host 版本一律是 3.2.1。

## v3.2.0

guard 的 main 改檔規則（R1、G5）改成「宣告直接做」，不再等外部分類來源
（[`docs/specs/guard-declared-direct`](./docs/specs/guard-declared-direct/SPEC.md)）。
動機：3.1.0 實測時 Jev（外部分類器）送出的 729 次中，門檻 0.8 只有 19% 有分類，
沒有分類的回合 guard 不介入，小功能仍由 main 自己做；而且 Jev 不屬於 shoal。

### Features

- 新的環境變數 `SHOAL_GUARD_R1`：`declare`（Claude 預設）、`classified`（3.1.0 的行為，
  保留給想用分類來源的人）、`off`（只關 R1 與 G5，硬規則、G4、R2 不變）。未設定、
  無法辨識的值，或在不能宣告的 host 上設 `declare`，都用該 host 的預設；其他 host
  維持「不 deny」。
- `declare` 模式下，main 的改檔工具與 shell 寫檔在 enforce 會被 deny，除非本輪有：
  已派出的 write role、使用者的 `#direct` 或 `SHOAL_GUARD_DIRECT=1`、main 的宣告，
  或分類檔的 `role` 為 `parent_local`。沒有分類檔、或其他 `role` 不影響結果。shadow 記
  `would_deny`。
- 宣告是單獨一次 shell 呼叫 `: shoal-direct "<理由>"`（`:` 是空指令；理由可用雙引號、
  單引號或不加引號，去掉空白後不得為空；不得串接其他指令、導向、註解或放進較長 script）。
  guard 記下本輪的宣告旗標（下一輪失效），log 寫 `decision: state`、`rule: declare` 與
  截成 200 字元、去掉控制字元的 `reason`；guard 不判斷理由內容。subagent 的宣告無效，
  宣告不解除 G4。字面判斷寫成專用的 `parse_declaration`（Python）與 `parseDeclaration`
  （TypeScript），兩邊重放 `tests/fixtures/declaration_cases.json`（112 筆）。
- deny 訊息改成自帶三個出口（派 `executor`／`applier`、執行宣告、請使用者加
  `#direct`），沒有 policy 文字的 host 也能只靠訊息繼續。`classified` 模式保留原本的 R1 訊息。
- 分類檔（`<state>/shoal/guard/turns/<session>.json`，`{"turn_id", "role"}`）列為公開的
  選用介面，`declare` 下只能放寬（`parent_local`）；格式見 INSTALL.md。
- Claude bootstrap 加一句：要自己改檔，先執行宣告指令，而且只在符合直接做的條件時宣告
  （`bootstrap-direct-declare`，非 required）。
- `docs/DESIGN-INVARIANTS.md` 第 3 條改為「hook 強制硬規則」包含 main 未派工、未宣告就改檔，
  並明寫這些規則不依賴任何分類器。
- 被 deny 的改檔與 shell 寫檔不計入 R2，也不會在同一次呼叫送出 R2 提醒。

### Codex

- Codex 的 `UserPromptSubmit` 事件現在會讀 prompt 內獨立的 `#direct`（規則與 Claude 相同，
  `payload.prompt` 的欄位由 autoroute gate 在 Codex 上已使用）。
- `declare` **沒有**在 Codex 啟用，Codex 維持 3.1.0 的行為（R1 提醒、R2 提醒）：repo 內沒有任何
  已記錄的 Codex shell 工具名稱與 payload 欄位，hook matcher 也不含 shell，宣告沒有出口，
  deny 會變成死路。hook 註冊（`shoal-guard-v1`）沒有變動，因此不需要在 Codex 重新核准 hook。
  缺的證據與取得方式見 `docs/specs/guard-declared-direct/PROGRESS.md`。

### Tests

- `tests/fixtures/guard_vectors.json` 新增 declare／off／classified／其他 host 的向量，既有
  向量以 `env_defaults`（`SHOAL_GUARD_R1=classified`）原樣重放；Python 與 TypeScript 共用。
  log 白名單新增 `reason`。

### 版本

- 產品與 claude、codex、grok、agy、opencode 各 host 版本一律是 3.2.0。

### 升級

- 用 plugin 的使用者：`claude plugin marketplace remove shoal`，再用 `#v3.2.0`
  加回並更新。
- 全域 guard（`tools/install_hooks.py --host claude`）：重跑 `--apply` 換新腳本；matcher 不變。
  想維持 3.1.0 的行為，設 `SHOAL_GUARD_R1=classified`。

## v3.1.0

`watcher` 與 `researcher` 在 codex、grok、agy、opencode 也綁定並安裝，五個 host 的
role 組合一致（delegation-default D17）。這些 host 上 shoal 只提供 role：名稱、
contract 文字、存取等級、由 tier 規則解出的 model、支援 effort 的 host 再加 effort 與
description。派工條款、guard 規則與路由文字不移植；各 host 的 main-session policy 文字
只有版本 marker 變動，Codex 另在 role 表多兩列（`test_policy` 要求列出每個安裝的 role）。
Claude 的輸出只有版本 marker 變動。

### Features

- 新 role 的 model 一律由 tier 規則解出，沒有手動指定：

  | Host | `watcher`（`verify`、`fast`） | `researcher`（`read-only` 加 `web`、`strong`） |
  | --- | --- | --- |
  | codex | `gpt-6-luna`，effort `low` | `gpt-6-sol`，effort `high` |
  | grok | `inherit`，effort `low` | `inherit`，effort `high` |
  | agy | `flash`（agy 沒有 effort 欄位） | `pro` |
  | opencode | `deepseek/deepseek-v4-flash`，`fallback = "none"` | `openai/gpt-5.6-sol`，`fallback = "none"` |

- 存取限制照各 host 的對照表推導：codex `watcher` 是 `sandbox_mode = "workspace-write"`
  （與 `verifier` 相同，不改檔由 contract 條款約束），`researcher` 是 `read-only` 加
  `web_search = "live"`；grok `watcher` 是 `execute`、`researcher` 是 `read-only`；agy
  `watcher` 的 allowlist 含 `run_command`、`researcher` 含 `read_url_content` 與
  `search_web`；opencode 的 role frame 對 `watcher` 禁 `edit`、`task`，對 `researcher`
  再禁 `bash`，並明寫 `webfetch`、`websearch` 為 allow。
- grok 與 opencode 各加兩個 role frame；每個 host 的 `src` 補兩個 legacy 快照檔，
  供 `role_text = "legacy"` 回復與既有等價測試使用。
- `install/validate_agents.py` 的 `ROLES` 加入兩個 role，Codex installer 與
  `--roles-only` 因此安裝它們；OpenCode 的 `install.sh` 與 route 解析的
  `DEFAULT_ROLE_DEFINITIONS` 同步加入。agy、grok、`tools/sync_global.py` 依 dist 目錄
  列舉，不需改程式。
- grok 的 plan mode 守衛訊息在可用的唯讀 role 清單加上 `researcher`（只改訊息文字，
  判斷仍依 role 的 `default_capability_mode`）。
- prompt lock：新增 `watcher-agent`、`researcher-agent` 兩個 Codex surface
  （`templates/agents/*.toml`），單次變動預算 8 行、800 字元，絕對上限 30 行與
  1900／1700 bytes；既有 surface 只有版本 marker 與 Codex role 表的兩列變動，預算不動。
  `LOCK.json` 有變動，commit 需要 `Lock-Renewal: approved`。

### Docs

- `core/README.md`、`README.md`、`INSTALL.md`、zh-TW／zh-CN README 改成五個 host 都有這兩個
  role；`README.md` 加各 host 解出的 model 表。

### 版本

- 產品與 claude、codex、grok、agy、opencode 各 host 版本一律是 3.1.0。

### 升級

- 用 plugin 的使用者：`claude plugin marketplace remove shoal`，再用 `#v3.1.0`
  加回並更新。
- codex、grok、agy、opencode 的使用者：重新跑各自的安裝或 `tools/sync_global.py`
  才會多出兩個 role 檔；沒有安裝的 host 不受影響。

## v3.0.3

收掉 v3.0.2 之後驗證留下的三個缺口，不需要實測。沒有改動任何 role 或 policy 條款，
受保護的 prompt 檔只有版本 marker 變動。

### Fixes

- Codex installer（`install/install.py`，完整與 `--roles-only` 兩種模式）處理 3.0.0
  改名前的 role 檔案：`agents/mech-executor.toml`、`agents/plan-verifier.toml`
  的位元組等於某個已發行的 shoal template 時，先備份成
  `<檔名>.shoal-codex-<時間>` 再移除（全部成功或全部還原）；使用者改過的檔案不動，
  在輸出的 note 回報 `renamed role drift`。`--dry-run` 只印 `would remove`，不改任何東西。
  與 `tools/sync_global.py` 同一條規則；已發行位元組的 sha256 表由測試對照 git 歷史。
- `#direct` 只在使用者打出的獨立 token 才算：前面是文字開頭或空白，後面是文字結尾、
  空白或句末標點（含 `。，、；：！？`），而且不在 fenced code block 或行內
  code span 裡。`(#direct)`、`docs/x#direct`、URL 片段、`#directly`、`##direct`
  不再放行。仍區分大小寫；每回合有效與 `SHOAL_GUARD_DIRECT=1` 不變。Python 與
  TypeScript（`hasDirectToken`，OpenCode adapter 本身不讀 prompt）共用
  `tests/fixtures/direct_token_vectors.json`。
- `tools/sync_global.py` 的 agy 遷移：移除指向本 repo 的舊名 role symlink 後，若
  `agents/<新名>` 還不存在就補上指向 `hosts/agy/dist/agents/<新名>` 的 symlink
  （`mech-executor` -> `applier`、`plan-verifier` -> `plan-critic`）。原本只移除不補，
  遷移後 `agents/applier`、`agents/plan-critic` 一直被回報不是 symlink。已存在的
  新名一律不動；dry-run 只回報。已經遷移過的機器要手動補這兩個連結。

### Docs

- `docs/assets/shoal-model-routing.svg` 的範例與 Claude 欄的 scout 改成 haiku
  （v3.0.0 起手動指定），圖表其餘不動。

### 版本

- 產品與 claude、codex、grok、agy、opencode 各 host 版本一律是 3.0.3。

### 升級

- 用 plugin 的使用者：`claude plugin marketplace remove shoal`，再用 `#v3.0.3`
  加回並更新。

## v3.0.2

`watcher` 對不知道要跑多久的指令，一律改成背景執行再輪詢。第四輪 live gate 中，
`watcher` 把一個約 11 分鐘的指令放在前景呼叫，到 shell 時限被中斷，結果遺失；
原條款要它先猜指令多久，實際上它不會猜。條款原文在
`docs/specs/delegation-default/CLAUSES.md` 的 2026-10-10 第四輪修訂。

### Features

- `watcher` 的 `long-command-background`：除非 brief 說明指令幾分鐘內就會結束，
  否則啟動背景指令，輸出與 exit status 寫進 log，再用短的前景呼叫輪詢 log，
  直到出現 exit status。
- Claude：用 `run_in_background: true` 啟動，log 末行寫 `EXIT_STATUS=<code>`，
  以每次遠低於前景時限的迴圈等待該行。
- 調度政策的 `watcher-long-commands` 加一句：已知指令預計多久時，在 brief 寫明；
  並把「`watcher` 在自己的前景執行」改成「執行並等待」，watcher 的 description 同步。
- prompt lock：`claude-watcher-agent` 掛 migration `delegation-default-3-0-2`
  （只免這個 surface 的單次變動預算，絕對上限 30 行、2600 bytes 不變）。

### 版本

- 產品與 claude、codex、grok、agy、opencode 各 host 版本一律是 3.0.2。

### 升級

- 用 plugin 的使用者：`claude plugin marketplace remove shoal`，再用 `#v3.0.2`
  加回並更新。

## v3.0.1

dispatch guard 補上 shell 寫檔的缺口。條款原文是
`docs/specs/delegation-default/SPEC.md` 的 G5（2026-10-10 核准），guard 行為記在
`docs/specs/dispatch-enforcement/SPEC.md` 的 2026-10-10 修訂。

### Features

- G5：Claude 在 enforce 下，R1 的條件成立（本輪被分類為 `judgment` 或
  `mechanical`、尚未派出 write role、沒有 `#direct` 或 `SHOAL_GUARD_DIRECT=1`）時，
  main session 前景呼叫的 `Bash` 指令只要字面上寫檔就 deny，規則 id 與訊息沿用
  R1；shadow 記 `would_deny`。原因：真實設定下實測，main 用
  `cat > 檔案 <<EOF` 寫了三個檔，沒用任何改檔工具，R1 看不到。其他 host、
  subagent、沒有本輪分類時不介入。
- 「寫檔」是對指令字串的字面判斷，刻意保守。算寫檔：`>`、`>>`、`>|`、`&>`
  導向一般檔案（含 heredoc）、`tee [-a] 檔案`、`sed -i` 與 `sed --in-place`。
  不算：導向 `/dev/` 底下、`2>&1` 與 `>&2`、`<` 輸入、heredoc 本文、引號內的
  `>`、`[[ ]]` 與 `(( ))` 內的比較，以及 R1 的豁免路徑（`/tmp`、`$TMPDIR`、
  `.ai`、Claude 的 projects 目錄，相對路徑依 cwd 解析）。目標是變數而看不出值時，
  只要明確是導向非 `/dev/` 的目標就算寫檔。
- 限制：用 interpreter 寫檔（python、node、perl 腳本）、`cp`、`mv`、
  `git apply`、`patch`、`dd of=`，以及 `$(...)` 內的導向擋不到，刻意不偵測。
- 被 deny 的指令不記成 edit；放行的 shell 寫檔不計入 R2 的檔案數。沒有寫檔的
  前景 `Bash` 照舊不判斷、不改狀態、不寫 log。背景 `Bash` 仍由 G4 處理，
  背景加寫檔只會得到一次 deny。
- Python guard 與 OpenCode TypeScript 移植共用
  `tests/fixtures/guard_vectors.json`（新增 30 筆 `g5_` 向量）與
  `tests/fixtures/shell_write_cases.json`（77 筆指令對寫檔目標）。

### 版本

- 產品與 claude、codex、grok、agy、opencode 各 host 版本一律是 3.0.1；
  policy 文件只有版本 marker 變動，prompt lock 在預算內。

### 升級

- Claude 全域安裝：重跑 `python3 tools/install_hooks.py --host claude --apply`
  取得新的 guard 腳本（matcher 不變，3.0.0 已含 `Bash`）。
- 用 plugin 的使用者：`claude plugin marketplace remove shoal`，再用 `#v3.0.1`
  加回並更新。

## v3.0.0

role 重整、預設派工與每次派工的 effort。設計與條款原文在
`docs/specs/delegation-default/`（`SPEC.md`、`CLAUSES.md`；2026-10-10 核准）。因為兩個
role 改名，這是 breaking release。

### Breaking changes

- role 改名（core 的 key，五個 host 一起換；行為、model、effort、權限與 prompt 語意不變）：

  | 舊名 | 新名 |
  | --- | --- |
  | `mech-executor` | `applier` |
  | `plan-verifier` | `plan-critic` |

  對照表在 `docs/specs/delegation-default/RENAME.md`。上游專案仍使用舊名，比對上游時先套用此表。
- `Explore` 不再列入 role 清單與路由條款；覆寫檔保留（haiku / low）。

### Features

- 新 role `watcher`（haiku / low，可跑不可寫）：在自己的前景執行被指派的指令、build、測試或 CI 到結束，回報指令、
  結束狀態與判定成敗的原始輸出。`researcher`（opus / high，唯讀加 web）：論文、外部文件與上游專案分析，主張逐項附來源，
  區分來源原文、推論與未驗證；研究結論會影響決策時，main 平行派出實驗組與對照組兩個互相獨立的 `researcher`。兩者都以 `status` 與
  `suggested_next` 結尾。第一階段只有 Claude 綁定，Codex、Grok、agy、OpenCode 的 `omitted_roles`
  列出它們。
- 每次派工帶 effort：新條款 `effort-per-delegation` 以 `Explicit instruction:` 開頭，要求 main
  對每次具名 role 的派工傳 `effort`；role frontmatter 的值是預設，使用者指定時優先，`verifier`、
  `plan-critic` 自行選擇時不低於 `medium`，`security-reviewer` 不低於 `high`。
  `dispatch-kind-label`：派可寫的 role（`executor`、`applier`、`security-executor`）時，
  description 以 `fix:`、`feat:`、`refactor:`、`test:`、`docs:` 之一開頭。
- 預設派工：條款 `direct-when-small`、`local-search-direct`、`delegate-cost-benefit`、
  `single-bug-direct`、`bootstrap-ownership` 改寫。已有穩定契約的實作、互不相干的偵察與長指令預設派工，main
  直接做的條件是寫 brief 的成本高於直接做；bootstrap 註明這個預設優先於 host 內建的「少派 subagent」指示。
  `long-running-main` 取代為 `watcher-long-commands`，`leaf-cannot-finish` 改為由 main
  派背景 `watcher`，main 不自己開背景 shell。新增 `research-fanout`、`plan-critic-gaps`、
  `followup-by-mode`（AUTO 下 role 回報 failed／insufficient 時自動接手，ASK 下停下）、
  `collect-results`（背景 role 完成後先回收並寫一行結果）。
- 常駐 bootstrap 直接寫派工路徑（第一輪 live gate：headless session 只拿到
  bootstrap）：`bootstrap-ownership`、`bootstrap-dispatch-brake` 改寫，新增
  `bootstrap-delegate-default`（executor／applier、每個偵察面一個 scout、背景
  watcher、兩個 researcher）與 `bootstrap-collect`；`watcher` 新增
  `long-command-background`，指令超過前景時限時可自己開背景 shell 等到結束。
- `docs/DESIGN-INVARIANTS.md` 第 2、3、4 條修訂：派工預設化；hook 硬規則加上 Claude 上的 R1 與 main
  背景 shell；各 host 規則相同、只換 model 與工具名稱綁定。
- `plan-critic` 新增補漏模式：brief 帶 `mode: gaps` 時不回 READY／REVISE，改列還沒被問到的需求、沒說出口的假設、
  風險與最多三個不同做法；問使用者與寫 Plan 仍由 main 負責。補漏條款在 core contract，使用 core contract 的 host
  都有。
- dispatch guard（`docs/specs/dispatch-enforcement` 的 2026-10-10 修訂）：Claude 在
  enforce 下 R1 改回 deny（本輪被分類為實作工作而尚未派 write role 時，deny main 的改檔工具）；新增 G4，deny
  main 的背景 `Bash`（`run_in_background: true`），要求改派背景 `watcher`。shadow 記
  `would_deny`；R2 與其他 host 的 R1 維持只提醒；subagent 不受影響。prompt 內獨立的 `#direct`
  放行那一輪（下一輪失效，不記錄 prompt 內容），`SHOAL_GUARD_DIRECT=1` 照舊放行。`Bash` 加進
  `tools/install_hooks.py` 與 plugin 的 `PreToolUse` matcher。
- 選模：Claude 的 `scout` 固定用 haiku（low），`executor` 的 effort 由 high 改 medium。

### 版本

- 產品與 claude、codex、grok、agy、opencode 各 host 版本一律是 3.0.0。prompt lock 以 migration
  `delegation-default-3-0-0`（`--allow-lock-update`）更新：新增 `watcher`、`researcher`
  的 surface，改名的 surface 換路徑，三個超過變動預算的 policy surface 掛 migration marker。

### 升級

- Codex、Grok、agy：`tools/sync_global.py`（每日同步）在 `--apply` 時移除確認是 shoal
  安裝的舊名檔案（`mech-executor`、`plan-verifier`）再安裝新名；dry-run 只回報。Grok 的
  `tools/install_grok.py` 同樣處理。
- Claude 由 dotfile 複製安裝，不在 sync 範圍：全域安裝要自己移除 `~/.claude/agents/mech-executor.md`
  與 `~/.claude/agents/plan-verifier.md`，並重跑
  `python3 tools/install_hooks.py --host claude --apply`（才有 G4 的 `Bash`
  matcher）。
- 用 plugin 的使用者：`claude plugin marketplace remove shoal`，再用 `#v3.0.0` 加回並更新。

## v2.1.1

跨機器共用設定檔時的三個修正。

### Fixes

- `tools/install_hooks.py`：claude 的 `settings.json` 與 agy 的 `hooks.json` 改寫可攜、
  且腳本不存在就 exit 0 的 command（`f="${XDG_DATA_HOME:-$HOME/.local/share}/shoal/guard/shoal_guard.py";
  [ -f "$f" ] || exit 0; exec python3 "$f" --host <host>`），不再寫入含家目錄的絕對路徑
  （設定檔進版控、跨機器共用時會失效）；沒裝 shoal 的機器不會因 python3 找不到檔案 exit 2
  而擋掉每個 PreToolUse。舊的絕對路徑與未防護的可攜 entry 視為 shoal 的，重跑就地換成這個，
  重複執行結果不變。
- `hooks/shoal_guard.py`：`--plugin` 的全域 guard 判斷（K4）也認得可攜與防護形式的 command（仍只在腳本存在時讓出）。
- `tools/sync_global.py` agy：skills、agents 目錄中 2.0.0 之前舊名的 symlink，不論指向哪裡
  （舊 dist 以外的目標，例如 dotfile 時代的安裝，或斷掉的連結）都視為舊安裝，`--apply` 移除、
  dry-run 回報；只 unlink 連結，一般檔案與非舊名不動。
- 新增測試確認 hook 腳本的語法可在 Python 3.9（macOS `/usr/bin/python3`）執行；實測
  `shoal_guard.py`、`shoal_autoroute_gate.py` 與 grok hooks 在 3.9 都能執行，不需要改腳本。

## v2.1.0

milestone 完成時的方向檢查成為必做，並新增使用者明確選擇才啟用的不計代價模式。
設計在 `docs/specs/milestone-direction-check/`。

### Features

- milestone 方向檢查成為必做：多切片 milestone 由 verifier 以原始需求、spec
  non-goals 與 `docs/DESIGN-INVARIANTS.md` 比對；單切片 spec 收尾與派出設計工作前
  由 main 自查；偏離即停；executor 在 brief 外的設計決定逐項審查。
- 不計代價模式：使用者明確選擇時，在已核准範圍內推進到 acceptance，不因花費、
  token、時間、切片數停下；AUTO 停止清單與方向檢查照常，不授予額外權限。
- 新增 `docs/DESIGN-INVARIANTS.md`，記錄 shoal 的設計不變式。

### 版本

- 產品 2.1.0；host 版本 claude、codex 為 2.1.1。

## v2.0.0

shoal 成為獨立產品：安裝出去的名稱全部換新，版本重新起算。設計與對照表在
`docs/specs/shoal-rebrand/`（`RENAME.md` 是唯一的對照來源）。

### Breaking changes

- 名稱：skill `shoal-orchestration`；Codex plugin 與 marketplace `shoal-codex`、
  `shoal-jev-router`（資料目錄 `shoal-jev/`）；Codex hook `shoal_autoroute_gate.py`，
  projection 是新的獨立 `shoal-autoroute-v1`；marker `<!-- shoal-claude v… -->`、
  `<!-- shoal-codex:begin -->` 等；Grok `shoal-grok`、agy `shoal-agy`、OpenCode
  `shoal-opencode`（tool `shoal_route`，設定目錄 `shoal/`）；install state
  `.shoal-install-state.json`；備份與暫存檔名 `.shoal-codex-<ts>`、`.shoal-stage-`。
- 環境變數前綴一律是 `SHOAL_`（例：`SHOAL_REF`、`SHOAL_TARGET_HOME`、`SHOAL_GROK_HOME`、
  `SHOAL_ROOT`）。不留相容層：舊前綴不再被讀取，dispatch guard 的舊別名
  也一併移除（`SHOAL_GUARD`、`SHOAL_GUARD_MAX_FILES` 本來就是主名稱）。
- 不改的：role 名稱、選模、權限與 guard 規則。

### 版本

- 產品與各 host 版本一律從 2.0.0 起算，不再沿用上游衍生的版本號：根目錄 `VERSION`、
  `hosts/{claude,codex,grok}/VERSION`、新增的 `hosts/agy/VERSION`（render 以它產生
  `<!-- shoal-agy v… -->`）、OpenCode plugin 的 `package.json`。`upstream.lock` 的
  `marker_version` 同步，上游版本仍只記在 `upstream.lock`。

### 遷移

installer 與 `tools/sync_global.py` 會辨識自己先前以舊名安裝的檔案（marker、hash 或安裝紀錄），
移除後以新名安裝；不是 shoal 安裝的舊名檔案一律不動並回報。

- Codex：`install/install.py` 先移除舊 hook 群組與 gate 腳本、轉換 `AGENTS.md` 的 marker 區塊、
  改名 `config.toml` 裡指向本 repo `plugin/` 的 marketplace 與 plugin table、移除過期的
  plugin cache、改名 jev 資料目錄、封存舊 install state，再以新名安裝並寫新的 state。
  你自己改過的舊 gate 腳本改名為 `<name>.pre-shoal-<時間>` 備份，不再註冊。新的 hook 路徑
  要在互動式 Codex 用 `/hooks` 再核准一次。
- Grok：`tools/install_grok.py` 確認舊名的 rules、hooks json 與 hooks 目錄是 shoal 安裝的
  （marker 帶 `-shoal.N`，或有 shoal 專屬的 guard 腳本）才移除，並一起備份。
- agy：`tools/sync_global.py` 把指向本 repo `hosts/agy/dist` 的舊 skill symlink 改指新名。
- OpenCode：`install.sh` 以舊 manifest 先 `--disable`，再以新名 `--enable`（`--global` 與
  `--target` 都是）；檔案被改過就整批不動。
- `tools/sync_global.py` 的 dry-run 只列「移除舊名」與「安裝新名」。

### Lock

- prompt lock 做一次 renewal：`LOCK.json` 的路徑、mirrors 與
  `required_fragments` 更新，內容變動的 surface 帶 `migration`
  （`shoal-rebrand-2-0-0`，`equivalence` 指向 `RENAME.md`）。路徑改名的
  surface 在 validator 走「新增」分支，所以另用 `tools/check_rename.py`
  證明等價：base 的舊內容套用 RENAME 的替換與版本號後，必須與新檔逐位元組
  相同。

### Tooling

- 新增 `tools/check_rename.py`（rename-aware lock 檢查）與 `tools/scan_legacy_names.py`
  （產品面舊名掃描，RENAME「掃描範圍」）。
- 移除 `tools/guard_parity.py`：它對照的舊 guard 已不存在。

## v1.5.0

### Features

- core-policy P2：Claude host 的 policy 改由 `core/policy` 條款組裝
  （`policy_text = "core"`）；兩處「workflow」改為 procedure／policy 的
  用字，沒有預期的行為變更。claude host 版本 1.4.2-claude.4。
- core-policy 完結：只有 Claude 使用 core，其他 host 維持 legacy。P3 不推進：
  Grok 的 rules 逐字取自上游 pilotfish-grok（agy 衍生自它），改由 core 組成會失去
  與上游的同步；Codex 有自己的選模與 decision checkpoint 機制，共用部分少且需
  lock migration；OpenCode 缺 plan-verifier 與 mech-executor。持平優先，不藉共用化
  新增能力。
- generic-shoal（`docs/specs/generic-shoal/`）完結。
- Codex 的 dispatch guard 預設切為 enforce（E6：23 筆決策、4 筆 would_deny
  皆正確、誤擋 0）。

### Fixes

- dispatch guard 的 R1、R2 改為提醒（不再擋）：派工與否是淨效益判斷，不該以
  數字門檻強制，回到 pilotfish 的 dispatch brake 原則（2026-10-06 設計對照）。
  Claude 與 Codex 每輪第一次以 additionalContext 提醒，其他 host 只記 log；
  LEAF、VERIFY_EDIT 照舊會擋。
- guard 納入 grok 1.0.46 建新檔用的 write 等編輯工具。

### 已知限制

- Grok 的 E6 延後，等免費額度恢復後再累積 shadow log。
- agy 固定 shadow。
- guard 擋不住 shell 寫檔（例如重導向、sed -i）。
- guard 在 Windows 為 no-op。

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
