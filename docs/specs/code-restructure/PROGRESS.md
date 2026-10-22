# code-restructure：PROGRESS

## P0（2026-10-19）

完成 T0.1、T0.2、T0.3、T0.4（部分，見下）、T0.6、T0.7（issue #26）。

### Hook 延遲 baseline（T0.2）

在 main 94d914f 的 code
上，`cd ~/shoal-live-360 && python3 tests/bench_hook_latency.py -n 200`，入口為
`plugins/claude-guard/hooks/run.sh shoal_guard.py --host claude --plugin`，每個
event 200 次（先暖一次 bytecode cache），state/cache 指向 throwaway 目錄。總耗時約 42 秒。

| event | p50 (ms) | p95 (ms) |
| --- | --- | --- |
| SessionStart | 68.70 | 133.26 |
| PreToolUse(Bash) | 54.72 | 87.32 |
| PreToolUse(Edit) | 56.60 | 110.73 |

觀察：單次量測的雜訊（同一 event 兩次 n=5 到 n=200 的 p50 差 10 到 15ms，p95 差數十 ms）遠大於 S0.4 的容許值
（p50 +1ms、p95 +3ms）。P1 前後比較時要在同一時段連跑多次取中位數，或把 O7 的門檻放寬；單次對照不可靠。

### T0.3 adapter golden

`tests/fixtures/adapter_golden.json`：157 筆（claude 51、codex 30、grok 38、agy 38，含
None 結果與 S1.5、S1.6 案例），inputs 與完整輸出都存在檔內。`guard_vectors.json` 是已 normalize 的
event，不是 adapter 的輸入，因此不當作 adapter payload；它由既有的 vector replay 負責（S0.3）。
測試：`tests/test_adapter_golden.py`（P0 `0a0ff8a` 只 commit fixture，測試檔於 P1
`700cdd0` 才 commit；verifier 以 `0a0ff8a` 的 guard 跑這些 P1 測試類別，ran 13、fail 0 全綠，因此
S1.11 實質成立）。敏感度：在 scratch 副本把 `adapt_claude` 的 edit 工具集合拿掉 `MultiEdit`，以
throwaway runner 取代 `shoal_guard` 模組後，golden 測試轉紅
（`pre_MultiEdit`、`pre_MultiEdit_nopath` 兩筆 FAIL）。

### T0.4 InstallAbort

`install/install.py` 有 175 個 `InstallAbort` 呼叫點、136 種訊息模板，凍結於
`tests/fixtures/install_abort_messages.json`
（`tests/test_install_abort_messages.py` 比對，P4 不得增刪改字）。逐字行為測試涵蓋
`merge_config_text`（13 種）、`merge_instruction_text`、`_validate_committed_state`
前兩道、`_assert_agents_root`、`_capture_policy_identity` 前四道。其餘約 100 種
（`_validate_committed_state` 深層欄位檢查、rollback/backup race、post-write
fingerprint）尚無逐字行為測試，只有模板被凍結；P4 的 T4.2 拆 `_validate_committed_state` 前要補，S4.3
目前只部分可驗。

## P1（2026-10-19）

完成 T1.1–T1.5a；T1.6 的 dist 副本、`.sha256`、共同驗收與延遲已做，fresh `verifier` 已於 2026-10-21
跑過，結果 CONFIRMED（見下節 Fresh verifier）。`hooks/shoal_guard.py` 3181 -> 3080 行。

### Hook 延遲（O7）

`cd ~/shoal-live-360 && python3 tests/bench_hook_latency.py -n 40 --json`，P1 前
（0a0ff8a）與 P1 後各連跑 3 次，單位 ms，格式 p50/p95。

| run | SessionStart | PreToolUse(Bash) | PreToolUse(Edit) |
| --- | --- | --- | --- |
| 前 1 | 96.68/571.81 | 89.87/128.59 | 93.65/170.20 |
| 前 2 | 66.70/94.19 | 77.74/105.54 | 92.94/141.44 |
| 前 3 | 83.17/440.54 | 84.35/124.91 | 83.24/155.07 |
| 後 1 | 44.54/71.96 | 43.09/60.98 | 46.49/96.14 |
| 後 2 | 51.46/134.97 | 43.00/66.43 | 39.43/46.25 |
| 後 3 | 39.54/97.17 | 50.58/90.07 | 78.73/128.54 |

p50 中位數：PreToolUse(Bash) 84.35 -> 43.09（門檻 +5ms 內，通過）；SessionStart 83.17 ->
44.54；PreToolUse(Edit) 92.94 -> 46.49。前後差距是機器負載（P1 前那組與其他 worktree 的工作同時跑），不是
code 變快；結論只能是「沒有變慢的證據」。

### 驗收

- `render --check`：claude、codex、grok、agy、opencode、claude-plugin 全 OK。
- 全套 unittest：1733 tests，1
  fail，`test_claude_live_probe.PluginSplitTests.test_install_failure_runs_nothing_live`。原因是
  worktree 路徑 `wt-guard` 含 `guard`，測試的假 host 以 `"guard" in argv[-1]`
  判斷失敗，`marketplace add <ROOT>` 被誤判。同一份 diff 套在路徑不含 `guard` 的 worktree，該模組 103
  tests 全 OK；其餘模組逐一跑過全 OK。

### Fresh verifier（2026-10-21）

HEAD `71c4382`；golden 與 guard_vectors 自 `0a0ff8a` 後未變。`test_adapter_golden` 18
tests OK。敏感度：移除 claude `MultiEdit`、codex `apply_patch`、grok
`run_terminal_command` 分別使 golden 轉紅（2 / 4 / 2 fails）。

- S1.3/S1.10：舊、新 guard 對 14 個 claude event × 3 種前置狀態共 42 步執行 `run()`，stdout 與
  state bytes 差異皆 0。
- S1.4：`_open_private` / `_open_readable` 文字與 `0a0ff8a` 相同；symlink probe
  行為一致，victim 檔與 0o644 皆未變動。
- S1.5：7 個 Workflow input -> dispatch None；4 host adapter differential fuzz
  60000 payloads，mismatches 0；S1.1/S1.9 host table 一致。
- dist sha256 `28696065…1fa6` 與所有副本一致；`render --check` 6 hosts OK。
- 全套 `python3 -m unittest discover -s tests`：1766 tests OK（skipped=1）。先前的
  `test_install_failure_runs_nothing_live` 失敗已消失，搬到 `~/Project/Active/shoal`
  後路徑不再含 "guard"，確認為路徑成因。
- 未重新量測：S0.4 hook latency。

## 2026-10-19

- P1：`hooks/shoal_guard.py` 3181 -> 3080 行（-101）。
- P4：`install/install.py` 2773 -> 3067 行（+294）；`install()` 692 -> 70
  行、`_validate_committed_state` 404 -> 44 行，以行數換可讀性。
- P5 不做：`render.py` 查表化 +38 行，無可讀性收益（Miyago 決定丟掉）。
