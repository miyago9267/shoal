# local-role-model-overlay：PROGRESS

## 2026-11-14

- 建立 spec 草稿：SPEC.md、TASKS.md、TESTS.md。依據 CVP Help Center 與
  Fable/Mythos 5.2 發布頁的查證結果。
- Miyago 核准，plan-critic 待 shoal plugin 載入的 session 補跑。
- T0.1 完成：`claude -p --agents` 以 haiku 為 main、probe agent 指定 model。
  `claude-mythos-5-2` 實際執行（modelUsage 含 `claude-mythos-5-2`，回覆
  PROBE-OK，含 main 共 $0.043）。不存在的 `claude-mythos-9-9` 改用 Sonnet 5.5
  並附 fallback 提示，exit 0。據此在 SPEC 加入 D6（fallback 降級處理）。
- T0.2 完成：同一份 security-reviewer 定義、effort high、同一個 brief 審 `hooks/shoal_guard.py`。
  Mythos 5.2：$2.65、381 秒、34k output tokens。Opus 5.5：$1.01、243 秒、19k output tokens。
  兩者都找到 modules.json 無完整性檢查、state 非 atomic 寫入、G5 parser 盲點。
  Mythos 獨有：超過 256 KiB payload 放行、subagent 背景 Bash 繞過 E1、`projects/` 豁免可寫 memory。
  Opus 獨有：chmod guard dir 使 state 失效、relay 檔可偽造、agy conversation 誤判。
  單一樣本，finding 未逐條驗證；O1 結論：每次約 $2.7，security review 頻率低，維持 effort high。
- T0.3 完成：`~/Project/Active/shoal` symlink 到 Forks 下的 checkout，`--update`
  dry-run 全部 up-to-date。
- T1.1–T1.4 完成：`tools/shoal_update.py` 加入 overlay 讀取、驗證與套用；
  `tests/test_local_overlay.py` 8 個測試先紅後綠；整套 1874 tests OK，六個 host `render
  --check` 通過。
- T1.4a 移出 P1：policy 文字變更觸發 prompt document lock，另開 slice。
- T1.5 完成：Mythos 5.2 審 diff（$1.18）。確認成立：role 名稱可 path traversal 寫出 stage 外
  （dry-run 也會寫）、`./security-reviewer` 繞過 flagged 檢查、`fable[1m]` / 完整 ID 繞過、
  regex 允許改變 YAML 型別的值、role 進錯誤訊息可偽造狀態行；假設：overlay 改變時 plugin cache
  不刷新。全部採納，寫入 D3、D7。
- T1.6 完成：fresh opus verifier（$0.35）CONFIRMED，advisory 與 T1.5 的 F1、F3 相同。
- F4 實測（隔離 CLAUDE_CONFIG_DIR）：版本相同時 `claude plugin update` 不刷新 cache；
  uninstall 再 install 兩個方向都正確。加入 D7。
- 修正後 overlay 測試 14 個、整套 1880 tests OK，六個 host `render --check` 通過。修正未再送 review，
  以 T2.1 實機安裝作為驗證。
- T2.1 完成：寫入 `~/.config/shoal/claude.local.toml` 後 `--update --apply`，core 與
  guard plugin
  reinstall，cache 的 `security-reviewer.md` 為 `model: claude-mythos-5-2`，`security-executor`
  仍是 opus；重跑全部 up-to-date，不再 reinstall。headless 派 `shoal:security-reviewer`，
  modelUsage 含 `claude-mythos-5-2`（S2.1）。
- T2.2 阻塞：PMS 不在這台 Linux 機器上，需在 Mac 執行。
- P3：Miyago 決定 Mythos 進 shoal 預設，security 退回 opus、plan-critic 退回 fable。實作
  `[probe.roles]` 探測；實機在沒有 overlay 下由探測升級兩個 role。
- T3.3 審查（Mythos，$1.85）6 個 finding：F2–F6 已修（D11–D13）；F3 後半（reinstall 補裝）與
  F1（D6 進 policy）列為 T3.5、T3.6。
- T3.5 完成：reinstall 途中 install 失敗時，swap 還原目錄後用還原的 marketplace 補裝已 uninstall
  的 plugin，輸出 `restored previous install`。測試用 fake CLI 的 `fail_match` 先紅後綠。
- T3.6 阻塞：policy 文件都在 lock 上限，需要 lock renewal 與升版（release），等 Miyago 決定。
