# 完成檢查的實測（shared-rules S3）

日期 2026-10-13，shoal 3.4.0（941c90b）。規則：回合有改檔、之後沒有 `verifier` / `watcher`、
main 也沒跑前景 shell 時，guard 擋下結束一次（訊息開頭 `Shoal completion check:`），第二次不擋。
規格見 `docs/specs/shared-rules/SPEC.md` B2-B4、D6。

## 方法

- 每案一個拋棄式 git repo（`~/shoal-stop/<case>/`：README.md、calc.py、test_calc.py），不在系統暫存路徑。
- Claude：`claude -p <prompt> --model opus --permission-mode acceptEdits
  --output-format stream-json --verbose --max-budget-usd 0.8`，
  真實設定（plugin `shoal@shoal` 3.4.0）。
- Codex（codex-cli 0.160.1）：`codex exec --json --dangerously-bypass-hook-trust --skip-git-repo-check
  -s workspace-write <prompt> < /dev/null`，預設 model（沒有被拒絕）。
- 證據：`guard.jsonl` 每次新增的行，加上 stream 本身。題目在 `prompts/`，逐次紀錄在 `results.json`。
- 4 次 headless（上限 6，無備用）；Claude 兩次共 USD 0.97，Codex 不回報金額。

## 結果

| 案例 | 符合預期 | 決定性 guard 記錄 | 擋了幾次／之後 |
| --- | --- | --- | --- |
| CL-nocheck | 是 | Edit `direct` allow；`STOP` block | 1／明寫「未經驗證」，沒跑檢查 |
| CL-check | 是 | Agent `dispatch_pending`；`dispatch_started` | 0／applier 改完後 main 跑 `unittest`（OK） |
| CX-nocheck | 是 | `apply_patch` `direct` allow；`STOP` block | 1／明寫「尚未驗證」，沒跑檢查 |
| CX-check | 是 | `apply_patch` R1 deny；`collaborationspawn_agent` `dispatch` allow | 0／role 改完後 main 跑 `unittest`（OK） |

## 有證據的部分

- Claude 接受 `{"decision":"block","reason":...}`：stream 中出現
  `Stop hook feedback:` 加完整訊息，之後多一輪回應；第二次結束沒有新的 guard 行，符合「只擋一次」。
- Codex 擋一次後會續跑；訊息本身不在 `--json` 輸出，只由模型的後續回覆引用。
- 有檢查時（兩個 `-check` 案例）都沒有 `STOP` 行。

## 沒有證據或有限制

- 每案只跑一次；沒測只改文件、僅有 verifier 或 watcher、或被擋後仍直接結束的情況。
- Codex 以 `--dangerously-bypass-hook-trust` 執行，使用者核准後的行為沒測。
- CX-nocheck 的同一次結束還觸發另一個 Stop hook（`ROUTE_ESCALATION_REQUIRED`），續跑不能單獨歸因於本 guard；
  訊息被 Codex 傳到模型的證據是模型引用了 `Shoal completion check`。
- CX-check 的 role 名稱沒出現在 stream 與 guard 行；CX-check 在派工前先被 R1 擋過一次 `apply_patch`。
- CL-check 的 Claude 前兩個 Bash 在改檔之前，不影響判斷；`__pycache__/` 只是測試產物。
- Claude 的 `prompt_id` 對應（Stop 與 UserPromptSubmit）由 CL-nocheck 的成功間接支持，沒有單獨比對。
