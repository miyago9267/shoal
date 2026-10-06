# generic-shoal 進度

## F2 agy subagent 辨識實測（2026-10-06，完成：維持 shadow）

agy 1.2.16，main 建一個檔案後以 `invoke_subagent` 派 `mech-executor`。probe 只記錄
路徑形狀（home 換成 `~`、UUID 換成 `<uuid>`）與欄位名稱。

| conversation | `initialNumSteps`（第一次 invocation） | `transcriptPath` 形狀 | `artifactDirectoryPath` 形狀 | 欄位集合 |
|---|---|---|---|---|
| main | 1 | `~/.gemini/antigravity-cli/brain/<uuid>/.system_generated/logs/transcript_full.jsonl` | `~/.gemini/antigravity-cli/brain/<uuid>` | 相同 |
| subagent | 0 | 同上 | 同上 | 相同 |

- 單一 payload 內沒有可區分 main 與 subagent 的正向證據：兩者的路徑形狀與欄位集合完全相同。
- 唯一差異是 conversation 第一次 invocation 的 `initialNumSteps`（main 1、subagent 0），三筆
  樣本（含 dispatch-enforcement E0 的兩筆）一致，但工具事件不帶這個欄位，且只在
  conversation 建立時可見；以它判斷需要跨事件記憶，樣本也不足以證明可靠。
- 決定：依 F2「判斷不明一律當 main」，agy 維持 R5 的固定 shadow。
