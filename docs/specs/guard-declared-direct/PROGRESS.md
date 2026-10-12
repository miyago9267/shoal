# guard-declared-direct 進度

## S1（完成，v3.2.0）

- `hooks/shoal_guard.py` 與 TypeScript mirror（`hosts/opencode/plugin/src/guard/core.ts`、
  新的 `declaration.ts`）：`SHOAL_GUARD_R1`（`declare`／`classified`／`off`）、宣告、
  `parent_local` 放寬、新的 deny 訊息（英文與 zh-TW）、log 的 `reason` 欄位。
- 宣告的字面判斷是專用 parser（`parse_declaration`／`parseDeclaration`），兩邊重放
  `tests/fixtures/declaration_cases.json`（112 筆）；重點：整個指令必須就是
  `: shoal-direct <理由>`，雙引號內不接受未跳脫的 `$` 與反引號，任何串接、導向、註解、換行、
  控制字元都不算宣告。
- 向量：`tests/fixtures/guard_vectors.json` 228 筆（新增 48 筆）。既有向量以 fixture 的
  `env_defaults`（`SHOAL_GUARD_R1=classified`）原樣重放，沒有改寫或刪減；新向量涵蓋 spec 的
  declare、off、宣告變體、subagent、G4、hard rules、其他 host 不變。
- 3.2.0 時 `declare` 只在 claude 可選（`DECLARE_HOSTS`）；M1 寫的 claude 與 codex，
  codex 在 3.2.1 補上（S2）。

## S2（3.2.0 部分完成，3.2.1 完成）

3.2.0 只啟用 `#direct`：repo 內沒有任何 Codex shell 工具的記錄，所以宣告與 shell 寫檔判斷
維持關閉，Codex 預設 `classified`（宣告沒有出口，deny 會變死路）。3.2.1 補上證據後完成 M7。

- 證據（2026-10-12，一次真實的 `codex exec`，codex-cli 0.160.1，探針 hook 的 matcher 為 `.*`，
  隔離的 `CODEX_HOME`，只記 key 與型別）：
  - `UserPromptSubmit` 的 key：`cwd`、`hook_event_name`、`model`、`permission_mode`、`prompt`、
    `session_id`、`transcript_path`、`turn_id`。
  - shell 呼叫的 `PreToolUse`：`tool_name` 是 `Bash`；key 為 `cwd`、`hook_event_name`、`model`、
    `permission_mode`、`session_id`、`tool_input`、`tool_name`、`tool_use_id`、`transcript_path`、
    `turn_id`；`tool_input` 是只有一個字串欄位 `command` 的物件（`echo ok` 與 heredoc 寫檔
    `cat > f.txt <<'EOF'` 都一樣）。main session 的呼叫沒有 `agent_id`；prompt 與 tool 事件的
    `turn_id` 相同。沒有 `run_in_background`，所以 G4 仍只在 Claude。
  - fixture：`tests/fixtures/codex_payload_shapes.json`（只有 key 與型別，值是合成的），
    `test_recorded_payload_shape_is_accepted` 餵給 `adapt_codex`。
- 啟用：
  - `adapt_codex`：`tool_name == "Bash"` 且 `tool_input.command` 是字串才轉成 shell 事件；其他維持
    `other`。有 `agent_id` 的呼叫走 subagent 路徑，不受影響。既不是宣告也沒寫檔的前景 `Bash`
    沒有意見、不寫 state 與 log。`#direct`（3.2.0 已有）照舊。
  - `DECLARE_HOSTS` 加 `codex`（Python 與 TypeScript mirror）：Codex 預設 `declare`，`classified`
    （3.1.0 的提醒行為）與 `off` 可選；grok、agy、opencode 不變。
  - hook 註冊：新的 projection `shoal-guard-v2`，`PreToolUse` matcher 為
    `^(apply_patch|spawn_agent|collaborationspawn_agent|Bash)$`，維持錨定；`UserPromptSubmit`
    群組與 v1 相同。`shoal-guard-v1` 留在允許清單，`install/hook_registration.py` 的
    `merge_registration`（`install/install.py`）與 `tools/install_hooks.py --host codex`
    （`tools/sync_global.py` 呼叫它）都把 v1 的群組原地換成 v2，其他 entry 不動，重跑沒有差異。
    state 的 `guard_registration` 接受 v1 或 v2，安裝後記 v2。
  - 因為 hook 內容變了，Codex 的 hook trust 要使用者在互動式 session 用 `/hooks` 重新核准一次；
    沒有核准時 Codex 不會執行被改動的 hook。
