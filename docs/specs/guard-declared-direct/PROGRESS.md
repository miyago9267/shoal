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
- 偏離 spec 字面的一點：`declare` 只在 claude 可選（`DECLARE_HOSTS`）。M1 寫 claude 與 codex，
  見下方 S2。

## S2（部分完成：只啟用有證據的部分）

- 啟用：Codex 的 `UserPromptSubmit` 讀 `payload.prompt` 的 `#direct`（規則同 Claude）。證據：
  `hooks/shoal_autoroute_gate.py` 在 Codex 讀同一個欄位，
  `tests/test_autoroute_hook.py` 的 payload 形狀與之相同。
- **未啟用：Codex 的 shell 宣告與 shell 寫檔判斷。** 缺的證據：repo 內沒有任何 Codex shell 工具
  的名稱或 `tool_input` 欄位的記錄。僅有的線索是 `dispatch-enforcement/SPEC.md` 轉述官方文件
  「`apply_patch`、Bash、MCP」，沒有實測 payload；`E0-RESULTS.md` 只記錄 `apply_patch`
  （`tool_input.command` 是 patch 全文）與 `collaborationspawn_agent`；hook 註冊的 matcher
  （`install/hook_registration.py` 的 `GUARD_TOOL_MATCHER`）不含 shell。本機 Codex 0.160.1
  二進位內的 `pre-tool-use.command.input` schema 只寫 `tool_name: string`、
  `tool_input: true`，沒有 shell 的欄位。
- 因此 matcher、`shoal-guard-v1` projection、`tools/install_hooks.py`、
  `tools/sync_global.py` 都沒有變動（hook trust 的 hash 不變，不需要在 Codex 重新核准）。
- 決定：Codex 的 `SHOAL_GUARD_R1` 預設是 `classified`（3.1.0 的行為：R1／R2 只提醒）。若預設
  `declare`，Codex 的 `apply_patch` 會被 deny，但 main 的 shell 呼叫到不了 guard，宣告沒有出口，
  只剩派工與使用者的 `#direct`，等於死路。在 Codex 明確設 `declare` 也一樣當成預設。
- 要補上的做法（一次真實 Codex 執行）：臨時註冊一個 `PreToolUse` hook，matcher 為 `.*`，
  只把 `tool_name` 與 `tool_input` 的 key 名稱（不記值）寫到 temp 檔，讓 main 跑一個
  `echo ok` 與一個 `cat > f <<EOF`。得到工具名稱與欄位後：`adapt_codex` 加一個 shell 分支
  （`tool_kind: shell`、`command`），`DECLARE_HOSTS` 加 `codex`，`GUARD_TOOL_MATCHER`（含
  `install_hooks.py` 的說明）加入該工具名稱，並補 Codex 向量。matcher 一改，hook trust 會變，
  需要在 Codex 用 `/hooks` 重新核准一次；舊註冊由 `tools/install_hooks.py --host codex --apply`
  與 `install/install.py` 原地升級（沿用 claude 在 v3.0.0 把 `Bash` 加進 matcher 的做法）。

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

## S4 live gate（待辦）

尚未執行。範圍依 spec：只跑 Claude 與 Codex，最多 8 次，回答 spec 的三個問題（未宣告被擋、
被擋後的選擇、小改動與三檔小功能的宣告率）。因為 Codex 的宣告尚未啟用，Codex 這一半在補上
shell 工具的證據之前只能量 `apply_patch` 的提醒與 `#direct`，不能量宣告。
