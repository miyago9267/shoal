# agy（Gemini）安裝

agents、skills、rules 目前是指向 `hosts/agy/dist` 的 symlink，由 dotfile 的 `setup_gemini.sh`
建立；沒有 dotfile 的使用者只會裝到 dispatch guard hook，沒有 role。G2 修好後，安裝入口會自行
建立這些檔案（symlink 不可用時改為複製），屆時此段改寫。

## Gemini/agy 的 dispatch guard

共用說明（Claude Code 與 Gemini/agy）見 [dispatch guard](../guard.md)。

```bash
python3 tools/install_hooks.py --host agy --apply
```

- `--host agy` 改 `~/.gemini/config/hooks.json`（`--home` 指 `~/.gemini`）：新增具名
  群組 `shoal-dispatch-guard`（3.8.0 之前叫 `shoal-guard`，重跑 `--apply` 會原地改名），含
  `SessionStart`、`PreInvocation`、`PreToolUse`（matcher `*`）與 `Stop`；
  每個 command 結尾帶 `--event <名稱>`，因為 agy 的 payload 不含事件名稱（舊安裝重跑 `--apply`
  會原地補上；沒有 `--event` 的舊註冊照舊用 payload 形狀推斷）。agy 預設 enforce
  （`tests/fixtures/agy_guard_event_shapes.json`，agy 1.3.4，2026-10-13：deny 對
  main 與 subagent 的
  `write_to_file` 都被遵守）。subagent 跑在自己的 conversation，payload 不帶 role 或 parent，
  guard 靠事件順序推斷並記在 `state/agy.conversations.json`（最後 64 筆）：這是推斷，不是事實。
  `invoke_subagent` 的 PreToolUse 為 `Subagents[]` 每一項記一筆待啟動；新 conversation 的
  `SessionStart` 認領最舊的一筆（優先同 workspace）：role 一致才知道 role，只有存取類別一致就用類別，
  混合派工（例如 applier 加 scout）類別為 unknown，此時 E1 不擋，只記 `would_deny_unknown_class`。
  同一 workspace 內兩個 agy session 同時派工可能被混淆。agy 的 `PreInvocation` 不帶使用者的 prompt，
  所以沒有 `#direct`；出口只有：派 write role 並等它啟動、`SHOAL_GUARD_WRITE_AGENTS`、`SHOAL_GUARD_DIRECT=1`。
  agy 不檢查 leaf 不得再派工（只記 log）；完成檢查接在 `Stop`，預設 shadow（只記 `would_block`），
  `SHOAL_GUARD_STOP=enforce` 才擋，擋的輸出格式尚未 live 驗證。
  agy 上 main 的解鎖只維持到 main conversation 的下一個 `PreInvocation` 且
  `invocationNum == 0`
  （程式只在這個條件重置回合，不是每次模型呼叫；`adapt_agy`）。2026-10-14 live 觀察到：
  subagent 回報時 agy 在 main conversation 補一則 `system_message`，緊接著 guard log 出現一筆
  main 的 `turn_boundary`（之前沒有 main 的新 `SessionStart`），所以 role 回來之後 main 再改檔
  又被擋。由此推得：subagent 回報會讓 main 開始新一輪 invocation，編號從 0 起算。raw stream
  不含 `invocationNum`，這是由「guard 只在 0 時記 `turn_boundary`」推得，沒有直接看到該欄位。
  實際效果：解鎖撐不到 subagent 回報之後；請把改檔派給該 role。