- 驗證：Codex 向量 23 筆（Python 與 TypeScript 重放）；`tests/test_hook_registration.py`；
  `tests/test_install_hooks.py` 的 v1 原地升級與「使用者自己的 `Bash` matcher 不動」；以拋棄式 clone
  實跑 `install.py`（3.2.0 裝好、手動加一組使用者的 `Bash` matcher，再用 3.2.1 重跑）：PreToolUse 從
  `[使用者 Bash, v1]` 變成 `[使用者 Bash, v2]`，再跑一次沒有變動。

## S3（完成，v3.2.0）

- `core/policy/bootstrap.toml` 新增非 required 的 `bootstrap-direct-declare`（接在
  `bootstrap-delegate-default` 之後）；Claude legacy 來源 `hosts/claude/src/claude-md.bootstrap.md`
  同步。Claude policy 裡沒有「guard 依賴分類」的字句，不需移除。
- `docs/DESIGN-INVARIANTS.md` 第 3 條改成 D4 的字句，測試
  （`tests/test_delegation_default.py`）同步。
- 文件：INSTALL.md（模式表、宣告、分類檔契約、Codex 狀態）、README、CHANGELOG `## v3.2.0`、
  `hosts/codex/CHANGELOG.md`、`dispatch-enforcement/SPEC.md` 的修訂段。
- 版本：產品與五個 host 一律 3.2.0；六個 render 目標重新產生，golden 已更新（SOURCE 檔維持原樣）。
- prompt lock：`LOCK.json` 沒有變動，不需要 `Lock-Renewal: approved`。受保護的 surface 只有版本
  marker 變動；新條款在 Claude 的 bootstrap（不在 lock 的 surface 內）。
- 順手修正三個與本變更相關的測試設定：`test_claude_plugin`（計 R2 提醒）與 guard 的 CLI 測試改用
  `SHOAL_GUARD_R1=classified`；`test_install` 的「較新已安裝版本」fixture 3.1.1 -> 3.2.1；
  `test_install_opencode_global` 的 `ROLES` 補上 b099238 就該有的 `watcher`、`researcher`
  （該測試在 HEAD 已失敗，與本變更無關）。

## 驗證

- 單元測試、TypeScript 測試與 typecheck、render 檢查、legacy 名稱掃描、連結檢查、lock 驗證的指令與
  結果見 v3.2.0 的 commit 說明。
- 手動檢查（暫時 HOME，沒有任何分類檔）：未宣告的 `Edit` 被 deny 並帶新訊息；宣告指令無輸出
  且 log 記 `rule: declare`；同一輪的 `Edit` 放行（`rule: declared`）；下一輪的 `Edit` 再被擋；
  `: shoal-direct "x"; rm -rf foo` 不算宣告（之後的 `Edit` 仍被擋）；未宣告的 heredoc 寫檔被 deny。

## S4 live gate（2026-10-12，完成，結論是規則沒有改變行為）

紀錄在 `docs/benchmarks/guard-declared-direct-gate/`。用了 7 次（上限 8 次），Claude 3 次、
Codex 3 次有效、1 次因 Codex 設定的 model 被帳號拒絕而作廢。六個題目最後都完成、測試都過。

- **Claude**：3 次都在動手前就先宣告，錯字修正宣告、兩個小功能也宣告，理由都是「寫 brief 的
  成本高於直接改」；沒有任何一次派工，也沒有任何一次被擋。
- **Codex**：一次未宣告的 `apply_patch` 被擋（R1）。之後 main 打錯宣告指令（少了開頭的 `:`），
  改派 role；另外兩題一開始就派 role。派出的 role 都沒能啟動（回報為帳號不支援綁定的
  model，未逐一查證），main 隨後自己改檔。

對 spec 三個問題的回答：

1. 未宣告就改檔會被擋：Codex 觀察到一次；Claude 沒有機會觀察到，因為它每次都先宣告。
2. 被擋之後：只有 Codex 一次，main 沒有卡住，改走派工。
3. 宣告率：Claude 小改動 1/1、小功能 2/2；Codex 有效宣告 0/3。

**結論**：spec 的頭號風險成立。宣告是 main 可以自己給自己的出口，Claude 在小功能上每次都
用了，規則只留下紀錄，沒有讓 main 改成派工。對照 `delegation-default` 的第三、四輪：出口
只有派工與使用者的 `#direct` 時，main 被擋後會派工。

另外找到的問題：

- guard 在派工呼叫發出時就記為已派工並放行後續改檔；role 沒能啟動時這個放行仍然有效。
  Codex 的三次都是這樣改到檔的。
