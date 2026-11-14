# local-role-model-overlay：TASKS

每完成一項就更新；狀態 `[ ]` 未做、`[x]` 完成。決策與範圍見 SPEC.md。

## P0 實測

- [x] T0.1 用一個暫時的 user agent（`model: claude-mythos-5-2`）派一次簡單任務，
  從 transcript 確認實際使用的 model ID；再用不存在的 ID 試一次，記錄 Claude Code
  是報錯還是 fallback（O2）。
- [x] T0.2 用同一個 agent 跑一次 Defense 範圍的小型 review，記錄 token 與額度消耗（O1）。
- [x] T0.3 修正本機 `SHOAL_ROOT`，讓 `agent-stack-auto-update.sh` 找得到 checkout。

## P1 Claude host 覆寫

- [x] T1.1 先寫失敗測試：`tests/test_local_overlay.py` 涵蓋 TESTS.md 的 S1.x。
- [x] T1.2 在 `tools/shoal_update.py` 加讀取與套用覆寫的函式（D1–D3），接在
  `update_claude()` 與 `verify()` 的 export 之後（D2）。
- [x] T1.3 `--update` 輸出覆寫狀態（D5）。
- [x] T1.4 `docs/model-catalog.md` 補一節「本機覆寫」。
- [ ] T1.4a（移出 P1）D6 寫進 policy 會觸發 prompt document lock（版本升級、legacy src、lock 續期），另開 slice；P1 先記在 `docs/model-catalog.md`。
- [x] T1.5 `security-reviewer` 審 D2–D3 的實作（risk trigger：security role 與 installer）。
- [x] T1.6 fresh `verifier` 驗 S0.x、S1.x。

## P2 首次使用

- [x] T2.1 寫入本機覆寫檔，跑 `shoal_install.py --update --apply`，確認
  `shoal:security-reviewer` 使用 Mythos。
- [ ] T2.2 在 PMS repo 派 `security-reviewer` 做 Defense 範圍的審查（攻擊紀錄分類、
  auth / 輸入驗證弱點、偵測規則），結果在 PMS repo 另開工作處理。
