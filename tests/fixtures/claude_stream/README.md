# Claude stream samples

**形狀依 2026-10-05 的 live 報告校正，值為 synthetic。**

事件序列與每種事件的 key 集合來自 claude-eval-parity AC-CE-018 的 live probe
（`install/claude_live_probe.py`；init 事件回報的 `claude_code_version` 為
`2.1.289`）。2026-10-05 共四次：前三次只跑 `auth` stage，第四次跑
`auth,dispatch`（parent 為 `claude-haiku-4-5-20251001`，scout 為
`claude-sonnet-5-5`）。live 報告只含形狀與數字，所以這些 `.jsonl` 的值全部是
手工填的佔位字串與數字，不含真實 prompt、fixture、session 或憑證，產生時沒有
呼叫任何模型。

| 檔案 | 內容 |
|---|---|
| `no-agent-call.jsonl` | parent 自己回答；序列與 live 的 `auth` 相同 |
| `dispatch-two-rounds.jsonl` | 序列與 key 集合和 live 的 `dispatch` 相同：一次 `Agent` 呼叫、task 相關的 `system` 事件、兩輪（兩個 `result`） |
| `dispatch-ok.jsonl` | 單輪的派工：`Agent` 呼叫後 child 有自己的工具呼叫。這個形狀沒有在 live 出現過，保留給解析器測試 |
| `unknown-event.jsonl` | 在 `dispatch-ok` 中插入一個解析器不認得的事件，必須被拒 |

已由 live 確認的部分：

- `auth` 的序列：`system/init`、`system/thinking_tokens`×2、`assistant`
  （thinking）、`assistant`（text）、`rate_limit_event`、`result/success`。
- `dispatch` 的序列有兩輪。第一輪含 `Agent` 的 tool_use、
  `system/background_tasks_changed`、`system/task_started`、`user`（tool_result）、
  `rate_limit_event`、child 的 `assistant`、`system/task_updated`、
  `system/task_notification`，以 `result/success` 結束；之後第二輪從新的
  `system/init` 開始，再以 `result/success` 結束。
- 各事件的 top-level key，以及 `assistant.message`、`message.usage`、
  `result.usage`、`result.modelUsage[]`、`rate_limit_info` 的 key。
- `rate_limit_info` 觀察到的值：`status` 為 `allowed_warning`，`rateLimitType`
  為 `five_hour` 或 `seven_day`，`isUsingOverage` 為 false。

由觀察反推、尚未由 live 直接確認的部分：

- **額度被拒絕時的 `status` 沒有出現過。** adapter 的規則（`status` 以
  `allowed` 開頭才繼續，其他值或 `isUsingOverage` 不是 false 就停止）是由
  `allowed*` 反推的。
- `total_cost_usd` 視為整個 session 的累計值：第二輪的值等於 `modelUsage`
  各模型 `costUSD` 的總和，其中包含只在第一輪執行的 subagent 模型。報告只留
  最後一個 `result` 的數字，第一輪的值沒有記錄；樣本中的 0.03 是假設。
- 樣本把 `origin` 放在第二輪的 `result`、把 `subagent_type` 與
  `task_description` 放在 child 的 `assistant`、把 `wire_tool_inputs` 放在帶
  tool_use 的 `assistant`；報告只知道這些 key 存在於該事件型別，不知道是
  哪一個事件。
- `tool_result` 出現在 child 的 `assistant` 訊息之前。它的內容是 child 的最終
  回答還是啟動回條，報告看不出來；樣本填的是 `READY`。
- `plugins`、`tasks`、`patch`、`tool_use_result`、`caller` 等巢狀內容的形狀。
- 超出 `--max-budget-usd` 時的結果事件（`budget` stage 尚未 live 執行）。

`install/role_fitness_claude.py` 的解析器遇到不認得的事件型別或形狀一律
fail closed。
