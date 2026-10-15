# modular-install 進度

規格：[SPEC.md](./SPEC.md)。任務：[TASKS.md](./TASKS.md)。版本：v3.8.1。
分支 `release-3.8.0`，PR #4。

## 各 slice

| Slice | Commit | 內容 |
| --- | --- | --- |
| S1 | `41d3630`、`c017c42` | 模組清單、`--list`、dry-run；推導改用 `install_hooks` |
| S2 | `ef30603` | guard chain 擴充點 |
| S3 | `05bf86b`、`ac957e4` | `--without` 生效、chain 註冊、guard 改名 `shoal-dispatch-guard` |
| S4 | `9533ea1`、`0cba2da` | Claude 拆成 `shoal` 與 `shoal-dispatch-guard`；live 已驗 |
| S5 | 本次 docs commit | README、INSTALL.md 的模組說明、SPEC 命名例外、本檔 |
| issue #3 | `40c95a1`、`641e1d1`、`bd568b1`、`296ac44` | chain 成員介面 |
| PR #4 | `d8af852`、`6ce52c3` | CI 與 review 意見 |
| v3.8.1 | `4a06ddb` | 相容檔 |

## issue #3 的決定與實作

決定留言：<https://github.com/miyago9267/shoal/issues/3#issuecomment-6164300725>。

| 決定 | 實作 |
| --- | --- |
| 輸出是一個 JSON 物件：`decision`、`reason`、可選 `context`；`member`、`version` 只寫 log | `hooks/shoal_guard.py` 與 OpenCode `src/guard/chain.ts`；`version` 可為數字（`d8af852`） |
| `events` 宣告要收的事件，預設 `["PreToolUse"]` | manifest 欄位與 `--chain-events`（驗證名稱、重新登記沿用原值）；Claude plugin 加掛改檔工具的 `PostToolUse` 與 `SessionEnd`；Codex 升為 `shoal-dispatch-guard-v2` |
| 只有 `PreToolUse` 的 deny 會擋（Stop 維持 block），其他事件只記 log | `_apply_chain`；任何事件的第一個 deny 之後後面的成員不再執行（`d8af852`） |
| Claude 把 `context` 轉成 `additionalContext`，其他 host 只記 log | 共用向量 `chain_context_*` |
| 注入 `SHOAL_GUARD_HOST`、`SHOAL_GUARD_EVENT` | 共用向量 `chain_env_*` |
| 單一成員上限 8 秒，整條 chain 為 hook 逾時 10 秒減 2 秒 | `chain_budget` 向量；成員 stdout 最多讀 64 KiB |
| 關掉 dispatch-guard 但該 host 有成員時只跑 chain | 共用向量 `chain_only_mode_*`，OpenCode 測試同名語意 |

## SPEC「Open checks」結果

| 項目 | 結果 |
| --- | --- |
| Claude 第二個 plugin 只帶 hook 是否可行 | 可行，已實作 `claude-guard-plugin/`；兩個 plugin 的 hook 在同一個 session 合併，是依 INSTALL 記錄與 render 測試的結論，live 驗證待補 |
| 公開 marketplace 的快取範圍 | 未驗證；相容檔依 `cache/<marketplace>/<plugin>/<版本>/` 的假設找 guard，找不到就 fail-open |
| agy、Grok、OpenCode 略過 guard 後 uninstall 與 drift 檢查 | 已由 `test_install_hooks`、`test_install_grok` 的 `--no-guard` 案例與 OpenCode manifest 測試涵蓋；agy 實機沒有再跑 |
| chain 成員逾時預設值 | 單一成員 5 秒起、上限 8 秒，整條 chain 8 秒；超過略過並記 `chain_budget` |

## verifier 在 S1 至 S3 的發現與處理

repo 內沒有保存 verifier 的原文，下面依 fix commit 的標題與內容整理，只列對得上的項目。

| Slice | 發現 | 處理 |
| --- | --- | --- |
| S1 | 模組推導對 guard 的辨識不可靠 | `c017c42`：改用 `install_hooks` 辨識；判斷不出來視為已安裝 |
| S3 | agy 舊群組 `shoal-guard` 也是外部專案的名字，不能無條件遷移 | `ac957e4`：每個 handler 都是 shoal 的才遷移，否則原樣保留並印 notice |
| S3 | 清單路徑規則與 guard 不一致 | `ac957e4`：`XDG_DATA_HOME` 非絕對路徑一律忽略 |
| S3 | 有 chain 成員時 `--without dispatch-guard` 會把 hook 一併移除 | `ac957e4`：chain-only 模式保留 hook |
| S2 | 沒有對應的 fix commit | 無記錄 |

## v3.8.0 升級事故與 v3.8.1

- 事故：v3.8.0 把 guard hook 拆到 `shoal-dispatch-guard`，基礎 plugin 不再有
  `hooks/shoal_guard.py`。升級前就開著的 Claude session 保留舊 hook 設定，每次
  Bash、Agent、Edit、Write 都因為「can't open file」失敗，直到手動補回檔案。
- 缺口：測試只涵蓋新 session 的 `hooks.json`，沒有涵蓋「舊 session 的設定仍指向舊路徑」。
- 修正（`4a06ddb`）：基礎 plugin 保留相容檔，來源 `hosts/claude/plugin-src/shoal_guard_compat.py`。
  轉交給 guard plugin 的腳本，找不到就以 0 結束；不在 `hooks.json`。
- 測試：`tests/test_claude_plugin.py` 的 `CompatShimTests`（轉交 argv 與 stdin、沿用 exit code、
  找 cache、找不到時靜默）與 golden／`--check`。

## 已知限制

- 相容檔看到同一個 marketplace 裡有 `claude-guard-plugin/` 就會轉交，不看該 plugin 是否啟用；
  選擇 `--without dispatch-guard` 但沒重開的舊 session 仍會跑 guard，重開後就沒有。
- guard plugin 與 base 的版本要同步，否則行為可能不一致。
- dotfile 的 updater 在 repo 外，要依 INSTALL.md 的契約另外改。
- OpenCode、Grok、agy 目前只轉發 `PreToolUse`，其他事件之後再做。
- 關掉 `jev-router` 不會替使用者解除安裝 plugin。

## 沒有驗證的項目

- S4 的 live：已跑 1 次（見下方）。
- 相容檔沒有在真實的 Claude session 驗證，只以假腳本與真實 guard 的 unit test 驗證。
- plugin cache 的實際目錄結構。
- agy 與 Grok 的實機 `--without dispatch-guard` 流程。

## CI

PR #4 在 `d8af852` 全部通過。

## S4 live

S4 live：2026-10-15 以 `install/claude_live_probe.py --case plugin-split` 跑 1 次
（經 `agent-secret run claude-eval`，haiku，約 0.004 美元）。
隔離設定中 `shoal@shoal` 與 `shoal-dispatch-guard@shoal` 皆為 3.8.1 且啟用；
main 直接改 README 被 guard 擋下（規則 STRICT），README 未變；
`shoal:executor`、`shoal:applier` 等 10 個 role 都列出；
暫存目錄已移除。結果檔記錄在 scratchpad，不入 repo。
另記：`agent-secret` 不允許以 `python3` 當指令，
必須直接執行腳本路徑。