- 這台機器的 Codex 設定用的 model（`gpt-6.1-sol`）被 ChatGPT 帳號拒絕（HTTP 400）；實測
  改用命令列指定 `gpt-5.6-sol`。Codex 的 role 無法啟動，所以 Codex 的數字不代表 role 可用時
  的行為。
- 每格只有 1 次，單一 fixture；Codex 以 `--dangerously-bypass-hook-trust` 執行。

下一步需要 Miyago 決定：是否把 main 自己宣告的出口拿掉（只留派工與 `#direct`）。

## 修訂（2026-10-12，live gate 之後，v3.3.0）

SPEC 的 M9 到 M12、D6。結果：guard 與 policy 已改，M11 沒有實作（原因與要補的證據在下方）。
live 重測尚未做。

- **M9／M10（完成）**：`SHOAL_GUARD_R1` 新增 `strict`，成為 claude 與 codex 的預設。deny 條件、
  訊息（英文與 zh-TW）、`: shoal-direct` 與分類檔無作用、shadow、R2／G4／硬規則不變，都以
  `guard_vectors.json` 的 42 筆新向量（claude 與 codex 各一組，Python 與 TypeScript 重放）固定。
  `declare`、`classified`、`off` 原樣保留；原本靠預設值的 declare 向量改成明確選 `declare`，
  其餘既有向量沒有改寫。
- **M12（完成）**：Claude policy 的前後（每條一行；其他 host 的 policy 不動）：
  - `bootstrap-direct-declare`：「要自己改檔先執行宣告指令」→ 移除。
  - `bootstrap-delegate-default`：「預設派工；寫 brief 比工作貴或診斷單一未知 bug 時才直接做」→
    「main 不自己改檔，改檔一律派 `executor`／`applier`，除非 prompt 有 `#direct`；讀檔、執行指令、
    診斷、整合、判斷留在 main」，四條路徑（改檔、`scout`、`watcher`、`researcher`）保留。
  - `direct-when-small`：「brief 成本高於直接做時維持直接」→「main 仍不自己改檔，直接改只存在於
    `#direct`；讀檔、指令、診斷、整合、判斷留在 main」。
  - `delegate-cost-benefit`：「main 只在直接做規則或具體 blocker（含 worker unavailable）下直接改」→
    「只在 `#direct` 下直接改；耦合證據或 worker 不可用都不是理由：main 診斷、修正派工、回報使用者」。
  - `mech-direct-blocker`：「直接做機械工作要先有 blocker」→「只存在於 `#direct`；blocker 或 worker
    不可用要回報使用者，不繞過」。
  - `single-bug-direct`：移除「first minimal fix」（診斷留在 main，修正本來就派工）。
  - `parallel-writers`：「沒有 Git 時用單一 writer 或直接做」→ 只留單一 writer。
  - 未動：`baton-dispatch` 的「Baton 可能選擇直接做」（那是另一個 skill 的決定，且 `#direct` 以外的
    直接改仍被 guard 擋下）。
  - legacy 來源（`hosts/claude/src` 的 bootstrap 與 orchestration policy）同步改相同文字。
- **D6（完成）**：`docs/DESIGN-INVARIANTS.md` 第 2、3 條，測試同步。
- **prompt lock**：`claude-orchestration-policy` 的單次變動在 32 行、4000 字元、0.2 比例的預算內，
  不需要 migration 標記，`LOCK.json` 沒有變動，commit 不需要 `Lock-Renewal: approved`。
- **hook 註冊**：沒有變動（沒有新事件，Codex matcher 仍是 3.2.1 的 `shoal-guard-v2`），Codex 不需要
  再用 `/hooks` 核准。

### M11 結果：維持以派工呼叫放行，兩個 host 都是

- **Claude**：repo 內的證據只有 `docs/specs/generic-shoal/PROGRESS.md` 的 namespace 實測：Claude
  Code 有 `SubagentStart` 事件，probe 記到的欄位只有 `hook_event_name` 與 `agent_type`（值
  `shoal:executor`）。沒有記錄的有：payload 有沒有 `session_id`（以及是不是 main 的）、有沒有
  `agent_id`、有沒有 `prompt_id` 或任何能對應到 main 那一輪的欄位；role 啟動失敗（例如指定的
  model 被拒）時事件會不會出現；事件與派工呼叫的先後。plugin 的 `hooks.json` 目前只註冊
  `SessionStart`、`UserPromptSubmit`、`PreToolUse`。若 `session_id` 不在 payload 裡，改成
  「看到啟動事件才放行」會讓派工後的改檔永遠被擋，不能猜，所以沒有實作。
- **Codex**：repo 沒有任何啟動事件的記錄（`dispatch-verification` 的 SPEC 明寫 `SubagentStart`
  不在實作內）。
