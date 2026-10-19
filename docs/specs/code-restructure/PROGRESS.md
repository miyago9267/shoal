# code-restructure：PROGRESS

## P0（2026-10-19）

完成 T0.1、T0.2、T0.3、T0.4（部分，見下）、T0.6、T0.7（issue #26）。

### Hook 延遲 baseline（T0.2）

在 main 94d914f 的 code 上，`cd ~/shoal-live-360 && python3 tests/bench_hook_latency.py -n 200`，入口為 `plugins/claude-guard/hooks/run.sh shoal_guard.py --host claude --plugin`，每個 event 200 次（先暖一次 bytecode cache），state/cache 指向 throwaway 目錄。總耗時約 42 秒。

| event | p50 (ms) | p95 (ms) |
| --- | --- | --- |
| SessionStart | 68.70 | 133.26 |
| PreToolUse(Bash) | 54.72 | 87.32 |
| PreToolUse(Edit) | 56.60 | 110.73 |

觀察：單次量測的雜訊（同一 event 兩次 n=5 到 n=200 的 p50 差 10 到 15ms，p95 差數十 ms）遠大於 S0.4 的容許值（p50 +1ms、p95 +3ms）。P1 前後比較時要在同一時段連跑多次取中位數，或把 O7 的門檻放寬；單次對照不可靠。

### T0.3 adapter golden

`tests/fixtures/adapter_golden.json`：157 筆（claude 51、codex 30、grok 38、agy 38，含 None 結果與 S1.5、S1.6 案例），inputs 與完整輸出都存在檔內。`guard_vectors.json` 是已 normalize 的 event，不是 adapter 的輸入，因此不當作 adapter payload；它由既有的 vector replay 負責（S0.3）。測試：`tests/test_adapter_golden.py`。敏感度：在 scratch 副本把 `adapt_claude` 的 edit 工具集合拿掉 `MultiEdit`，以 throwaway runner 取代 `shoal_guard` 模組後，golden 測試轉紅（`pre_MultiEdit`、`pre_MultiEdit_nopath` 兩筆 FAIL）。

### T0.4 InstallAbort

`install/install.py` 有 175 個 `InstallAbort` 呼叫點、136 種訊息模板，凍結於 `tests/fixtures/install_abort_messages.json`（`tests/test_install_abort_messages.py` 比對，P4 不得增刪改字）。逐字行為測試涵蓋 `merge_config_text`（13 種）、`merge_instruction_text`、`_validate_committed_state` 前兩道、`_assert_agents_root`、`_capture_policy_identity` 前四道。其餘約 100 種（`_validate_committed_state` 深層欄位檢查、rollback/backup race、post-write fingerprint）尚無逐字行為測試，只有模板被凍結；P4 的 T4.2 拆 `_validate_committed_state` 前要補，S4.3 目前只部分可驗。
