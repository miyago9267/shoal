# code-restructure：TESTS（EARS）

編號對應 TASKS.md。「SHALL」為驗收條件。

## 通則

- T0.1 WHEN 任一 phase 的變更完成，THE SYSTEM SHALL 通過 `python3 -m unittest discover -s tests`。
- T0.2 WHEN 任一 phase 的變更完成，THE SYSTEM SHALL 讓 `python3 tools/render.py --check` 對 claude、codex、agy、grok、opencode 與 claude-plugin 全部通過。
- T0.3 WHEN 任一 phase 的變更完成，THE SYSTEM SHALL 讓 `tests/fixtures/guard_vectors.json` 的每個 vector 結果與重構前相同。
- T0.4 WHEN 重構前後各量測一次 hook 延遲，THE SYSTEM SHALL 使 `run.sh` 入口的 p50 增加不超過 1ms、p95 增加不超過 3ms（O7 可調整）。
- T0.5 THE SYSTEM SHALL NOT 在 P1、P3、P4、P5 修改任何 golden 檔；P2 只允許新增 guard bundle manifest 並移除舊 `.sha256`。

## Guard（P1、P2）

- T1.1 WHEN host 表被讀取，THE SYSTEM SHALL 對每個既有 host 回傳與重構前相同的 default mode、role-aware、stop、conversation 等屬性（逐 host 比對舊 frozenset 的成員）。
- T1.2 WHEN 同一個 payload 分別丟給重構前後的 `adapt_claude`、`adapt_codex`、`adapt_grok`，THE SYSTEM SHALL 回傳相等的 normalized event（以所有 `tests/fixtures/*_shapes.json` 與 vectors 為輸入）。
- T1.3 WHEN `_Guard._locked` 建立新 state，THE SYSTEM SHALL 寫出與重構前位元組相同的 JSON（key 與順序）。
- T1.4 IF 目標檔是 symlink，THEN `_open_nofollow` SHALL 拒絕開啟，行為與 `_open_private` / `_open_readable` 原本相同。
- T1.5 WHEN guard 以 `python3 -I hooks/shoal_guard.py --host claude`、或 cache 目錄唯讀的環境啟動，THE SYSTEM SHALL 正常處理事件。
- T1.6 WHEN `import shoal_guard` 在 `hooks/` 於 `sys.path` 的情況下執行，THE SYSTEM SHALL 解析到 package（`__file__` 以 `__init__.py` 結尾）且 `shoal_guard.main` 是 `shoal_guard.cli.main`；WHEN `python3 hooks/shoal_guard.py` 直接執行，THE SYSTEM SHALL 與 `run.sh` 入口產生相同輸出。
- T1.7 WHILE 作業系統是 Windows，THE SYSTEM SHALL 在 import 重模組之前結束並維持 no-op。
- T1.8 THE SYSTEM SHALL 讓 `hooks/shoal_guard/*.py` 每個檔案通過 `ast.parse(feature_version=(3, 9))` 並含 `from __future__ import annotations`（`test_py39_compat` 遞迴涵蓋）。
- T1.9 WHEN 單一事件（例如 `PreToolUse(Edit)`）被處理，THE SYSTEM SHALL NOT 載入 `chain.py`（沒有 chain member）與 `shell.py`（非 Bash 事件），若採用 lazy import（延遲驗收需要時）。

## Guard bundle 發佈（P2）

- T2.1 WHEN `bundle_digest` 對同一組檔案呼叫兩次，THE SYSTEM SHALL 回傳相同值；WHEN 任一模組內容或檔名改變，THE SYSTEM SHALL 回傳不同值。
- T2.2 WHEN render 產生 claude-guard plugin 與 grok dist，THE SYSTEM SHALL 在兩處各輸出與 `hooks/` 相同的 bundle（入口加所有模組，逐位元組）。
- T2.3 IF dist 內有 bundle 之外多出的檔案（例如殘留舊模組），THEN `render --check` SHALL 失敗，`--write` SHALL 移除它。
- T2.4 IF `install_grok` 讀到的 dist bundle 與同 commit 的 `hooks/` bundle 有任一檔不同或檔集合不同，THEN THE SYSTEM SHALL 中止並提示 `render --write`。
- T2.5 WHEN `shoal_update verify guard` 比對已安裝 bundle，THE SYSTEM SHALL 在任一檔不同時回報 `failed` 並列出不同的相對路徑。
- T2.6 WHEN `install_hooks.py --host claude|agy|codex` 在暫存 HOME 安裝，THE SYSTEM SHALL 寫入入口與整個 package、command 字串與重構前相同、`OWNED` regex 仍能辨識。
- T2.7 WHEN 安裝過程在寫入 package 後、替換入口前失敗，THE SYSTEM SHALL 保留舊入口與舊 package 可用（hook 不會讀到半套）。
- T2.8 WHEN `install.py` 的 state 記錄舊單檔 guard fingerprint 且已安裝檔等於該 fingerprint，THE SYSTEM SHALL 升級成 bundle 並記錄 `bundle_digest`，不報 `installed_hook_drift`。
- T2.9 IF 已安裝的 guard 與 proven fingerprint 不符，THEN THE SYSTEM SHALL 與重構前一樣報 `installed_hook_drift` 並拒絕覆蓋。
- T2.10 WHEN 以 `--no-guard` 或 uninstall 移除，THE SYSTEM SHALL 只在 bundle 符合 proven fingerprint 時移除入口與整個 package 目錄。
- T2.11 WHEN 在暫存 HOME 完整跑「安裝 → 送入一個 PreToolUse payload 取得 deny → 解除安裝」，THE SYSTEM SHALL 與重構前結果相同（Codex、Claude settings、agy 各一次）。

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