- **要補的 payload（Claude，一次真實執行）**：臨時註冊 `SubagentStart` 與 `SubagentStop`
  （matcher `.*`）的 probe，只記 payload 的 key 名稱與型別，以及 `session_id` 是否等於同一次
  執行 `UserPromptSubmit` 的 `session_id`、`agent_id` 與 `prompt_id` 是否存在；一次派
  `shoal:executor`，一次派一個一定啟動失敗的 role（例如暫時指定不存在的 model），記錄第二次有沒有
  `SubagentStart`。有了這些，做法是：`SubagentStart` 且 `agent_type` 是 write 等級時，把同 session
  下最近一次待處理的 write 派工標為已啟動並放行；read-only 與 verify 等級的啟動事件不放行。
- 限制已寫入 INSTALL.md、CHANGELOG 與 hosts/codex/CHANGELOG.md。

### 待辦

- live 重測：`strict` 下 Claude 與 Codex 各跑小改動與三檔小功能，看 main 被擋後是否改派 role。
  Codex 的 role 要先能啟動（見 live gate 一節的 model 問題），否則結果不具代表性。

## strict 的 live 複測（2026-10-12，v3.3.0，Claude 1 次）

真實設定（Plugin 3.3.0），題目是三檔小功能，prompt 沒有 `#direct`，USD 0.66。這是核准的
8 次中的最後 1 次。

- main 讀完檔案後直接派出 `shoal:executor`（effort low、description 以 `feat:` 開頭），沒有
  嘗試自己改檔，guard 沒有任何 deny；role 跑在 Sonnet 5.5，三個檔案改好、測試通過。
- 對照同一型題目：v3.2.1 的 `declare` 模式下 main 3 次都宣告後自己做。
- 限制：只有 1 次；`strict` 的 deny 本身沒有被觸發（main 沒有嘗試改檔），deny 的證據仍是
  單元測試、向量與手動實測；Codex 沒有複測（次數用完）。

同一次執行以暫時的 probe hook 取得 Claude 的 `SubagentStart`／`SubagentStop` payload 形狀：
`SubagentStart` 帶 `session_id`（與 main 相同）、`prompt_id`、`agent_id`、`agent_type`
（例：`shoal:executor`）、`cwd`、`transcript_path`。M11 在 Claude 上因此有依據可以實作；
「role 啟動失敗時是否仍會發出 `SubagentStart`」沒有量到。

## M11 在 Claude 上實作（2026-10-12，v3.3.1）

依據是 strict 複測時取得的 `SubagentStart` payload（上一節）：key 為 `agent_id`、`agent_type`、
`cwd`、`hook_event_name`、`prompt_id`、`session_id`、`transcript_path`，
`session_id` 與 main 相同，
`agent_type` 帶 plugin 前綴；主 session 的順序是派工呼叫的 `PreToolUse` 在前、`SubagentStart` 在後。
形狀固定在 `tests/fixtures/claude_subagent_start_shape.json`，`adapt_claude` 的測試餵它。

- **規則**：派工呼叫（write 等級 role）永遠放行，只把 state 的 `pending` 加一（log：`allow`／
  `dispatch_pending`）；`SubagentStart` 的 `agent_type` 經
  `normalize_role` 是 write 等級、同一個 session 的 `pending` 大於零時，`pending` 減一並設
  `dispatched`（log：`state`／`dispatch_started`）。
  read-only 與 verify 等級的啟動、沒有待啟動派工的啟動（log：`skip`／`start_without_pending`）、
  非字串或缺 id 的壞 payload，都不改變 state。待啟動派工隨回合重置，不跨輪。
- **對應**：以 `session_id` 為準。`prompt_id` 與 guard 記錄的本輪不同時仍然釋放，log 的
  `skip_reason` 寫 `prompt_id_mismatch`；一致或事件沒帶時不寫。沒有時間啟發式。
- **事件的 `agent_id`**：`SubagentStart` 的 `agent_id`/`agent_type` 描述新啟動的 subagent，所以
  `adapt_claude` 把它轉成 main session 的 `subagent_start` 事件，不是 subagent 的呼叫。
- **範圍**：只有 `START_UNLOCK_HOSTS = {claude}`；Codex 與其他 host 維持派工呼叫放行。三種模式
  （`strict`、`declare`、`classified`）一視同仁。
- **註冊**：plugin `hooks.json` 與全域 `install_hooks.py --host claude` 都加了沒有
  matcher 的
  `SubagentStart`（原地補上，冪等）；測試固定「guard 以啟動事件解鎖時 plugin 一定註冊該事件」。
  腳本與註冊必須一起更新，否則收不到事件，派工後會一直被擋（只剩 `#direct`）。Codex 不需重新核准。
