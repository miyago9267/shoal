# code-restructure：TESTS（EARS）

編號對應 TASKS.md。「SHALL」為驗收條件。

## 通則

- T0.1 WHEN 任一 phase 的變更完成，THE SYSTEM SHALL 通過 `python3 -m unittest discover -s tests`。
- T0.2 WHEN 任一 phase 的變更完成，THE SYSTEM SHALL 讓 `python3 tools/render.py --check` 對 claude、codex、agy、grok、opencode 與 claude-plugin 全部通過。
- T0.3 WHEN 任一 phase 的變更完成，THE SYSTEM SHALL 讓 `tests/fixtures/guard_vectors.json` 的每個 vector 結果與重構前相同。
- T0.4 WHEN P1 前後各量測一次 hook 延遲，THE SYSTEM SHALL 使 `run.sh` 入口的 p50 增加不超過 1ms、p95 增加不超過 3ms（O7 可調整）。
- T0.5 THE SYSTEM SHALL NOT 在 P3、P4、P5 修改任何 golden 檔；P1 只允許更新 guard 副本與其 `.sha256`（內容隨 guard 原始碼改變）。

## Guard（P1）

- T1.1 WHEN host 表被讀取，THE SYSTEM SHALL 對每個既有 host 回傳與重構前相同的 default mode、role-aware、stop、conversation 等屬性（逐 host 比對舊 frozenset 的成員）。
- T1.2 WHEN 同一個 payload 分別丟給重構前後的 `adapt_claude`、`adapt_codex`、`adapt_grok`，THE SYSTEM SHALL 回傳相等的 normalized event（以所有 `tests/fixtures/*_shapes.json` 與 vectors 為輸入）。
- T1.3 WHEN `_Guard._locked` 建立新 state，THE SYSTEM SHALL 寫出與重構前位元組相同的 JSON（key 與順序）。
- T1.4 IF 目標檔是 symlink，THEN `_open_nofollow` SHALL 拒絕開啟，行為與 `_open_private` / `_open_readable` 原本相同。

## Hook 登記（P3）

- T3.1 WHEN 對同一份既有 `settings.json` / agy `hooks.json` 執行 apply 與 remove，THE SYSTEM SHALL 產生與重構前位元組相同的結果（含非 shoal handler 與 key 順序不變）。
- T3.2 WHEN Codex 經 `install()` 或經 `install_hooks.py --host codex` 寫入 `hooks.json`，THE SYSTEM SHALL 產生相同位元組（O3 的對照結果決定基準；差異存在時停下回報）。
- T3.3 THE SYSTEM SHALL 讓 `install_hooks.py` 不再定義任何 `hooks` 事件到 group 的對照（登記只在 `hook_registration.py`），以 grep 檢查固定。
- T3.4 WHEN `sync_global` 的 `--json` plan 在重構前後對同一組輸入執行，THE SYSTEM SHALL 回傳相等的 plan。

## install.py（P4）

- T4.1 WHEN `install()` 對同一組輸入（含 dry-run、`--no-guard`、`--no-autoroute`、舊 state 升級）執行，THE SYSTEM SHALL 產生相同的寫入集合、備份路徑、state 與輸出文字。
- T4.2 IF 任一步驟失敗，THEN THE SYSTEM SHALL 與重構前一樣不留下半套寫入，且 `InstallAbort` 訊息逐字相同。
- T4.3 WHEN `_validate_committed_state` 對 T0.4 列出的每個壞 state 執行，THE SYSTEM SHALL 以相同順序、相同訊息拒絕。
- T4.4 THE SYSTEM SHALL 使 `install/install.py` 內沒有超過 120 行的函式（以 AST 腳本檢查，作為報告而非 CI 門檻）。

## render.py（P5）

- T5.1 WHEN 五個 host 重新 render，THE SYSTEM SHALL 產生與 golden 位元組相同的檔案集合。
- T5.2 IF binding 違反既有規則（read-only role 含寫入工具、agy 設 effort、模型不在白名單等），THEN THE SYSTEM SHALL 以與重構前相同的 `RenderError` 訊息拒絕（現有負向測試保留）。
- T5.3 WHERE 外部程式碼仍呼叫 `render.validate_*` / `render.render_*`，THE SYSTEM SHALL 繼續提供同名函式。

## 會被牽動的測試

見 SPEC.md「會被牽動的測試」；重寫時保留每個測試原有的斷言意圖，不以刪除取代。
