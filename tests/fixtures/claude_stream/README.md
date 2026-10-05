# Claude stream samples

**形狀依 2026-10-05 的 live 報告校正，值為 synthetic。**

事件序列與每種事件的 key 集合來自 claude-eval-parity AC-CE-018 的 live probe
（`install/claude_live_probe.py`；init 事件回報的 `claude_code_version` 為
`2.1.289`）。2026-10-05 共五次：前三次只跑 `auth` stage，第四、五次跑
`auth,dispatch`（parent 為 `claude-haiku-4-5-20251001`，scout 為
`claude-sonnet-5-5`）。live 報告只含形狀與數字，所以這些 `.jsonl` 的值全部是
手工填的佔位字串與數字，不含真實 prompt、fixture、session 或憑證，產生時沒有
呼叫任何模型。

| 檔案 | 內容 |
|---|---|
| `no-agent-call.jsonl` | parent 自己回答；序列與 live 的 `auth` 相同 |
| `dispatch-two-rounds.jsonl` | 第四次的 `dispatch` 順序：第一個 `result` 在第二個 `system/init` 之前 |
| `dispatch-results-last.jsonl` | 第五次的 `dispatch` 順序：第二個 `system/init` 先出現，兩個 `result` 連在最後 |
| `dispatch-two-rounds-ends-without-result.jsonl` | 負面樣本：第四次的事件換了順序，最後一個事件不是 `result`，必須被拒 |
| `dispatch-results-last-no-child-message.jsonl` | 負面樣本：第五次的順序但沒有 child 的 `assistant` 訊息，派工不得被接受 |
| `dispatch-ok.jsonl` | 單一 `result` 的派工，child 有自己的工具呼叫。這個形狀沒有在 live 出現過，保留給解析器測試 |
| `unknown-event.jsonl` | 在 `dispatch-ok` 中插入一個解析器不認得的事件，必須被拒 |

## 兩種實測的 `dispatch` 順序

同一個 stage 連跑兩次，事件相同但順序不同，所以解析器不依賴事件的相對位置，
只要求最後一個事件是 `result`。

- 第四次：`system/init`、`system/thinking_tokens`×2、`assistant`×2、
  `system/background_tasks_changed`、`system/task_started`、`user`、
  `rate_limit_event`、`system/thinking_tokens`、`assistant`、
  `system/background_tasks_changed`、`system/task_updated`、
  `system/task_notification`、`system/thinking_tokens`、`assistant`×2、
  `result/success`、`system/init`、`system/thinking_tokens`×2、`assistant`×2、
  `result/success`。
- 第五次：`system/init`、`system/thinking_tokens`×2、`assistant`×2、
  `system/background_tasks_changed`、`system/task_started`、`user`、
  `rate_limit_event`、`system/thinking_tokens`×2、`assistant`×3、
  `system/background_tasks_changed`、`system/task_updated`、
  `system/task_notification`、`system/init`、`assistant`×2、`result/success`、
  `result/success`。

## 已由 live 確認

- `auth` 的序列：`system/init`、`system/thinking_tokens`×2、`assistant`
  （thinking）、`assistant`（text）、`rate_limit_event`、`result/success`。
- `Agent` 以背景 task 執行（`task_started.is_backgrounded` 為 true）。它的
  `tool_result` 出現在 child 開始之前，是啟動回條（第五次為 1130 個字元），
  不是回答；child 的回答在 `parent_tool_use_id` 等於該 `Agent` 呼叫 id 的
  `assistant` 事件裡（第五次為 5 個字元，任務要求只回一個字）。
- 一次派工有兩個 `result`：其中一個的 `origin.kind` 為 `task-notification`
  （task 完成後 parent 被喚醒）。第五次兩個 `result` 的 `total_cost_usd`
  相同，等於 `modelUsage` 各模型 `costUSD` 的總和（含 subagent 的模型），
  所以它是 session 的累計值；兩個 `result` 的 `usage` 加總等於 parent 模型的
  `modelUsage`，不含 subagent。
- 各事件的 top-level key，以及 `assistant.message`、`message.usage`、
  `result.usage`、`result.modelUsage[]`、`result.origin`、`rate_limit_info`、
  `task_updated.patch`、`task_notification.usage` 的 key。
- `rate_limit_info` 觀察到的值：`status` 為 `allowed_warning`，`rateLimitType`
  為 `five_hour` 或 `seven_day`，`isUsingOverage` 為 false。
- `task_notification.status` 與 `task_updated.patch.status` 觀察到的值是
  `completed`。

## 由觀察反推、尚未由 live 直接確認

- **額度被拒絕時的 `status` 沒有出現過。** adapter 的規則（`status` 以
  `allowed` 開頭才繼續，其他值或 `isUsingOverage` 不是 false 就停止）是由
  `allowed*` 反推的。
- task 失敗時 `task_notification.status` 的值沒有出現過；adapter 把
  `completed` 以外的值都視為未完成。
- 第四次的報告沒有記到 `origin` 的值與第一個 `result` 的數字，樣本中該次
  第一個 `result` 的 0.03 與沒有 `origin` 是假設。
- 樣本把 `subagent_type` 與 `task_description` 放在 child 的 `assistant`、把
  `wire_tool_inputs` 放在帶 tool_use 的 `assistant`；報告只知道這些 key 存在
  於該事件型別，不知道是哪一個事件。
- child 有多則訊息或自己呼叫工具時的形狀（實測的 scout 只回一則文字）。
- `plugins`、`tasks`、`tool_use_result`、`caller` 等巢狀內容的形狀。
- 超出 `--max-budget-usd` 時的結果事件（`budget` stage 尚未 live 執行）。

`install/role_fitness_claude.py` 的解析器遇到不認得的事件型別或形狀一律
fail closed。