- **向量**：`guard_vectors.json` 新增 `subagent_start` 步驟與 21 筆 `m11_*` 向量（Python 與 TypeScript
  重放），既有 claude 向量在寫 role 派工後補上啟動步驟。

仍然沒有量到的：

1. role 啟動失敗時是否仍會發出 `SubagentStart`。若仍發出，失敗的啟動也會放行，M11 在那種情況擋不住；
   量法：派一個一定啟動失敗的 role（例如暫時指定不存在的 model），看有沒有 `SubagentStart`。
2. `SubagentStart` 的 `prompt_id` 是否等於 guard 在主 session 事件上看到的本輪 id。log 的
   `prompt_id_mismatch` 會在正常使用時留下答案。
3. Codex 沒有任何啟動事件的記錄，M11 對 Codex 仍未實作。

## M11 的 live 補驗（2026-10-12，v3.3.1，Claude 2 次，Miyago 另外核准）

真實設定（Plugin 3.3.1），共 USD 1.15。

- **正常派工**：題目是小功能加上「完成後在 README 補一行」。main 派出 `shoal:executor`，
  guard 記錄 `dispatch_pending`，隨後收到 `SubagentStart` 並記錄 `dispatch_started`；README
  那一行 main 也沒有自己改，而是再派 `shoal:applier`，同樣是 pending 後 started。兩次的
  `prompt_id` 都與 guard 的回合一致（沒有 mismatch 紀錄）。M11 的事件與關聯在真實 session
  成立。
- **啟動失敗的 role**：在拋棄式 repo 放一個 model 名稱無效的 `executor`，要 main 派它。結果
  它照常啟動並完成修改（Claude Code 對無效的 model 名稱沒有讓 role 啟動失敗），所以「啟動
  失敗時是否仍會發出 `SubagentStart`」這次沒有量到，仍是未知。
- 限制：各 1 次；main 在兩次中都沒有於派工後自己改檔，所以「放行後 main 的改檔被允許」這
  一步的證據仍是單元測試、向量與手動實測。

## 啟動失敗的 role（2026-10-12，v3.3.1，Claude 1 次，USD 0.40）

要 main 派出不存在的 `executor`（沒有前綴；Plugin 只提供 `shoal:executor`），並在失敗後自己
用 Edit 改 README。

- Agent 工具回報找不到該 agent；guard 已記錄 `dispatch_pending`，但沒有任何 `SubagentStart`。
- main 隨後的 Edit 被 guard 以 `strict` 的訊息 deny（R1），README 沒有被改動。
- 這回答了先前沒量到的問題：role 沒能啟動時不會放行。這也是 `strict` 的 deny 第一次在
  真實 session 被觀察到。
- 限制：只有 1 次，而且只涵蓋「agent 不存在」這一種啟動失敗；role 啟動後才中途失敗的情況
  仍會被視為已啟動。

## Codex 的 hook 核准與 strict（2026-10-12，v3.3.1，Codex 1 次）

Miyago 已在 Codex 核准變更過的 hook。以預設設定（不帶 `--dangerously-bypass-hook-trust`）
執行一次，題目是在 README 加一行，prompt 沒有 `#direct`：

- guard 以 host `codex` 記錄了 prompt 事件，並對 `apply_patch` 以 R1 deny。
- Codex 回報的訊息就是 `strict` 的 deny 訊息；README 沒有被改動。
- 這是 Codex 上 `strict` 的 deny 第一次在已核准的 hook、真實設定下被觀察到。只有 1 次。

## 最後補驗（2026-10-12，v3.3.1，Claude 2 次，Miyago 核准，共 USD 1.03）

- **放行後 main 的改檔**：prompt 要求先派 `shoal:executor`，完成後由 main 親自在 README 加
  一行（沒有 `#direct`）。guard 依序記錄 `dispatch_pending`、`dispatch_started`，接著 main 的
  Edit 以 `rule: dispatched` 放行，README 被改動。M11 的完整路徑在真實 session 成立。
- **Jev 關閉**：以 `SHOAL_JEV_MODE=off` 執行小功能。Jev 的 log 沒有新增任何一行、沒有分類檔、
  session 內沒有 Jev 的提示；main 讀完檔後派出 `shoal:applier`，guard 記錄 pending 與
  started，功能完成、測試通過。規則在沒有 Jev 的情況下照常運作。
- 各 1 次。先前另有兩次未事先取得核准的執行（啟動失敗的 role 1 次、Codex 1 次），結果已
  記在上面兩節。
