# code-restructure：TESTS（EARS）

編號前綴 S- 以區別 TASKS.md 的任務編號；S1.x 對應 P1 等。「SHALL」為驗收條件。

## 通則

- S0.1 WHEN 任一 phase 的變更完成，THE SYSTEM SHALL 通過 `python3 -m unittest discover -s tests`。
- S0.2 WHEN 任一 phase 的變更完成，THE SYSTEM SHALL 讓 `python3 tools/render.py --check` 對 claude、codex、agy、grok、opencode 與 claude-plugin 全部通過。
- S0.3 WHEN 任一 phase 的變更完成，THE SYSTEM SHALL 讓 `tests/fixtures/guard_vectors.json` 的每個 vector 結果與重構前相同。
- S0.4 WHEN P1 前後各量測一次 hook 延遲，THE SYSTEM SHALL 使 `run.sh` 入口的 p50 增加不超過 1ms、p95 增加不超過 3ms（O7 可調整）。
- S0.5 THE SYSTEM SHALL NOT 在 P4、P5 修改任何 golden 檔；P1 只允許更新 guard 副本與其 `.sha256`（內容隨 guard 原始碼改變）。

## Guard（P1）

- S1.1 WHEN host 表被讀取，THE SYSTEM SHALL 對每個既有 host 回傳與重構前相同的 default mode、role-aware、stop、conversation 等屬性（逐 host 比對舊 frozenset 的成員）。
- S1.2 WHEN `tests/fixtures/adapter_golden.json` 的每個 payload 丟給新的 `adapt_*`（含 `adapt_agy`），THE SYSTEM SHALL assertEqual 回傳 golden 的完整 dict（含 None）；golden 在 P1 不得編輯，且 golden 測試於 main 為綠、改動任一 tool-name 對照後轉紅。
- S1.3 WHEN `_Guard._locked` 建立新 state，THE SYSTEM SHALL 寫出與重構前位元組相同的 JSON（key 與順序）。
- S1.4 IF 目標檔是 symlink，THEN `_open_private` SHALL 拒絕開啟、`_open_readable` SHALL 維持原行為（兩者不合併；symlink 的 modules.json 仍使 chain 依原行為處理，不 fail-open、不改使用者檔案權限）。
- S1.5 WHEN claude `Workflow` 事件帶任何 tool_input（含 `subagent_type:"executor"`），THE SYSTEM SHALL 使 `dispatched_role` 為 None。
- S1.6 WHEN 輸入為 claude Bash `run_in_background=True`、Post/PostFailure 背景 Bash、codex Bash/Post 非 str command、grok `run_terminal_command` 非 str、grok stop（reason != end_turn 或來自 subagent），THE SYSTEM SHALL 產生與 adapter golden 相同的結果（background_shell 先於 shell；stop 為 None）；這些案例須明列於 golden 輸入。
- S1.7 WHEN 各 host 送入主 session payload，THE SYSTEM SHALL 使 `is_subagent` 為 False；SubagentStart 的 tid 於 claude 為 prompt_id、codex/grok 為 None。
- S1.8 WHEN 輸入為未知 tool，THE SYSTEM SHALL 回傳 kind `other`；edit-name 集合 SHALL 等於凍結 literal（claude 4、grok 6），grok path-key 順序為 file_path, path, target_file, filePath；prompt 文字 SHALL NOT 出現在 event 或 log。
- S1.9 THE SYSTEM SHALL 使每個舊 host 集合名稱等於 P0 凍結的 literal，`set(ADAPTERS)` 等於 {claude, codex, grok, agy}，且 `HOST_DEFAULT_MODE.get("opencode")` 為 None。
- S1.10 WHEN prior state 為 {"dispatched":"yes","pending":3,"role_running":true,"changed":false} 且發生 prompt boundary，THE SYSTEM SHALL 使 dispatched 為 False、pending 為 0、無 role_running，且 JSON key 順序等於現行 golden。
- S1.11 WHERE S1.5、S1.6、S1.9 屬 security 回歸，THE SYSTEM SHALL 在 P0 於現有 code 先全綠，才允許 P1 code 變更。

## install.py（P4）

- S4.1 WHEN `install()` 對同一組輸入（含 dry-run、`--no-guard`、`--no-autoroute`、舊 state 升級）執行，THE SYSTEM SHALL 產生相同的寫入集合、備份路徑、state 與輸出文字。
- S4.2 IF 任一步驟失敗，THEN THE SYSTEM SHALL 與重構前一樣不留下半套寫入，且 `InstallAbort` 訊息逐字相同。
- S4.3 WHEN `_validate_committed_state` 對 T0.4 列出的每個壞 state 執行，THE SYSTEM SHALL 以相同順序、相同訊息拒絕。
- S4.4 THE SYSTEM SHALL 使 `install/install.py` 內沒有超過 120 行的函式（以 AST 腳本檢查，作為報告而非 CI 門檻）。

## render.py（P5）

- S5.1 WHEN 五個 host 重新 render，THE SYSTEM SHALL 產生與 golden 位元組相同的檔案集合。
- S5.2 IF binding 違反既有規則（read-only role 含寫入工具、agy 設 effort、模型不在白名單等），THEN THE SYSTEM SHALL 以與重構前相同的 `RenderError` 訊息拒絕（現有負向測試保留）。
- S5.3 WHERE 外部程式碼仍呼叫 `render.validate_*` / `render.render_*`，THE SYSTEM SHALL 繼續提供同名函式。

## 會被牽動的測試

見 SPEC.md「會被牽動的測試」；重寫時保留每個測試原有的斷言意圖，不以刪除取代。
