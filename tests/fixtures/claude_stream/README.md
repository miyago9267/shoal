# Claude stream samples

**形狀依 2026-10-05 的 live 報告校正，值為 synthetic。**

事件序列與每種事件的 key 集合來自 claude-eval-parity AC-CE-018 的兩次 live
probe（`install/claude_live_probe.py`，只跑 `auth` stage；init 事件回報的
`claude_code_version` 為 `2.1.289`，模型 `claude-haiku-4-5-20251001`）。live
報告只含形狀與數字，所以這些 `.jsonl` 的值全部是手工填的佔位字串與數字，不含
真實 prompt、fixture、session 或憑證，產生時沒有呼叫任何模型。

| 檔案 | 內容 |
|---|---|
| `dispatch-ok.jsonl` | parent 呼叫一次 `Agent`（`subagent_type: plan-verifier`），child 回 `READY` |
| `no-agent-call.jsonl` | parent 自己回答，沒有 `Agent` 呼叫；序列與 live 相同（`system/init`、`assistant`（thinking）、`assistant`（text）、`rate_limit_event`、`result/success`） |
| `unknown-event.jsonl` | 在 `dispatch-ok` 中插入一個解析器不認得的事件，必須被拒 |

已由 live 確認的部分：

- `system/init`、`assistant`、`rate_limit_event`、`result/success` 的 top-level
  key，以及 `assistant.message`、`message.usage`、`result.usage`、
  `result.modelUsage[]` 的 key。
- `rate_limit_event` 出現在最後一個 `assistant` 與 `result` 之間，top-level key
  為 `rate_limit_info`（dict）、`session_id`、`type`、`uuid`。

尚未由 live 確認、仍是依公開文件構造的部分：

- `rate_limit_info` 內部的 key（樣本放空 dict；adapter 不解讀其內容）。
- `Agent` 工具呼叫、`user` 事件與 `tool_result` 的形狀，以及 subagent 事件的
  `parent_tool_use_id`（`dispatch` stage 尚未 live 執行）。
- 超出 `--max-budget-usd` 時的結果事件（`budget` stage 尚未 live 執行）。

`install/role_fitness_claude.py` 的解析器遇到不認得的事件型別或形狀一律
fail closed。
